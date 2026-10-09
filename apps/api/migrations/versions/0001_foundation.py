"""Create the production planning hierarchy.

Revision ID: 0001_foundation
Revises:
"""

from alembic import op
import sqlalchemy as sa

revision = "0001_foundation"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workspaces",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("workspace_id", "email"),
    )
    op.create_index("ix_users_workspace_id", "users", ["workspace_id"])
    op.create_table(
        "series",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("genre", sa.String(80), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_series_workspace_id", "series", ["workspace_id"])
    op.create_table(
        "episodes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("series_id", sa.Uuid(), sa.ForeignKey("series.id", ondelete="CASCADE"), nullable=False),
        sa.Column("episode_number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.UniqueConstraint("series_id", "episode_number"),
        sa.CheckConstraint("episode_number > 0", name="episode_number_positive"),
    )
    op.create_index("ix_episodes_series_id", "episodes", ["series_id"])
    op.create_table(
        "scenes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("episode_id", sa.Uuid(), sa.ForeignKey("episodes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scene_number", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("location", sa.String(160), nullable=False),
        sa.Column("time_of_day", sa.String(80), nullable=False),
        sa.UniqueConstraint("episode_id", "scene_number"),
        sa.CheckConstraint("scene_number > 0", name="scene_number_positive"),
    )
    op.create_index("ix_scenes_episode_id", "scenes", ["episode_id"])
    op.create_table(
        "shots",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("scene_id", sa.Uuid(), sa.ForeignKey("scenes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("shot_number", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("shot_type", sa.String(80), nullable=False),
        sa.Column("duration_seconds", sa.Numeric(8, 2), nullable=False),
        sa.Column("number_of_characters", sa.Integer(), nullable=False),
        sa.Column("dialogue_present", sa.Boolean(), nullable=False),
        sa.Column("object_interaction", sa.Boolean(), nullable=False),
        sa.Column("motion_complexity", sa.String(16), nullable=False),
        sa.Column("camera_motion", sa.String(80), nullable=False),
        sa.Column("quality_threshold", sa.String(16), nullable=False),
        sa.Column("budget_limit", sa.Numeric(12, 4), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.UniqueConstraint("scene_id", "shot_number"),
        sa.CheckConstraint("shot_number > 0", name="shot_number_positive"),
        sa.CheckConstraint("duration_seconds > 0", name="shot_duration_positive"),
        sa.CheckConstraint("number_of_characters >= 0", name="shot_characters_nonnegative"),
        sa.CheckConstraint("budget_limit IS NULL OR budget_limit >= 0", name="shot_budget_nonnegative"),
    )
    op.create_index("ix_shots_scene_id", "shots", ["scene_id"])


def downgrade() -> None:
    op.drop_table("shots")
    op.drop_table("scenes")
    op.drop_table("episodes")
    op.drop_table("series")
    op.drop_table("users")
    op.drop_table("workspaces")
