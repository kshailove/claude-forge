"""Unit tests for the IdentityResolver service.

Covers:
  - auto_resolve_all: email match creates/updates mapping
  - auto_resolve_all: manual mapping NOT overwritten
  - auto_resolve_all: no email match → counted as unresolved
  - upsert_tool_user: creates mapping when canonical user exists
  - upsert_tool_user: returns None when no user matches
  - upsert_tool_user: never overwrites manual mapping
  - get_unresolved_mappings: returns list (empty in M8v1)
  - ALL_TOOLS constant covers expected tools
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
import pytest_asyncio

from app.services.identity_resolver import ALL_TOOLS, IdentityResolver


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_user(email: str = "alice@example.com") -> MagicMock:
    user = MagicMock()
    user.id = uuid.uuid4()
    user.email = email
    user.is_active = True
    return user


def _make_mapping(
    tool: str = "github",
    tool_user_id: str = "gh-123",
    tool_email: str | None = "alice@example.com",
    resolution_method: str = "auto",
    canonical_user_id: uuid.UUID | None = None,
) -> MagicMock:
    m = MagicMock()
    m.tool = tool
    m.tool_user_id = tool_user_id
    m.tool_email = tool_email
    m.resolution_method = resolution_method
    m.canonical_user_id = canonical_user_id or uuid.uuid4()
    return m


def _make_db(
    mappings: list = None,
    users: list = None,
    existing_mapping=None,
) -> AsyncMock:
    """Build a mock AsyncSession that returns the provided data."""
    db = AsyncMock()

    def _make_result(items):
        result = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all = MagicMock(return_value=items or [])
        result.scalars = MagicMock(return_value=scalars_mock)
        result.scalar_one_or_none = MagicMock(return_value=existing_mapping)
        return result

    # Default: execute returns empty results
    db.execute = AsyncMock(side_effect=lambda *a, **kw: _make_result([]))
    db.flush = AsyncMock()
    db.add = MagicMock()

    return db


# ---------------------------------------------------------------------------
# ALL_TOOLS
# ---------------------------------------------------------------------------


class TestAllTools:
    def test_all_tools_contains_expected_tools(self):
        expected = {"github", "jira", "clickup", "slack", "pagerduty", "zenduty", "keka"}
        assert set(ALL_TOOLS) == expected

    def test_all_tools_is_tuple(self):
        assert isinstance(ALL_TOOLS, tuple)


# ---------------------------------------------------------------------------
# auto_resolve_all
# ---------------------------------------------------------------------------


class TestAutoResolveAll:
    @pytest.mark.asyncio
    async def test_auto_resolve_matches_by_email(self):
        """tool_email matches users.email → mapping canonical_user_id is updated."""
        user = _make_user(email="alice@example.com")
        mapping = _make_mapping(tool_email="alice@example.com", resolution_method="auto")

        db = AsyncMock()
        db.flush = AsyncMock()

        # First call: returns mappings; second call: returns users
        call_count = 0

        async def execute_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            scalars = MagicMock()
            if call_count == 1:
                scalars.all = MagicMock(return_value=[mapping])
            else:
                scalars.all = MagicMock(return_value=[user])
            result.scalars = MagicMock(return_value=scalars)
            return result

        db.execute = AsyncMock(side_effect=execute_side_effect)

        resolver = IdentityResolver()
        result = await resolver.auto_resolve_all("github", db)

        # The mapping's canonical_user_id should have been updated to the user's id
        assert mapping.canonical_user_id == user.id
        assert result.resolved_count >= 1

    @pytest.mark.asyncio
    async def test_manual_mapping_not_overwritten(self):
        """Manual mapping resolution_method stays 'manual'; canonical_user_id unchanged."""
        original_user_id = uuid.uuid4()
        mapping = _make_mapping(
            tool_email="bob@example.com",
            resolution_method="manual",
            canonical_user_id=original_user_id,
        )
        different_user = _make_user(email="bob@example.com")
        different_user.id = uuid.uuid4()  # Different user

        db = AsyncMock()
        db.flush = AsyncMock()

        call_count = 0

        async def execute_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            scalars = MagicMock()
            if call_count == 1:
                scalars.all = MagicMock(return_value=[mapping])
            else:
                scalars.all = MagicMock(return_value=[different_user])
            result.scalars = MagicMock(return_value=scalars)
            return result

        db.execute = AsyncMock(side_effect=execute_side_effect)

        resolver = IdentityResolver()
        result = await resolver.auto_resolve_all("github", db)

        # Manual mapping should NOT have been overwritten
        assert mapping.canonical_user_id == original_user_id
        assert mapping.resolution_method == "manual"

    @pytest.mark.asyncio
    async def test_no_email_match_counted_as_unresolved(self):
        """Mapping with no matching user email → unresolved_count incremented."""
        mapping = _make_mapping(tool_email="noone@nowhere.com", resolution_method="auto")

        db = AsyncMock()
        db.flush = AsyncMock()

        call_count = 0

        async def execute_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            scalars = MagicMock()
            if call_count == 1:
                scalars.all = MagicMock(return_value=[mapping])
            else:
                # No users match
                scalars.all = MagicMock(return_value=[])
            result.scalars = MagicMock(return_value=scalars)
            return result

        db.execute = AsyncMock(side_effect=execute_side_effect)

        resolver = IdentityResolver()
        result = await resolver.auto_resolve_all("github", db)

        assert result.unresolved_count >= 1

    @pytest.mark.asyncio
    async def test_no_mappings_returns_zero_counts(self):
        """No tool users → resolved=0, unresolved=0."""
        db = AsyncMock()
        db.flush = AsyncMock()

        async def execute_side_effect(*args, **kwargs):
            result = MagicMock()
            scalars = MagicMock()
            scalars.all = MagicMock(return_value=[])
            result.scalars = MagicMock(return_value=scalars)
            return result

        db.execute = AsyncMock(side_effect=execute_side_effect)

        resolver = IdentityResolver()
        result = await resolver.auto_resolve_all("github", db)

        assert result.resolved_count == 0
        assert result.unresolved_count == 0

    @pytest.mark.asyncio
    async def test_resolve_result_has_tool_field(self):
        """ResolveResult.tool matches the tool name passed in."""
        db = AsyncMock()
        db.flush = AsyncMock()

        async def execute_side_effect(*args, **kwargs):
            result = MagicMock()
            scalars = MagicMock()
            scalars.all = MagicMock(return_value=[])
            result.scalars = MagicMock(return_value=scalars)
            return result

        db.execute = AsyncMock(side_effect=execute_side_effect)

        resolver = IdentityResolver()
        result = await resolver.auto_resolve_all("slack", db)

        assert result.tool == "slack"


# ---------------------------------------------------------------------------
# upsert_tool_user
# ---------------------------------------------------------------------------


class TestUpsertToolUser:
    @pytest.mark.asyncio
    async def test_upsert_creates_new_mapping_when_user_exists(self):
        """When no existing mapping and user found → creates new IdentityMapping."""
        user = _make_user(email="charlie@example.com")

        db = AsyncMock()
        db.flush = AsyncMock()
        db.add = MagicMock()

        call_count = 0

        async def execute_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            scalars = MagicMock()
            if call_count == 1:
                # User lookup
                result.scalar_one_or_none = MagicMock(return_value=user)
            else:
                # Existing mapping lookup — None
                result.scalar_one_or_none = MagicMock(return_value=None)
            scalars.all = MagicMock(return_value=[])
            result.scalars = MagicMock(return_value=scalars)
            return result

        db.execute = AsyncMock(side_effect=execute_side_effect)

        resolver = IdentityResolver()
        canonical_id = await resolver.upsert_tool_user(
            tool="github",
            tool_user_id="gh-charlie",
            tool_email="charlie@example.com",
            tool_display_name="Charlie Dev",
            db=db,
        )

        assert canonical_id == user.id
        db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_upsert_returns_none_when_no_user_match(self):
        """No matching user and no existing mapping → returns None, no insert."""
        db = AsyncMock()
        db.flush = AsyncMock()
        db.add = MagicMock()

        async def execute_side_effect(*args, **kwargs):
            result = MagicMock()
            result.scalar_one_or_none = MagicMock(return_value=None)
            scalars = MagicMock()
            scalars.all = MagicMock(return_value=[])
            result.scalars = MagicMock(return_value=scalars)
            return result

        db.execute = AsyncMock(side_effect=execute_side_effect)

        resolver = IdentityResolver()
        canonical_id = await resolver.upsert_tool_user(
            tool="jira",
            tool_user_id="jira-unknown",
            tool_email="nobody@nowhere.com",
            tool_display_name="Nobody",
            db=db,
        )

        assert canonical_id is None
        db.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_upsert_never_overwrites_manual_mapping(self):
        """Existing manual mapping → returns existing canonical_user_id unchanged."""
        existing_uid = uuid.uuid4()
        existing_mapping = _make_mapping(
            resolution_method="manual",
            canonical_user_id=existing_uid,
        )
        different_user = _make_user(email="dave@example.com")
        different_user.id = uuid.uuid4()

        db = AsyncMock()
        db.flush = AsyncMock()
        db.add = MagicMock()

        call_count = 0

        async def execute_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                # User lookup
                result.scalar_one_or_none = MagicMock(return_value=different_user)
            else:
                # Existing mapping lookup → return manual mapping
                result.scalar_one_or_none = MagicMock(return_value=existing_mapping)
            scalars = MagicMock()
            scalars.all = MagicMock(return_value=[])
            result.scalars = MagicMock(return_value=scalars)
            return result

        db.execute = AsyncMock(side_effect=execute_side_effect)

        resolver = IdentityResolver()
        result_uid = await resolver.upsert_tool_user(
            tool="github",
            tool_user_id="gh-dave",
            tool_email="dave@example.com",
            tool_display_name="Dave",
            db=db,
        )

        # Should return the existing manual mapping's canonical_user_id, not the new user's
        assert result_uid == existing_uid
        db.add.assert_not_called()


# ---------------------------------------------------------------------------
# get_unresolved_mappings
# ---------------------------------------------------------------------------


class TestGetUnresolvedMappings:
    @pytest.mark.asyncio
    async def test_get_unresolved_returns_list(self):
        """get_unresolved_mappings always returns a list (empty in M8v1)."""
        db = AsyncMock()
        resolver = IdentityResolver()
        result = await resolver.get_unresolved_mappings("github", db)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_resolve_all_tools_runs_for_each_tool(self):
        """resolve_all_tools calls auto_resolve_all for each tool in ALL_TOOLS."""
        db = AsyncMock()

        resolver = IdentityResolver()
        results_called = []

        async def _mock_auto_resolve(tool, db):
            results_called.append(tool)
            from app.schemas.identity import ResolveResult
            return ResolveResult(
                tool=tool,
                resolved_count=0,
                unresolved_count=0,
                conflicts=[],
            )

        resolver.auto_resolve_all = _mock_auto_resolve

        results = await resolver.resolve_all_tools(db)

        assert set(results_called) == set(ALL_TOOLS)
        assert len(results) == len(ALL_TOOLS)
