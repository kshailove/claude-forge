"""PagerDuty REST API async client with token authentication and rate-limit handling.

Spec reference: §6.3, §5.5, M3a
"""
from __future__ import annotations

import asyncio
import logging
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

PAGERDUTY_API_BASE = "https://api.pagerduty.com"
PAGE_SIZE = 100
MAX_RETRIES = 3
RETRY_DELAYS = [2, 4, 8]  # seconds — exponential backoff

# PagerDuty allows 960 req/min. We track a conservative budget.
RATE_LIMIT_REQUESTS_PER_MIN = 960
RATE_LIMIT_SAFETY_BUFFER = 60  # start throttling when < 60 remaining in window


class PagerDutyRateLimitError(Exception):
    """Raised when PagerDuty returns HTTP 429 and we have exhausted retries."""

    def __init__(self, retry_after: int = 60) -> None:
        self.retry_after = retry_after
        super().__init__(f"PagerDuty rate limit hit. Retry after {retry_after}s")


class PagerDutyClient:
    """Async PagerDuty REST API client authenticated with an API token.

    Usage:
        async with PagerDutyClient(api_key="Token ...") as client:
            async for incident in client.get_incidents(since, until):
                ...
    """

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._client: httpx.AsyncClient | None = None
        # Simple in-process rate-limit token bucket
        self._request_count = 0
        self._window_start = time.monotonic()

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    async def __aenter__(self) -> "PagerDutyClient":
        self._client = httpx.AsyncClient(
            base_url=PAGERDUTY_API_BASE,
            headers={
                "Authorization": f"Token token={self._api_key}",
                "Accept": "application/vnd.pagerduty+json;version=2",
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
                "PagerDutyClient must be used as an async context manager: "
                "`async with PagerDutyClient(api_key) as client:`"
            )
        return self._client

    async def _throttle(self) -> None:
        """Enforce conservative rate limiting: stay well under 960 req/min."""
        now = time.monotonic()
        elapsed = now - self._window_start

        if elapsed >= 60:
            # Reset the window
            self._request_count = 0
            self._window_start = now
            return

        if self._request_count >= (RATE_LIMIT_REQUESTS_PER_MIN - RATE_LIMIT_SAFETY_BUFFER):
            # Sleep until the current window expires
            sleep_secs = 60 - elapsed + 1
            logger.warning(
                "pagerduty_rate_limit_throttle",
                sleep_seconds=sleep_secs,
                request_count=self._request_count,
            )
            await asyncio.sleep(sleep_secs)
            self._request_count = 0
            self._window_start = time.monotonic()

    async def _get(self, url: str, params: dict | None = None) -> httpx.Response:
        """Perform a GET request with retry on 5xx and 429 rate-limit handling."""
        client = self._check_client()

        for attempt, delay in enumerate([0] + RETRY_DELAYS):
            if delay:
                logger.info(
                    "pagerduty_request_retry",
                    url=url,
                    attempt=attempt,
                    delay_seconds=delay,
                )
                await asyncio.sleep(delay)

            await self._throttle()

            try:
                response = await client.get(url, params=params)
                self._request_count += 1
            except httpx.TransportError as exc:
                if attempt < MAX_RETRIES:
                    logger.warning("pagerduty_transport_error", url=url, error=str(exc))
                    continue
                raise

            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", 60))
                if attempt < MAX_RETRIES:
                    logger.warning(
                        "pagerduty_rate_limited",
                        url=url,
                        retry_after=retry_after,
                        attempt=attempt,
                    )
                    await asyncio.sleep(retry_after)
                    continue
                raise PagerDutyRateLimitError(retry_after=retry_after)

            if response.status_code in (500, 502, 503, 504):
                if attempt < MAX_RETRIES:
                    logger.warning(
                        "pagerduty_server_error",
                        status=response.status_code,
                        url=url,
                        attempt=attempt,
                    )
                    continue
                response.raise_for_status()

            response.raise_for_status()
            return response

        raise RuntimeError(f"Max retries exceeded for GET {url}")

    # ------------------------------------------------------------------
    # Public API methods
    # ------------------------------------------------------------------

    async def validate_connection(self) -> dict:
        """Validate the API key by calling GET /abilities.

        Returns the abilities dict on success; raises httpx.HTTPStatusError on failure.
        """
        response = await self._get("/abilities")
        return response.json()

    async def get_incidents(
        self,
        since: datetime,
        until: datetime,
        service_ids: list[str] | None = None,
    ) -> AsyncIterator[dict]:
        """Yield all incidents in the given time window.

        Paginates using offset + limit + response.more field.

        Args:
            since: Window start (UTC).
            until: Window end (UTC).
            service_ids: Optional list of PagerDuty service IDs to filter.
                         Empty list or None = all services.
        """
        since_iso = _dt_to_iso(since)
        until_iso = _dt_to_iso(until)
        offset = 0

        while True:
            params: dict[str, Any] = {
                "since": since_iso,
                "until": until_iso,
                "statuses[]": ["triggered", "acknowledged", "resolved"],
                "limit": PAGE_SIZE,
                "offset": offset,
            }
            if service_ids:
                params["service_ids[]"] = service_ids

            response = await self._get("/incidents", params=params)
            data = response.json()

            for incident in data.get("incidents", []):
                yield incident

            if not data.get("more", False):
                break

            offset += PAGE_SIZE

    async def get_incident_log_entries(self, incident_id: str) -> list[dict]:
        """Return overview log entries for an incident.

        Used to extract first acknowledgement and resolution timestamps.

        Args:
            incident_id: PagerDuty incident ID string (e.g. 'P123ABC').
        """
        response = await self._get(
            f"/incidents/{incident_id}/log_entries",
            params={"is_overview": "true"},
        )
        return response.json().get("log_entries", [])

    async def get_oncall_schedules(self) -> list[dict]:
        """Return all on-call schedules (up to PAGE_SIZE).

        For large orgs with many schedules, extend to paginate if needed.
        """
        response = await self._get("/schedules", params={"limit": PAGE_SIZE})
        return response.json().get("schedules", [])

    async def get_schedule_oncalls(
        self,
        schedule_id: str,
        since: datetime,
        until: datetime,
    ) -> list[dict]:
        """Return on-call entries for a specific schedule within the given window.

        Args:
            schedule_id: PagerDuty schedule ID.
            since: Window start (UTC).
            until: Window end (UTC).
        """
        response = await self._get(
            "/oncalls",
            params={
                "schedule_ids[]": [schedule_id],
                "since": _dt_to_iso(since),
                "until": _dt_to_iso(until),
                "limit": PAGE_SIZE,
            },
        )
        return response.json().get("oncalls", [])

    async def get_users(self) -> AsyncIterator[dict]:
        """Yield all PagerDuty users (paginated).

        Used for identity resolution (PagerDuty user email → users.email).
        """
        offset = 0
        while True:
            response = await self._get(
                "/users",
                params={"limit": PAGE_SIZE, "offset": offset},
            )
            data = response.json()
            for user in data.get("users", []):
                yield user

            if not data.get("more", False):
                break
            offset += PAGE_SIZE


# ---------------------------------------------------------------------------
# Severity normalization
# ---------------------------------------------------------------------------


def normalize_pagerduty_severity(
    urgency: str | None,
    priority_name: str | None,
) -> str:
    """Normalize PagerDuty urgency/priority fields to p1/p2/p3/p4.

    Logic (per spec §M3a):
    1. If priority_name matches P1/P2/P3/P4 exactly (case-insensitive), use that.
    2. Otherwise fall back to urgency: high → p1, low → p2.
    3. Default: p2.

    Args:
        urgency: PagerDuty incident urgency ('high' or 'low').
        priority_name: PagerDuty priority name (e.g. 'P1', 'P2', 'P3', 'P4', or None).
    """
    if priority_name:
        normalized = priority_name.strip().upper()
        if normalized in ("P1", "P2", "P3", "P4"):
            return normalized.lower()

    urgency_map = {
        "high": "p1",
        "low": "p2",
    }
    return urgency_map.get((urgency or "").lower(), "p2")


def extract_pagerduty_timestamps(
    log_entries: list[dict],
    incident_data: dict,
) -> tuple[datetime | None, datetime | None]:
    """Extract acknowledged_at and resolved_at from log entries.

    Returns:
        Tuple of (acknowledged_at, resolved_at) as UTC-aware datetimes or None.
    """
    acknowledged_at: datetime | None = None
    resolved_at: datetime | None = None

    for entry in log_entries:
        entry_type: str = entry.get("type", "")
        created_at_str: str | None = entry.get("created_at")
        if not created_at_str:
            continue

        ts = _parse_pd_datetime(created_at_str)

        if "acknowledge" in entry_type.lower() and acknowledged_at is None:
            acknowledged_at = ts
        elif "resolve" in entry_type.lower() and resolved_at is None:
            resolved_at = ts

    # Fall back to incident-level resolved_at if log entries don't have it
    if resolved_at is None and incident_data.get("resolved_at"):
        resolved_at = _parse_pd_datetime(incident_data["resolved_at"])

    return acknowledged_at, resolved_at


# ---------------------------------------------------------------------------
# Datetime helpers
# ---------------------------------------------------------------------------


def _dt_to_iso(dt: datetime) -> str:
    """Convert datetime to PagerDuty-compatible ISO 8601 UTC string."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_pd_datetime(dt_str: str) -> datetime:
    """Parse a PagerDuty ISO 8601 datetime string to a timezone-aware datetime."""
    dt_str = dt_str.rstrip("Z")
    if "+" in dt_str or dt_str.endswith(("-05:00", "-04:00")):
        dt = datetime.fromisoformat(dt_str)
    else:
        dt = datetime.fromisoformat(dt_str).replace(tzinfo=timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
