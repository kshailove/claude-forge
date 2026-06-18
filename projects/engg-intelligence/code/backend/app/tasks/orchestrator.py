"""Nightly Run Orchestrator — Celery Beat task fired at 01:00 UTC daily.

Spec §5.2 and §8 M0f.

Orchestration flow:
  1. Check for an already-running nightly run (abort if found).
  2. Create nightly_runs record with status='running'.
  3. Build a Celery group of integration task stubs with staggered ETA countdowns.
  4. Wrap in a chord so run_metric_computation fires when all tasks complete.
  5. Update nightly_runs on completion/failure.
  6. Invalidate Redis caches at ~02:45 UTC.
  7. On Monday: enqueue digest snapshot preparation.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

import structlog
from celery import chord, group, shared_task
from celery.utils.log import get_task_logger

from app.celery_app import celery_app

logger = get_task_logger(__name__)
struct_logger = structlog.get_logger(__name__)


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
# Main orchestrator task — fires at 01:00 UTC via Celery Beat
# ---------------------------------------------------------------------------

@celery_app.task(
    bind=True,
    name="app.tasks.orchestrator.run_nightly_batch",
    max_retries=1,
    acks_late=True,
)
def run_nightly_batch(self, nightly_run_id: str | None = None) -> dict:
    """Create a nightly_runs record and dispatch all integration tasks as a Celery chord.

    Staggered countdowns (seconds from 01:00 UTC):
      GitHub:      countdown=0    (fires at 01:00)
      Jira/ClickUp: countdown=1200 (fires at 01:20)
      Incidents:   countdown=2400  (fires at 01:40)
      Slack:       countdown=3600  (fires at 02:00)
      Keka:        countdown=4500  (fires at 02:15)
    Metric computation chord callback: ~02:30 UTC
    Cache invalidation: ~02:45 UTC
    """
    return _run_async(_run_nightly_batch_async(nightly_run_id))


async def _run_nightly_batch_async(nightly_run_id: str | None) -> dict:
    """Async implementation of the nightly orchestrator."""
    from sqlalchemy import select

    from app.core.database import get_session_factory
    from app.models.nightly import NightlyRun

    session_factory = get_session_factory()
    now = datetime.now(tz=timezone.utc)

    async with session_factory() as session:
        # --- Guard: abort if a run is already in progress ---
        existing_result = await session.execute(
            select(NightlyRun).where(NightlyRun.status == "running")
        )
        existing_run = existing_result.scalar_one_or_none()
        if existing_run and nightly_run_id is None:
            struct_logger.warning(
                "nightly_run_skipped",
                reason="run_already_active",
                existing_run_id=str(existing_run.id),
            )
            return {"status": "skipped", "reason": "run_already_active"}

        # --- Create or fetch the nightly_runs record ---
        if nightly_run_id:
            # Triggered manually via API — record already created
            from uuid import UUID
            result = await session.execute(
                select(NightlyRun).where(NightlyRun.id == UUID(nightly_run_id))
            )
            nightly_run = result.scalar_one_or_none()
            if nightly_run is None:
                struct_logger.error("nightly_run_not_found", run_id=nightly_run_id)
                return {"status": "error", "reason": "nightly_run_not_found"}
        else:
            nightly_run = NightlyRun(
                scheduled_at=now.replace(minute=0, second=0, microsecond=0),
                started_at=now,
                status="running",
                integrations_completed={},
                metric_computation_status="pending",
            )
            session.add(nightly_run)
            await session.flush()

        nightly_run.started_at = now
        nightly_run.status = "running"
        run_id_str = str(nightly_run.id)
        await session.commit()

    struct_logger.info("nightly_run_started", run_id=run_id_str)

    # --- Resolve GitHub integration_id (if connected) ---
    github_integration_id: str | None = None
    async with session_factory() as session:
        from sqlalchemy import select as _select
        from app.models.integration import Integration as _Integration
        gh_result = await session.execute(
            _select(_Integration).where(
                _Integration.type == "github",
                _Integration.status == "connected",
            )
        )
        gh_integration = gh_result.scalar_one_or_none()
        if gh_integration:
            github_integration_id = str(gh_integration.id)

    # --- Build the Celery chord of integration tasks ---
    # M1: GitHub real task. M2: Jira + ClickUp real tasks. M3–M8: stubs.
    if github_integration_id:
        from app.tasks.github_ingest import github_nightly_batch as _github_task
        github_task = _github_task.s(github_integration_id).set(countdown=0)  # 01:00
    else:
        github_task = _nightly_stub_task.s("github", run_id_str).set(countdown=0)

    # Resolve Jira + ClickUp integration IDs (M2)
    jira_integration_id: str | None = None
    clickup_integration_id: str | None = None
    async with session_factory() as session:
        from sqlalchemy import select as _select2
        from app.models.integration import Integration as _Integration2

        jira_result = await session.execute(
            _select2(_Integration2).where(
                _Integration2.type == "jira",
                _Integration2.status == "connected",
            )
        )
        jira_integration = jira_result.scalar_one_or_none()
        if jira_integration:
            jira_integration_id = str(jira_integration.id)

        clickup_result = await session.execute(
            _select2(_Integration2).where(
                _Integration2.type == "clickup",
                _Integration2.status == "connected",
            )
        )
        clickup_integration = clickup_result.scalar_one_or_none()
        if clickup_integration:
            clickup_integration_id = str(clickup_integration.id)

    # Build Jira/ClickUp tasks or stubs
    if jira_integration_id or clickup_integration_id:
        from celery import group as _group2
        pm_subtasks = []
        if jira_integration_id:
            from app.tasks.jira_ingest import jira_nightly_batch as _jira_task
            pm_subtasks.append(_jira_task.s(jira_integration_id))
        if clickup_integration_id:
            from app.tasks.clickup_ingest import clickup_nightly_batch as _clickup_task
            pm_subtasks.append(_clickup_task.s(clickup_integration_id))
        # Wrap in a group if multiple, otherwise use the single task directly
        if len(pm_subtasks) == 1:
            pm_task = pm_subtasks[0].set(countdown=1200)
        else:
            pm_task = _group2(*pm_subtasks).set(countdown=1200)
    else:
        pm_task = _nightly_stub_task.s("jira_clickup", run_id_str).set(countdown=1200)

    # --- Resolve incident integration IDs (M3: PagerDuty / Zenduty) ---
    pagerduty_integration_id: str | None = None
    zenduty_integration_id: str | None = None
    async with session_factory() as session:
        from sqlalchemy import select as _select3
        from app.models.integration import Integration as _Integration3

        for _itype in ("pagerduty", "zenduty"):
            _int_result = await session.execute(
                _select3(_Integration3).where(
                    _Integration3.type == _itype,
                    _Integration3.status == "connected",
                )
            )
            _int = _int_result.scalar_one_or_none()
            if _int:
                if _itype == "pagerduty":
                    pagerduty_integration_id = str(_int.id)
                else:
                    zenduty_integration_id = str(_int.id)

    # Incidents: dispatch whichever provider is connected (PD takes priority)
    if pagerduty_integration_id:
        from app.tasks.pagerduty_ingest import pagerduty_nightly_batch as _pd_task
        incidents_task = _pd_task.s(pagerduty_integration_id).set(countdown=2400)
    elif zenduty_integration_id:
        from app.tasks.zenduty_ingest import zenduty_nightly_batch as _zd_task
        incidents_task = _zd_task.s(zenduty_integration_id).set(countdown=2400)
    else:
        incidents_task = _nightly_stub_task.s("incidents", run_id_str).set(countdown=2400)

    # --- Resolve Slack integration ID (M6) ---
    slack_integration_id: str | None = None
    async with session_factory() as session:
        from sqlalchemy import select as _select_slack
        from app.models.integration import Integration as _IntegrationSlack

        slack_result = await session.execute(
            _select_slack(_IntegrationSlack).where(
                _IntegrationSlack.type == "slack",
                _IntegrationSlack.status == "connected",
            )
        )
        slack_integration = slack_result.scalar_one_or_none()
        if slack_integration:
            slack_integration_id = str(slack_integration.id)

    if slack_integration_id:
        from app.tasks.slack_ingest import slack_nightly_batch as _slack_task
        slack_task = _slack_task.s(slack_integration_id).set(countdown=3600)  # 02:00
    else:
        slack_task = _nightly_stub_task.s("slack", run_id_str).set(countdown=3600)

    # --- Resolve Keka integration ID (M8c) ---
    keka_integration_id: str | None = None
    async with session_factory() as session:
        from sqlalchemy import select as _select_keka
        from app.models.integration import Integration as _IntegrationKeka

        keka_result = await session.execute(
            _select_keka(_IntegrationKeka).where(
                _IntegrationKeka.type == "keka",
                _IntegrationKeka.status == "connected",
            )
        )
        keka_integration = keka_result.scalar_one_or_none()
        if keka_integration:
            keka_integration_id = str(keka_integration.id)

    if keka_integration_id:
        from app.tasks.keka_sync import keka_org_sync as _keka_task
        keka_task = _keka_task.s(keka_integration_id).set(countdown=4500)     # 02:15
    else:
        keka_task = _nightly_stub_task.s("keka", run_id_str).set(countdown=4500)

    integration_tasks = group(
        github_task,
        pm_task,                                                               # 01:20
        incidents_task,                                                        # 01:40
        slack_task,                                                            # 02:00
        keka_task,                                                             # 02:15
    )

    # Chord callback: metric computation fires after all integration tasks complete
    chord_result = chord(integration_tasks)(
        run_metric_computation.s(run_id_str).set(countdown=0)
    )

    struct_logger.info(
        "nightly_run_chord_dispatched",
        run_id=run_id_str,
        chord_id=str(chord_result.id),
    )
    return {"status": "dispatched", "run_id": run_id_str}


# ---------------------------------------------------------------------------
# Integration stub tasks (no-op for M0 — implemented in M1–M8)
# ---------------------------------------------------------------------------

@celery_app.task(
    bind=True,
    name="app.tasks.orchestrator._nightly_stub_task",
    max_retries=3,
    acks_late=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=900,
    retry_jitter=True,
)
def _nightly_stub_task(self, integration_type: str, nightly_run_id: str) -> dict:
    """No-op stub integration task for M0. Real implementations come in M1–M8.

    When implemented, each real task will:
      1. Fetch data from the integration API.
      2. Upsert records to the database.
      3. Mark nightly_runs.integrations_completed[type] = True.
    """
    struct_logger.info(
        "nightly_stub_task_complete",
        integration_type=integration_type,
        nightly_run_id=nightly_run_id,
    )
    _run_async(_mark_integration_complete(nightly_run_id, integration_type, success=True))
    return {"integration": integration_type, "status": "stub_complete"}


async def _compute_pr_health_for_all_teams() -> None:
    """Compute and persist PR Health metric snapshots for all teams.

    Called by the metric computation chord callback (M1c).
    """
    from sqlalchemy import select

    from app.core.database import get_session_factory
    from app.metrics.pr_health import write_pr_health_snapshot
    from app.models.team import Team

    session_factory = get_session_factory()
    async with session_factory() as session:
        result = await session.execute(select(Team))
        teams = result.scalars().all()

    for team in teams:
        try:
            async with session_factory() as session:
                await write_pr_health_snapshot(team_id=team.id, db=session)
                await session.commit()
            struct_logger.info(
                "pr_health_computed",
                team_id=str(team.id),
                team_name=team.name,
            )
        except Exception as exc:
            struct_logger.error(
                "pr_health_computation_failed",
                team_id=str(team.id),
                error=str(exc),
                exc_info=True,
            )
            # Never abort all teams for one failure
            continue


async def _compute_sprint_health_for_all_teams() -> None:
    """Compute and persist Sprint Health metric snapshots for all teams.

    Called by the metric computation chord callback (M2c).
    Skips teams with no sprint data (setup_required=True).
    """
    from sqlalchemy import select

    from app.core.database import get_session_factory
    from app.metrics.sprint_health import (
        compute_sprint_health,
        compute_sprint_health_score,
        write_sprint_health_snapshot,
    )
    from app.models.team import Team

    session_factory = get_session_factory()
    async with session_factory() as session:
        result = await session.execute(select(Team))
        teams = result.scalars().all()

    for team in teams:
        try:
            async with session_factory() as session:
                metrics = await compute_sprint_health(team_id=team.id, db=session)
                if metrics is None or metrics.setup_required:
                    struct_logger.debug(
                        "sprint_health_skipped_no_data",
                        team_id=str(team.id),
                    )
                    continue
                score = compute_sprint_health_score(metrics)
                await write_sprint_health_snapshot(
                    team_id=team.id,
                    metrics=metrics,
                    score=score,
                    db=session,
                )
                await session.commit()
            struct_logger.info(
                "sprint_health_computed",
                team_id=str(team.id),
                team_name=team.name,
                score=score,
            )
        except Exception as exc:
            struct_logger.error(
                "sprint_health_computation_failed",
                team_id=str(team.id),
                error=str(exc),
                exc_info=True,
            )
            continue


async def _compute_incident_load_for_all_teams() -> None:
    """Compute and persist Incident Load metric snapshots for all teams.

    Called by the metric computation chord callback (M3c).
    Skips teams with no incident data gracefully.
    """
    from sqlalchemy import select

    from app.core.database import get_session_factory
    from app.metrics.incident_load import (
        compute_incident_load,
        compute_incident_load_score,
        write_incident_load_snapshot,
    )
    from app.models.team import Team

    session_factory = get_session_factory()
    async with session_factory() as session:
        result = await session.execute(select(Team))
        teams = result.scalars().all()

    for team in teams:
        try:
            async with session_factory() as session:
                metrics = await compute_incident_load(team_id=team.id, db=session)
                if metrics.incident_count == 0:
                    struct_logger.debug(
                        "incident_load_skipped_no_incidents",
                        team_id=str(team.id),
                    )
                    continue
                score = compute_incident_load_score(metrics)
                await write_incident_load_snapshot(
                    team_id=team.id,
                    metrics=metrics,
                    score=score,
                    db=session,
                )
                await session.commit()
            struct_logger.info(
                "incident_load_computed",
                team_id=str(team.id),
                team_name=team.name,
                score=score,
                incident_count=metrics.incident_count,
            )
        except Exception as exc:
            struct_logger.error(
                "incident_load_computation_failed",
                team_id=str(team.id),
                error=str(exc),
                exc_info=True,
            )
            continue


async def _compute_dora_for_all_teams() -> None:
    """Compute and persist DORA metric snapshots for all teams.

    Called by the metric computation chord callback (M3c).
    Skips teams with no release data gracefully.
    """
    from sqlalchemy import select

    from app.core.database import get_session_factory
    from app.metrics.dora import compute_dora_metrics, write_dora_snapshot
    from app.models.team import Team

    session_factory = get_session_factory()
    async with session_factory() as session:
        result = await session.execute(select(Team))
        teams = result.scalars().all()

    for team in teams:
        try:
            async with session_factory() as session:
                metrics = await compute_dora_metrics(team_id=team.id, db=session)
                await write_dora_snapshot(team_id=team.id, metrics=metrics, db=session)
                await session.commit()
            struct_logger.info(
                "dora_computed",
                team_id=str(team.id),
                team_name=team.name,
                df_band=metrics.deployment_frequency_band,
                lt_band=metrics.lead_time_band,
                cfr_band=metrics.change_failure_rate_band,
                mttr_band=metrics.mttr_band,
            )
        except Exception as exc:
            struct_logger.error(
                "dora_computation_failed",
                team_id=str(team.id),
                error=str(exc),
                exc_info=True,
            )
            continue


async def _compute_slack_signal_for_all_teams() -> None:
    """Compute and persist Slack Signal metric snapshots for all teams.

    Called by the metric computation chord callback (M6c).

    Degradation handling (spec §2.4):
    If compute_slack_signal_score() returns None (degraded or no data), no snapshot
    is written and a debug log is emitted. The weight is implicitly redistributed
    by callers of the composite score endpoint (the score query omits the component).
    """
    from sqlalchemy import select

    from app.core.database import get_session_factory
    from app.metrics.slack_signal import (
        compute_slack_signal,
        compute_slack_signal_score,
        write_slack_signal_snapshot,
    )
    from app.models.team import Team

    session_factory = get_session_factory()
    async with session_factory() as session:
        result = await session.execute(select(Team))
        teams = result.scalars().all()

    for team in teams:
        try:
            async with session_factory() as session:
                metrics = await compute_slack_signal(team_id=team.id, db=session)

                if metrics.degraded:
                    struct_logger.info(
                        "slack_signal_skipped_degraded",
                        team_id=str(team.id),
                        reason=metrics.degraded_reason,
                    )
                    continue

                score = compute_slack_signal_score(metrics)
                if score is None:
                    struct_logger.debug(
                        "slack_signal_skipped_no_data",
                        team_id=str(team.id),
                    )
                    continue

                await write_slack_signal_snapshot(
                    team_id=team.id,
                    metrics=metrics,
                    score=score,
                    db=session,
                )
                await session.commit()

            struct_logger.info(
                "slack_signal_computed",
                team_id=str(team.id),
                team_name=team.name,
                score=score,
                after_hours_pct=metrics.after_hours_message_pct,
                weekend_pct=metrics.weekend_message_pct,
            )
        except Exception as exc:
            struct_logger.error(
                "slack_signal_computation_failed",
                team_id=str(team.id),
                error=str(exc),
                exc_info=True,
            )
            # Never abort all teams for one failure
            continue


async def _mark_integration_complete(
    nightly_run_id: str, integration_type: str, success: bool
) -> None:
    """Update nightly_runs.integrations_completed for a given integration."""
    from uuid import UUID
    from sqlalchemy import select

    from app.core.database import get_session_factory
    from app.models.nightly import NightlyRun

    session_factory = get_session_factory()
    async with session_factory() as session:
        result = await session.execute(
            select(NightlyRun).where(NightlyRun.id == UUID(nightly_run_id))
        )
        run = result.scalar_one_or_none()
        if run is None:
            return
        run.mark_integration_complete(integration_type, success)
        await session.commit()


# ---------------------------------------------------------------------------
# Metric computation chord callback (~02:30 UTC)
# ---------------------------------------------------------------------------

@celery_app.task(
    bind=True,
    name="app.tasks.orchestrator.run_metric_computation",
    max_retries=2,
    acks_late=True,
)
def run_metric_computation(self, results: list, nightly_run_id: str) -> dict:
    """Chord callback: recompute all team metric scores after ingestion completes.

    Called automatically by Celery when ALL integration tasks in the chord complete
    (whether successfully or not). Processes partial data if some integrations failed.

    After computation: dispatches cache invalidation (countdown=900s ≈ 15 min buffer).
    On Monday: also enqueues digest snapshot preparation.
    """
    return _run_async(_run_metric_computation_async(results, nightly_run_id))


async def _run_metric_computation_async(results: list, nightly_run_id: str) -> dict:
    """Async implementation of metric computation."""
    from uuid import UUID
    from sqlalchemy import select

    from app.core.database import get_session_factory
    from app.models.nightly import NightlyRun

    session_factory = get_session_factory()

    struct_logger.info(
        "metric_computation_started",
        nightly_run_id=nightly_run_id,
        integration_results_count=len(results) if results else 0,
    )

    async with session_factory() as session:
        result = await session.execute(
            select(NightlyRun).where(NightlyRun.id == UUID(nightly_run_id))
        )
        run = result.scalar_one_or_none()
        if run is None:
            struct_logger.error("nightly_run_not_found_for_metrics", run_id=nightly_run_id)
            return {"status": "error", "reason": "run_not_found"}

        run.metric_computation_status = "running"
        await session.commit()

    # Metric computation: M1c PR Health + M2c Sprint Health.
    struct_logger.info(
        "metric_computation_started",
        nightly_run_id=nightly_run_id,
    )

    # Compute PR Health scores for all teams (M1c)
    try:
        await _compute_pr_health_for_all_teams()
    except Exception as exc:
        struct_logger.error(
            "metric_computation_pr_health_failed",
            nightly_run_id=nightly_run_id,
            error=str(exc),
            exc_info=True,
        )

    # Compute Sprint Health scores for all teams (M2c)
    try:
        await _compute_sprint_health_for_all_teams()
    except Exception as exc:
        struct_logger.error(
            "metric_computation_sprint_health_failed",
            nightly_run_id=nightly_run_id,
            error=str(exc),
            exc_info=True,
        )

    # Compute Incident Load scores for all teams (M3c)
    try:
        await _compute_incident_load_for_all_teams()
    except Exception as exc:
        struct_logger.error(
            "metric_computation_incident_load_failed",
            nightly_run_id=nightly_run_id,
            error=str(exc),
            exc_info=True,
        )

    # Compute DORA metrics for all teams (M3c)
    try:
        await _compute_dora_for_all_teams()
    except Exception as exc:
        struct_logger.error(
            "metric_computation_dora_failed",
            nightly_run_id=nightly_run_id,
            error=str(exc),
            exc_info=True,
        )

    # Compute Slack Signal scores for all teams (M6c)
    try:
        await _compute_slack_signal_for_all_teams()
    except Exception as exc:
        struct_logger.error(
            "metric_computation_slack_signal_failed",
            nightly_run_id=nightly_run_id,
            error=str(exc),
            exc_info=True,
        )

    # M8a: Run identity resolution after all ingests complete
    # Dispatch as a separate task to avoid blocking metric computation
    try:
        from app.tasks.identity_tasks import auto_resolve_identities
        auto_resolve_identities.apply_async(
            queue="q_github",
            countdown=60,  # Small delay to let DB writes settle
        )
        struct_logger.info(
            "identity_resolution_queued_post_nightly",
            nightly_run_id=nightly_run_id,
        )
    except Exception as exc:
        struct_logger.error(
            "identity_resolution_queue_failed",
            nightly_run_id=nightly_run_id,
            error=str(exc),
        )

    async with session_factory() as session:
        result = await session.execute(
            select(NightlyRun).where(NightlyRun.id == UUID(nightly_run_id))
        )
        run = result.scalar_one_or_none()
        if run is None:
            return {"status": "error", "reason": "run_not_found"}

        run.metric_computation_status = "completed"
        # Derive overall run status from integration completion flags
        derived_status = run.compute_status()
        run.status = derived_status
        from datetime import datetime, timezone
        run.completed_at = datetime.now(tz=timezone.utc)
        await session.commit()

    struct_logger.info(
        "metric_computation_complete",
        nightly_run_id=nightly_run_id,
        status=derived_status,
    )

    # Dispatch cache invalidation after a short buffer (~15 min)
    invalidate_caches.apply_async(
        args=[nightly_run_id],
        countdown=900,  # 15 minutes after metric computation
        queue="q_github",
    )

    # On Monday: also trigger digest snapshot preparation
    from datetime import date
    if date.today().weekday() == 0:  # Monday = 0
        trigger_digest_snapshot.apply_async(
            args=[nightly_run_id],
            queue="q_digest",
        )

    return {"status": derived_status, "run_id": nightly_run_id}


# ---------------------------------------------------------------------------
# Cache invalidation (~02:45 UTC)
# ---------------------------------------------------------------------------

@celery_app.task(
    bind=True,
    name="app.tasks.orchestrator.invalidate_caches",
    acks_late=True,
)
def invalidate_caches(self, nightly_run_id: str) -> dict:
    """Invalidate all overview and team_score Redis cache keys after nightly metrics."""
    return _run_async(_invalidate_caches_async(nightly_run_id))


async def _invalidate_caches_async(nightly_run_id: str) -> dict:
    from app.core.redis import cache_delete_pattern

    deleted_overview = await cache_delete_pattern("overview:*")
    deleted_team = await cache_delete_pattern("team_score:*")
    deleted_engineers = await cache_delete_pattern("engineers:*")

    struct_logger.info(
        "cache_invalidated",
        nightly_run_id=nightly_run_id,
        deleted_overview=deleted_overview,
        deleted_team_score=deleted_team,
        deleted_engineers=deleted_engineers,
    )
    return {
        "status": "complete",
        "deleted_keys": deleted_overview + deleted_team + deleted_engineers,
    }


# ---------------------------------------------------------------------------
# Digest preparation (Monday ~02:45 UTC, chord callback side-effect)
# ---------------------------------------------------------------------------

@celery_app.task(
    bind=True,
    name="app.tasks.orchestrator.trigger_digest_snapshot",
    acks_late=True,
)
def trigger_digest_snapshot(self, nightly_run_id: str) -> dict:
    """Create a DigestRun snapshot record on Monday after nightly metrics complete.

    Full implementation delivered in M7a.
    """
    struct_logger.info(
        "digest_snapshot_stub",
        nightly_run_id=nightly_run_id,
        note="Full implementation in M7a",
    )
    return {"status": "stub"}


@celery_app.task(
    bind=True,
    name="app.tasks.orchestrator.trigger_digest_send",
    acks_late=True,
)
def trigger_digest_send() -> dict:
    """Monday 06:00 UTC: send all generated digests for the current week.

    Full implementation delivered in M7b.
    """
    struct_logger.info(
        "digest_send_stub",
        note="Full implementation in M7b",
    )
    return {"status": "stub"}


# ---------------------------------------------------------------------------
# Data retention purge (daily 04:00 UTC)
# ---------------------------------------------------------------------------

@celery_app.task(
    bind=True,
    name="app.tasks.orchestrator.purge_old_data",
    acks_late=True,
)
def purge_old_data() -> dict:
    """Delete metric snapshots and related data older than 12 months.

    Spec §7.3 (Reliability) and §5.11 (Celery Beat schedule).
    Full implementation in M9.
    """
    struct_logger.info("purge_old_data_stub", note="Full implementation in M9")
    return {"status": "stub"}
