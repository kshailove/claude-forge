"""Admin router — users, teams, org-tree, nightly runs, identity mappings endpoints.

Spec §4.7, §4.8, §4.9, §4.10.
All endpoints require the 'admin' role.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.rbac import AdminUser, require_roles
from app.core.security import hash_password
from app.models.integration import IdentityMapping
from app.models.nightly import NightlyRun
from app.models.team import OrgNode, Team, TeamMembership
from app.models.user import User
from app.schemas.admin import (
    CreateTeamRequest,
    CreateUserRequest,
    NightlyRunListResponse,
    NightlyRunResponse,
    OrgTreeNode,
    OrgTreeRequest,
    OrgTreeResponse,
    OrgTreeNodeResponse,
    TeamDetail,
    TeamListResponse,
    TriggerNightlyRunResponse,
    UpdateTeamRequest,
    UpdateUserRequest,
    UserDetail,
    UserListResponse,
)
from app.schemas.identity import (
    AutoResolveJobResponse,
    IdentityMappingListResponse,
    IdentityMappingResponse,
    ManualMappingRequest,
    UnresolvedByToolResponse,
    UnresolvedMapping,
)

router = APIRouter(prefix="/admin", tags=["admin"])


# ===========================================================================
# Users
# ===========================================================================


@router.post(
    "/users",
    response_model=UserDetail,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles("admin"))],
)
async def create_user(
    body: CreateUserRequest,
    db: AsyncSession = Depends(get_db),
) -> UserDetail:
    """Create a new platform user. Admin only."""
    # Check uniqueness
    existing = await db.execute(
        select(User).where(
            (User.email == body.email) | (User.username == body.username)
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": {
                    "code": "USER_ALREADY_EXISTS",
                    "message": "A user with this email or username already exists.",
                    "details": {},
                }
            },
        )

    user = User(
        email=body.email,
        username=body.username,
        password_hash=hash_password(body.password),
        role=body.role,
        team_id=body.team_id,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return UserDetail.model_validate(user)


@router.get(
    "/users",
    response_model=UserListResponse,
    dependencies=[Depends(require_roles("admin"))],
)
async def list_users(
    db: AsyncSession = Depends(get_db),
) -> UserListResponse:
    """List all users. Admin only."""
    result = await db.execute(select(User).order_by(User.created_at))
    users = result.scalars().all()
    return UserListResponse(
        users=[UserDetail.model_validate(u) for u in users],
        total=len(users),
    )


@router.get(
    "/users/{user_id}",
    response_model=UserDetail,
    dependencies=[Depends(require_roles("admin"))],
)
async def get_user(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> UserDetail:
    """Get a single user by ID. Admin only."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return UserDetail.model_validate(user)


@router.put(
    "/users/{user_id}",
    response_model=UserDetail,
    dependencies=[Depends(require_roles("admin"))],
)
async def update_user(
    user_id: uuid.UUID,
    body: UpdateUserRequest,
    admin: AdminUser,
    db: AsyncSession = Depends(get_db),
) -> UserDetail:
    """Update a user. Admin only."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    if body.email is not None:
        user.email = body.email
    if body.username is not None:
        user.username = body.username
    if body.role is not None:
        user.role = body.role
    if body.team_id is not None:
        user.team_id = body.team_id
    if body.is_active is not None:
        user.is_active = body.is_active

    await db.flush()
    await db.refresh(user)
    return UserDetail.model_validate(user)


@router.delete(
    "/users/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    dependencies=[Depends(require_roles("admin"))],
)
async def delete_user(
    user_id: uuid.UUID,
    admin: AdminUser,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Soft-delete a user (sets is_active=False). Admin only.

    Blocks deletion of the last admin account.
    """
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    # Prevent deleting the last admin
    if user.role == "admin":
        count_result = await db.execute(
            select(func.count()).select_from(User).where(
                User.role == "admin", User.is_active == True
            )
        )
        admin_count = count_result.scalar_one()
        if admin_count <= 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": {
                        "code": "CANNOT_DELETE_LAST_ADMIN",
                        "message": "Cannot delete the last admin account.",
                        "details": {},
                    }
                },
            )

    user.is_active = False
    await db.flush()


# ===========================================================================
# Teams
# ===========================================================================


@router.post(
    "/teams",
    response_model=TeamDetail,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles("admin"))],
)
async def create_team(
    body: CreateTeamRequest,
    db: AsyncSession = Depends(get_db),
) -> TeamDetail:
    """Create a team. Admin only."""
    existing = await db.execute(select(Team).where(Team.slug == body.slug))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": {
                    "code": "SLUG_ALREADY_EXISTS",
                    "message": f"A team with slug '{body.slug}' already exists.",
                    "details": {},
                }
            },
        )

    team = Team(name=body.name, slug=body.slug, em_user_id=body.em_user_id)
    db.add(team)
    await db.flush()
    await db.refresh(team)
    return TeamDetail.model_validate(team)


@router.get(
    "/teams",
    response_model=TeamListResponse,
    dependencies=[Depends(require_roles("admin"))],
)
async def list_teams(
    db: AsyncSession = Depends(get_db),
) -> TeamListResponse:
    """List all teams. Admin only."""
    result = await db.execute(select(Team).order_by(Team.name))
    teams = result.scalars().all()
    return TeamListResponse(
        teams=[TeamDetail.model_validate(t) for t in teams],
        total=len(teams),
    )


@router.get(
    "/teams/{team_id}",
    response_model=TeamDetail,
    dependencies=[Depends(require_roles("admin"))],
)
async def get_team(
    team_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> TeamDetail:
    result = await db.execute(select(Team).where(Team.id == team_id))
    team = result.scalar_one_or_none()
    if team is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return TeamDetail.model_validate(team)


@router.put(
    "/teams/{team_id}",
    response_model=TeamDetail,
    dependencies=[Depends(require_roles("admin"))],
)
async def update_team(
    team_id: uuid.UUID,
    body: UpdateTeamRequest,
    db: AsyncSession = Depends(get_db),
) -> TeamDetail:
    result = await db.execute(select(Team).where(Team.id == team_id))
    team = result.scalar_one_or_none()
    if team is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    if body.name is not None:
        team.name = body.name
    if body.slug is not None:
        team.slug = body.slug
    if body.em_user_id is not None:
        team.em_user_id = body.em_user_id

    await db.flush()
    await db.refresh(team)
    return TeamDetail.model_validate(team)


# ===========================================================================
# Org Tree
# ===========================================================================


@router.post(
    "/org-tree",
    response_model=OrgTreeResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_roles("admin"))],
)
async def bulk_upsert_org_tree(
    body: OrgTreeRequest,
    db: AsyncSession = Depends(get_db),
) -> OrgTreeResponse:
    """Bulk replace org tree (manual source). Admin only.

    Deletes all existing 'manual' source rows and inserts new ones.
    """
    # Delete all manual-source org nodes
    await db.execute(delete(OrgNode).where(OrgNode.source == "manual"))

    # Insert new nodes
    for node in body.nodes:
        org_node = OrgNode(
            employee_user_id=node.employee_user_id,
            manager_user_id=node.manager_user_id,
            source="manual",
        )
        db.add(org_node)

    await db.flush()
    return await _get_org_tree_response(db)


@router.get(
    "/org-tree",
    response_model=OrgTreeResponse,
    dependencies=[Depends(require_roles("admin"))],
)
async def get_org_tree(
    db: AsyncSession = Depends(get_db),
) -> OrgTreeResponse:
    """Get current org tree. Admin only."""
    return await _get_org_tree_response(db)


async def _get_org_tree_response(db: AsyncSession) -> OrgTreeResponse:
    """Build the org tree response, detecting source and last Keka sync."""
    from app.models.integration import Integration

    result = await db.execute(select(OrgNode).order_by(OrgNode.employee_user_id))
    nodes = result.scalars().all()

    # Determine source: if any keka nodes exist, source is keka
    sources = {n.source for n in nodes}
    source = "keka" if "keka" in sources else "manual"

    # Get last Keka sync timestamp from integrations table
    last_keka_sync: datetime | None = None
    if source == "keka":
        keka_result = await db.execute(
            select(Integration).where(Integration.type == "keka")
        )
        keka_integration = keka_result.scalar_one_or_none()
        if keka_integration:
            last_keka_sync = keka_integration.last_synced_at

    return OrgTreeResponse(
        source=source,
        last_keka_sync_at=last_keka_sync,
        nodes=[
            OrgTreeNodeResponse(
                employee_user_id=n.employee_user_id,
                manager_user_id=n.manager_user_id,
                source=n.source,
            )
            for n in nodes
        ],
    )


# ===========================================================================
# Nightly Runs
# ===========================================================================


@router.get(
    "/nightly-runs",
    response_model=NightlyRunListResponse,
    dependencies=[Depends(require_roles("admin"))],
)
async def list_nightly_runs(
    db: AsyncSession = Depends(get_db),
) -> NightlyRunListResponse:
    """List the last 30 nightly run records. Admin only."""
    result = await db.execute(
        select(NightlyRun).order_by(NightlyRun.scheduled_at.desc()).limit(30)
    )
    runs = result.scalars().all()
    return NightlyRunListResponse(
        runs=[NightlyRunResponse.model_validate(r) for r in runs]
    )


@router.post(
    "/nightly-runs/trigger",
    response_model=TriggerNightlyRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_roles("admin"))],
)
async def trigger_nightly_run(
    db: AsyncSession = Depends(get_db),
) -> TriggerNightlyRunResponse:
    """Manually trigger a nightly run. Admin only.

    Returns 409 if a run is already in progress.
    """
    # Check if a run is already active
    active_result = await db.execute(
        select(NightlyRun).where(NightlyRun.status == "running")
    )
    active_run = active_result.scalar_one_or_none()
    if active_run:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": {
                    "code": "RUN_ALREADY_ACTIVE",
                    "message": "A nightly run is already in progress.",
                    "details": {},
                }
            },
        )

    # Create a new pending run and dispatch to Celery
    now = datetime.now(tz=timezone.utc)
    new_run = NightlyRun(scheduled_at=now, status="pending")
    db.add(new_run)
    await db.flush()
    await db.refresh(new_run)

    # Dispatch to Celery (import here to avoid circular imports)
    from app.tasks.orchestrator import run_nightly_batch
    run_nightly_batch.apply_async(
        kwargs={"nightly_run_id": str(new_run.id)},
        queue="q_github",  # orchestrator uses default queue
    )

    return TriggerNightlyRunResponse(
        run_id=new_run.id,
        message="Nightly run queued",
    )


# ===========================================================================
# Identity Mappings (M8b)
# ===========================================================================


@router.get(
    "/identity-mappings",
    response_model=IdentityMappingListResponse,
    dependencies=[Depends(require_roles("admin"))],
)
async def list_identity_mappings(
    tool: str | None = Query(default=None, description="Filter by tool name."),
    resolution_method: str | None = Query(
        default=None,
        description="Filter by resolution method: 'auto' or 'manual'.",
    ),
    page: int = Query(default=1, ge=1, description="Page number (1-based)."),
    page_size: int = Query(default=50, ge=1, le=200, description="Items per page."),
    db: AsyncSession = Depends(get_db),
) -> IdentityMappingListResponse:
    """List identity mappings with optional filtering. Admin only.

    Query params:
      - tool: filter by tool (github, jira, slack, etc.)
      - resolution_method: filter by 'auto' or 'manual'
      - page, page_size: pagination
    """
    query = select(IdentityMapping)

    if tool is not None:
        query = query.where(IdentityMapping.tool == tool)
    if resolution_method is not None:
        query = query.where(IdentityMapping.resolution_method == resolution_method)

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    # Paginate
    offset = (page - 1) * page_size
    query = query.order_by(IdentityMapping.tool, IdentityMapping.tool_user_id)
    query = query.offset(offset).limit(page_size)

    result = await db.execute(query)
    mappings = result.scalars().all()

    return IdentityMappingListResponse(
        mappings=[IdentityMappingResponse.model_validate(m) for m in mappings],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/identity-mappings/unresolved",
    response_model=UnresolvedByToolResponse,
    dependencies=[Depends(require_roles("admin"))],
)
async def get_unresolved_identity_mappings(
    db: AsyncSession = Depends(get_db),
) -> UnresolvedByToolResponse:
    """List unresolved tool users (no identity mapping) per tool. Admin only.

    Returns a dict of tool → list of unresolved tool users.

    In v1, "unresolved" means: identity_mappings rows whose tool_email does not
    match any active users.email. Since the FK constraint prevents storing
    unmapped rows, this returns any rows where the linked canonical_user
    has become inactive.
    """
    from app.services.identity_resolver import ALL_TOOLS, IdentityResolver

    resolver = IdentityResolver()
    result: dict[str, list[UnresolvedMapping]] = {t: [] for t in ALL_TOOLS}

    for tool in ALL_TOOLS:
        unresolved = await resolver.get_unresolved_mappings(tool, db)
        result[tool] = unresolved

    return UnresolvedByToolResponse(**result)


@router.post(
    "/identity-mappings",
    response_model=IdentityMappingResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles("admin"))],
)
async def create_identity_mapping(
    body: ManualMappingRequest,
    db: AsyncSession = Depends(get_db),
) -> IdentityMappingResponse:
    """Manually create an identity mapping. Admin only.

    Body: { canonical_user_id, tool, tool_user_id, tool_email? }

    Validates that canonical_user_id exists in the users table.
    Creates mapping with resolution_method='manual'.
    Returns 409 if a mapping for (tool, tool_user_id) already exists.
    """
    # Validate canonical user exists
    user_result = await db.execute(
        select(User).where(User.id == body.canonical_user_id)
    )
    canonical_user = user_result.scalar_one_or_none()
    if canonical_user is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": {
                    "code": "USER_NOT_FOUND",
                    "message": f"No user found with id={body.canonical_user_id}.",
                    "details": {},
                }
            },
        )

    # Check for existing mapping
    existing_result = await db.execute(
        select(IdentityMapping).where(
            IdentityMapping.tool == body.tool,
            IdentityMapping.tool_user_id == body.tool_user_id,
        )
    )
    existing = existing_result.scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": {
                    "code": "IDENTITY_MAPPING_EXISTS",
                    "message": (
                        f"A mapping for tool='{body.tool}' tool_user_id='{body.tool_user_id}' "
                        "already exists. Delete it first or use the update endpoint."
                    ),
                    "details": {},
                }
            },
        )

    mapping = IdentityMapping(
        canonical_user_id=body.canonical_user_id,
        tool=body.tool,
        tool_user_id=body.tool_user_id,
        tool_email=body.tool_email,
        resolution_method="manual",
    )
    db.add(mapping)
    await db.flush()
    await db.refresh(mapping)

    return IdentityMappingResponse.model_validate(mapping)


@router.delete(
    "/identity-mappings/{mapping_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    dependencies=[Depends(require_roles("admin"))],
)
async def delete_identity_mapping(
    mapping_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Remove an identity mapping by ID. Admin only."""
    result = await db.execute(
        select(IdentityMapping).where(IdentityMapping.id == mapping_id)
    )
    mapping = result.scalar_one_or_none()
    if mapping is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    await db.delete(mapping)
    await db.flush()


@router.post(
    "/identity-mappings/auto-resolve",
    response_model=AutoResolveJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_roles("admin"))],
)
async def trigger_auto_resolve(
    db: AsyncSession = Depends(get_db),
) -> AutoResolveJobResponse:
    """Trigger auto-resolution for all tools. Admin only.

    Enqueues the auto_resolve_identities Celery task.
    Returns the task ID for polling.
    """
    from app.tasks.identity_tasks import auto_resolve_identities

    task_result = auto_resolve_identities.apply_async(
        queue="q_github",
    )

    return AutoResolveJobResponse(
        status="accepted",
        task_id=task_result.id,
        message="Auto-resolution task queued. All tools will be processed.",
    )
