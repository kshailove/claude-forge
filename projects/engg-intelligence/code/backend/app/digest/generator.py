"""Digest generator — renders role-scoped HTML emails from compiled MJML templates.

Flow:
  Sunday 22:00  → create_digest_snapshot()   records DigestRun, captures metric state
  Monday 06:00  → generate_for_recipient()   renders HTML per user, stores in digest_emails

Template lookup:
  Role engineer → compiled/digest_engineer.html
  Role em       → compiled/digest_em.html
  Role director → compiled/digest_director.html  (also admin)

Spec §8 M7a.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

import structlog
from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.digest import DigestEmail, DigestRun
from app.models.metrics import EngineerMetricSnapshot, TeamMetricSnapshot
from app.models.team import Team, TeamMembership
from app.models.user import User

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Template directory — pre-compiled HTML lives here at runtime
# ---------------------------------------------------------------------------

_TEMPLATES_DIR = Path(__file__).parent.parent / "templates" / "compiled"

# ---------------------------------------------------------------------------
# Jinja2 environment
# ---------------------------------------------------------------------------

def _make_jinja_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )


# ---------------------------------------------------------------------------
# Role → template filename mapping
# ---------------------------------------------------------------------------

_ROLE_TEMPLATE: dict[str, str] = {
    "engineer": "digest_engineer.html",
    "em": "digest_em.html",
    "director": "digest_director.html",
    "admin": "digest_director.html",  # admins get the director view
}


# ---------------------------------------------------------------------------
# DigestGenerator
# ---------------------------------------------------------------------------

class DigestGenerator:
    """Generates and stores per-user HTML digest emails."""

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    async def create_digest_snapshot(self, db: AsyncSession) -> str:
        """Create a DigestRun record capturing the current metric state.

        Called Sunday 22:00 UTC by Celery Beat.
        Returns the UUID of the newly created DigestRun as a string.
        """
        now = datetime.now(tz=timezone.utc)

        # Count active users so we know how many emails to expect
        user_count_result = await db.execute(
            select(func.count()).select_from(User).where(User.is_active.is_(True))
        )
        recipient_count: int = user_count_result.scalar_one() or 0

        digest_run = DigestRun(
            run_at=now,
            snapshot_taken_at=now,
            status="pending",
            recipient_count=recipient_count,
        )
        db.add(digest_run)
        await db.commit()
        await db.refresh(digest_run)

        logger.info(
            "digest_snapshot_created",
            digest_run_id=str(digest_run.id),
            recipient_count=recipient_count,
        )
        return str(digest_run.id)

    async def generate_for_recipient(
        self,
        user_id: str,
        digest_run_id: str,
        db: AsyncSession,
    ) -> str:
        """Render role-scoped HTML for one user and persist to digest_emails.

        Returns the rendered HTML string.
        """
        user_uuid = UUID(user_id)
        run_uuid = UUID(digest_run_id)

        html = await self._render_for_user(user_uuid, db)

        # Load user role for storage
        user_result = await db.execute(select(User).where(User.id == user_uuid))
        user: User | None = user_result.scalar_one_or_none()
        if user is None:
            raise ValueError(f"User {user_id} not found")

        # Upsert digest_emails row
        existing = await db.execute(
            select(DigestEmail).where(
                and_(
                    DigestEmail.user_id == user_uuid,
                    DigestEmail.digest_run_id == run_uuid,
                )
            )
        )
        digest_email: DigestEmail | None = existing.scalar_one_or_none()

        if digest_email is None:
            digest_email = DigestEmail(
                digest_run_id=run_uuid,
                user_id=user_uuid,
                role_scope=user.role,
                html_content=html,
                delivery_status="pending",
            )
            db.add(digest_email)
        else:
            digest_email.html_content = html
            digest_email.delivery_status = "pending"

        await db.commit()

        logger.info(
            "digest_generated",
            user_id=user_id,
            role=user.role,
            digest_run_id=digest_run_id,
        )
        return html

    async def preview_for_user(self, user_id: str, db: AsyncSession) -> str:
        """Render role-scoped HTML for preview without persisting to DB.

        Used by the /digests/preview API endpoint.
        """
        user_uuid = UUID(user_id)
        return await self._render_for_user(user_uuid, db)

    async def _render_for_user(self, user_uuid: UUID, db: AsyncSession) -> str:
        """Core render logic shared by generate_for_recipient and preview_for_user."""
        # Load user
        user_result = await db.execute(select(User).where(User.id == user_uuid))
        user: User | None = user_result.scalar_one_or_none()
        if user is None:
            raise ValueError(f"User {user_uuid} not found")

        role = user.role
        template_name = _ROLE_TEMPLATE.get(role, "digest_engineer.html")

        # Build role-scoped context
        now = datetime.now(tz=timezone.utc)
        week_start = now - timedelta(days=7)
        week_label = f"Week of {week_start.strftime('%B %d, %Y')}"

        base_ctx: dict[str, Any] = {
            "username": user.username,
            "current_date": now.strftime("%B %d, %Y"),
            "week_label": week_label,
            "generated_at": now.strftime("%Y-%m-%d %H:%M"),
        }

        if role == "engineer":
            ctx = {**base_ctx, **await self._engineer_context(user, db)}
        elif role == "em":
            ctx = {**base_ctx, **await self._em_context(user, db)}
        else:
            # director / admin
            ctx = {**base_ctx, **await self._director_context(db)}

        return self._render_template(template_name, ctx)

    # -----------------------------------------------------------------------
    # Template rendering
    # -----------------------------------------------------------------------

    def _render_template(self, template_name: str, context: dict[str, Any]) -> str:
        """Render a compiled HTML template with Jinja2.

        Falls back to a plain-text placeholder when the compiled file does not
        exist yet (e.g. in CI or before `mjml` CLI has been run).
        """
        template_path = _TEMPLATES_DIR / template_name
        if not template_path.exists():
            logger.warning(
                "compiled_template_missing",
                template=template_name,
                hint="Run `npx mjml` at Docker build time to compile MJML → HTML",
            )
            return self._fallback_html(context)

        env = _make_jinja_env()
        tmpl = env.get_template(template_name)
        return tmpl.render(**context)

    @staticmethod
    def _fallback_html(ctx: dict[str, Any]) -> str:
        """Minimal HTML returned when compiled templates are absent."""
        return (
            f"<html><body>"
            f"<h2>Engineering Weekly Digest — {ctx.get('week_label', '')}</h2>"
            f"<p>Hi {ctx.get('username', 'there')},</p>"
            f"<p>Your weekly digest is ready. Compiled templates are not available in this environment.</p>"
            f"<p style='color:#94a3b8;font-size:11px;'>Generated at {ctx.get('generated_at', '')} UTC</p>"
            f"</body></html>"
        )

    # -----------------------------------------------------------------------
    # Role-scoped data builders
    # -----------------------------------------------------------------------

    async def _engineer_context(
        self, user: User, db: AsyncSession
    ) -> dict[str, Any]:
        """Fetch engineer-specific metrics from engineer_metric_snapshots."""
        now = datetime.now(tz=timezone.utc)
        week_ago = now - timedelta(days=7)

        # Fetch metrics for this engineer in the last week
        snaps_result = await db.execute(
            select(EngineerMetricSnapshot).where(
                and_(
                    EngineerMetricSnapshot.user_id == user.id,
                    EngineerMetricSnapshot.snapshot_at >= week_ago,
                )
            ).order_by(EngineerMetricSnapshot.snapshot_at.desc())
        )
        snaps = list(snaps_result.scalars().all())

        def _get(key: str, default: Any = 0) -> Any:
            for s in snaps:
                if s.metric_key == key:
                    return float(s.metric_value)
            return default

        avg_cycle_secs = _get("avg_cycle_time_seconds", 0)
        avg_review_secs = _get("avg_first_review_latency_seconds", 0)

        return {
            "prs_authored": int(_get("prs_authored", 0)),
            "prs_merged": int(_get("prs_merged", 0)),
            "avg_cycle_time_hours": round(avg_cycle_secs / 3600, 1) if avg_cycle_secs else "—",
            "prs_reviewed": int(_get("prs_reviewed", 0)),
            "avg_first_review_latency_hours": round(avg_review_secs / 3600, 1) if avg_review_secs else "—",
            "tickets_closed": int(_get("tickets_closed", 0)),
            "carry_overs": int(_get("carry_overs", 0)),
            "pages_this_week": int(_get("pages_this_week", 0)),
        }

    async def _em_context(
        self, user: User, db: AsyncSession
    ) -> dict[str, Any]:
        """Fetch EM's team metrics from team_metric_snapshots."""
        if user.team_id is None:
            return self._em_empty_context()

        team_result = await db.execute(select(Team).where(Team.id == user.team_id))
        team: Team | None = team_result.scalar_one_or_none()
        team_name = team.name if team else "Unknown Team"

        # Latest composite + component scores
        async def _latest_score(component: str) -> float | None:
            result = await db.execute(
                select(TeamMetricSnapshot.score)
                .where(
                    and_(
                        TeamMetricSnapshot.team_id == user.team_id,
                        TeamMetricSnapshot.component == component,
                    )
                )
                .order_by(TeamMetricSnapshot.snapshot_at.desc())
                .limit(1)
            )
            row = result.scalar_one_or_none()
            return float(row) if row is not None else None

        composite = await _latest_score("composite")
        pr_score = await _latest_score("pr_health")
        sprint_score = await _latest_score("sprint_health")
        incident_score = await _latest_score("incident_load")

        # RAG from composite
        if composite is not None:
            rag = "green" if composite >= 70 else "amber" if composite >= 40 else "red"
        else:
            rag = "amber"

        # Latest PR health detail from engineer snapshots (team-wide)
        now = datetime.now(tz=timezone.utc)
        week_ago = now - timedelta(days=7)
        snaps_result = await db.execute(
            select(EngineerMetricSnapshot).where(
                and_(
                    EngineerMetricSnapshot.team_id == user.team_id,
                    EngineerMetricSnapshot.snapshot_at >= week_ago,
                )
            )
        )
        snaps = list(snaps_result.scalars().all())

        def _team_agg(key: str) -> float | None:
            vals = [float(s.metric_value) for s in snaps if s.metric_key == key]
            return sum(vals) / len(vals) if vals else None

        avg_cycle_secs = _team_agg("avg_cycle_time_seconds")
        avg_mtta_secs = _team_agg("avg_mtta_seconds")
        avg_mttr_secs = _team_agg("avg_mttr_seconds")
        stale_count_vals = [float(s.metric_value) for s in snaps if s.metric_key == "stale_pr_count"]
        stale_pr_count = int(sum(stale_count_vals)) if stale_count_vals else 0

        # Sprint velocity trend (last 5 snapshots)
        velocity_result = await db.execute(
            select(TeamMetricSnapshot.score)
            .where(
                and_(
                    TeamMetricSnapshot.team_id == user.team_id,
                    TeamMetricSnapshot.component == "sprint_velocity",
                )
            )
            .order_by(TeamMetricSnapshot.snapshot_at.desc())
            .limit(5)
        )
        velocity_rows = velocity_result.scalars().all()
        velocity_trend = [round(float(v), 0) for v in reversed(velocity_rows)]

        # Sprint completion
        completion_result = await db.execute(
            select(TeamMetricSnapshot.score)
            .where(
                and_(
                    TeamMetricSnapshot.team_id == user.team_id,
                    TeamMetricSnapshot.component == "sprint_completion_pct",
                )
            )
            .order_by(TeamMetricSnapshot.snapshot_at.desc())
            .limit(1)
        )
        sprint_completion = completion_result.scalar_one_or_none()

        # Risk flags
        risk_flags = []
        if stale_pr_count > 5:
            risk_flags.append(f"{stale_pr_count} stale PRs open (>5 threshold)")
        # carry-over
        carry_result = await db.execute(
            select(TeamMetricSnapshot.score)
            .where(
                and_(
                    TeamMetricSnapshot.team_id == user.team_id,
                    TeamMetricSnapshot.component == "carry_over_rate_pct",
                )
            )
            .order_by(TeamMetricSnapshot.snapshot_at.desc())
            .limit(1)
        )
        carry_pct = carry_result.scalar_one_or_none()
        if carry_pct is not None and float(carry_pct) > 20:
            risk_flags.append(f"Carry-over rate {float(carry_pct):.0f}% (>20% threshold)")

        # P1 incidents from engineer snapshots
        p1_counts = [float(s.metric_value) for s in snaps if s.metric_key == "p1_incident_count"]
        total_p1 = int(sum(p1_counts))
        if total_p1 > 0:
            risk_flags.append(f"{total_p1} P1 incident(s) this week")

        # DORA snapshot from latest snapshots
        dora_ctx = await self._dora_context_for_team(user.team_id, db)

        return {
            "team_name": team_name,
            "composite_score": round(composite, 0) if composite is not None else "—",
            "rag": rag,
            "pr_health_score": round(pr_score, 0) if pr_score is not None else None,
            "sprint_health_score": round(sprint_score, 0) if sprint_score is not None else None,
            "incident_load_score": round(incident_score, 0) if incident_score is not None else None,
            "avg_cycle_time_hours": round(avg_cycle_secs / 3600, 1) if avg_cycle_secs else "—",
            "stale_pr_count": stale_pr_count,
            "sprint_completion_pct": round(float(sprint_completion), 0) if sprint_completion is not None else None,
            "velocity_trend": velocity_trend,
            "mtta_minutes": round(avg_mtta_secs / 60, 0) if avg_mtta_secs else "—",
            "mttr_hours": round(avg_mttr_secs / 3600, 1) if avg_mttr_secs else "—",
            "risk_flags": risk_flags,
            **dora_ctx,
        }

    def _em_empty_context(self) -> dict[str, Any]:
        return {
            "team_name": "Unknown",
            "composite_score": "—",
            "rag": "amber",
            "pr_health_score": None,
            "sprint_health_score": None,
            "incident_load_score": None,
            "avg_cycle_time_hours": "—",
            "stale_pr_count": 0,
            "sprint_completion_pct": None,
            "velocity_trend": [],
            "mtta_minutes": "—",
            "mttr_hours": "—",
            "risk_flags": [],
            "dora_deploy_freq": "—",
            "dora_deploy_freq_band": "Low",
            "dora_lead_time": "—",
            "dora_lead_time_band": "Low",
            "dora_cfr": "—",
            "dora_cfr_band": "Low",
            "dora_mttr": "—",
            "dora_mttr_band": "Low",
        }

    async def _director_context(self, db: AsyncSession) -> dict[str, Any]:
        """Fetch all teams' metrics for director/admin digest."""
        teams_result = await db.execute(select(Team).order_by(Team.name))
        teams: list[Team] = list(teams_result.scalars().all())

        teams_data = []
        teams_dora = []
        risk_teams = []
        top_performers = []

        for team in teams:
            # Latest composite score
            comp_result = await db.execute(
                select(TeamMetricSnapshot.score, TeamMetricSnapshot.rag)
                .where(
                    and_(
                        TeamMetricSnapshot.team_id == team.id,
                        TeamMetricSnapshot.component == "composite",
                    )
                )
                .order_by(TeamMetricSnapshot.snapshot_at.desc())
                .limit(1)
            )
            comp_row = comp_result.one_or_none()

            async def _score(comp: str, tid: UUID = team.id) -> float | None:
                r = await db.execute(
                    select(TeamMetricSnapshot.score)
                    .where(
                        and_(
                            TeamMetricSnapshot.team_id == tid,
                            TeamMetricSnapshot.component == comp,
                        )
                    )
                    .order_by(TeamMetricSnapshot.snapshot_at.desc())
                    .limit(1)
                )
                v = r.scalar_one_or_none()
                return float(v) if v is not None else None

            composite_score = float(comp_row[0]) if comp_row else 0.0
            rag = comp_row[1] if comp_row else "amber"
            pr_score = await _score("pr_health")
            sprint_score = await _score("sprint_health")
            incident_score = await _score("incident_load")

            team_entry = {
                "name": team.name,
                "composite_score": composite_score,
                "rag": rag,
                "pr_health_score": round(pr_score, 0) if pr_score else None,
                "sprint_health_score": round(sprint_score, 0) if sprint_score else None,
                "incident_load_score": round(incident_score, 0) if incident_score else None,
            }
            teams_data.append(team_entry)

            # Risk flags for red/amber teams
            if rag in ("red", "amber"):
                issues: list[str] = []
                stale_result = await db.execute(
                    select(TeamMetricSnapshot.score)
                    .where(
                        and_(
                            TeamMetricSnapshot.team_id == team.id,
                            TeamMetricSnapshot.component == "stale_pr_count",
                        )
                    )
                    .order_by(TeamMetricSnapshot.snapshot_at.desc())
                    .limit(1)
                )
                stale_val = stale_result.scalar_one_or_none()
                if stale_val is not None and float(stale_val) > 5:
                    issues.append(f"{int(float(stale_val))} stale PRs")
                carry_result = await db.execute(
                    select(TeamMetricSnapshot.score)
                    .where(
                        and_(
                            TeamMetricSnapshot.team_id == team.id,
                            TeamMetricSnapshot.component == "carry_over_rate_pct",
                        )
                    )
                    .order_by(TeamMetricSnapshot.snapshot_at.desc())
                    .limit(1)
                )
                carry_val = carry_result.scalar_one_or_none()
                if carry_val is not None and float(carry_val) > 20:
                    issues.append(f"{float(carry_val):.0f}% carry-over")
                if issues:
                    risk_teams.append({
                        "name": team.name,
                        "rag": rag,
                        "composite_score": composite_score,
                        "issues": issues,
                    })

            # DORA
            dora_ctx = await self._dora_context_for_team(team.id, db)
            teams_dora.append({
                "name": team.name,
                "deploy_freq_band": dora_ctx.get("dora_deploy_freq_band", "—"),
                "lead_time_band": dora_ctx.get("dora_lead_time_band", "—"),
                "cfr_band": dora_ctx.get("dora_cfr_band", "—"),
                "mttr_band": dora_ctx.get("dora_mttr_band", "—"),
            })

            # Top performers — green teams with score >= 75
            if rag == "green" and composite_score >= 75:
                top_performers.append({
                    "name": team.name,
                    "composite_score": composite_score,
                    "score_delta": None,  # Would need historical comparison
                })

        return {
            "total_teams": len(teams),
            "teams": teams_data,
            "teams_dora": teams_dora,
            "risk_teams": risk_teams,
            "top_performers": top_performers,
        }

    async def _dora_context_for_team(
        self, team_id: UUID, db: AsyncSession
    ) -> dict[str, Any]:
        """Build DORA template variables for a single team."""
        async def _snap(comp: str) -> float | None:
            r = await db.execute(
                select(TeamMetricSnapshot.score)
                .where(
                    and_(
                        TeamMetricSnapshot.team_id == team_id,
                        TeamMetricSnapshot.component == comp,
                    )
                )
                .order_by(TeamMetricSnapshot.snapshot_at.desc())
                .limit(1)
            )
            v = r.scalar_one_or_none()
            return float(v) if v is not None else None

        deploy_freq = await _snap("dora_deployment_frequency")
        lead_secs = await _snap("dora_lead_time_seconds")
        cfr = await _snap("dora_change_failure_rate_pct")
        mttr_secs = await _snap("dora_mttr_seconds")

        def _deploy_band(f: float | None) -> str:
            if f is None:
                return "Low"
            if f >= 1.0:
                return "Elite"
            if f >= 1 / 7:
                return "High"
            if f >= 1 / 30:
                return "Medium"
            return "Low"

        def _lead_band(s: float | None) -> str:
            if s is None:
                return "Low"
            hours = s / 3600
            if hours <= 1:
                return "Elite"
            if hours <= 24:
                return "High"
            if hours <= 168:
                return "Medium"
            return "Low"

        def _cfr_band(pct: float | None) -> str:
            if pct is None:
                return "Low"
            if pct <= 1:
                return "Elite"
            if pct <= 5:
                return "High"
            if pct <= 15:
                return "Medium"
            return "Low"

        def _mttr_band(s: float | None) -> str:
            if s is None:
                return "Low"
            hours = s / 3600
            if hours <= 1:
                return "Elite"
            if hours <= 24:
                return "High"
            if hours <= 168:
                return "Medium"
            return "Low"

        lead_fmt = f"{round(lead_secs / 3600, 1)}h" if lead_secs else "—"
        mttr_fmt = f"{round(mttr_secs / 3600, 1)}h" if mttr_secs else "—"

        return {
            "dora_deploy_freq": round(deploy_freq, 2) if deploy_freq else "—",
            "dora_deploy_freq_band": _deploy_band(deploy_freq),
            "dora_lead_time": lead_fmt,
            "dora_lead_time_band": _lead_band(lead_secs),
            "dora_cfr": round(cfr, 1) if cfr else "—",
            "dora_cfr_band": _cfr_band(cfr),
            "dora_mttr": mttr_fmt,
            "dora_mttr_band": _mttr_band(mttr_secs),
        }
