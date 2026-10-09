"""Generation attempts and explicit cost ledger.

Revision ID: 0002_generation
Revises: 0001_foundation
"""

from alembic import op
import sqlalchemy as sa

revision = "0002_generation"
down_revision = "0001_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "generation_attempts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("shot_id", sa.Uuid(), sa.ForeignKey("shots.id", ondelete="CASCADE"), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(120), nullable=False),
        sa.Column("provider", sa.String(80), nullable=False),
        sa.Column("model", sa.String(80), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("shot_snapshot", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("provider_job_id", sa.String(200), nullable=True),
        sa.Column("output_url", sa.Text(), nullable=True),
        sa.Column("output_media_type", sa.String(80), nullable=True),
        sa.Column("estimated_cost", sa.Numeric(12, 4), nullable=False),
        sa.Column("actual_cost", sa.Numeric(12, 4), nullable=True),
        sa.Column("cost_kind", sa.String(20), nullable=True),
        sa.Column("generation_time_seconds", sa.Numeric(10, 2), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("shot_id", "attempt_number"),
        sa.UniqueConstraint("idempotency_key"),
        sa.UniqueConstraint("provider", "provider_job_id"),
        sa.CheckConstraint("attempt_number > 0", name="attempt_number_positive"),
        sa.CheckConstraint("estimated_cost >= 0", name="attempt_estimate_nonnegative"),
        sa.CheckConstraint("actual_cost IS NULL OR actual_cost >= 0", name="attempt_actual_nonnegative"),
    )
    op.create_index("ix_generation_attempts_shot_id", "generation_attempts", ["shot_id"])
    op.create_table(
        "cost_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("series_id", sa.Uuid(), sa.ForeignKey("series.id", ondelete="CASCADE"), nullable=False),
        sa.Column("shot_id", sa.Uuid(), sa.ForeignKey("shots.id", ondelete="CASCADE"), nullable=False),
        sa.Column("generation_attempt_id", sa.Uuid(), sa.ForeignKey("generation_attempts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(80), nullable=False),
        sa.Column("model", sa.String(80), nullable=False),
        sa.Column("operation", sa.String(40), nullable=False),
        sa.Column("amount_usd", sa.Numeric(12, 4), nullable=False),
        sa.Column("amount_kind", sa.String(20), nullable=False),
        sa.Column("event_key", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("event_key"),
        sa.CheckConstraint("amount_usd >= 0", name="cost_amount_nonnegative"),
    )
    op.create_index("ix_cost_events_workspace_id", "cost_events", ["workspace_id"])
    op.create_index("ix_cost_events_series_id", "cost_events", ["series_id"])
    op.create_index("ix_cost_events_shot_id", "cost_events", ["shot_id"])
    op.create_index("ix_cost_events_generation_attempt_id", "cost_events", ["generation_attempt_id"])


def downgrade() -> None:
    op.drop_table("cost_events")
    op.drop_table("generation_attempts")
