"""Celery application factory and Beat schedule configuration.

Import this module wherever Celery tasks are registered:
    from app.celery_app import celery_app

Spec §2.6, §5.11
"""
from __future__ import annotations

import os

from celery import Celery
from celery.schedules import crontab

# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

celery_app = Celery(
    "engg_intelligence",
    broker=os.environ.get("CELERY_BROKER_URL", "redis://redis:6379/0"),
    backend=os.environ.get("CELERY_RESULT_BACKEND", "redis://redis:6379/1"),
    include=[
        "app.tasks.orchestrator",
        "app.tasks.github_ingest",
        "app.tasks.github_backfill",
        # M2: PM integrations
        "app.tasks.jira_ingest",
        "app.tasks.jira_backfill",
        "app.tasks.clickup_ingest",
        # M3: Incident integrations
        "app.tasks.pagerduty_ingest",
        "app.tasks.zenduty_ingest",
        # M6: Slack integration
        "app.tasks.slack_ingest",
        # M7: Weekly digest
        "app.tasks.digest_tasks",
        # M8: Identity resolution + Keka HRMS
        "app.tasks.identity_tasks",
        "app.tasks.keka_sync",
        # M9: Maintenance / data retention
        "app.tasks.maintenance",
    ],
)

# ---------------------------------------------------------------------------
# Celery configuration
# ---------------------------------------------------------------------------

celery_app.conf.update(
    # Serialization
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    # Timezone
    timezone="UTC",
    enable_utc=True,
    # Reliability — acks_late on all queues: task acknowledged only after completion
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    # Retry defaults (overridden per task where needed)
    task_max_retries=3,
    # Result TTL — keep results for 24 hours then discard
    result_expires=86400,
    # Worker prefetch — 1 per worker to ensure fair distribution with acks_late
    worker_prefetch_multiplier=1,
    # Broker connection retry on startup
    broker_connection_retry_on_startup=True,
)

# ---------------------------------------------------------------------------
# Queue routing (per-integration isolation)
# ---------------------------------------------------------------------------

celery_app.conf.task_routes = {
    "app.tasks.orchestrator.run_nightly_batch": {"queue": "q_github"},
    "app.tasks.orchestrator.run_metric_computation": {"queue": "q_github"},
    "app.tasks.orchestrator.invalidate_caches": {"queue": "q_github"},
    # M8: Identity resolution (runs on q_github — lightweight, no dedicated queue)
    "app.tasks.identity_tasks.auto_resolve_identities": {"queue": "q_github"},
    # M8: Keka sync (dedicated q_keka queue, concurrency=1)
    "app.tasks.keka_sync.keka_org_sync": {"queue": "q_keka"},
    # Wildcard routes (registered in later milestones)
    "app.tasks.github.*": {"queue": "q_github"},
    "app.tasks.pm.*": {"queue": "q_jira_clickup"},
    "app.tasks.incidents.*": {"queue": "q_incidents"},
    "app.tasks.slack.*": {"queue": "q_slack"},
    "app.tasks.keka.*": {"queue": "q_keka"},
    "app.tasks.digest.*": {"queue": "q_digest"},
}

# All queues — declared so workers can bind to specific subsets
celery_app.conf.task_queues = {
    "q_github": {},
    "q_jira_clickup": {},
    "q_incidents": {},
    "q_slack": {},
    "q_keka": {},
    "q_digest": {},
}

# ---------------------------------------------------------------------------
# Celery Beat schedule (all times UTC)
# ---------------------------------------------------------------------------

celery_app.conf.beat_schedule = {
    # Nightly Run Orchestrator: fires daily at 01:00 UTC
    # Dispatches all integration tasks as a Celery chord with staggered countdowns:
    #   GitHub:      01:00 UTC (countdown=0)
    #   Jira/ClickUp: 01:20 UTC (countdown=1200s)
    #   Incidents:   01:40 UTC (countdown=2400s)
    #   Slack:       02:00 UTC (countdown=3600s)
    #   Keka:        02:15 UTC (countdown=4500s)
    #   Metric computation chord callback: ~02:30 UTC
    #   Cache invalidation: ~02:45 UTC
    "nightly-run-orchestrator": {
        "task": "app.tasks.orchestrator.run_nightly_batch",
        "schedule": crontab(minute=0, hour=1),
        "options": {"queue": "q_github"},
    },
    # Digest snapshot: Sunday 22:00 UTC — captures metric state before Monday send
    "digest-snapshot": {
        "task": "app.tasks.digest_tasks.digest_snapshot_task",
        "schedule": crontab(minute=0, hour=22, day_of_week=0),
        "options": {"queue": "q_digest"},
    },
    # Digest send: Monday 06:00 UTC — fan-out per-user email delivery
    "digest-monday-send": {
        "task": "app.tasks.digest_tasks.digest_trigger_all",
        "schedule": crontab(minute=0, hour=6, day_of_week=1),
        "options": {"queue": "q_digest"},
    },
    # Data retention: purge data older than 12 months — daily at 03:00 UTC
    # M9: moved to dedicated app.tasks.maintenance module
    "data-retention-purge": {
        "task": "app.tasks.maintenance.purge_old_data",
        "schedule": crontab(minute=0, hour=3),
        "options": {"queue": "q_github"},
    },
}

celery_app.conf.beat_scheduler = "celery.beat.PersistentScheduler"
