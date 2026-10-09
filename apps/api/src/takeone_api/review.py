"""Human review transitions. A generation result has at most one final review."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .models import Episode, GenerationAttempt, Review, Scene, Series, Shot


FAILURE_REASONS = (
    "identity_drift", "wardrobe_inconsistency", "prop_inconsistency",
    "location_inconsistency", "bad_motion", "bad_hands",
    "object_interaction_failure", "lip_sync", "story_mismatch",
    "camera_issue", "low_quality", "other",
)


class ReviewError(Exception):
    def __init__(self, message: str, status_code: int = 409):
        super().__init__(message)
        self.status_code = status_code


def record_review(
    db: Session, *, workspace_id: UUID, reviewer_id: UUID, attempt_id: UUID,
    decision: str, failure_reason: str | None, notes: str,
) -> Review:
    if decision not in ("accepted", "rejected"):
        raise ReviewError("Decision must be accepted or rejected", 422)
    if decision == "rejected" and failure_reason not in FAILURE_REASONS:
        raise ReviewError("A valid failure reason is required for rejection", 422)
    if decision == "accepted" and failure_reason is not None:
        raise ReviewError("Accepted reviews cannot have a failure reason", 422)

    shot = db.scalar(
        select(Shot).join(Scene).join(Episode).join(Series)
        .join(GenerationAttempt, GenerationAttempt.shot_id == Shot.id)
        .where(GenerationAttempt.id == attempt_id, Series.workspace_id == workspace_id)
        .with_for_update(of=Shot)
    )
    if shot is None:
        raise ReviewError("Attempt not found", 404)
    attempt = db.get(GenerationAttempt, attempt_id)
    if attempt.status != "review" or shot.status != "review":
        raise ReviewError("Attempt is not awaiting review")
    if db.scalar(select(Review.id).where(Review.generation_attempt_id == attempt_id)) is not None:
        raise ReviewError("Attempt was already reviewed")
    review = Review(
        generation_attempt_id=attempt_id, reviewer_id=reviewer_id,
        decision=decision, failure_reason=failure_reason, notes=notes.strip(),
    )
    db.add(review)
    shot.status = decision
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ReviewError("Attempt was already reviewed") from exc
    db.refresh(review)
    return review
