"""Structured shots, continuity, and routing decisions.

Revision ID: 0004_shot_specs
Revises: 0003_review
"""

from alembic import op
import sqlalchemy as sa

revision = "0004_shot_specs"
down_revision = "0003_review"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "characters",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("series_id", sa.Uuid(), sa.ForeignKey("series.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("visual_reference_url", sa.Text(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.UniqueConstraint("series_id", "name"),
    )
    op.create_index("ix_characters_series_id", "characters", ["series_id"])
    op.create_table(
        "character_states",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("character_id", sa.Uuid(), sa.ForeignKey("characters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("episode_start", sa.Integer(), nullable=False),
        sa.Column("episode_end", sa.Integer(), nullable=False),
        sa.Column("hairstyle", sa.String(160), nullable=False),
        sa.Column("wardrobe", sa.String(160), nullable=False),
        sa.Column("injury_state", sa.String(160), nullable=False),
        sa.Column("props", sa.Text(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.CheckConstraint("episode_start > 0 AND episode_end >= episode_start", name="character_state_range_valid"),
    )
    op.create_index("ix_character_states_character_id", "character_states", ["character_id"])
    op.create_table(
        "shot_specs",
        sa.Column("shot_id", sa.Uuid(), sa.ForeignKey("shots.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("character_ids", sa.JSON(), nullable=False),
        sa.Column("location", sa.String(160), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("dialogue", sa.Text(), nullable=False),
        sa.Column("continuity_notes", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "routing_decisions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("shot_id", sa.Uuid(), sa.ForeignKey("shots.id", ondelete="CASCADE"), nullable=False),
        sa.Column("spec_version", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(80), nullable=False),
        sa.Column("model", sa.String(80), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("estimated_cost", sa.Numeric(12, 4), nullable=False),
        sa.Column("confidence", sa.String(16), nullable=False),
        sa.Column("rule_version", sa.String(32), nullable=False),
        sa.Column("is_mock", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_routing_decisions_shot_id", "routing_decisions", ["shot_id"])
    op.add_column("generation_attempts", sa.Column("creative_direction", sa.Text(), nullable=True))
    op.add_column("generation_attempts", sa.Column("prompt_source", sa.String(20), nullable=False, server_default="manual"))


def downgrade() -> None:
    op.drop_column("generation_attempts", "prompt_source")
    op.drop_column("generation_attempts", "creative_direction")
    op.drop_table("routing_decisions")
    op.drop_table("shot_specs")
    op.drop_table("character_states")
    op.drop_table("characters")
