"""ClickUp REST API v2 async client with API token authentication.

Spec reference: §6.3, M2b
Auth: Authorization: {api_token}  (no "Bearer" prefix — ClickUp uses raw token)
Rate limit: ClickUp standard API is 100 req/min.
  Implemented as a token bucket: 100 tokens, refill at 100/60 s rate.
Pagination: tasks use page-based pagination (page=0, 1, 2, ...).
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

CLICKUP_API_BASE = "https://api.clickup.com"
MAX_RETRIES = 3
RETRY_DELAYS = [2, 4, 8]

# Token bucket parameters for rate limiting (100 req/min)
_BUCKET_CAPACITY = 100
_BUCKET_REFILL_RATE = 100 / 60.0  # tokens per second


# ---------------------------------------------------------------------------
# Token bucket rate limiter
# ---------------------------------------------------------------------------


class _TokenBucket:
    """Simple in-process token bucket for rate limiting."""

    def __init__(self, capacity: float, refill_rate: float) -> None:
        self._capacity = capacity
        self._tokens = capacity
        self._refill_rate = refill_rate  # tokens per second
        self._last_refill: float = time.monotonic()

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(
            self._capacity,
            self._tokens + elapsed * self._refill_rate,
        )
        self._last_refill = now

    async def acquire(self) -> None:
        """Wait until a token is available and consume it."""
        while True:
            self._refill()
            if self._tokens >= 1:
                self._tokens -= 1
                return
            # Calculate sleep needed to accumulate 1 token
            deficit = 1.0 - self._tokens
            sleep_secs = deficit / self._refill_rate
            await asyncio.sleep(sleep_secs)


# ---------------------------------------------------------------------------
# Client class
# ---------------------------------------------------------------------------


class ClickUpClient:
    """Async ClickUp REST API v2 client authenticated with an API token.

    Usage:
        async with ClickUpClient(api_token="pk_...") as client:
            async for task in client.get_tasks(list_id="12345"):
                ...
    """

    def __init__(self, api_token: str) -> None:
        self._api_token = api_token
        self._client: httpx.AsyncClient | None = None
        self._rate_limiter = _TokenBucket(
            capacity=_BUCKET_CAPACITY,
            refill_rate=_BUCKET_REFILL_RATE,
        )

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    async def __aenter__(self) -> "ClickUpClient":
        self._client = httpx.AsyncClient(
            base_url=CLICKUP_API_BASE,
            headers={
                # ClickUp uses raw token — no "Bearer" prefix
                "Authorization": self._api_token,
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
                "ClickUpClient must be used as an async context manager: "
                "`async with ClickUpClient(api_token) as client:`"
            )
        return self._client

    async def _get(self, path: str, params: dict | None = None) -> httpx.Response:
        """Perform a GET with token-bucket rate limiting and retry on 5xx."""
        client = self._check_client()

        for attempt, delay in enumerate([0] + RETRY_DELAYS):
            if delay:
                logger.info(
                    "clickup_request_retry",
                    path=path,
                    attempt=attempt,
                    delay_seconds=delay,
                )
                await asyncio.sleep(delay)

            # Acquire rate-limit token before firing request
            await self._rate_limiter.acquire()

            try:
                response = await client.get(path, params=params)
            except httpx.TransportError as exc:
                if attempt < MAX_RETRIES:
                    logger.warning("clickup_transport_error", path=path, error=str(exc))
                    continue
                raise

            # 429 — respect Retry-After
            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", 10))
                logger.warning(
                    "clickup_rate_limited",
                    path=path,
                    retry_after_seconds=retry_after,
                )
                await asyncio.sleep(retry_after)
                continue

            if response.status_code in (500, 502, 503, 504):
                if attempt < MAX_RETRIES:
                    logger.warning(
                        "clickup_server_error",
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

    async def validate(self, workspace_id: str) -> dict:
        """Validate credentials by fetching the workspace info.

        GET /api/v2/team  — returns list of authorized workspaces (teams).
        Raises httpx.HTTPStatusError on invalid token.
        """
        response = await self._get("/api/v2/team")
        data = response.json()
        teams: list[dict] = data.get("teams", [])
        for team in teams:
            if str(team.get("id")) == str(workspace_id):
                return team
        # Token valid but workspace not found in authorised list
        raise ValueError(
            f"Workspace {workspace_id!r} not found among authorised ClickUp workspaces. "
            f"Available: {[t.get('id') for t in teams]}"
        )

    async def get_spaces(self, workspace_id: str) -> list[dict]:
        """Return all Spaces in a workspace.

        GET /api/v2/team/{workspace_id}/space
        """
        response = await self._get(f"/api/v2/team/{workspace_id}/space")
        return response.json().get("spaces", [])

    async def get_folders(self, space_id: str) -> list[dict]:
        """Return all Folders in a Space.

        GET /api/v2/space/{space_id}/folder
        """
        response = await self._get(f"/api/v2/space/{space_id}/folder")
        return response.json().get("folders", [])

    async def get_lists(self, folder_id: str) -> list[dict]:
        """Return all Lists inside a Folder.

        GET /api/v2/folder/{folder_id}/list
        """
        response = await self._get(f"/api/v2/folder/{folder_id}/list")
        return response.json().get("lists", [])

    async def get_folderless_lists(self, space_id: str) -> list[dict]:
        """Return all folderless Lists directly in a Space.

        GET /api/v2/space/{space_id}/list
        """
        response = await self._get(f"/api/v2/space/{space_id}/list")
        return response.json().get("lists", [])

    async def get_tasks(
        self,
        list_id: str,
        date_updated_gt: int | None = None,
    ) -> AsyncIterator[dict]:
        """Yield all tasks in a List, optionally filtered by update timestamp.

        GET /api/v2/list/{list_id}/task
        Pagination: page=0, 1, 2, ... until empty response.

        Args:
            list_id: ClickUp list ID.
            date_updated_gt: Unix millisecond timestamp; only tasks updated
                             after this timestamp are returned.
        """
        return self._paginate_tasks(list_id, date_updated_gt)

    async def _paginate_tasks(
        self,
        list_id: str,
        date_updated_gt: int | None,
    ) -> AsyncIterator[dict]:
        """Internal async generator for task pagination."""
        page = 0
        while True:
            params: dict[str, Any] = {
                "page": page,
                "include_closed": "true",
            }
            if date_updated_gt is not None:
                params["date_updated_gt"] = date_updated_gt

            response = await self._get(f"/api/v2/list/{list_id}/task", params=params)
            data = response.json()
            tasks: list[dict] = data.get("tasks", [])

            for task in tasks:
                yield task

            if not tasks:
                break
            page += 1

    async def get_task_activity(self, task_id: str) -> list[dict]:
        """Return all activity (state transitions) for a task.

        GET /api/v2/task/{task_id}/activity
        Returns a list of activity entries ordered chronologically.
        """
        response = await self._get(f"/api/v2/task/{task_id}/activity")
        data = response.json()
        return data.get("activity", [])

    async def get_workspace_hierarchy(self, workspace_id: str) -> dict:
        """Return the full Space→Folder→List hierarchy for a workspace.

        Used by the admin setup wizard to let admins map teams to sprint Lists.
        Returns:
            {
                "workspace_id": "...",
                "spaces": [
                    {
                        "id": "...", "name": "...",
                        "folders": [
                            {
                                "id": "...", "name": "...",
                                "lists": [{"id": "...", "name": "...", ...}]
                            }
                        ],
                        "folderless_lists": [{"id": "...", "name": "...", ...}]
                    }
                ]
            }
        """
        spaces = await self.get_spaces(workspace_id)
        result_spaces: list[dict] = []

        for space in spaces:
            space_id = str(space["id"])
            folders_raw = await self.get_folders(space_id)
            folders_out: list[dict] = []

            for folder in folders_raw:
                folder_id = str(folder["id"])
                lists_raw = await self.get_lists(folder_id)
                folders_out.append(
                    {
                        "id": folder["id"],
                        "name": folder.get("name", ""),
                        "lists": [
                            {
                                "id": lst["id"],
                                "name": lst.get("name", ""),
                                "start_date": lst.get("start_date"),
                                "due_date": lst.get("due_date"),
                                "task_count": lst.get("task_count"),
                            }
                            for lst in lists_raw
                        ],
                    }
                )

            folderless_raw = await self.get_folderless_lists(space_id)
            result_spaces.append(
                {
                    "id": space["id"],
                    "name": space.get("name", ""),
                    "folders": folders_out,
                    "folderless_lists": [
                        {
                            "id": lst["id"],
                            "name": lst.get("name", ""),
                            "start_date": lst.get("start_date"),
                            "due_date": lst.get("due_date"),
                            "task_count": lst.get("task_count"),
                        }
                        for lst in folderless_raw
                    ],
                }
            )

        return {"workspace_id": workspace_id, "spaces": result_spaces}
