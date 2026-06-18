"""Zenduty REST API async client with token authentication and conservative rate limiting.

Spec reference: §6.4, §5.5, M3b

Decision 3 (spec §9): Zenduty may rebrand. The base_url is stored in config_json
and overridable at connect time. Any response with a Deprecation or Sunset header
triggers a WARNING log so operators can plan ahead.
"""
from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any

import httpx
import structlog

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ZENDUTY_DEFAULT_BASE_URL = "https://www.zenduty.com/api/v1"
PAGE_SIZE = 100
MAX_RETRIES = 3
RETRY_DELAYS = [2, 4, 8]  # seconds — exponential backoff

# Zenduty rate limit is undocumented; conservative 60 req/min bucket
RATE_LIMIT_REQUESTS_PER_MIN = 60
RATE_LIMIT_SAFETY_BUFFER = 5


class ZendutyRateLimitError(Exception):
    """Raised when Zenduty returns HTTP 429 and we exhaust retries."""

    def __init__(self, retry_after: int = 60) -> None:
        self.retry_after = retry_after
        super().__init__(f"Zenduty rate limit hit. Retry after {retry_after}s")


class ZendutyClient:
    """Async Zenduty REST API client authenticated with a Token API key.

    Usage:
        async with ZendutyClient(api_key="...", base_url="...") as client:
            async for incident in client.get_incidents():
                ...
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = ZENDUTY_DEFAULT_BASE_URL,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._client: httpx.AsyncClient | None = None
        # In-process rate-limit token bucket
        self._request_count = 0
        self._window_start = time.monotonic()

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    async def __aenter__(self) -> "ZendutyClient":
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers={
                "Authorization": f"Token {self._api_key}",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(30.0, connect=10.0),
            follow_redirects=True,
        )
        return self

    async def __aexit__(self, *_: Any) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _check_client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError(
                "ZendutyClient must be used as an async context manager: "
                "`async with ZendutyClient(api_key, base_url) as client:`"
            )
        return self._client

    async def _throttle(self) -> None:
        """Enforce conservative 60 req/min rate limiting."""
        now = time.monotonic()
        elapsed = now - self._window_start

        if elapsed >= 60:
            self._request_count = 0
            self._window_start = now
            return

        if self._request_count >= (RATE_LIMIT_REQUESTS_PER_MIN - RATE_LIMIT_SAFETY_BUFFER):
            sleep_secs = 60 - elapsed + 1
            logger.warning(
                "zenduty_rate_limit_throttle",
                sleep_seconds=sleep_secs,
                request_count=self._request_count,
            )
            await asyncio.sleep(sleep_secs)
            self._request_count = 0
            self._window_start = time.monotonic()

    def _check_deprecation_headers(self, response: httpx.Response, url: str) -> None:
        """Log a warning if the response includes Deprecation or Sunset headers.

        Per spec Decision 3: Zenduty may rebrand; operators need advance warning
        when endpoints are deprecated so they can plan migrations.
        """
        if "Deprecation" in response.headers:
            logger.warning(
                "zenduty_deprecation_header_detected",
                url=url,
                deprecation=response.headers.get("Deprecation"),
                sunset=response.headers.get("Sunset"),
                message="Zenduty API deprecation notice received. Review integration config.",
            )
        elif "Sunset" in response.headers:
            logger.warning(
                "zenduty_sunset_header_detected",
                url=url,
                sunset=response.headers.get("Sunset"),
                message="Zenduty API sunset notice received. Migration may be required.",
            )

    async def _get(self, path: str, params: dict | None = None) -> httpx.Response:
        """Perform a GET request with retry on 5xx and 429 rate-limit handling."""
        client = self._check_client()

        for attempt, delay in enumerate([0] + RETRY_DELAYS):
            if delay:
                logger.info(
                    "zenduty_request_retry",
                    path=path,
                    attempt=attempt,
                    delay_seconds=delay,
                )
                await asyncio.sleep(delay)

            await self._throttle()

            try:
                response = await client.get(path, params=params)
                self._request_count += 1
            except httpx.TransportError as exc:
                if attempt < MAX_RETRIES:
                    logger.warning("zenduty_transport_error", path=path, error=str(exc))
                    continue
                raise

            self._check_deprecation_headers(response, path)

            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", 60))
                if attempt < MAX_RETRIES:
                    logger.warning(
                        "zenduty_rate_limited",
                        path=path,
                        retry_after=retry_after,
                        attempt=attempt,
                    )
                    await asyncio.sleep(retry_after)
                    continue
                raise ZendutyRateLimitError(retry_after=retry_after)

            if response.status_code in (500, 502, 503, 504):
                if attempt < MAX_RETRIES:
                    logger.warning(
                        "zenduty_server_error",
                        status=response.status_code,
                        path=path,
                        attempt=attempt,
                    )
                    continue
                response.raise_for_status()

            response.raise_for_status()
            return response

        raise RuntimeError(f"Max retries exceeded for GET {path}")

    # ------------------------------------------------------------------
    # Public API methods
    # ------------------------------------------------------------------

    async def validate_connection(self) -> list[dict]:
        """Validate the API key by calling GET /teams/.

        Returns the teams list on success; raises httpx.HTTPStatusError on failure.
        """
        return await self.get_teams()

    async def get_incidents(self, page: int = 1) -> dict:
        """Return a single page of incidents.

        Args:
            page: 1-based page number.

        Returns:
            Raw dict from Zenduty with 'results', 'count', 'next', 'previous' keys.

        Note: Zenduty does not support since/until query params natively.
              Filter by created_at range client-side after fetching.
        """
        response = await self._get("/incidents/", params={"page": page})
        return response.json()

    async def get_incident_details(self, incident_number: int | str) -> dict:
        """Return full details for a specific incident.

        Args:
            incident_number: Zenduty incident number.
        """
        response = await self._get(f"/incidents/{incident_number}/")
        return response.json()

    async def get_teams(self) -> list[dict]:
        """Return all teams the API key has access to."""
        response = await self._get("/teams/")
        data = response.json()
        # Zenduty may return a list or a paginated dict
        if isinstance(data, list):
            return data
        return data.get("results", data.get("teams", []))

    async def get_schedules(self, team_id: str) -> list[dict]:
        """Return all on-call schedules for a team.

        Args:
            team_id: Zenduty team unique ID.
        """
        response = await self._get(f"/teams/{team_id}/schedules/")
        data = response.json()
        if isinstance(data, list):
            return data
        return data.get("results", [])

    async def get_schedule_oncalls(
        self,
        team_id: str,
        schedule_id: str,
        start_time: datetime,
        end_time: datetime,
    ) -> list[dict]:
        """Return on-call entries for a specific schedule and time window.

        Args:
            team_id: Zenduty team unique ID.
            schedule_id: Zenduty schedule unique ID.
            start_time: Window start (UTC).
            end_time: Window end (UTC).
        """
        response = await self._get(
            f"/teams/{team_id}/schedules/{schedule_id}/oncalls/",
            params={
                "start_time": _dt_to_iso(start_time),
                "end_time": _dt_to_iso(end_time),
            },
        )
        data = response.json()
        if isinstance(data, list):
            return data
        return data.get("results", [])

    async def get_members(self, team_id: str) -> list[dict]:
        """Return all members of a team.

        Used for identity resolution (Zenduty user email → users.email).

        Args:
            team_id: Zenduty team unique ID.
        """
        response = await self._get(f"/teams/{team_id}/members/")
        data = response.json()
        if isinstance(data, list):
            return data
        return data.get("results", [])


# ---------------------------------------------------------------------------
# Severity normalization
# ---------------------------------------------------------------------------


def normalize_zenduty_severity(urgency: int | None) -> str:
    """Normalize Zenduty urgency integer to p1/p2/p3/p4.

    Zenduty urgency mapping (per spec §M3b):
        1 = critical → p1
        2 = high     → p2
        3 = medium   → p3
        4 = low      → p4
        other/None   → p3 (default to medium)

    Args:
        urgency: Zenduty incident urgency integer.
    """
    urgency_map = {
        1: "p1",
        2: "p2",
        3: "p3",
        4: "p4",
    }
    return urgency_map.get(urgency, "p3")


def compute_zenduty_timestamps(
    incident_data: dict,
) -> tuple[datetime | None, datetime | None, datetime | None]:
    """Extract triggered_at, acknowledged_at, resolved_at from a Zenduty incident dict.

    Returns:
        Tuple of (triggered_at, acknowledged_at, resolved_at) as UTC-aware datetimes or None.
    """
    triggered_at: datetime | None = None
    acknowledged_at: datetime | None = None
    resolved_at: datetime | None = None

    if incident_data.get("creation_date"):
        triggered_at = _parse_zd_datetime(incident_data["creation_date"])

    if incident_data.get("acknowledged_date"):
        acknowledged_at = _parse_zd_datetime(incident_data["acknowledged_date"])

    if incident_data.get("resolved_date") or incident_data.get("resolved_at"):
        ts_str = incident_data.get("resolved_date") or incident_data.get("resolved_at")
        if ts_str:
            resolved_at = _parse_zd_datetime(ts_str)

    return triggered_at, acknowledged_at, resolved_at


# ---------------------------------------------------------------------------
# Datetime helpers
# ---------------------------------------------------------------------------


def _dt_to_iso(dt: datetime) -> str:
    """Convert datetime to Zenduty-compatible ISO 8601 UTC string."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_zd_datetime(dt_str: str) -> datetime:
    """Parse a Zenduty ISO 8601 datetime string to a timezone-aware UTC datetime."""
    dt_str_clean = dt_str.rstrip("Z")
    if "+" in dt_str_clean:
        dt = datetime.fromisoformat(dt_str_clean)
    else:
        dt = datetime.fromisoformat(dt_str_clean).replace(tzinfo=timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
