"""Jira Cloud REST API async client with Basic (email:api_token) authentication.

Spec reference: §6.2, M2a
Rate limit: Jira Cloud throttles at ~200 req/s; we add 0.1 s sleep after every
100 requests and honour 429 responses with Retry-After semantics.
Pagination: startAt + maxResults (100 per page) + total pattern.
"""
from __future__ import annotations

import asyncio
import base64
import logging
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any

import httpx
import structlog

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_RETRIES = 3
RETRY_DELAYS = [2, 4, 8]  # seconds — exponential backoff
PAGE_SIZE = 100
# After this many requests in one client lifetime, throttle 0.1 s between calls
THROTTLE_AFTER_REQUESTS = 100
THROTTLE_SLEEP_SECONDS = 0.1

# Map common Jira workflow statuses → normalised flow state.
# Extend as needed via project-specific overrides.
JIRA_STATUS_TO_STATE: dict[str, str] = {
    # To Do variants
    "to do": "todo",
    "open": "todo",
    "backlog": "todo",
    "new": "todo",
    "created": "todo",
    "reopened": "todo",
    # In Progress variants
    "in progress": "in_progress",
    "in development": "in_progress",
    "development": "in_progress",
    "coding": "in_progress",
    "implementation": "in_progress",
    # In Review / Testing
    "in review": "in_review",
    "code review": "in_review",
    "peer review": "in_review",
    "testing": "in_review",
    "in testing": "in_review",
    "qa": "in_review",
    "ready for review": "in_review",
    "review": "in_review",
    # Done variants
    "done": "done",
    "closed": "done",
    "resolved": "done",
    "complete": "done",
    "completed": "done",
    "released": "done",
    "deployed": "done",
    "verified": "done",
    # Blocked
    "blocked": "blocked",
    "impediment": "blocked",
    "on hold": "blocked",
    "waiting": "blocked",
    "waiting for customer": "blocked",
    "waiting for support": "blocked",
}


def _map_jira_status(raw_status: str) -> str:
    """Map a raw Jira status string to a normalised flow state."""
    return JIRA_STATUS_TO_STATE.get(raw_status.lower().strip(), raw_status.lower())


# ---------------------------------------------------------------------------
# Client class
# ---------------------------------------------------------------------------


class JiraClient:
    """Async Jira Cloud REST API client authenticated with email + API token.

    Usage:
        async with JiraClient(base_url="https://company.atlassian.net",
                              email="user@company.com",
                              api_token="ATATT...") as client:
            async for issue in client.get_recently_updated_issues(["PROJ"], since_dt):
                ...
    """

    def __init__(self, base_url: str, email: str, api_token: str) -> None:
        # Strip trailing slash — all paths are absolute below
        self._base_url = base_url.rstrip("/")
        self._email = email
        self._api_token = api_token
        self._client: httpx.AsyncClient | None = None
        self._request_count: int = 0

    # ------------------------------------------------------------------
    # Auth helpers
    # ------------------------------------------------------------------

    def _auth_header(self) -> str:
        """Build Basic auth header: base64(email:api_token)."""
        credentials = f"{self._email}:{self._api_token}"
        encoded = base64.b64encode(credentials.encode()).decode()
        return f"Basic {encoded}"

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    async def __aenter__(self) -> "JiraClient":
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers={
                "Authorization": self._auth_header(),
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(30.0, connect=10.0),
            follow_redirects=True,
        )
        self._request_count = 0
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
                "JiraClient must be used as an async context manager: "
                "`async with JiraClient(...) as client:`"
            )
        return self._client

    async def _get(self, path: str, params: dict | None = None) -> httpx.Response:
        """Perform a GET with retry on 5xx and rate-limit throttling."""
        client = self._check_client()

        for attempt, delay in enumerate([0] + RETRY_DELAYS):
            if delay:
                logger.info(
                    "jira_request_retry",
                    path=path,
                    attempt=attempt,
                    delay_seconds=delay,
                )
                await asyncio.sleep(delay)

            try:
                response = await client.get(path, params=params)
            except httpx.TransportError as exc:
                if attempt < MAX_RETRIES:
                    logger.warning("jira_transport_error", path=path, error=str(exc))
                    continue
                raise

            self._request_count += 1

            # 429 — Too Many Requests: honour Retry-After header
            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", 10))
                logger.warning(
                    "jira_rate_limited",
                    path=path,
                    retry_after_seconds=retry_after,
                )
                await asyncio.sleep(retry_after)
                continue  # retry immediately after sleeping

            # Throttle proactively after THROTTLE_AFTER_REQUESTS
            if self._request_count % THROTTLE_AFTER_REQUESTS == 0:
                await asyncio.sleep(THROTTLE_SLEEP_SECONDS)

            if response.status_code in (500, 502, 503, 504):
                if attempt < MAX_RETRIES:
                    logger.warning(
                        "jira_server_error",
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
    # Pagination helper (startAt / maxResults / total)
    # ------------------------------------------------------------------

    async def _paginate_jira(
        self,
        path: str,
        results_key: str,
        params: dict | None = None,
    ) -> AsyncIterator[dict]:
        """Yield individual items from a Jira paginated endpoint.

        Jira uses { startAt, maxResults, total, <results_key>: [...] }.
        """
        base_params: dict = dict(params or {})
        base_params["maxResults"] = PAGE_SIZE
        start_at = 0

        while True:
            base_params["startAt"] = start_at
            response = await self._get(path, params=base_params)
            data = response.json()

            items: list[dict] = data.get(results_key, [])
            for item in items:
                yield item

            total: int = data.get("total", 0)
            start_at += len(items)
            if start_at >= total or not items:
                break

    # ------------------------------------------------------------------
    # Public API methods
    # ------------------------------------------------------------------

    async def validate(self) -> dict:
        """Validate credentials by calling GET /rest/api/3/myself.

        Returns the user profile dict on success.
        Raises httpx.HTTPStatusError on invalid credentials.
        """
        response = await self._get("/rest/api/3/myself")
        return response.json()

    async def get_boards(self, project_key: str) -> list[dict]:
        """Return all Agile boards for the given project key.

        GET /rest/agile/1.0/board?projectKeyOrId={project_key}
        """
        boards: list[dict] = []
        async for board in self._paginate_jira(
            "/rest/agile/1.0/board",
            results_key="values",
            params={"projectKeyOrId": project_key},
        ):
            boards.append(board)
        return boards

    async def get_sprints(
        self, board_id: int | str, state: str = "active,closed"
    ) -> AsyncIterator[dict]:
        """Yield sprints for a given board.

        GET /rest/agile/1.0/board/{board_id}/sprint?state={state}
        """
        return self._paginate_jira(
            f"/rest/agile/1.0/board/{board_id}/sprint",
            results_key="values",
            params={"state": state},
        )

    async def get_sprint_issues(self, sprint_id: int | str) -> AsyncIterator[dict]:
        """Yield all issues in a sprint.

        GET /rest/agile/1.0/sprint/{sprint_id}/issue
        fields: summary, status, assignee, story_points, issuetype,
                created, updated, resolutiondate
        """
        fields = (
            "summary,status,assignee,story_points,customfield_10016,"
            "issuetype,created,updated,resolutiondate"
        )
        return self._paginate_jira(
            f"/rest/agile/1.0/sprint/{sprint_id}/issue",
            results_key="issues",
            params={"fields": fields},
        )

    async def get_issue_changelog(self, issue_id: str) -> list[dict]:
        """Return changelog entries for an issue.

        GET /rest/api/3/issue/{issue_id}/changelog
        Returns list of changelog items (each with 'created' + 'items' list).
        """
        entries: list[dict] = []
        async for entry in self._paginate_jira(
            f"/rest/api/3/issue/{issue_id}/changelog",
            results_key="values",
        ):
            entries.append(entry)
        return entries

    async def get_recently_updated_issues(
        self,
        project_keys: list[str],
        since_dt: datetime,
    ) -> AsyncIterator[dict]:
        """Yield issues across project_keys updated since since_dt.

        Uses JQL: project in ({keys}) AND updated >= "{since}"
        GET /rest/api/3/search
        """
        keys_str = ", ".join(f'"{k}"' for k in project_keys)
        since_str = since_dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M")
        jql = f"project in ({keys_str}) AND updated >= \"{since_str}\""
        fields = (
            "summary,status,assignee,story_points,customfield_10016,"
            "issuetype,created,updated,resolutiondate,sprint"
        )
        return self._paginate_jira(
            "/rest/api/3/search",
            results_key="issues",
            params={"jql": jql, "fields": fields},
        )
