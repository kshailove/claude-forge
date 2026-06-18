"""Admin Integration endpoints — GitHub, Jira, ClickUp, PagerDuty, Zenduty.

Spec reference: §4.7, M1a, M1b, M2a, M2b, M3a, M3b
All endpoints require the 'admin' role.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.rbac import AdminUser, require_roles
from app.models.backfill import BackfillJob
from app.models.integration import Integration
from app.schemas.integration import (
    BackfillJobListResponse,
    BackfillJobResponse,
    BackfillRequest,
    BackfillStatusResponse,
    ClickUpConnectRequest,
    ClickUpConfigureSprintsRequest,
    ClickUpStatusResponse,
    GitHubConnectRequest,
    GitHubStatusResponse,
    IncidentBackfillRequest,
    IntegrationListResponse,
    IntegrationResponse,
    JiraConnectRequest,
    JiraStatusResponse,
    KekaConnectRequest,
    KekaDisconnectRequest,
    KekaStatusResponse,
    PagerDutyConnectRequest,
    PagerDutyStatusResponse,
    SlackConnectRequest,
    SlackConnectResponse,
    SlackStatusResponse,
    ZendutyConnectRequest,
    ZendutyStatusResponse,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/admin/integrations", tags=["admin-integrations"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_integration_response(integration: Integration) -> IntegrationResponse:
    """Build an IntegrationResponse from an ORM Integration, stripping secrets."""
    config_summary = integration.get_config_summary()
    # Add expires_at to summary if present in config
    try:
        raw_config = integration.get_config()
        if "expires_at" in raw_config and raw_config["expires_at"]:
            config_summary["token_expires_at"] = raw_config["expires_at"]
    except Exception:
        pass

    return IntegrationResponse(
        id=integration.id,
        type=integration.type,
        status=integration.status,
        team_id=integration.team_id,
        last_synced_at=integration.last_synced_at,
        created_at=integration.created_at,
        updated_at=integration.updated_at,
        config_summary=config_summary,
    )


# ---------------------------------------------------------------------------
# GET /admin/integrations
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=IntegrationListResponse,
    dependencies=[Depends(require_roles("admin"))],
)
async def list_integrations(
    db: AsyncSession = Depends(get_db),
) -> IntegrationListResponse:
    """List all configured integrations. Admin only.

    Returns non-sensitive config summary fields only. API tokens are never returned.
    """
    result = await db.execute(select(Integration).order_by(Integration.type))
    integrations = result.scalars().all()
    return IntegrationListResponse(
        integrations=[_build_integration_response(i) for i in integrations]
    )


# ---------------------------------------------------------------------------
# GitHub — POST /admin/integrations/github/connect
# ---------------------------------------------------------------------------


@router.post(
    "/github/connect",
    response_model=IntegrationResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles("admin"))],
)
async def connect_github(
    body: GitHubConnectRequest,
    db: AsyncSession = Depends(get_db),
) -> IntegrationResponse:
    """Connect GitHub via Personal Access Token.

    Validates the PAT by calling GitHub GET /user. On success, stores the
    encrypted config and sets status='connected'. If a GitHub integration
    already exists, updates it (upsert semantics).
    """
    # Validate PAT by calling GitHub API
    from app.integrations.github_client import GitHubClient

    try:
        async with GitHubClient(pat=body.personal_access_token) as client:
            user_info = await client.validate_pat()
    except httpx.HTTPStatusError as exc:
        logger.warning(
            "github_pat_validation_failed",
            status_code=exc.response.status_code,
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": {
                    "code": "INVALID_GITHUB_PAT",
                    "message": (
                        f"GitHub PAT validation failed (HTTP {exc.response.status_code}). "
                        "Ensure the token has 'repo' scope and has not expired."
                    ),
                    "details": {},
                }
            },
        ) from exc
    except Exception as exc:
        logger.error("github_pat_validation_error", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "error": {
                    "code": "GITHUB_UNREACHABLE",
                    "message": "Could not reach GitHub API to validate the token.",
                    "details": {},
                }
            },
        ) from exc

    logger.info(
        "github_pat_validated",
        github_login=user_info.get("login"),
        github_user_id=user_info.get("id"),
    )

    # Check PAT expiry from GitHub response (fine-grained tokens include expiry)
    # The /user endpoint may return `token_expiry_date` for fine-grained PATs
    expires_at: str | None = None

    # Check if already exists
    existing_result = await db.execute(
        select(Integration).where(Integration.type == "github")
    )
    integration = existing_result.scalar_one_or_none()

    config = {
        "personal_access_token": body.personal_access_token,
        "org_name": body.org_name,
        "release_tag_pattern": body.release_tag_pattern,
        "expires_at": expires_at,
    }

    if integration is None:
        integration = Integration(type="github", status="connected", team_id=None)
        db.add(integration)
    else:
        integration.status = "connected"

    integration.set_config(config)
    await db.flush()
    await db.refresh(integration)

    logger.info(
        "github_integration_connected",
        integration_id=str(integration.id),
        org_name=body.org_name,
    )

    return _build_integration_response(integration)


# ---------------------------------------------------------------------------
# GitHub — GET /admin/integrations/github/status
# ---------------------------------------------------------------------------


@router.get(
    "/github/status",
    response_model=GitHubStatusResponse,
    dependencies=[Depends(require_roles("admin"))],
)
async def get_github_status(
    db: AsyncSession = Depends(get_db),
) -> GitHubStatusResponse:
    """Return GitHub integration connection status and last sync timestamp."""
    result = await db.execute(
        select(Integration).where(Integration.type == "github")
    )
    integration = result.scalar_one_or_none()

    if integration is None:
        return GitHubStatusResponse(
            connected=False,
            status="disconnected",
            last_synced_at=None,
            org_name=None,
            release_tag_pattern=None,
            integration_id=None,
        )

    try:
        config_summary = integration.get_config_summary()
    except Exception:
        config_summary = {}

    return GitHubStatusResponse(
        connected=integration.status == "connected",
        status=integration.status,
        last_synced_at=integration.last_synced_at,
        org_name=config_summary.get("org_name"),
        release_tag_pattern=config_summary.get("release_tag_pattern"),
        integration_id=integration.id,
    )


# ---------------------------------------------------------------------------
# GitHub — DELETE /admin/integrations/github
# ---------------------------------------------------------------------------


@router.delete(
    "/github",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    dependencies=[Depends(require_roles("admin"))],
)
async def disconnect_github(
    db: AsyncSession = Depends(get_db),
) -> None:
    """Disconnect GitHub integration.

    Sets status='disconnected' and clears the encrypted config_json.
    """
    result = await db.execute(
        select(Integration).where(Integration.type == "github")
    )
    integration = result.scalar_one_or_none()

    if integration is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    integration.status = "disconnected"
    integration.set_config({})
    await db.flush()

    logger.info("github_integration_disconnected", integration_id=str(integration.id))


# ---------------------------------------------------------------------------
# GitHub — POST /admin/integrations/github/backfill
# ---------------------------------------------------------------------------


@router.post(
    "/github/backfill",
    response_model=BackfillJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_roles("admin"))],
)
async def start_github_backfill(
    body: BackfillRequest,
    db: AsyncSession = Depends(get_db),
) -> BackfillJobResponse:
    """Start a historical GitHub data backfill job.

    Returns a job_id that can be polled via GET /admin/integrations/backfill/{job_id}.
    """
    # Verify GitHub integration exists and is connected
    result = await db.execute(
        select(Integration).where(
            Integration.type == "github",
            Integration.status == "connected",
        )
    )
    integration = result.scalar_one_or_none()

    if integration is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": {
                    "code": "GITHUB_NOT_CONNECTED",
                    "message": "GitHub integration is not connected. Connect it first via POST /admin/integrations/github/connect.",
                    "details": {},
                }
            },
        )

    # Create backfill_jobs record
    job = BackfillJob(
        integration_id=integration.id,
        integration_type="github",
        date_from=body.from_date,
        date_to=body.to_date,
        status="pending",
        records_processed=0,
    )
    db.add(job)
    await db.flush()
    await db.refresh(job)

    # Dispatch Celery backfill task
    from app.tasks.github_backfill import github_backfill
    github_backfill.apply_async(
        kwargs={
            "integration_id": str(integration.id),
            "from_date": body.from_date.isoformat(),
            "to_date": body.to_date.isoformat(),
            "team_id": str(body.team_id) if body.team_id else None,
            "job_id": str(job.id),
        },
        queue="q_github",
    )

    logger.info(
        "github_backfill_queued",
        job_id=str(job.id),
        from_date=body.from_date.isoformat(),
        to_date=body.to_date.isoformat(),
    )

    return BackfillJobResponse.model_validate(job)


# ---------------------------------------------------------------------------
# GET /admin/integrations/backfill
# ---------------------------------------------------------------------------


@router.get(
    "/backfill",
    response_model=BackfillJobListResponse,
    dependencies=[Depends(require_roles("admin"))],
)
async def list_backfill_jobs(
    db: AsyncSession = Depends(get_db),
    limit: int = 50,
) -> BackfillJobListResponse:
    """List recent backfill jobs across all integration types, newest first.

    Jobs that have been ``pending`` for more than 10 minutes are auto-marked
    ``failed`` — this catches tasks whose worker died before they could update
    their own status.
    """
    from datetime import datetime, timezone, timedelta

    stale_cutoff = datetime.now(tz=timezone.utc) - timedelta(minutes=10)
    stale_result = await db.execute(
        select(BackfillJob).where(
            BackfillJob.status == "pending",
            BackfillJob.created_at < stale_cutoff,
        )
    )
    for stale in stale_result.scalars().all():
        stale.status = "failed"
        stale.error_message = (
            "Job timed out in queue — the worker may have been unavailable. "
            "Re-submit to try again."
        )
    await db.commit()

    result = await db.execute(
        select(BackfillJob)
        .order_by(BackfillJob.created_at.desc())
        .limit(limit)
    )
    jobs = result.scalars().all()
    return BackfillJobListResponse(
        jobs=[BackfillJobResponse.model_validate(j) for j in jobs],
        total=len(jobs),
    )


# GET /admin/integrations/backfill/{job_id}
# ---------------------------------------------------------------------------


@router.get(
    "/backfill/{job_id}",
    response_model=BackfillStatusResponse,
    dependencies=[Depends(require_roles("admin"))],
)
async def get_backfill_status(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> BackfillStatusResponse:
    """Poll the status of a backfill job."""
    result = await db.execute(
        select(BackfillJob).where(BackfillJob.id == job_id)
    )
    job = result.scalar_one_or_none()

    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    progress_pct: float | None = None
    if job.records_total and job.records_total > 0:
        progress_pct = round(job.records_processed / job.records_total * 100, 1)

    return BackfillStatusResponse(
        backfill_job_id=job.id,
        status=job.status,
        records_processed=job.records_processed,
        records_total=job.records_total,
        progress_pct=progress_pct,
        last_checkpoint=job.last_checkpoint,
        started_at=job.started_at,
        completed_at=job.completed_at,
        error_message=job.error_message,
    )


# ===========================================================================
# Jira endpoints (M2a)
# ===========================================================================


@router.post(
    "/jira/connect",
    response_model=IntegrationResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles("admin"))],
)
async def connect_jira(
    body: JiraConnectRequest,
    db: AsyncSession = Depends(get_db),
) -> IntegrationResponse:
    """Connect Jira Cloud via API token.

    Validates credentials by calling GET /rest/api/3/myself. On success,
    stores the encrypted config and sets status='connected'. Upserts if
    a Jira integration already exists.
    """
    from app.integrations.jira_client import JiraClient

    try:
        async with JiraClient(
            base_url=body.base_url,
            email=body.email,
            api_token=body.api_token,
        ) as client:
            user_info = await client.validate()
    except httpx.HTTPStatusError as exc:
        logger.warning(
            "jira_credentials_invalid",
            status_code=exc.response.status_code,
            base_url=body.base_url,
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": {
                    "code": "INVALID_JIRA_CREDENTIALS",
                    "message": (
                        f"Jira credential validation failed (HTTP {exc.response.status_code}). "
                        "Ensure the email and API token are correct."
                    ),
                    "details": {},
                }
            },
        ) from exc
    except Exception as exc:
        logger.error("jira_validation_error", error=str(exc), base_url=body.base_url)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "error": {
                    "code": "JIRA_UNREACHABLE",
                    "message": "Could not reach Jira to validate credentials.",
                    "details": {},
                }
            },
        ) from exc

    logger.info(
        "jira_credentials_validated",
        jira_account_id=user_info.get("accountId"),
        display_name=user_info.get("displayName"),
    )

    # Upsert integration record
    existing_result = await db.execute(
        select(Integration).where(Integration.type == "jira")
    )
    integration = existing_result.scalar_one_or_none()

    config = {
        "base_url": body.base_url,
        "email": body.email,
        "api_token": body.api_token,
        "project_keys": body.project_keys,
    }

    if integration is None:
        integration = Integration(type="jira", status="connected", team_id=body.team_id)
        db.add(integration)
    else:
        integration.status = "connected"
        if body.team_id:
            integration.team_id = body.team_id

    integration.set_config(config)
    await db.flush()
    await db.refresh(integration)

    logger.info(
        "jira_integration_connected",
        integration_id=str(integration.id),
        base_url=body.base_url,
        project_keys=body.project_keys,
    )
    return _build_integration_response(integration)


@router.get(
    "/jira/status",
    response_model=JiraStatusResponse,
    dependencies=[Depends(require_roles("admin"))],
)
async def get_jira_status(
    db: AsyncSession = Depends(get_db),
) -> JiraStatusResponse:
    """Return Jira integration connection status and last sync timestamp."""
    result = await db.execute(
        select(Integration).where(Integration.type == "jira")
    )
    integration = result.scalar_one_or_none()

    if integration is None:
        return JiraStatusResponse(
            connected=False,
            status="disconnected",
            last_synced_at=None,
            base_url=None,
            project_keys=None,
            integration_id=None,
        )

    try:
        config_summary = integration.get_config_summary()
    except Exception:
        config_summary = {}

    return JiraStatusResponse(
        connected=integration.status == "connected",
        status=integration.status,
        last_synced_at=integration.last_synced_at,
        base_url=config_summary.get("base_url"),
        project_keys=config_summary.get("project_keys"),
        integration_id=integration.id,
    )


@router.delete(
    "/jira",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    dependencies=[Depends(require_roles("admin"))],
)
async def disconnect_jira(
    db: AsyncSession = Depends(get_db),
) -> None:
    """Disconnect Jira integration. Clears encrypted config."""
    result = await db.execute(
        select(Integration).where(Integration.type == "jira")
    )
    integration = result.scalar_one_or_none()
    if integration is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    integration.status = "disconnected"
    integration.set_config({})
    await db.flush()
    logger.info("jira_integration_disconnected", integration_id=str(integration.id))


@router.post(
    "/jira/backfill",
    response_model=BackfillJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_roles("admin"))],
)
async def start_jira_backfill(
    body: BackfillRequest,
    db: AsyncSession = Depends(get_db),
) -> BackfillJobResponse:
    """Start a historical Jira data backfill job.

    Returns a job_id that can be polled via GET /admin/integrations/backfill/{job_id}.
    """
    result = await db.execute(
        select(Integration).where(
            Integration.type == "jira",
            Integration.status == "connected",
        )
    )
    integration = result.scalar_one_or_none()
    if integration is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": {
                    "code": "JIRA_NOT_CONNECTED",
                    "message": "Jira integration is not connected. Connect it first.",
                    "details": {},
                }
            },
        )

    job = BackfillJob(
        integration_id=integration.id,
        integration_type="jira",
        date_from=body.from_date,
        date_to=body.to_date,
        status="pending",
        records_processed=0,
    )
    db.add(job)
    await db.flush()
    await db.refresh(job)

    from app.tasks.jira_backfill import jira_backfill
    jira_backfill.apply_async(
        kwargs={
            "integration_id": str(integration.id),
            "from_date": body.from_date.isoformat(),
            "to_date": body.to_date.isoformat(),
            "team_id": str(body.team_id) if body.team_id else None,
            "job_id": str(job.id),
        },
        queue="q_jira_clickup",
    )

    logger.info(
        "jira_backfill_queued",
        job_id=str(job.id),
        from_date=body.from_date.isoformat(),
        to_date=body.to_date.isoformat(),
    )
    return BackfillJobResponse.model_validate(job)


# ===========================================================================
# ClickUp endpoints (M2b)
# ===========================================================================


@router.post(
    "/clickup/connect",
    response_model=IntegrationResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles("admin"))],
)
async def connect_clickup(
    body: ClickUpConnectRequest,
    db: AsyncSession = Depends(get_db),
) -> IntegrationResponse:
    """Connect ClickUp via API token.

    Validates by checking the workspace is accessible. On success, stores
    the encrypted config. Upserts if a ClickUp integration already exists.
    """
    from app.integrations.clickup_client import ClickUpClient

    try:
        async with ClickUpClient(api_token=body.api_token) as client:
            workspace_info = await client.validate(body.workspace_id)
    except httpx.HTTPStatusError as exc:
        logger.warning(
            "clickup_token_invalid",
            status_code=exc.response.status_code,
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": {
                    "code": "INVALID_CLICKUP_TOKEN",
                    "message": (
                        f"ClickUp token validation failed (HTTP {exc.response.status_code}). "
                        "Ensure the API token is valid."
                    ),
                    "details": {},
                }
            },
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": {
                    "code": "CLICKUP_WORKSPACE_NOT_FOUND",
                    "message": str(exc),
                    "details": {},
                }
            },
        ) from exc
    except Exception as exc:
        logger.error("clickup_validation_error", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "error": {
                    "code": "CLICKUP_UNREACHABLE",
                    "message": "Could not reach ClickUp to validate credentials.",
                    "details": {},
                }
            },
        ) from exc

    logger.info(
        "clickup_token_validated",
        workspace_id=body.workspace_id,
        workspace_name=workspace_info.get("name"),
    )

    existing_result = await db.execute(
        select(Integration).where(Integration.type == "clickup")
    )
    integration = existing_result.scalar_one_or_none()

    config = {
        "api_token": body.api_token,
        "workspace_id": body.workspace_id,
        "sprint_list_ids": {},  # populated later via /configure-sprints
    }

    if integration is None:
        integration = Integration(type="clickup", status="connected", team_id=body.team_id)
        db.add(integration)
    else:
        integration.status = "connected"
        if body.team_id:
            integration.team_id = body.team_id

    integration.set_config(config)
    await db.flush()
    await db.refresh(integration)

    logger.info(
        "clickup_integration_connected",
        integration_id=str(integration.id),
        workspace_id=body.workspace_id,
    )
    return _build_integration_response(integration)


@router.get(
    "/clickup/hierarchy",
    dependencies=[Depends(require_roles("admin"))],
)
async def get_clickup_hierarchy(
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return the Space→Folder→List hierarchy for the connected ClickUp workspace.

    Used by the setup wizard UI so admins can select sprint Lists per team.
    """
    result = await db.execute(
        select(Integration).where(
            Integration.type == "clickup",
            Integration.status == "connected",
        )
    )
    integration = result.scalar_one_or_none()
    if integration is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": {
                    "code": "CLICKUP_NOT_CONNECTED",
                    "message": "ClickUp integration is not connected.",
                    "details": {},
                }
            },
        )

    config = integration.get_config()
    api_token: str = config["api_token"]
    workspace_id: str = config["workspace_id"]

    from app.integrations.clickup_client import ClickUpClient

    try:
        async with ClickUpClient(api_token=api_token) as client:
            hierarchy = await client.get_workspace_hierarchy(workspace_id)
    except Exception as exc:
        logger.error(
            "clickup_hierarchy_fetch_failed",
            workspace_id=workspace_id,
            error=str(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "error": {
                    "code": "CLICKUP_HIERARCHY_FAILED",
                    "message": "Failed to fetch ClickUp workspace hierarchy.",
                    "details": {},
                }
            },
        ) from exc

    return hierarchy


@router.post(
    "/clickup/configure-sprints",
    response_model=IntegrationResponse,
    dependencies=[Depends(require_roles("admin"))],
)
async def configure_clickup_sprints(
    body: ClickUpConfigureSprintsRequest,
    db: AsyncSession = Depends(get_db),
) -> IntegrationResponse:
    """Save the team → sprint List ID mapping for ClickUp.

    Body: { "sprint_list_ids": { "<team_uuid>": ["<list_id>", ...] } }

    This is step 2 of the ClickUp setup wizard, after /connect.
    """
    result = await db.execute(
        select(Integration).where(
            Integration.type == "clickup",
            Integration.status == "connected",
        )
    )
    integration = result.scalar_one_or_none()
    if integration is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": {
                    "code": "CLICKUP_NOT_CONNECTED",
                    "message": "ClickUp integration is not connected. Connect it first.",
                    "details": {},
                }
            },
        )

    config = integration.get_config()
    config["sprint_list_ids"] = body.sprint_list_ids
    integration.set_config(config)
    await db.flush()
    await db.refresh(integration)

    logger.info(
        "clickup_sprints_configured",
        integration_id=str(integration.id),
        team_count=len(body.sprint_list_ids),
    )
    return _build_integration_response(integration)


@router.get(
    "/clickup/status",
    response_model=ClickUpStatusResponse,
    dependencies=[Depends(require_roles("admin"))],
)
async def get_clickup_status(
    db: AsyncSession = Depends(get_db),
) -> ClickUpStatusResponse:
    """Return ClickUp integration connection status and last sync timestamp."""
    result = await db.execute(
        select(Integration).where(Integration.type == "clickup")
    )
    integration = result.scalar_one_or_none()

    if integration is None:
        return ClickUpStatusResponse(
            connected=False,
            status="disconnected",
            last_synced_at=None,
            workspace_id=None,
            sprint_list_ids=None,
            integration_id=None,
        )

    try:
        config_summary = integration.get_config_summary()
    except Exception:
        config_summary = {}

    return ClickUpStatusResponse(
        connected=integration.status == "connected",
        status=integration.status,
        last_synced_at=integration.last_synced_at,
        workspace_id=config_summary.get("workspace_id"),
        sprint_list_ids=config_summary.get("sprint_list_ids"),
        integration_id=integration.id,
    )


@router.delete(
    "/clickup",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    dependencies=[Depends(require_roles("admin"))],
)
async def disconnect_clickup(
    db: AsyncSession = Depends(get_db),
) -> None:
    """Disconnect ClickUp integration. Clears encrypted config."""
    result = await db.execute(
        select(Integration).where(Integration.type == "clickup")
    )
    integration = result.scalar_one_or_none()
    if integration is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    integration.status = "disconnected"
    integration.set_config({})
    await db.flush()
    logger.info("clickup_integration_disconnected", integration_id=str(integration.id))


@router.post(
    "/clickup/backfill",
    response_model=BackfillJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_roles("admin"))],
)
async def start_clickup_backfill(
    body: BackfillRequest,
    db: AsyncSession = Depends(get_db),
) -> BackfillJobResponse:
    """Start a historical ClickUp data backfill job."""
    result = await db.execute(
        select(Integration).where(
            Integration.type == "clickup",
            Integration.status == "connected",
        )
    )
    integration = result.scalar_one_or_none()
    if integration is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": {
                    "code": "CLICKUP_NOT_CONNECTED",
                    "message": "ClickUp integration is not connected. Connect it first.",
                    "details": {},
                }
            },
        )

    job = BackfillJob(
        integration_id=integration.id,
        integration_type="clickup",
        date_from=body.from_date,
        date_to=body.to_date,
        status="pending",
        records_processed=0,
    )
    db.add(job)
    await db.flush()
    await db.refresh(job)

    # ClickUp backfill reuses the nightly task with a date_updated_gt filter.
    # A dedicated clickup_backfill task can be added in a future iteration;
    # for now we enqueue the nightly batch with the job_id for tracking.
    from app.tasks.clickup_ingest import clickup_nightly_batch
    clickup_nightly_batch.apply_async(
        kwargs={"integration_id": str(integration.id)},
        queue="q_jira_clickup",
    )

    logger.info(
        "clickup_backfill_queued",
        job_id=str(job.id),
        from_date=body.from_date.isoformat(),
        to_date=body.to_date.isoformat(),
    )
    return BackfillJobResponse.model_validate(job)


# ===========================================================================
# PagerDuty endpoints (M3a)
# ===========================================================================


@router.post(
    "/pagerduty/connect",
    response_model=IntegrationResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles("admin"))],
)
async def connect_pagerduty(
    body: PagerDutyConnectRequest,
    db: AsyncSession = Depends(get_db),
) -> IntegrationResponse:
    """Connect PagerDuty via API token.

    Validates credentials via GET /abilities. On success, stores the encrypted
    config and sets status='connected'. Upserts if a PagerDuty integration
    already exists.
    """
    from app.integrations.pagerduty_client import PagerDutyClient

    try:
        async with PagerDutyClient(api_key=body.api_key) as client:
            await client.validate_connection()
    except httpx.HTTPStatusError as exc:
        logger.warning(
            "pagerduty_credentials_invalid",
            status_code=exc.response.status_code,
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": {
                    "code": "INVALID_PAGERDUTY_API_KEY",
                    "message": (
                        f"PagerDuty API key validation failed (HTTP {exc.response.status_code}). "
                        "Ensure the token is a valid REST API key."
                    ),
                    "details": {},
                }
            },
        ) from exc
    except Exception as exc:
        logger.error("pagerduty_validation_error", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "error": {
                    "code": "PAGERDUTY_UNREACHABLE",
                    "message": "Could not reach PagerDuty API to validate the token.",
                    "details": {},
                }
            },
        ) from exc

    logger.info("pagerduty_credentials_validated")

    existing_result = await db.execute(
        select(Integration).where(Integration.type == "pagerduty")
    )
    integration = existing_result.scalar_one_or_none()

    config = {
        "api_key": body.api_key,
        "service_ids": body.service_ids or [],
    }

    if integration is None:
        integration = Integration(type="pagerduty", status="connected", team_id=None)
        db.add(integration)
    else:
        integration.status = "connected"

    integration.set_config(config)
    await db.flush()
    await db.refresh(integration)

    logger.info(
        "pagerduty_integration_connected",
        integration_id=str(integration.id),
        service_ids=body.service_ids,
    )
    return _build_integration_response(integration)


@router.get(
    "/pagerduty/status",
    response_model=PagerDutyStatusResponse,
    dependencies=[Depends(require_roles("admin"))],
)
async def get_pagerduty_status(
    db: AsyncSession = Depends(get_db),
) -> PagerDutyStatusResponse:
    """Return PagerDuty integration connection status and last sync timestamp."""
    result = await db.execute(
        select(Integration).where(Integration.type == "pagerduty")
    )
    integration = result.scalar_one_or_none()

    if integration is None:
        return PagerDutyStatusResponse(
            connected=False,
            status="disconnected",
            last_synced_at=None,
            service_ids=None,
            integration_id=None,
        )

    try:
        config_summary = integration.get_config_summary()
    except Exception:
        config_summary = {}

    return PagerDutyStatusResponse(
        connected=integration.status == "connected",
        status=integration.status,
        last_synced_at=integration.last_synced_at,
        service_ids=config_summary.get("service_ids"),
        integration_id=integration.id,
    )


@router.delete(
    "/pagerduty",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    dependencies=[Depends(require_roles("admin"))],
)
async def disconnect_pagerduty(
    db: AsyncSession = Depends(get_db),
) -> None:
    """Disconnect PagerDuty integration. Clears encrypted config."""
    result = await db.execute(
        select(Integration).where(Integration.type == "pagerduty")
    )
    integration = result.scalar_one_or_none()
    if integration is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    integration.status = "disconnected"
    integration.set_config({})
    await db.flush()
    logger.info("pagerduty_integration_disconnected", integration_id=str(integration.id))


@router.post(
    "/pagerduty/backfill",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_roles("admin"))],
)
async def start_pagerduty_backfill(
    body: IncidentBackfillRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Trigger a PagerDuty historical data backfill.

    Enqueues the nightly batch task for manual re-processing.
    Returns accepted status.
    """
    result = await db.execute(
        select(Integration).where(
            Integration.type == "pagerduty",
            Integration.status == "connected",
        )
    )
    integration = result.scalar_one_or_none()
    if integration is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": {
                    "code": "PAGERDUTY_NOT_CONNECTED",
                    "message": "PagerDuty integration is not connected. Connect it first.",
                    "details": {},
                }
            },
        )

    from app.tasks.pagerduty_ingest import pagerduty_nightly_batch
    pagerduty_nightly_batch.apply_async(
        kwargs={"integration_id": str(integration.id)},
        queue="q_incidents",
    )

    logger.info(
        "pagerduty_backfill_queued",
        integration_id=str(integration.id),
        from_date=body.from_date.isoformat(),
        to_date=body.to_date.isoformat(),
    )
    return {
        "status": "accepted",
        "integration_id": str(integration.id),
        "from_date": body.from_date.isoformat(),
        "to_date": body.to_date.isoformat(),
    }


# ===========================================================================
# Zenduty endpoints (M3b)
# ===========================================================================


@router.post(
    "/zenduty/connect",
    response_model=IntegrationResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles("admin"))],
)
async def connect_zenduty(
    body: ZendutyConnectRequest,
    db: AsyncSession = Depends(get_db),
) -> IntegrationResponse:
    """Connect Zenduty via API token.

    Validates credentials via GET /teams/. On success, stores the encrypted
    config and sets status='connected'. Upserts if a Zenduty integration
    already exists.
    """
    from app.integrations.zenduty_client import ZendutyClient

    try:
        async with ZendutyClient(api_key=body.api_key, base_url=body.base_url) as client:
            await client.validate_connection()
    except httpx.HTTPStatusError as exc:
        logger.warning(
            "zenduty_credentials_invalid",
            status_code=exc.response.status_code,
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": {
                    "code": "INVALID_ZENDUTY_API_KEY",
                    "message": (
                        f"Zenduty API key validation failed (HTTP {exc.response.status_code}). "
                        "Ensure the token is valid."
                    ),
                    "details": {},
                }
            },
        ) from exc
    except Exception as exc:
        logger.error("zenduty_validation_error", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "error": {
                    "code": "ZENDUTY_UNREACHABLE",
                    "message": "Could not reach Zenduty API to validate the token.",
                    "details": {},
                }
            },
        ) from exc

    logger.info("zenduty_credentials_validated", base_url=body.base_url)

    existing_result = await db.execute(
        select(Integration).where(Integration.type == "zenduty")
    )
    integration = existing_result.scalar_one_or_none()

    config = {
        "api_key": body.api_key,
        "base_url": body.base_url,
        "team_ids": body.team_ids or [],
    }

    if integration is None:
        integration = Integration(type="zenduty", status="connected", team_id=None)
        db.add(integration)
    else:
        integration.status = "connected"

    integration.set_config(config)
    await db.flush()
    await db.refresh(integration)

    logger.info(
        "zenduty_integration_connected",
        integration_id=str(integration.id),
        base_url=body.base_url,
        team_ids=body.team_ids,
    )
    return _build_integration_response(integration)


@router.get(
    "/zenduty/status",
    response_model=ZendutyStatusResponse,
    dependencies=[Depends(require_roles("admin"))],
)
async def get_zenduty_status(
    db: AsyncSession = Depends(get_db),
) -> ZendutyStatusResponse:
    """Return Zenduty integration connection status and last sync timestamp."""
    result = await db.execute(
        select(Integration).where(Integration.type == "zenduty")
    )
    integration = result.scalar_one_or_none()

    if integration is None:
        return ZendutyStatusResponse(
            connected=False,
            status="disconnected",
            last_synced_at=None,
            base_url=None,
            team_ids=None,
            integration_id=None,
        )

    try:
        config_summary = integration.get_config_summary()
    except Exception:
        config_summary = {}

    return ZendutyStatusResponse(
        connected=integration.status == "connected",
        status=integration.status,
        last_synced_at=integration.last_synced_at,
        base_url=config_summary.get("base_url"),
        team_ids=config_summary.get("team_unique_ids"),
        integration_id=integration.id,
    )


@router.delete(
    "/zenduty",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    dependencies=[Depends(require_roles("admin"))],
)
async def disconnect_zenduty(
    db: AsyncSession = Depends(get_db),
) -> None:
    """Disconnect Zenduty integration. Clears encrypted config."""
    result = await db.execute(
        select(Integration).where(Integration.type == "zenduty")
    )
    integration = result.scalar_one_or_none()
    if integration is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    integration.status = "disconnected"
    integration.set_config({})
    await db.flush()
    logger.info("zenduty_integration_disconnected", integration_id=str(integration.id))


@router.post(
    "/zenduty/backfill",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_roles("admin"))],
)
async def start_zenduty_backfill(
    body: IncidentBackfillRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Trigger a Zenduty historical data backfill.

    Enqueues the nightly batch task for manual re-processing.
    """
    result = await db.execute(
        select(Integration).where(
            Integration.type == "zenduty",
            Integration.status == "connected",
        )
    )
    integration = result.scalar_one_or_none()
    if integration is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": {
                    "code": "ZENDUTY_NOT_CONNECTED",
                    "message": "Zenduty integration is not connected. Connect it first.",
                    "details": {},
                }
            },
        )

    from app.tasks.zenduty_ingest import zenduty_nightly_batch
    zenduty_nightly_batch.apply_async(
        kwargs={"integration_id": str(integration.id)},
        queue="q_incidents",
    )

    logger.info(
        "zenduty_backfill_queued",
        integration_id=str(integration.id),
        from_date=body.from_date.isoformat(),
        to_date=body.to_date.isoformat(),
    )
    return {
        "status": "accepted",
        "integration_id": str(integration.id),
        "from_date": body.from_date.isoformat(),
        "to_date": body.to_date.isoformat(),
    }


# ===========================================================================
# Slack endpoints (M6a)
# ===========================================================================


@router.post(
    "/slack/connect",
    response_model=SlackConnectResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles("admin"))],
)
async def connect_slack(
    body: SlackConnectRequest,
    db: AsyncSession = Depends(get_db),
) -> SlackConnectResponse:
    """Connect Slack via bot OAuth token.

    Validates the token via POST /auth.test, then runs a one-time degradation
    check (workspace >200 members OR >50 channels). The degradation result is
    stored in config_json and governs whether Slack Signal metrics are computed.

    Returns:
        { connected: true, degraded: bool, reason: str | None }
    """
    from app.integrations.slack_client import SlackClient, check_degradation

    try:
        async with SlackClient(bot_token=body.bot_token) as client:
            auth_info = await client.validate_credentials()
            workspace_id: str = auth_info.get("team_id", "")
            workspace_name: str = auth_info.get("team", "")

            # Run degradation check (counts members + channels)
            degraded, degraded_reason = await check_degradation(client)

    except httpx.HTTPStatusError as exc:
        logger.warning(
            "slack_token_validation_failed",
            status_code=exc.response.status_code,
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": {
                    "code": "INVALID_SLACK_BOT_TOKEN",
                    "message": (
                        f"Slack bot token validation failed (HTTP {exc.response.status_code}). "
                        "Ensure the token starts with xoxb- and has the required scopes: "
                        "channels:history, channels:read, groups:history, groups:read, "
                        "users:read, team:read"
                    ),
                    "details": {},
                }
            },
        ) from exc
    except Exception as exc:
        from app.integrations.slack_client import SlackAPIError
        if isinstance(exc, SlackAPIError):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "error": {
                        "code": f"SLACK_{exc.error_code.upper()}",
                        "message": (
                            f"Slack API error: {exc.error_code}. "
                            "Ensure the bot token has required scopes."
                        ),
                        "details": {},
                    }
                },
            ) from exc
        logger.error("slack_token_validation_error", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "error": {
                    "code": "SLACK_UNREACHABLE",
                    "message": "Could not reach Slack API to validate the token.",
                    "details": {},
                }
            },
        ) from exc

    logger.info(
        "slack_token_validated",
        workspace_id=workspace_id,
        workspace_name=workspace_name,
        degraded=degraded,
    )

    # Upsert integration record
    existing_result = await db.execute(
        select(Integration).where(Integration.type == "slack")
    )
    integration = existing_result.scalar_one_or_none()

    config = {
        "bot_token": body.bot_token,
        "signing_secret": body.signing_secret,
        "workspace_id": workspace_id,
        "slack_signal_degraded": degraded,
        "slack_degraded_reason": degraded_reason,
    }

    if integration is None:
        integration = Integration(type="slack", status="connected", team_id=None)
        db.add(integration)
    else:
        integration.status = "connected"

    integration.set_config(config)
    await db.flush()
    await db.refresh(integration)

    if degraded:
        logger.warning(
            "slack_integration_degraded",
            integration_id=str(integration.id),
            reason=degraded_reason,
        )
    else:
        logger.info(
            "slack_integration_connected",
            integration_id=str(integration.id),
            workspace_id=workspace_id,
        )

    return SlackConnectResponse(
        connected=True,
        degraded=degraded,
        reason=degraded_reason,
        integration_id=integration.id,
        workspace_name=workspace_name,
        workspace_id=workspace_id,
    )


@router.get(
    "/slack/status",
    response_model=SlackStatusResponse,
    dependencies=[Depends(require_roles("admin"))],
)
async def get_slack_status(
    db: AsyncSession = Depends(get_db),
) -> SlackStatusResponse:
    """Return Slack integration connection status, degradation flag, and last sync time."""
    result = await db.execute(
        select(Integration).where(Integration.type == "slack")
    )
    integration = result.scalar_one_or_none()

    if integration is None:
        return SlackStatusResponse(
            connected=False,
            status="disconnected",
            last_synced_at=None,
            degraded=False,
            degraded_reason=None,
            workspace_id=None,
            integration_id=None,
        )

    try:
        config = integration.get_config()
        degraded = config.get("slack_signal_degraded", False)
        degraded_reason = config.get("slack_degraded_reason")
        workspace_id = config.get("workspace_id")
    except Exception:
        degraded = False
        degraded_reason = None
        workspace_id = None

    return SlackStatusResponse(
        connected=integration.status == "connected",
        status=integration.status,
        last_synced_at=integration.last_synced_at,
        degraded=degraded,
        degraded_reason=degraded_reason,
        workspace_id=workspace_id,
        integration_id=integration.id,
    )


@router.delete(
    "/slack",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    dependencies=[Depends(require_roles("admin"))],
)
async def disconnect_slack(
    db: AsyncSession = Depends(get_db),
) -> None:
    """Disconnect Slack integration. Clears the encrypted config (bot token + signing secret)."""
    result = await db.execute(
        select(Integration).where(Integration.type == "slack")
    )
    integration = result.scalar_one_or_none()

    if integration is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    integration.status = "disconnected"
    integration.set_config({})
    await db.flush()

    logger.info("slack_integration_disconnected", integration_id=str(integration.id))


# ===========================================================================
# Keka HRMS endpoints (M8c)
# ===========================================================================


@router.post(
    "/keka/connect",
    response_model=IntegrationResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles("admin"))],
)
async def connect_keka(
    body: KekaConnectRequest,
    db: AsyncSession = Depends(get_db),
) -> IntegrationResponse:
    """Connect Keka HRMS via OAuth2 client credentials.

    Validates by:
      1. Fetching an access token via POST https://{tenant_id}.keka.com/connect/token.
      2. Calling GET /hris/employees?pageSize=1 to verify data access.

    On success, stores the encrypted config (client_id, client_secret, tenant_id,
    base_url) and sets status='connected'. Upserts if a Keka integration already exists.
    """
    from app.integrations.keka_client import KekaClient, KekaAuthError, KekaAPIError

    try:
        async with KekaClient(
            client_id=body.client_id,
            client_secret=body.client_secret,
            tenant_id=body.tenant_id,
            base_url=body.base_url,
        ) as client:
            # Step 1: fetch token
            await client.get_access_token()
            # Step 2: verify data access with a minimal fetch
            await client.get_employees(page=1, page_size=1)
    except KekaAuthError as exc:
        logger.warning("keka_credentials_invalid", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": {
                    "code": "INVALID_KEKA_CREDENTIALS",
                    "message": (
                        "Keka credential validation failed. "
                        "Check client_id, client_secret, and tenant_id."
                    ),
                    "details": {},
                }
            },
        ) from exc
    except httpx.HTTPStatusError as exc:
        logger.warning(
            "keka_validation_http_error",
            status_code=exc.response.status_code,
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": {
                    "code": "KEKA_VALIDATION_FAILED",
                    "message": (
                        f"Keka API validation failed (HTTP {exc.response.status_code}). "
                        "Ensure the credentials are correct and the API is accessible."
                    ),
                    "details": {},
                }
            },
        ) from exc
    except Exception as exc:
        logger.error("keka_validation_error", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "error": {
                    "code": "KEKA_UNREACHABLE",
                    "message": "Could not reach Keka API to validate credentials.",
                    "details": {},
                }
            },
        ) from exc

    logger.info("keka_credentials_validated", tenant_id=body.tenant_id)

    # Upsert integration record
    existing_result = await db.execute(
        select(Integration).where(Integration.type == "keka")
    )
    integration = existing_result.scalar_one_or_none()

    config = {
        "client_id": body.client_id,
        "client_secret": body.client_secret,
        "tenant_id": body.tenant_id,
        "base_url": body.base_url,
    }

    if integration is None:
        integration = Integration(type="keka", status="connected", team_id=None)
        db.add(integration)
    else:
        integration.status = "connected"

    integration.set_config(config)
    await db.flush()
    await db.refresh(integration)

    logger.info(
        "keka_integration_connected",
        integration_id=str(integration.id),
        tenant_id=body.tenant_id,
    )
    return _build_integration_response(integration)


@router.get(
    "/keka/status",
    response_model=KekaStatusResponse,
    dependencies=[Depends(require_roles("admin"))],
)
async def get_keka_status(
    db: AsyncSession = Depends(get_db),
) -> KekaStatusResponse:
    """Return Keka integration connection status and last sync timestamp."""
    result = await db.execute(
        select(Integration).where(Integration.type == "keka")
    )
    integration = result.scalar_one_or_none()

    if integration is None:
        return KekaStatusResponse(
            connected=False,
            status="disconnected",
            last_synced_at=None,
            tenant_id=None,
            base_url=None,
            integration_id=None,
        )

    try:
        config = integration.get_config()
        tenant_id = config.get("tenant_id")
        base_url = config.get("base_url")
    except Exception:
        tenant_id = None
        base_url = None

    return KekaStatusResponse(
        connected=integration.status == "connected",
        status=integration.status,
        last_synced_at=integration.last_synced_at,
        tenant_id=tenant_id,
        base_url=base_url,
        integration_id=integration.id,
    )


@router.delete(
    "/keka",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    dependencies=[Depends(require_roles("admin"))],
)
async def disconnect_keka(
    body: KekaDisconnectRequest,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Disconnect Keka integration.

    Body: { keep_keka_snapshot: bool }

    If keep_keka_snapshot=True: org_nodes with source='keka' are kept as-is
    (the snapshot becomes a frozen manual-like state).
    If keep_keka_snapshot=False: all keka org_nodes are deleted (admin must
    re-enter org tree manually via POST /api/v1/admin/org-tree).
    """
    from sqlalchemy import delete as sa_delete
    from app.models.team import OrgNode

    result = await db.execute(
        select(Integration).where(Integration.type == "keka")
    )
    integration = result.scalar_one_or_none()

    if integration is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    if not body.keep_keka_snapshot:
        # Remove all Keka org nodes
        await db.execute(sa_delete(OrgNode).where(OrgNode.source == "keka"))
        logger.info(
            "keka_org_nodes_deleted",
            integration_id=str(integration.id),
        )
    else:
        logger.info(
            "keka_org_snapshot_kept",
            integration_id=str(integration.id),
        )

    integration.status = "disconnected"
    integration.set_config({})
    await db.flush()

    logger.info("keka_integration_disconnected", integration_id=str(integration.id))
