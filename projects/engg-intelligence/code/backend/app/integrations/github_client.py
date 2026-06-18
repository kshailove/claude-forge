"""GitHub REST API v3 async client with PAT authentication and rate-limit handling.

Spec reference: §6.1, §5.3
"""
from __future__ import annotations

import asyncio
import logging
import re
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

GITHUB_API_BASE = "https://api.github.com"
RATE_LIMIT_LOW_THRESHOLD = 100  # sleep when remaining drops below this
MAX_RETRIES = 3
RETRY_DELAYS = [2, 4, 8]  # seconds — exponential backoff


class GitHubRateLimitError(Exception):
    """Raised when GitHub rate limit is exhausted and reset_at is in the future."""

    def __init__(self, reset_at: datetime) -> None:
        self.reset_at = reset_at
        super().__init__(f"GitHub rate limit exhausted. Resets at {reset_at.isoformat()}")


class GitHubClient:
    """Async GitHub REST API v3 client authenticated with a Personal Access Token.

    Usage:
        async with GitHubClient(pat="ghp_...") as client:
            async for repo in client.get_org_repos("myorg"):
                ...
    """

    def __init__(self, pat: str) -> None:
        self._pat = pat
        self._client: httpx.AsyncClient | None = None

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    async def __aenter__(self) -> "GitHubClient":
        self._client = httpx.AsyncClient(
            base_url=GITHUB_API_BASE,
            headers={
                "Authorization": f"token {self._pat}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
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
                "GitHubClient must be used as an async context manager: "
                "`async with GitHubClient(pat) as client:`"
            )
        return self._client

    async def _get(self, url: str, params: dict | None = None) -> httpx.Response:
        """Perform a GET request with retry on 5xx and rate-limit awareness."""
        client = self._check_client()

        for attempt, delay in enumerate([0] + RETRY_DELAYS):
            if delay:
                logger.info(
                    "github_request_retry",
                    url=url,
                    attempt=attempt,
                    delay_seconds=delay,
                )
                await asyncio.sleep(delay)

            try:
                response = await client.get(url, params=params)
            except httpx.TransportError as exc:
                if attempt < MAX_RETRIES:
                    logger.warning("github_transport_error", url=url, error=str(exc))
                    continue
                raise

            # Rate-limit headers
            remaining = int(response.headers.get("X-RateLimit-Remaining", 1000))
            reset_ts = int(response.headers.get("X-RateLimit-Reset", 0))

            if response.status_code == 403 and remaining == 0:
                reset_at = datetime.fromtimestamp(reset_ts, tz=timezone.utc)
                raise GitHubRateLimitError(reset_at)

            if remaining < RATE_LIMIT_LOW_THRESHOLD:
                logger.info(
                    "github_rate_limit_approaching",
                    remaining=remaining,
                    reset_ts=reset_ts,
                )
                # If near-zero but not zero, sleep until reset
                if remaining < 10 and reset_ts > 0:
                    sleep_secs = max(0, reset_ts - int(time.time()) + 5)
                    logger.warning(
                        "github_rate_limit_sleeping",
                        sleep_seconds=sleep_secs,
                        reset_ts=reset_ts,
                    )
                    await asyncio.sleep(sleep_secs)
                else:
                    # Throttle: 1s sleep between requests when remaining < threshold
                    await asyncio.sleep(1)

            if response.status_code in (500, 502, 503, 504):
                if attempt < MAX_RETRIES:
                    logger.warning(
                        "github_server_error",
                        status=response.status_code,
                        url=url,
                        attempt=attempt,
                    )
                    continue
                response.raise_for_status()

            response.raise_for_status()
            return response

        # Should not reach here but mypy wants a return
        raise RuntimeError(f"Max retries exceeded for GET {url}")

    async def _paginate(
        self,
        url: str,
        params: dict | None = None,
    ) -> AsyncIterator[dict]:
        """Yield individual items from a paginated GitHub list endpoint.

        Follows ``Link: <next_url>; rel="next"`` headers until exhausted.
        """
        next_url: str | None = url
        base_params = dict(params or {})
        base_params.setdefault("per_page", 100)

        while next_url is not None:
            if next_url == url:
                response = await self._get(next_url, params=base_params)
            else:
                # Follow Link header — URL already includes query params
                response = await self._get(next_url)

            data = response.json()
            if isinstance(data, list):
                for item in data:
                    yield item
            elif isinstance(data, dict):
                # Some endpoints return {"items": [...]} or similar
                for item in data.get("items", []):
                    yield item

            # Follow pagination via Link header
            link_header = response.headers.get("Link", "")
            next_url = _parse_next_link(link_header)

    # ------------------------------------------------------------------
    # Public API methods
    # ------------------------------------------------------------------

    async def validate_pat(self) -> dict:
        """Validate the PAT by calling GET /user. Returns user info dict.

        Raises httpx.HTTPStatusError on invalid/expired PAT.
        """
        response = await self._get("/user")
        return response.json()

    async def get_org_repos(self, org_name: str) -> AsyncIterator[dict]:
        """Yield all repositories in an organisation.

        Uses GET /orgs/{org}/repos?type=all&per_page=100 with pagination.
        """
        return self._paginate(
            f"/orgs/{org_name}/repos",
            params={"type": "all", "per_page": 100},
        )

    async def get_recent_prs(
        self,
        owner: str,
        repo: str,
        since_dt: datetime,
    ) -> AsyncIterator[dict]:
        """Yield PRs updated since ``since_dt``.

        Uses GET /repos/{owner}/{repo}/pulls?state=all&sort=updated&direction=desc&since=...
        """
        since_iso = since_dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        return self._paginate(
            f"/repos/{owner}/{repo}/pulls",
            params={
                "state": "all",
                "sort": "updated",
                "direction": "desc",
                "since": since_iso,
                "per_page": 100,
            },
        )

    async def get_pr_reviews(
        self, owner: str, repo: str, pr_number: int
    ) -> list[dict]:
        """Return all reviews for a PR.

        Uses GET /repos/{owner}/{repo}/pulls/{number}/reviews (not paginated in practice,
        but we handle link headers defensively).
        """
        items: list[dict] = []
        async for review in self._paginate(f"/repos/{owner}/{repo}/pulls/{pr_number}/reviews"):
            items.append(review)
        return items

    async def get_pr_commits(
        self, owner: str, repo: str, pr_number: int
    ) -> list[dict]:
        """Return all commits for a PR.

        Uses GET /repos/{owner}/{repo}/pulls/{number}/commits.
        """
        items: list[dict] = []
        async for commit in self._paginate(f"/repos/{owner}/{repo}/pulls/{pr_number}/commits"):
            items.append(commit)
        return items

    async def get_recent_releases(
        self,
        owner: str,
        repo: str,
        tag_pattern: str,
    ) -> list[dict]:
        """Return releases matching ``tag_pattern`` regex.

        Fetches the last 100 releases and filters by tag_name client-side.
        Uses GET /repos/{owner}/{repo}/releases?per_page=100.
        """
        try:
            compiled_pattern = re.compile(tag_pattern)
        except re.error:
            logger.warning(
                "github_invalid_tag_pattern",
                tag_pattern=tag_pattern,
                fallback=".*",
            )
            compiled_pattern = re.compile(".*")

        items: list[dict] = []
        async for release in self._paginate(
            f"/repos/{owner}/{repo}/releases", params={"per_page": 100}
        ):
            if compiled_pattern.search(release.get("tag_name", "")):
                items.append(release)
        return items


# ---------------------------------------------------------------------------
# Link header parser
# ---------------------------------------------------------------------------


def _parse_next_link(link_header: str) -> str | None:
    """Extract the ``next`` URL from a GitHub Link response header.

    Example header value:
        <https://api.github.com/...?page=2>; rel="next", <...>; rel="last"
    """
    if not link_header:
        return None
    for part in link_header.split(","):
        part = part.strip()
        if 'rel="next"' in part:
            match = re.match(r"<([^>]+)>", part)
            if match:
                return match.group(1)
    return None
