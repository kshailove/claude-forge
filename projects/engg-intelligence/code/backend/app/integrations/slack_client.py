"""Slack Web API async client with bot-token authentication and rate-limit handling.

Spec reference: §6 (Slack details), §8 M6a
Auth: Authorization: Bearer {bot_token}
API base: https://slack.com/api

Rate limits:
- conversations.history: Tier 3 — 1 req/min per channel (strict 60s per-channel cooldown)
- conversations.list: Tier 2 — standard retry on 429
- users.list: Tier 2 — standard retry on 429

Privacy: We collect message metadata (timestamps, user IDs) ONLY. Message content
is never fetched, stored, or logged.
"""
from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx
import structlog

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SLACK_API_BASE = "https://slack.com/api"
MAX_RETRIES = 3
RETRY_DELAYS = [2, 4, 8]  # seconds — exponential backoff

# Tier 3 rate limit: 1 req/min per channel for conversations.history
CHANNEL_HISTORY_COOLDOWN_SECONDS = 60


class SlackRateLimitError(Exception):
    """Raised when a Slack API call returns 429 and we cannot recover in time."""

    def __init__(self, retry_after: int) -> None:
        self.retry_after = retry_after
        super().__init__(f"Slack rate limited. Retry after {retry_after}s")


class SlackAPIError(Exception):
    """Raised when Slack API returns ok=false."""

    def __init__(self, error_code: str, method: str) -> None:
        self.error_code = error_code
        self.method = method
        super().__init__(f"Slack API error on {method}: {error_code}")


class SlackClient:
    """Async Slack Web API client authenticated with a bot token.

    Usage:
        async with SlackClient(bot_token="xoxb-...") as client:
            info = await client.validate_credentials()
            async for channel in client.get_channels():
                ...
    """

    def __init__(self, bot_token: str) -> None:
        self._bot_token = bot_token
        self._client: httpx.AsyncClient | None = None
        # Per-channel rate limit tracking: channel_id → last_request_time
        self._channel_last_request: dict[str, float] = {}

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    async def __aenter__(self) -> "SlackClient":
        self._client = httpx.AsyncClient(
            base_url=SLACK_API_BASE,
            headers={
                "Authorization": f"Bearer {self._bot_token}",
                "Content-Type": "application/x-www-form-urlencoded",
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
                "SlackClient must be used as an async context manager: "
                "`async with SlackClient(bot_token) as client:`"
            )
        return self._client

    async def _post(self, method: str, params: dict | None = None) -> dict:
        """POST to a Slack API method with retry on rate limits and 5xx.

        Slack API methods always return HTTP 200 with {ok: bool} in JSON.
        A 429 from Slack means rate limited (check Retry-After header).
        """
        client = self._check_client()
        url = f"/{method}"
        req_params = params or {}

        for attempt, delay in enumerate([0] + RETRY_DELAYS):
            if delay:
                logger.info(
                    "slack_request_retry",
                    method=method,
                    attempt=attempt,
                    delay_seconds=delay,
                )
                await asyncio.sleep(delay)

            try:
                response = await client.post(url, data=req_params)
            except httpx.TransportError as exc:
                if attempt < MAX_RETRIES:
                    logger.warning("slack_transport_error", method=method, error=str(exc))
                    continue
                raise

            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", "60"))
                if attempt < MAX_RETRIES:
                    logger.warning(
                        "slack_rate_limited",
                        method=method,
                        retry_after=retry_after,
                        attempt=attempt,
                    )
                    await asyncio.sleep(retry_after)
                    continue
                raise SlackRateLimitError(retry_after)

            if response.status_code in (500, 502, 503, 504):
                if attempt < MAX_RETRIES:
                    logger.warning(
                        "slack_server_error",
                        status=response.status_code,
                        method=method,
                        attempt=attempt,
                    )
                    continue
                response.raise_for_status()

            response.raise_for_status()
            data = response.json()

            if not data.get("ok"):
                error_code = data.get("error", "unknown_error")
                # Some errors are non-retriable (e.g. invalid_auth, missing_scope)
                non_retriable = {
                    "invalid_auth", "not_authed", "account_inactive",
                    "token_revoked", "missing_scope", "no_permission",
                }
                if error_code in non_retriable:
                    raise SlackAPIError(error_code, method)
                # Retry-able Slack API errors (e.g. fatal_error)
                if attempt < MAX_RETRIES:
                    logger.warning(
                        "slack_api_error_retrying",
                        method=method,
                        error_code=error_code,
                        attempt=attempt,
                    )
                    continue
                raise SlackAPIError(error_code, method)

            return data

        raise RuntimeError(f"Max retries exceeded for Slack method {method}")

    async def _get(self, method: str, params: dict | None = None) -> dict:
        """GET a Slack API method (used for list endpoints with cursor pagination)."""
        client = self._check_client()
        url = f"/{method}"
        req_params = params or {}

        for attempt, delay in enumerate([0] + RETRY_DELAYS):
            if delay:
                logger.info(
                    "slack_get_retry",
                    method=method,
                    attempt=attempt,
                    delay_seconds=delay,
                )
                await asyncio.sleep(delay)

            try:
                response = await client.get(url, params=req_params)
            except httpx.TransportError as exc:
                if attempt < MAX_RETRIES:
                    logger.warning("slack_transport_error", method=method, error=str(exc))
                    continue
                raise

            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", "60"))
                if attempt < MAX_RETRIES:
                    logger.warning(
                        "slack_rate_limited",
                        method=method,
                        retry_after=retry_after,
                        attempt=attempt,
                    )
                    await asyncio.sleep(retry_after)
                    continue
                raise SlackRateLimitError(retry_after)

            if response.status_code in (500, 502, 503, 504):
                if attempt < MAX_RETRIES:
                    logger.warning(
                        "slack_server_error",
                        status=response.status_code,
                        method=method,
                        attempt=attempt,
                    )
                    continue
                response.raise_for_status()

            response.raise_for_status()
            data = response.json()

            if not data.get("ok"):
                error_code = data.get("error", "unknown_error")
                non_retriable = {
                    "invalid_auth", "not_authed", "account_inactive",
                    "token_revoked", "missing_scope", "no_permission",
                }
                if error_code in non_retriable:
                    raise SlackAPIError(error_code, method)
                if attempt < MAX_RETRIES:
                    logger.warning(
                        "slack_api_error_retrying",
                        method=method,
                        error_code=error_code,
                        attempt=attempt,
                    )
                    continue
                raise SlackAPIError(error_code, method)

            return data

        raise RuntimeError(f"Max retries exceeded for Slack method {method}")

    # ------------------------------------------------------------------
    # Public API methods
    # ------------------------------------------------------------------

    async def validate_credentials(self) -> dict:
        """Validate bot token via POST /auth.test.

        Returns dict with {ok, team, team_id, user_id}.
        Raises SlackAPIError on invalid token.
        """
        data = await self._post("auth.test")
        logger.info(
            "slack_credentials_validated",
            team=data.get("team"),
            team_id=data.get("team_id"),
            user_id=data.get("user_id"),
        )
        return {
            "ok": data.get("ok"),
            "team": data.get("team"),
            "team_id": data.get("team_id"),
            "user_id": data.get("user_id"),
        }

    async def get_team_info(self) -> dict:
        """Fetch team/workspace info via POST /team.info.

        Returns full Slack API response including team.num_members.
        """
        data = await self._post("team.info")
        return data

    async def get_channels(
        self, exclude_archived: bool = True
    ) -> AsyncIterator[dict]:
        """Yield all channels via GET /conversations.list with cursor pagination.

        Each yielded dict has at minimum: {id, name, num_members}.

        Args:
            exclude_archived: If True, skip archived channels (default True).
        """
        cursor: str | None = None

        while True:
            params: dict[str, Any] = {
                "types": "public_channel,private_channel",
                "limit": 200,
                "exclude_archived": "true" if exclude_archived else "false",
            }
            if cursor:
                params["cursor"] = cursor

            data = await self._get("conversations.list", params=params)
            channels = data.get("channels", [])

            for channel in channels:
                yield {
                    "id": channel.get("id"),
                    "name": channel.get("name"),
                    "num_members": channel.get("num_members", 0),
                    "is_archived": channel.get("is_archived", False),
                    "is_private": channel.get("is_private", False),
                }

            # Follow cursor
            next_cursor = (
                data.get("response_metadata", {}).get("next_cursor") or ""
            ).strip()
            if not next_cursor:
                break
            cursor = next_cursor

    async def get_channel_history(
        self,
        channel_id: str,
        oldest: float,
        latest: float,
    ) -> AsyncIterator[dict]:
        """Yield message metadata from a channel's history.

        Fetches GET /conversations.history with strict per-channel 60s rate limiting.
        Only yields metadata: {ts, user, type} — message content is NOT fetched or logged.

        Args:
            channel_id: Slack channel ID.
            oldest: Unix timestamp (float) — start of window (inclusive).
            latest: Unix timestamp (float) — end of window (exclusive).
        """
        # Enforce 60s cooldown between requests to the same channel (Tier 3)
        now = time.monotonic()
        last_req = self._channel_last_request.get(channel_id)
        if last_req is not None:
            elapsed = now - last_req
            if elapsed < CHANNEL_HISTORY_COOLDOWN_SECONDS:
                wait_time = CHANNEL_HISTORY_COOLDOWN_SECONDS - elapsed
                logger.info(
                    "slack_channel_rate_limit_wait",
                    channel_id=channel_id,
                    wait_seconds=round(wait_time, 1),
                )
                await asyncio.sleep(wait_time)

        cursor: str | None = None

        while True:
            self._channel_last_request[channel_id] = time.monotonic()

            params: dict[str, Any] = {
                "channel": channel_id,
                "oldest": str(oldest),
                "latest": str(latest),
                "limit": 200,
                # Only request metadata fields — reduces payload size
                # (Slack doesn't filter server-side, but we strip content client-side)
            }
            if cursor:
                params["cursor"] = cursor

            data = await self._get("conversations.history", params=params)
            messages = data.get("messages", [])

            for msg in messages:
                # Yield metadata ONLY — never store or log msg["text"] or attachments
                yield {
                    "ts": msg.get("ts"),
                    "user": msg.get("user"),
                    "type": msg.get("type", "message"),
                    "subtype": msg.get("subtype"),  # bot_message, channel_join, etc.
                }

            has_more = data.get("has_more", False)
            if not has_more:
                break

            next_cursor = (
                data.get("response_metadata", {}).get("next_cursor") or ""
            ).strip()
            if not next_cursor:
                break
            cursor = next_cursor

            # Re-enforce the 60s cooldown between paginated requests to same channel
            await asyncio.sleep(CHANNEL_HISTORY_COOLDOWN_SECONDS)
            self._channel_last_request[channel_id] = time.monotonic()

    async def get_users(self) -> AsyncIterator[dict]:
        """Yield workspace users via GET /users.list with cursor pagination.

        Requires users:read scope. Returns {id, name, is_bot, deleted, tz}.
        Email is included if users:read.email scope is available (may be absent).
        """
        cursor: str | None = None

        while True:
            params: dict[str, Any] = {"limit": 200}
            if cursor:
                params["cursor"] = cursor

            data = await self._get("users.list", params=params)
            members = data.get("members", [])

            for member in members:
                profile = member.get("profile", {})
                yield {
                    "id": member.get("id"),
                    "name": member.get("name"),
                    "real_name": member.get("real_name"),
                    "is_bot": member.get("is_bot", False),
                    "deleted": member.get("deleted", False),
                    "tz": member.get("tz"),  # e.g. "America/New_York"
                    # email may be absent if users:read.email scope not granted
                    "email": profile.get("email"),
                }

            next_cursor = (
                data.get("response_metadata", {}).get("next_cursor") or ""
            ).strip()
            if not next_cursor:
                break
            cursor = next_cursor


# ---------------------------------------------------------------------------
# Degradation check (run once on install)
# ---------------------------------------------------------------------------


async def check_degradation(client: SlackClient) -> tuple[bool, str | None]:
    """Check if the Slack workspace exceeds size thresholds that degrade signal quality.

    Degradation criteria (spec §8 M6a, §2.4):
    - member_count > 200, OR
    - channel_count > 50

    Returns:
        Tuple of (degraded: bool, reason: str | None)
    """
    team_info = await client.get_team_info()
    member_count: int = team_info.get("team", {}).get("num_members", 0)

    channel_count = 0
    async for _ in client.get_channels():
        channel_count += 1
        # Short-circuit: once we exceed 50, we know it's degraded
        if channel_count > 50:
            break

    reasons: list[str] = []
    if member_count > 200:
        reasons.append(f"workspace has {member_count} members (threshold: 200)")
    if channel_count > 50:
        reasons.append(f"workspace has >{channel_count - 1} channels (threshold: 50)")

    degraded = bool(reasons)
    reason = "; ".join(reasons) if reasons else None

    logger.info(
        "slack_degradation_check",
        member_count=member_count,
        channel_count=channel_count,
        degraded=degraded,
        reason=reason,
    )
    return degraded, reason
