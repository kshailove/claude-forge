# TimescaleDB to Vanilla PostgreSQL Migration

Use this guide when migrating from a self-hosted TimescaleDB deployment to a
managed PostgreSQL service (Amazon RDS, Google Cloud SQL, Azure Database for
PostgreSQL) that does not support the TimescaleDB extension.

---

## When to use this guide

You need this migration if:

- You started with `docker-compose.yml` (Path A — TimescaleDB) and now want
  to move to a managed PostgreSQL service.
- Your cloud provider does not offer TimescaleDB support.
- You are on AWS RDS, Google Cloud SQL, or Azure DB for PostgreSQL Standard tier.

> Amazon RDS for PostgreSQL and Google Cloud SQL do **not** support
> TimescaleDB. Aurora PostgreSQL does not support it either.
> If you need TimescaleDB on a managed service, consider
> [Timescale Cloud](https://www.timescale.com/cloud).

---

## Pre-migration checklist

- [ ] Identify a maintenance window (the migration requires downtime).
- [ ] Provision the new managed PostgreSQL 16 instance.
- [ ] Ensure network connectivity between migration host and both databases.
- [ ] Install `pg_dump` and `psql` matching the source PostgreSQL version.

---

## Step 1 — Export data from TimescaleDB as CSV

Stop the application (prevents writes during export):

```bash
docker compose down api celery-worker celery-beat
```

Export each time-series hypertable to CSV:

```bash
# Team metric snapshots
docker compose exec db psql -U engg -d engg_intelligence -c \
  "\COPY team_metric_snapshots TO '/tmp/team_metric_snapshots.csv' WITH CSV HEADER"

# Engineer metric snapshots
docker compose exec db psql -U engg -d engg_intelligence -c \
  "\COPY engineer_metric_snapshots TO '/tmp/engineer_metric_snapshots.csv' WITH CSV HEADER"

# Slack activity buckets
docker compose exec db psql -U engg -d engg_intelligence -c \
  "\COPY slack_activity_buckets TO '/tmp/slack_activity_buckets.csv' WITH CSV HEADER"
```

Copy CSV files out of the container:

```bash
docker compose cp db:/tmp/team_metric_snapshots.csv ./export/
docker compose cp db:/tmp/engineer_metric_snapshots.csv ./export/
docker compose cp db:/tmp/slack_activity_buckets.csv ./export/
```

Dump all regular (non-hypertable) tables:

```bash
docker compose exec db pg_dump -U engg -d engg_intelligence \
  --exclude-table=team_metric_snapshots \
  --exclude-table=engineer_metric_snapshots \
  --exclude-table=slack_activity_buckets \
  -F c -f /tmp/regular_tables.dump

docker compose cp db:/tmp/regular_tables.dump ./export/
```

---

## Step 2 — Create new schema with vanilla partitioning

Set `USE_TIMESCALEDB=false` in your `.env` (or Kubernetes Secret) and point
`DATABASE_URL` at the new managed PostgreSQL instance.

Apply Alembic migrations — this creates the schema with declarative range
partitioning instead of TimescaleDB hypertables:

```bash
# Against the new managed PostgreSQL
DATABASE_URL=postgresql+asyncpg://user:pass@new-rds-host:5432/engg_intelligence \
USE_TIMESCALEDB=false \
docker compose run --rm api alembic upgrade head
```

Restore regular tables:

```bash
pg_restore \
  --host=new-rds-host \
  --username=your-user \
  --dbname=engg_intelligence \
  --no-owner \
  --no-acl \
  -F c ./export/regular_tables.dump
```

---

## Step 3 — Import hypertable data

```bash
# team_metric_snapshots
psql postgresql://your-user:pass@new-rds-host:5432/engg_intelligence \
  -c "\COPY team_metric_snapshots FROM './export/team_metric_snapshots.csv' WITH CSV HEADER"

# engineer_metric_snapshots
psql postgresql://your-user:pass@new-rds-host:5432/engg_intelligence \
  -c "\COPY engineer_metric_snapshots FROM './export/engineer_metric_snapshots.csv' WITH CSV HEADER"

# slack_activity_buckets
psql postgresql://your-user:pass@new-rds-host:5432/engg_intelligence \
  -c "\COPY slack_activity_buckets FROM './export/slack_activity_buckets.csv' WITH CSV HEADER"
```

---

## Step 4 — Verify queries work

Run the diagnostic queries below and confirm they return data and complete
within an acceptable time:

```sql
-- Last 30 days of team metrics (tests partition pruning)
SELECT team_id, snapshot_at, composite_score
FROM team_metric_snapshots
WHERE snapshot_at > now() - INTERVAL '30 days'
ORDER BY snapshot_at DESC
LIMIT 100;

-- Sparkline query (tests date_trunc bucketing)
SELECT date_trunc('week', snapshot_at) AS week,
       avg(composite_score) AS avg_score
FROM team_metric_snapshots
WHERE team_id = 'your-team-uuid'
  AND snapshot_at > now() - INTERVAL '90 days'
GROUP BY 1
ORDER BY 1;

-- Slack bucket aggregation
SELECT date_trunc('day', bucket_hour) AS day,
       sum(message_count) AS messages
FROM slack_activity_buckets
WHERE engineer_id = 'your-engineer-uuid'
  AND bucket_hour > now() - INTERVAL '30 days'
GROUP BY 1
ORDER BY 1;
```

---

## Step 5 — Restart the application

Update `DATABASE_URL` and `USE_TIMESCALEDB=false` in your deployment
configuration, then restart:

```bash
# Docker Compose
docker compose up -d

# Kubernetes
kubectl set env deployment/engg-intelligence-api \
  USE_TIMESCALEDB=false -n engg-intelligence
kubectl rollout restart deployment -n engg-intelligence
```

---

## Performance tradeoff

| Query | TimescaleDB | Vanilla PostgreSQL |
|-------|-------------|-------------------|
| Last-30-days sparkline (p95) | ~15ms | 30–75ms |
| 90-day team aggregate (p95) | ~25ms | 50–125ms |
| Continuous aggregate read | ~5ms | N/A (re-computed) |

Vanilla PostgreSQL with declarative partitioning performs well for datasets
up to ~100M rows. At larger scales, add a materialised view layer or consider
Timescale Cloud.

The API response cache (2-hour TTL in Redis) means most end-user requests
never hit these queries — the performance difference is only observable in
the nightly metric computation job.
