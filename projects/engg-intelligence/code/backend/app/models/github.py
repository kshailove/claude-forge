"""GitHub ORM models: PullRequest, PRReview, Commit, GithubRelease."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy import Uuid as UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class PullRequest(Base):
    __tablename__ = "pull_requests"
    __table_args__ = (
        UniqueConstraint("repo_full_name", "pr_number", name="uq_prs_repo_number"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    github_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)
    repo_full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    pr_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    author_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    state: Mapped[str] = mapped_column(String(10), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    merged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    first_review_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cycle_time_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pr_size_additions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pr_size_deletions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    base_branch: Mapped[str] = mapped_column(String(255), nullable=False)
    head_branch: Mapped[str] = mapped_column(String(255), nullable=False)
    team_id: Mapped[uuid.UUID] = mapped_column(
        UUID(),
        ForeignKey("teams.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_activity_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    author: Mapped["User | None"] = relationship("User", foreign_keys=[author_user_id])  # type: ignore[name-defined]
    team: Mapped["Team"] = relationship("Team")  # type: ignore[name-defined]
    reviews: Mapped[list["PRReview"]] = relationship(
        "PRReview", back_populates="pull_request", cascade="all, delete-orphan"
    )
    commits: Mapped[list["Commit"]] = relationship(
        "Commit", back_populates="pull_request"
    )

    def __repr__(self) -> str:
        return f"<PullRequest #{self.pr_number} repo={self.repo_full_name!r} state={self.state!r}>"


class PRReview(Base):
    __tablename__ = "pr_reviews"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    github_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)
    pr_id: Mapped[uuid.UUID] = mapped_column(
        UUID(),
        ForeignKey("pull_requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    reviewer_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    state: Mapped[str] = mapped_column(String(25), nullable=False)
    comment_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    pull_request: Mapped["PullRequest"] = relationship("PullRequest", back_populates="reviews")
    reviewer: Mapped["User | None"] = relationship("User", foreign_keys=[reviewer_user_id])  # type: ignore[name-defined]


class Commit(Base):
    __tablename__ = "commits"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    sha: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    repo_full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    author_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    committed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    pr_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(),
        ForeignKey("pull_requests.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    author: Mapped["User | None"] = relationship("User", foreign_keys=[author_user_id])  # type: ignore[name-defined]
    pull_request: Mapped["PullRequest | None"] = relationship(
        "PullRequest", back_populates="commits"
    )


class GithubRelease(Base):
    __tablename__ = "github_releases"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    release_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)
    repo_full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    tag_name: Mapped[str] = mapped_column(String(255), nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    team_id: Mapped[uuid.UUID] = mapped_column(
        UUID(),
        ForeignKey("teams.id", ondelete="CASCADE"),
        nullable=False,
    )

    team: Mapped["Team"] = relationship("Team")  # type: ignore[name-defined]
