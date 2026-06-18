"""ORM models package.

Import all models here so that:
  1. Alembic migrations can discover all tables via Base.metadata.
  2. Circular FK references are resolved (users↔teams).
"""
from app.core.database import Base  # noqa: F401

# Import all model modules (order matters for circular FK resolution)
from app.models.user import User  # noqa: F401
from app.models.team import Team, TeamMembership, OrgNode  # noqa: F401
from app.models.integration import Integration, IdentityMapping  # noqa: F401
from app.models.github import PullRequest, PRReview, Commit, GithubRelease  # noqa: F401
from app.models.tickets import Sprint, Ticket, TicketStateTransition  # noqa: F401
from app.models.incidents import (  # noqa: F401
    Incident,
    IncidentAssignment,
    OncallSchedule,
    OncallShift,
)
from app.models.slack import SlackActivityBucket  # noqa: F401
from app.models.metrics import TeamMetricSnapshot, EngineerMetricSnapshot  # noqa: F401
from app.models.digest import DigestRun, DigestEmail  # noqa: F401
from app.models.nightly import NightlyRun  # noqa: F401
from app.models.backfill import BackfillJob  # noqa: F401

__all__ = [
    "Base",
    "User",
    "Team",
    "TeamMembership",
    "OrgNode",
    "Integration",
    "IdentityMapping",
    "PullRequest",
    "PRReview",
    "Commit",
    "GithubRelease",
    "Sprint",
    "Ticket",
    "TicketStateTransition",
    "Incident",
    "IncidentAssignment",
    "OncallSchedule",
    "OncallShift",
    "SlackActivityBucket",
    "TeamMetricSnapshot",
    "EngineerMetricSnapshot",
    "DigestRun",
    "DigestEmail",
    "NightlyRun",
    "BackfillJob",
]
