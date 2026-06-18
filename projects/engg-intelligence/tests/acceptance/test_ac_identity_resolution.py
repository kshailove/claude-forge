"""Acceptance tests for identity resolution.

AC criteria verified:
  - Auto-resolve matches by email → mapping created/updated
  - Manual mapping not overwritten by auto-resolve
  - Unresolved users listed (no email match → appears in unresolved list)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

from app.services.identity_resolver import IdentityResolver

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _seed_user(db, email: str, username: str | None = None) -> MagicMock:
    """Seed a real User row in the in-memory DB."""
    from app.core.security import hash_password
    from app.models.user import User
    user = User(
        id=uuid.uuid4(),
        email=email,
        username=username or email.split("@")[0].replace(".", "_"),
        password_hash=hash_password("TestPass123!"),
        role="engineer",
        team_id=None,
        is_active=True,
    )
    db.add(user)
    await db.flush()
    return user


async def _seed_identity_mapping(
    db,
    canonical_user_id: uuid.UUID,
    tool: str = "github",
    tool_user_id: str = "gh-user-1",
    tool_email: str | None = None,
    resolution_method: str = "auto",
):
    """Seed an IdentityMapping row."""
    from app.models.integration import IdentityMapping
    mapping = IdentityMapping(
        id=uuid.uuid4(),
        canonical_user_id=canonical_user_id,
        tool=tool,
        tool_user_id=tool_user_id,
        tool_email=tool_email,
        resolution_method=resolution_method,
    )
    db.add(mapping)
    await db.flush()
    return mapping


# ---------------------------------------------------------------------------
# AC: Auto-resolve matches by email
# ---------------------------------------------------------------------------


class TestAutoResolveMatchesByEmail:
    async def test_ac_auto_resolve_matches_by_email(
        self, async_db_session, sample_team, sample_users
    ):
        """AC: tool_email matches users.email → canonical_user_id updated on mapping."""
        # Seed a canonical user
        target_user = await _seed_user(async_db_session, "alice@example.com", "alice_dev")

        # Seed an identity mapping with same email but pointing to a placeholder user
        placeholder_user = await _seed_user(
            async_db_session, "placeholder@internal.example.com", "placeholder"
        )
        mapping = await _seed_identity_mapping(
            async_db_session,
            canonical_user_id=placeholder_user.id,
            tool="github",
            tool_user_id="gh-alice",
            tool_email="alice@example.com",
            resolution_method="auto",
        )

        resolver = IdentityResolver()
        result = await resolver.auto_resolve_all("github", async_db_session)

        # Alice's mapping should have been resolved to the correct user
        assert result.resolved_count >= 1

    async def test_ac_auto_resolve_updates_canonical_user_id(
        self, async_db_session, sample_team, sample_users
    ):
        """AC: After auto_resolve_all, mapping.canonical_user_id matches the platform user."""
        from sqlalchemy import select
        from app.models.integration import IdentityMapping

        # Seed the canonical user
        target_user = await _seed_user(async_db_session, "bob@example.com", "bob_dev")

        # Seed a placeholder mapping
        placeholder = await _seed_user(async_db_session, "placeholder2@x.com", "ph2")
        mapping = await _seed_identity_mapping(
            async_db_session,
            canonical_user_id=placeholder.id,
            tool="jira",
            tool_user_id="jira-bob",
            tool_email="bob@example.com",
            resolution_method="auto",
        )

        resolver = IdentityResolver()
        await resolver.auto_resolve_all("jira", async_db_session)

        # Re-fetch the mapping
        result = await async_db_session.execute(
            select(IdentityMapping).where(IdentityMapping.id == mapping.id)
        )
        updated_mapping = result.scalar_one_or_none()
        assert updated_mapping is not None
        assert updated_mapping.canonical_user_id == target_user.id


# ---------------------------------------------------------------------------
# AC: Manual mapping not overwritten
# ---------------------------------------------------------------------------


class TestManualMappingNotOverwritten:
    async def test_ac_manual_mapping_not_overwritten(
        self, async_db_session, sample_team, sample_users
    ):
        """AC: Existing manual mapping stays unchanged when auto-resolve runs."""
        from sqlalchemy import select
        from app.models.integration import IdentityMapping

        # The canonical user for the manual mapping
        manual_user = await _seed_user(async_db_session, "manual@example.com", "manual_dev")

        # A different user that email would match
        other_user = await _seed_user(async_db_session, "carol@example.com", "carol_dev")

        # Seed manual mapping: tool_email = carol@example.com but manually pointing to manual_user
        mapping = await _seed_identity_mapping(
            async_db_session,
            canonical_user_id=manual_user.id,
            tool="slack",
            tool_user_id="slack-carol",
            tool_email="carol@example.com",
            resolution_method="manual",
        )
        original_canonical_id = manual_user.id

        # Run auto-resolve (should skip manual mapping)
        resolver = IdentityResolver()
        await resolver.auto_resolve_all("slack", async_db_session)

        # Re-fetch
        result = await async_db_session.execute(
            select(IdentityMapping).where(IdentityMapping.id == mapping.id)
        )
        updated = result.scalar_one_or_none()
        assert updated is not None
        assert updated.canonical_user_id == original_canonical_id
        assert updated.resolution_method == "manual"

    async def test_ac_upsert_does_not_overwrite_manual_mapping(
        self, async_db_session, sample_team, sample_users
    ):
        """AC: upsert_tool_user with matching email does not overwrite a manual mapping."""
        from sqlalchemy import select
        from app.models.integration import IdentityMapping

        # Canonical user for manual mapping
        manual_target = await _seed_user(async_db_session, "dana@example.com", "dana_dev")

        # A different user that email would resolve to
        auto_target = await _seed_user(async_db_session, "eve@example.com", "eve_dev")

        # Seed a manual mapping
        mapping = await _seed_identity_mapping(
            async_db_session,
            canonical_user_id=manual_target.id,
            tool="pagerduty",
            tool_user_id="pd-dana",
            tool_email="eve@example.com",  # email would auto-resolve to eve
            resolution_method="manual",
        )

        resolver = IdentityResolver()
        returned_id = await resolver.upsert_tool_user(
            tool="pagerduty",
            tool_user_id="pd-dana",
            tool_email="eve@example.com",
            tool_display_name="Dana",
            db=async_db_session,
        )

        # Must still point to the manual target, not auto-resolved eve
        assert returned_id == manual_target.id


# ---------------------------------------------------------------------------
# AC: Unresolved users listed
# ---------------------------------------------------------------------------


class TestUnresolvedUsersListed:
    async def test_ac_unresolved_users_listed_when_no_email_match(
        self, async_db_session, sample_team, sample_users
    ):
        """AC: Tool user with no matching platform email → counted as unresolved."""
        from sqlalchemy import select
        from app.models.integration import IdentityMapping

        # Seed a placeholder user (needed for FK) to hold the "unresolved" mapping
        placeholder = await _seed_user(async_db_session, "placeholder99@x.com", "ph99")

        # Seed a mapping with an email that has no matching platform user
        mapping = await _seed_identity_mapping(
            async_db_session,
            canonical_user_id=placeholder.id,
            tool="github",
            tool_user_id="gh-ghost-user",
            tool_email="ghost@nowhere-special.com",  # no platform user with this email
            resolution_method="auto",
        )

        resolver = IdentityResolver()
        result = await resolver.auto_resolve_all("github", async_db_session)

        # ghost@nowhere-special.com has no matching user → unresolved
        assert result.unresolved_count >= 1

    async def test_ac_get_unresolved_mappings_returns_list(
        self, async_db_session, sample_team
    ):
        """AC: get_unresolved_mappings returns a list (empty or populated)."""
        resolver = IdentityResolver()
        result = await resolver.get_unresolved_mappings("github", async_db_session)
        assert isinstance(result, list)

    async def test_ac_upsert_with_no_match_returns_none(
        self, async_db_session, sample_team, sample_users
    ):
        """AC: upsert_tool_user with non-existent email → returns None (user tracked as unresolved)."""
        resolver = IdentityResolver()
        result = await resolver.upsert_tool_user(
            tool="github",
            tool_user_id="gh-unresolvable",
            tool_email="nobody@completely-unknown-domain.com",
            tool_display_name="Ghost User",
            db=async_db_session,
        )
        assert result is None

    async def test_ac_resolve_all_tools_processes_every_tool(
        self, async_db_session, sample_team, sample_users
    ):
        """AC: resolve_all_tools processes all known tool integrations."""
        from app.services.identity_resolver import ALL_TOOLS

        resolver = IdentityResolver()
        results = await resolver.resolve_all_tools(async_db_session)

        assert len(results) == len(ALL_TOOLS)
        resolved_tools = {r.tool for r in results}
        assert resolved_tools == set(ALL_TOOLS)
