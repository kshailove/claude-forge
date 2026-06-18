"""Celery worker configuration.

Imported by celery CLI: `celery -A app.celery_app worker --config celeryconfig`

This file defines per-queue concurrency settings and worker pool configuration.
The Beat schedule is defined in app/celery_app.py.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Queue-level concurrency (used when starting workers for specific queues)
# ---------------------------------------------------------------------------
# Start specific queues with:
#   celery -A app.celery_app worker -Q q_github --concurrency=4
#   celery -A app.celery_app worker -Q q_jira_clickup --concurrency=2
#   ... etc.
#
# In docker-compose the single worker container runs all queues with concurrency=4.
# In Kubernetes (M9) each queue gets its own worker Deployment with the
# concurrency and replica counts specified in the Helm chart.

QUEUE_CONCURRENCY: dict[str, int] = {
    "q_github": 4,       # 4 concurrent workers (multiple repos in parallel)
    "q_jira_clickup": 2, # 2 concurrent (Jira + ClickUp alongside each other)
    "q_incidents": 2,    # 2 concurrent (PagerDuty + Zenduty)
    "q_slack": 1,        # 1 concurrent (rate-limit sensitive: 1 req/min per channel)
    "q_keka": 1,         # 1 concurrent (sequential org tree sync)
    "q_digest": 4,       # 4 concurrent (parallel digest generation per recipient)
}

# ---------------------------------------------------------------------------
# Worker settings (applied when starting with this config)
# ---------------------------------------------------------------------------

# Prefetch: 1 per worker slot ensures fair distribution with acks_late=True
worker_prefetch_multiplier = 1

# Task acknowledgement: only after successful completion
# (tasks are re-queued on worker crash)
task_acks_late = True
task_reject_on_worker_lost = True

# Pool: prefork (default) — suitable for CPU-bound and blocking I/O tasks
worker_pool = "prefork"

# Heartbeat (seconds): workers report liveness to broker
broker_heartbeat = 30

# Max tasks per child process — restart workers periodically to prevent memory leaks
worker_max_tasks_per_child = 100
