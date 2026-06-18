"""Keka HRMS nightly sync task.

Fetches all employees from Keka and atomically replaces org_nodes.
Keka is authoritative: replaces both keka and manual org_nodes.
Also runs identity resolution for the keka tool.

Spec reference: §5.7, §6.7, M8c
Task queue: q_keka (concurrency=1)
Schedule: 02:15 UTC (countdown=4500 from 01:00 UTC orchestrator)
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import structlog
from celery.utils.log import get_task_logger
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.celery_app import celery_app

logger = get_task_logger(__name__)
struct_logger = structlog.get_logger(__name__)

# Maximum consecutive failures before setting integration status='error'
MAX_CONSECUTIVE_FAILURES = 3


# ---------------------------------------------------------------------------
# Helper: run async code from sync Celery task
# ---------------------------------------------------------------------------


def _run_async(coro: Any) -> Any:
    """Execute an async coroutine from a synchronous Celery task context."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# Main nightly Keka sync task
# ---------------------------------------------------------------------------


@celery_app.task(
    bind=True,
    name="app.tasks.keka_sync.keka_org_sync",
    queue="q_keka",
    max_retries=3,
    acks_late=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=900,
    retry_jitter=True,
)
def keka_org_sync(self, integration_id: str) -> dict:
    """Nightly Keka org tree sync.

    1. Fetches all employees from Keka API (paginated).
    2. Resolves each employee's work_email → canonical user_id.
    3. Atomically replaces ALL org_nodes (both keka and manual source) with
       new keka-sourced rows in a single transaction.
    4. Runs identity resolution for keka tool.
    5. Updates integrations.last_synced_at.

    Args:
        integration_id: UUID string of the Keka Integration record.
    """
    return _run_async(_keka_org_sync_async(integration_id))


async def _keka_org_sync_async(integration_id: str) -> dict:
    """Async implementation of keka_org_sync."""
    from app.core.database import get_session_factory
    from app.integrations.keka_client import KekaClient
    from app.models.integration import Integration
    from app.models.team import OrgNode
    from app.models.user import User
    from app.services.identity_resolver import IdentityResolver

    session_factory = get_session_factory()

    # --- Load integration config ---
    async with session_factory() as session:
        result = await session.execute(
            select(Integration).where(
                Integration.id == UUID(integration_id),
                Integration.type == "keka",
            )
        )
        integration = result.scalar_one_or_none()
        if integration is None:
            struct_logger.error(
                "keka_sync_integration_not_found",
                integration_id=integration_id,
            )
            return {"status": "error", "reason": "integration_not_found"}

        if integration.status != "connected":
            struct_logger.warning(
                "keka_sync_integration_not_connected",
                integration_id=integration_id,
                status=integration.status,
            )
            return {"status": "skipped", "reason": "integration_not_connected"}

        config = integration.get_config()

    client_id: str = config["client_id"]
    client_secret: str = config["client_secret"]
    tenant_id: str = config["tenant_id"]
    base_url: str = config.get("base_url", "https://api.keka.com/v1")

    struct_logger.info(
        "keka_sync_started",
        integration_id=integration_id,
        tenant_id=tenant_id,
    )

    # --- Fetch all employees ---
    employees: list[dict] = []
    try:
        async with KekaClient(
            client_id=client_id,
            client_secret=client_secret,
            tenant_id=tenant_id,
            base_url=base_url,
        ) as keka:
            async for emp in keka.get_all_employees():
                employees.append(emp)
    except Exception as exc:
        struct_logger.error(
            "keka_sync_fetch_failed",
            integration_id=integration_id,
            error=str(exc),
            exc_info=True,
        )
        # Check consecutive failure count and potentially set status='error'
        await _check_consecutive_failures(integration_id, session_factory)
        raise

    struct_logger.info(
        "keka_employees_fetched",
        integration_id=integration_id,
        count=len(employees),
    )

    # --- Build user lookup by work email ---
    async with session_factory() as session:
        users_result = await session.execute(
            select(User).where(User.is_active == True)
        )
        users_by_email: dict[str, UUID] = {
            u.email.lower(): u.id
            for u in users_result.scalars().all()
        }

    # --- Map Keka employees → (employee_user_id, manager_user_id) ---
    # Also prepare identity mapping upserts for the keka tool
    org_node_rows: list[dict] = []
    keka_identity_rows: list[tuple[str, str | None]] = []  # (keka_employee_id, work_email)

    for emp in employees:
        work_email: str | None = emp.get("workEmail")
        keka_employee_id: str = emp.get("id", "")
        first_name: str = emp.get("firstName", "")
        last_name: str = emp.get("lastName", "")
        display_name = f"{first_name} {last_name}".strip() or keka_employee_id

        keka_identity_rows.append((keka_employee_id, work_email))

        if not work_email:
            struct_logger.debug(
                "keka_employee_no_email",
                keka_id=keka_employee_id,
                display_name=display_name,
            )
            continue

        employee_user_id = users_by_email.get(work_email.lower())
        if employee_user_id is None:
            struct_logger.debug(
                "keka_employee_user_not_found",
                keka_id=keka_employee_id,
                work_email=work_email,
            )
            continue

        # Resolve manager
        manager_user_id: UUID | None = None
        reporting_manager: dict | None = emp.get("reportingManager")
        if reporting_manager:
            manager_email: str | None = reporting_manager.get("workEmail")
            if manager_email:
                manager_user_id = users_by_email.get(manager_email.lower())

        org_node_rows.append(
            {
                "employee_user_id": employee_user_id,
                "manager_user_id": manager_user_id,
                "source": "keka",
            }
        )

    struct_logger.info(
        "keka_org_nodes_prepared",
        integration_id=integration_id,
        org_node_count=len(org_node_rows),
        total_employees=len(employees),
    )

    # --- Atomic org tree replacement ---
    async with session_factory() as session:
        async with session.begin():
            # Step 1: DELETE all org_nodes (keka is authoritative — replaces manual too)
            await session.execute(delete(OrgNode))

            # Step 2: INSERT new keka org nodes
            for row in org_node_rows:
                org_node = OrgNode(
                    employee_user_id=row["employee_user_id"],
                    manager_user_id=row["manager_user_id"],
                    source="keka",
                )
                session.add(org_node)

        # Transaction committed by context manager exit

    struct_logger.info(
        "keka_org_tree_replaced",
        integration_id=integration_id,
        rows_inserted=len(org_node_rows),
    )

    # --- Identity resolution for keka tool ---
    # Upsert identity_mappings for each keka employee
    resolver = IdentityResolver()
    async with session_factory() as session:
        for keka_id, work_email in keka_identity_rows:
            if not work_email:
                continue
            try:
                await resolver.upsert_tool_user(
                    tool="keka",
                    tool_user_id=keka_id,
                    tool_email=work_email,
                    tool_display_name=None,
                    db=session,
                )
            except Exception as exc:
                struct_logger.warning(
                    "keka_identity_upsert_failed",
                    keka_id=keka_id,
                    work_email=work_email,
                    error=str(exc),
                )
        await session.commit()

    struct_logger.info(
        "keka_identity_mappings_updated",
        integration_id=integration_id,
        processed=len(keka_identity_rows),
    )

    # --- Update last_synced_at ---
    async with session_factory() as session:
        result = await session.execute(
            select(Integration).where(Integration.id == UUID(integration_id))
        )
        integration_record = result.scalar_one_or_none()
        if integration_record:
            integration_record.last_synced_at = datetime.now(tz=timezone.utc)
            integration_record.status = "connected"  # Clear any previous error state
        await session.commit()

    struct_logger.info(
        "keka_sync_complete",
        integration_id=integration_id,
        employees_fetched=len(employees),
        org_nodes_inserted=len(org_node_rows),
    )

    return {
        "status": "completed",
        "integration_id": integration_id,
        "employees_fetched": len(employees),
        "org_nodes_inserted": len(org_node_rows),
    }


async def _check_consecutive_failures(
    integration_id: str, session_factory: Any
) -> None:
    """Increment failure count and set integration status='error' after 3 failures.

    Uses a simple in-config counter approach.
    """
    from app.models.integration import Integration

    try:
        async with session_factory() as session:
            result = await session.execute(
                select(Integration).where(Integration.id == UUID(integration_id))
            )
            integration = result.scalar_one_or_none()
            if integration is None:
                return

            config = integration.get_config()
            consecutive_failures = config.get("_consecutive_failures", 0) + 1
            config["_consecutive_failures"] = consecutive_failures
            integration.set_config(config)

            if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                integration.status = "error"
                struct_logger.error(
                    "keka_integration_status_set_error",
                    integration_id=integration_id,
                    consecutive_failures=consecutive_failures,
                )

            await session.commit()
    except Exception as exc:
        struct_logger.error(
            "keka_failure_tracking_error",
            integration_id=integration_id,
            error=str(exc),
        )
