"""Keka HRMS async client — OAuth2 client-credentials flow.

Auth flow:
  POST https://{tenant_id}.keka.com/connect/token
  grant_type=client_credentials, scope=kekaapi
  Returns: { access_token, expires_in, token_type }

Config JSON shape stored in integrations.config_json:
  {
    "client_id":     "...",
    "client_secret": "...",
    "tenant_id":     "...",
    "base_url":      "https://api.keka.com/v1"   # default; some tenants use custom domain
  }

Spec reference: §6.7, M8c
"""
from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx
import structlog

logger = structlog.get_logger(__name__)

# Default Keka API base (overridable per config)
KEKA_DEFAULT_BASE_URL = "https://api.keka.com/v1"
# Token endpoint template
KEKA_TOKEN_URL_TEMPLATE = "https://{tenant_id}.keka.com/connect/token"

MAX_RETRIES = 3
RETRY_DELAYS = [2, 4, 8]  # seconds


class KekaAuthError(Exception):
    """Raised when OAuth2 client-credentials token fetch fails."""


class KekaAPIError(Exception):
    """Raised for non-2xx responses from Keka API."""

    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        super().__init__(f"Keka API error {status_code}: {message}")


class KekaClient:
    """Async Keka HRMS REST API client.

    Usage:
        async with KekaClient(client_id=..., client_secret=..., tenant_id=...) as client:
            async for employee in client.get_all_employees():
                ...
    """

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        tenant_id: str,
        base_url: str = KEKA_DEFAULT_BASE_URL,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._tenant_id = tenant_id
        self._base_url = base_url.rstrip("/")

        # Token cache
        self._access_token: str | None = None
        self._token_expires_at: float = 0.0  # Unix timestamp

        self._client: httpx.AsyncClient | None = None

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    async def __aenter__(self) -> "KekaClient":
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=10.0),
            follow_redirects=True,
        )
        return self

    async def __aexit__(self, *_: Any) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _check_client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError(
                "KekaClient must be used as an async context manager: "
                "`async with KekaClient(...) as client:`"
            )
        return self._client

    # ------------------------------------------------------------------
    # Token management
    # ------------------------------------------------------------------

    async def get_access_token(self) -> str:
        """Fetch (or return cached) OAuth2 access token via client credentials."""
        # Return cached token if still valid (with 60s buffer)
        if self._access_token and time.time() < self._token_expires_at - 60:
            return self._access_token

        client = self._check_client()
        token_url = KEKA_TOKEN_URL_TEMPLATE.format(tenant_id=self._tenant_id)

        try:
            response = await client.post(
                token_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "scope": "kekaapi",
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.error(
                "keka_token_fetch_failed",
                status_code=exc.response.status_code,
                tenant_id=self._tenant_id,
            )
            raise KekaAuthError(
                f"Keka OAuth2 token fetch failed (HTTP {exc.response.status_code}): "
                f"{exc.response.text}"
            ) from exc
        except httpx.TransportError as exc:
            logger.error("keka_token_transport_error", error=str(exc))
            raise KekaAuthError(f"Keka token endpoint unreachable: {exc}") from exc

        token_data = response.json()
        self._access_token = token_data["access_token"]
        expires_in = int(token_data.get("expires_in", 3600))
        self._token_expires_at = time.time() + expires_in

        logger.info(
            "keka_token_fetched",
            tenant_id=self._tenant_id,
            expires_in=expires_in,
        )
        return self._access_token

    # ------------------------------------------------------------------
    # Internal request helper
    # ------------------------------------------------------------------

    async def _get(self, path: str, params: dict | None = None) -> dict:
        """Perform an authenticated GET with retry on 5xx."""
        client = self._check_client()

        for attempt, delay in enumerate([0] + RETRY_DELAYS):
            if delay:
                logger.info(
                    "keka_request_retry",
                    path=path,
                    attempt=attempt,
                    delay=delay,
                )
                await asyncio.sleep(delay)

            token = await self.get_access_token()
            try:
                response = await client.get(
                    f"{self._base_url}{path}",
                    params=params,
                    headers={"Authorization": f"Bearer {token}"},
                )
            except httpx.TransportError as exc:
                if attempt < MAX_RETRIES:
                    logger.warning("keka_transport_error", path=path, error=str(exc))
                    continue
                raise

            if response.status_code == 401:
                # Token may have expired — invalidate cache and retry once
                self._access_token = None
                self._token_expires_at = 0.0
                if attempt < MAX_RETRIES:
                    continue
                response.raise_for_status()

            if response.status_code in (500, 502, 503, 504):
                if attempt < MAX_RETRIES:
                    logger.warning(
                        "keka_server_error",
                        status=response.status_code,
                        path=path,
                    )
                    continue
                response.raise_for_status()

            response.raise_for_status()
            return response.json()

        raise RuntimeError(f"Max retries exceeded for GET {path}")

    # ------------------------------------------------------------------
    # Public API methods
    # ------------------------------------------------------------------

    async def get_employees(
        self, page: int = 1, page_size: int = 100
    ) -> dict:
        """Fetch a single page of employees.

        GET /hris/employees?page={page}&pageSize={page_size}

        Response shape:
          {
            "data": [
              {
                "id": "...",
                "firstName": "...",
                "lastName": "...",
                "workEmail": "user@company.com",
                "reportingManager": {
                  "id": "...",
                  "workEmail": "manager@company.com"
                }
              },
              ...
            ],
            "succeeded": true,
            "pageNumber": 1,
            "pageSize": 100,
            "totalCount": 250
          }
        """
        return await self._get(
            "/hris/employees",
            params={"page": page, "pageSize": page_size},
        )

    async def get_all_employees(self) -> AsyncIterator[dict]:
        """Async generator that yields all employees across all pages.

        Handles pagination automatically until totalCount is exhausted.
        """
        page = 1
        page_size = 100
        total_fetched = 0

        while True:
            data = await self.get_employees(page=page, page_size=page_size)
            employees: list[dict] = data.get("data", [])

            if not employees:
                break

            for emp in employees:
                yield emp

            total_fetched += len(employees)
            total_count = data.get("totalCount", 0)

            logger.debug(
                "keka_employees_page_fetched",
                page=page,
                fetched=len(employees),
                total_fetched=total_fetched,
                total_count=total_count,
            )

            if total_fetched >= total_count:
                break

            page += 1
