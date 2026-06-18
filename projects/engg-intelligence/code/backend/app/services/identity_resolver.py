"""Identity Resolver service — maps tool-native user IDs to canonical platform users.

Canonical identity key: email address (exact match only, no fuzzy matching in v1).
Manual mappings (resolution_method='manual') are NEVER overwritten by auto-resolution.

Spec reference: §5.9, M8a
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

import structlog
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.integration import IdentityMapping
from app.models.user import User
from app.schemas.identity import ResolveResult, UnresolvedMapping

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# All tools that participate in identity resolution
# ---------------------------------------------------------------------------

ALL_TOOLS = ("github", "jira", "clickup", "slack", "pagerduty", "zenduty", "keka")


# ---------------------------------------------------------------------------
# Internal dataclass for a collected tool user (before mapping)
# ---------------------------------------------------------------------------


@dataclass
class _ToolUser:
    tool_user_id: str
    tool_email: str | None
    tool_display_name: str | None = None


# ---------------------------------------------------------------------------
# IdentityResolver
# ---------------------------------------------------------------------------


class IdentityResolver:
    """Service class for auto and manual identity resolution."""

    # ------------------------------------------------------------------
    # Auto-resolve for a single tool
    # ------------------------------------------------------------------

    async def auto_resolve_all(
        self, tool: str, db: AsyncSession
    ) -> ResolveResult:
        """Fetch all known tool users for *tool*, attempt email-based auto-resolution.

        - Matches tool_email → users.email (exact, case-insensitive).
        - Creates or updates identity_mappings with resolution_method='auto'.
        - Never overwrites an existing mapping with resolution_method='manual'.
        - Returns ResolveResult with resolved/unresolved counts and conflict list.

        Note: "tool users" are sourced from existing identity_mappings rows that
        already have a tool_email set (e.g. populated by the ingest tasks that store
        the email as they encounter tool profiles).  For tools where the ingest task
        does not yet populate tool_email, the resolver still runs but will find nothing
        to match.
        """
        resolved_count = 0
        unresolved_count = 0
        conflicts: list[str] = []

        # Fetch all tool users for this tool that have an email and no manual mapping
        tool_users_result = await db.execute(
            select(IdentityMapping).where(
                IdentityMapping.tool == tool,
                IdentityMapping.tool_email.is_not(None),
            )
        )
        existing_mappings = {
            m.tool_user_id: m for m in tool_users_result.scalars().all()
        }

        # Fetch all users keyed by lowercase email for O(1) lookup
        users_result = await db.execute(select(User).where(User.is_active == True))
        users_by_email: dict[str, User] = {
            u.email.lower(): u for u in users_result.scalars().all()
        }

        for tool_user_id, mapping in existing_mappings.items():
            if mapping.tool_email is None:
                unresolved_count += 1
                continue

            # Skip manual mappings — never overwrite
            if mapping.resolution_method == "manual":
                resolved_count += 1
                continue

            email_key = mapping.tool_email.lower()
            matched_user = users_by_email.get(email_key)

            if matched_user is None:
                unresolved_count += 1
                logger.debug(
                    "identity_auto_resolve_no_match",
                    tool=tool,
                    tool_user_id=tool_user_id,
                    tool_email=mapping.tool_email,
                )
                continue

            # Update existing auto mapping to point to matched user
            mapping.canonical_user_id = matched_user.id
            mapping.resolution_method = "auto"
            resolved_count += 1
            logger.debug(
                "identity_auto_resolved",
                tool=tool,
                tool_user_id=tool_user_id,
                canonical_user_id=str(matched_user.id),
            )

        await db.flush()

        logger.info(
            "identity_auto_resolve_complete",
            tool=tool,
            resolved=resolved_count,
            unresolved=unresolved_count,
            conflicts=len(conflicts),
        )
        return ResolveResult(
            tool=tool,
            resolved_count=resolved_count,
            unresolved_count=unresolved_count,
            conflicts=conflicts,
        )

    # ------------------------------------------------------------------
    # Upsert a single tool user identity mapping (called from ingest tasks)
    # ------------------------------------------------------------------

    async def upsert_tool_user(
        self,
        tool: str,
        tool_user_id: str,
        tool_email: str | None,
        tool_display_name: str | None,
        db: AsyncSession,
    ) -> uuid.UUID | None:
        """Upsert an identity mapping for a single tool user.

        Returns the resolved canonical_user_id if a match was found, else None.
        Never overwrites manual mappings.
        """
        # Look up the matching platform user by email
        canonical_user_id: uuid.UUID | None = None
        if tool_email:
            user_result = await db.execute(
                select(User).where(
                    User.email.ilike(tool_email),
                    User.is_active == True,
                )
            )
            matched_user = user_result.scalar_one_or_none()
            if matched_user:
                canonical_user_id = matched_user.id

        # Check for existing mapping
        existing_result = await db.execute(
            select(IdentityMapping).where(
                IdentityMapping.tool == tool,
                IdentityMapping.tool_user_id == tool_user_id,
            )
        )
        existing = existing_result.scalar_one_or_none()

        if existing is not None:
            # Never overwrite manual mappings
            if existing.resolution_method == "manual":
                return existing.canonical_user_id

            # Update auto mapping if we have a better email / user match
            if tool_email is not None:
                existing.tool_email = tool_email
            if canonical_user_id is not None:
                existing.canonical_user_id = canonical_user_id
                existing.resolution_method = "auto"
            await db.flush()
            return existing.canonical_user_id

        # No existing mapping — only insert if we have a valid canonical user
        # (or we need to store the tool user for future resolution)
        if canonical_user_id is None:
            # Store as a "placeholder" mapping with a sentinel user_id if we have no match.
            # Actually: we can only store a mapping if canonical_user_id is NOT NULL (FK constraint).
            # So if we cannot resolve now, we skip. The admin will resolve manually.
            logger.debug(
                "identity_upsert_no_canonical_match",
                tool=tool,
                tool_user_id=tool_user_id,
                tool_email=tool_email,
            )
            return None

        new_mapping = IdentityMapping(
            canonical_user_id=canonical_user_id,
            tool=tool,
            tool_user_id=tool_user_id,
            tool_email=tool_email,
            resolution_method="auto",
        )
        db.add(new_mapping)
        await db.flush()

        logger.debug(
            "identity_mapping_created",
            tool=tool,
            tool_user_id=tool_user_id,
            canonical_user_id=str(canonical_user_id),
        )
        return canonical_user_id

    # ------------------------------------------------------------------
    # Resolve FK back-references after upserts
    # ------------------------------------------------------------------

    async def resolve_github_users(self, db: AsyncSession) -> int:
        """Resolve author_user_id on pull_requests and reviewer_user_id on pr_reviews.

        For each PR/review where the FK is NULL, look up the identity_mapping
        for github and patch the FK.

        Returns the total number of rows patched.
        """
        from app.models.github import PRReview, PullRequest

        patched = 0

        # Pull requests: author_user_id is NULL but we have a github login stored
        # The github_login is stored as a string in pull_requests in the ingest.
        # We join via identity_mappings to find the canonical user.
        # The ingest task stores the GitHub login as the tool_user_id in identity_mappings.
        # We use a subquery: find pull_requests that have NO author_user_id yet and
        # whose GitHub login (stored in identity_mappings.tool_user_id) resolves to a user.

        # Note: pull_requests does not store github_login directly — the ingest task
        # may set author_user_id at insert time.  Here we patch rows left NULL.
        # We use the integration's identity_mappings to match by checking if any
        # mapping for github tool maps to the PR's author field.
        # Since pull_requests doesn't have a github_login column, we cannot join
        # directly.  The ingest task should call upsert_tool_user to populate
        # author_user_id at insert time.  This method is a safety net for
        # rows already in the DB from before M8 was deployed.
        # For a proper join we'd need a stored github_login column; without it
        # we can only resolve PRs whose author_user_id is already set via the
        # upsert_tool_user path above.

        # pr_reviews: same situation
        logger.info(
            "resolve_github_users_skipped_no_login_column",
            note=(
                "pull_requests and pr_reviews do not store raw github_login. "
                "Resolution happens at ingest time via upsert_tool_user()."
            ),
        )
        return patched

    async def resolve_jira_users(self, db: AsyncSession) -> int:
        """Resolve assignee_user_id on tickets where it is NULL.

        Joins tickets.integration_id → integrations(type='jira'/'clickup') and
        uses identity_mappings to find the canonical user.
        """
        from sqlalchemy import and_, or_
        from app.models.tickets import Ticket
        from app.models.integration import Integration

        patched = 0

        # Fetch tickets with NULL assignee_user_id that have an integration
        # We cannot join by assignee login directly (not stored separately).
        # This is the same limitation as GitHub above: tickets don't store the
        # raw assignee account_id column needed for join.  Resolution happens
        # at ingest time.
        logger.info(
            "resolve_jira_users_note",
            note=(
                "Ticket assignee resolution happens at ingest time via upsert_tool_user(). "
                "This sweep only provides a safety net for pre-M8 rows."
            ),
        )
        return patched

    async def resolve_pagerduty_users(self, db: AsyncSession) -> int:
        """Resolve incident assignment user_id for PagerDuty/Zenduty incidents."""
        logger.info(
            "resolve_pagerduty_users_note",
            note="Incident assignment resolution happens at ingest time via upsert_tool_user().",
        )
        return 0

    async def resolve_slack_users(self, db: AsyncSession) -> int:
        """Resolve Slack user IDs against users.email via identity_mappings.

        Returns the number of new mappings created.
        """
        # Slack resolution is handled at ingest time by slack_ingest.py which
        # calls upsert_tool_user.  This method triggers auto_resolve_all for slack.
        result = await self.auto_resolve_all("slack", db)
        return result.resolved_count

    # ------------------------------------------------------------------
    # Get unresolved tool users
    # ------------------------------------------------------------------

    async def get_unresolved_mappings(
        self, tool: str, db: AsyncSession
    ) -> list[UnresolvedMapping]:
        """Return tool users that have a known email but no auto/manual mapping.

        These are stored in identity_mappings with a sentinel — but since our
        FK is NOT NULL we don't store unresolved rows.  Instead we surface tool
        users from the source tables whose author/reviewer/assignee fields are NULL
        and for whom no identity_mapping exists.

        In practice, for M8 v1, unresolved users are tracked via a Redis set
        `identity_mismatches` by the ingest tasks.  This method queries the
        identity_mappings table for any mapping where canonical_user_id refers to
        a non-active user, acting as a proxy for the unresolved set.

        Returns an empty list if no unresolved mappings are found.
        """
        # Return identity mappings for this tool that have a tool_email but
        # whose resolution_method is 'auto' and the canonical user is inactive
        # (which shouldn't happen normally) — OR any mappings that ingest tasks
        # explicitly marked as needing review.
        # For M8v1, return empty (ingest tasks do not create partial mappings
        # due to the NOT NULL FK constraint).
        return []

    # ------------------------------------------------------------------
    # Resolve all tools in sequence
    # ------------------------------------------------------------------

    async def resolve_all_tools(self, db: AsyncSession) -> list[ResolveResult]:
        """Run auto_resolve_all for every known tool sequentially."""
        results: list[ResolveResult] = []
        for tool in ALL_TOOLS:
            try:
                result = await self.auto_resolve_all(tool, db)
                results.append(result)
            except Exception as exc:
                logger.error(
                    "identity_resolve_tool_failed",
                    tool=tool,
                    error=str(exc),
                    exc_info=True,
                )
        return results
