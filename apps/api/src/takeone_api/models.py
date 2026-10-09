import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def new_id() -> uuid.UUID:
    return uuid.uuid4()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("workspace_id", "email"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    email: Mapped[str] = mapped_column(String(320))
    role: Mapped[str] = mapped_column(String(32), default="owner")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Series(Base):
    __tablename__ = "series"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    genre: Mapped[str] = mapped_column(String(80), default="")
    status: Mapped[str] = mapped_column(String(32), default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    episodes: Mapped[list["Episode"]] = relationship(back_populates="series")


class Character(Base):
    __tablename__ = "characters"
    __table_args__ = (UniqueConstraint("series_id", "name"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    series_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("series.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text, default="")
    visual_reference_url: Mapped[str] = mapped_column(Text, default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    states: Mapped[list["CharacterState"]] = relationship(cascade="all, delete-orphan")


class CharacterState(Base):
    __tablename__ = "character_states"
    __table_args__ = (CheckConstraint("episode_start > 0 AND episode_end >= episode_start", name="character_state_range_valid"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    character_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("characters.id", ondelete="CASCADE"), index=True)
    episode_start: Mapped[int] = mapped_column(Integer)
    episode_end: Mapped[int] = mapped_column(Integer)
    hairstyle: Mapped[str] = mapped_column(String(160), default="")
    wardrobe: Mapped[str] = mapped_column(String(160), default="")
    injury_state: Mapped[str] = mapped_column(String(160), default="")
    props: Mapped[str] = mapped_column(Text, default="")
    notes: Mapped[str] = mapped_column(Text, default="")


class Episode(Base):
    __tablename__ = "episodes"
    __table_args__ = (
        UniqueConstraint("series_id", "episode_number"),
        CheckConstraint("episode_number > 0", name="episode_number_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    series_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("series.id", ondelete="CASCADE"), index=True)
    episode_number: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(32), default="draft")
    series: Mapped[Series] = relationship(back_populates="episodes")
    scenes: Mapped[list["Scene"]] = relationship(back_populates="episode")


class Scene(Base):
    __tablename__ = "scenes"
    __table_args__ = (
        UniqueConstraint("episode_id", "scene_number"),
        CheckConstraint("scene_number > 0", name="scene_number_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    episode_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("episodes.id", ondelete="CASCADE"), index=True)
    scene_number: Mapped[int] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(Text, default="")
    location: Mapped[str] = mapped_column(String(160), default="")
    time_of_day: Mapped[str] = mapped_column(String(80), default="")
    episode: Mapped[Episode] = relationship(back_populates="scenes")
    shots: Mapped[list["Shot"]] = relationship(back_populates="scene")


class Shot(Base):
    __tablename__ = "shots"
    __table_args__ = (
        UniqueConstraint("scene_id", "shot_number"),
        CheckConstraint("shot_number > 0", name="shot_number_positive"),
        CheckConstraint("duration_seconds > 0", name="shot_duration_positive"),
        CheckConstraint("number_of_characters >= 0", name="shot_characters_nonnegative"),
        CheckConstraint("budget_limit IS NULL OR budget_limit >= 0", name="shot_budget_nonnegative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    scene_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("scenes.id", ondelete="CASCADE"), index=True)
    shot_number: Mapped[int] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(Text, default="")
    shot_type: Mapped[str] = mapped_column(String(80), default="")
    duration_seconds: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    number_of_characters: Mapped[int] = mapped_column(Integer, default=0)
    dialogue_present: Mapped[bool] = mapped_column(Boolean, default=False)
    object_interaction: Mapped[bool] = mapped_column(Boolean, default=False)
    motion_complexity: Mapped[str] = mapped_column(String(16), default="low")
    camera_motion: Mapped[str] = mapped_column(String(80), default="static")
    quality_threshold: Mapped[str] = mapped_column(String(16), default="standard")
    budget_limit: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="draft")
    scene: Mapped[Scene] = relationship(back_populates="shots")


class ShotSpec(Base):
    __tablename__ = "shot_specs"

    shot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("shots.id", ondelete="CASCADE"), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    character_ids: Mapped[list] = mapped_column(JSON, default=list)
    location: Mapped[str] = mapped_column(String(160), default="")
    action: Mapped[str] = mapped_column(Text, default="")
    dialogue: Mapped[str] = mapped_column(Text, default="")
    continuity_notes: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class RoutingDecision(Base):
    __tablename__ = "routing_decisions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    shot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("shots.id", ondelete="CASCADE"), index=True)
    spec_version: Mapped[int] = mapped_column(Integer)
    provider: Mapped[str] = mapped_column(String(80))
    model: Mapped[str] = mapped_column(String(80))
    reason: Mapped[str] = mapped_column(Text)
    estimated_cost: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    confidence: Mapped[str] = mapped_column(String(16))
    rule_version: Mapped[str] = mapped_column(String(32))
    is_mock: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class GenerationAttempt(Base):
    __tablename__ = "generation_attempts"
    __table_args__ = (
        UniqueConstraint("shot_id", "attempt_number"),
        UniqueConstraint("idempotency_key"),
        UniqueConstraint("provider", "provider_job_id"),
        CheckConstraint("attempt_number > 0", name="attempt_number_positive"),
        CheckConstraint("estimated_cost >= 0", name="attempt_estimate_nonnegative"),
        CheckConstraint("actual_cost IS NULL OR actual_cost >= 0", name="attempt_actual_nonnegative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    shot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("shots.id", ondelete="CASCADE"), index=True)
    attempt_number: Mapped[int] = mapped_column(Integer)
    idempotency_key: Mapped[str] = mapped_column(String(120))
    provider: Mapped[str] = mapped_column(String(80))
    model: Mapped[str] = mapped_column(String(80))
    prompt: Mapped[str] = mapped_column(Text)
    creative_direction: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_source: Mapped[str] = mapped_column(String(20), default="manual")
    shot_snapshot: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(32), default="queued")
    provider_job_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    output_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_media_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    estimated_cost: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    actual_cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    cost_kind: Mapped[str | None] = mapped_column(String(20), nullable=True)
    generation_time_seconds: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review: Mapped["Review | None"] = relationship(back_populates="attempt", uselist=False)


class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (
        UniqueConstraint("generation_attempt_id"),
        CheckConstraint("decision IN ('accepted', 'rejected')", name="review_decision_valid"),
        CheckConstraint(
            "(decision = 'accepted' AND failure_reason IS NULL) OR "
            "(decision = 'rejected' AND failure_reason IS NOT NULL)",
            name="review_reason_matches_decision",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    generation_attempt_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("generation_attempts.id", ondelete="CASCADE"), index=True)
    reviewer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    decision: Mapped[str] = mapped_column(String(16))
    failure_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    attempt: Mapped[GenerationAttempt] = relationship(back_populates="review")


class CostEvent(Base):
    __tablename__ = "cost_events"
    __table_args__ = (
        UniqueConstraint("event_key"),
        CheckConstraint("amount_usd >= 0", name="cost_amount_nonnegative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    series_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("series.id", ondelete="CASCADE"), index=True)
    shot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("shots.id", ondelete="CASCADE"), index=True)
    generation_attempt_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("generation_attempts.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(80))
    model: Mapped[str] = mapped_column(String(80))
    operation: Mapped[str] = mapped_column(String(40))
    amount_usd: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    amount_kind: Mapped[str] = mapped_column(String(20))
    event_key: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
