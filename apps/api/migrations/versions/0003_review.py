"""Immutable human reviews.

Revision ID: 0003_review
Revises: 0002_generation
"""

from alembic import op
import sqlalchemy as sa

revision = "0003_review"
down_revision = "0002_generation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "reviews",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("generation_attempt_id", sa.Uuid(), sa.ForeignKey("generation_attempts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("reviewer_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("decision", sa.String(16), nullable=False),
        sa.Column("failure_reason", sa.String(64), nullable=True),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("generation_attempt_id"),
        sa.CheckConstraint("decision IN ('accepted', 'rejected')", name="review_decision_valid"),
        sa.CheckConstraint(
            "(decision = 'accepted' AND failure_reason IS NULL) OR "
            "(decision = 'rejected' AND failure_reason IS NOT NULL)",
            name="review_reason_matches_decision",
        ),
    )
    op.create_index("ix_reviews_generation_attempt_id", "reviews", ["generation_attempt_id"])
    op.create_index("ix_reviews_reviewer_id", "reviews", ["reviewer_id"])


def downgrade() -> None:
    op.drop_table("reviews")
