from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .auth import CurrentUser, current_user
from .db import get_db
from .generation import GenerationError, create_attempt, scoped_shot
from .generation_routes import AttemptRead
from .models import Episode, GenerationAttempt, Review, Scene, Series, Shot, ShotSpec
from .providers import providers
from .review import FAILURE_REASONS, ReviewError, record_review
from .schemas import ReviewRead, ShotRead
from .temporal_dispatch import TemporalDispatcher, get_dispatcher

router = APIRouter(prefix="/api/v1")


class ReviewCreate(BaseModel):
    decision: str
    failure_reason: str | None = None
    notes: str = Field(default="", max_length=5000)


class RetryCreate(BaseModel):
    provider: str | None = None
    model: str | None = None
    prompt: str | None = Field(default=None, min_length=1, max_length=10000)
    creative_direction: str | None = Field(default=None, max_length=5000)


class ReviewQueueItem(BaseModel):
    attempt: AttemptRead
    shot: ShotRead
    series_title: str
    episode_number: int
    scene_number: int


@router.get("/review/failure-reasons", response_model=list[str])
def failure_reasons(owner: CurrentUser = Depends(current_user)):
    return list(FAILURE_REASONS)


@router.get("/review", response_model=list[ReviewQueueItem])
def review_queue(owner: CurrentUser = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.execute(
        select(GenerationAttempt, Shot, Series.title, Episode.episode_number, Scene.scene_number)
        .join(Shot, GenerationAttempt.shot_id == Shot.id)
        .join(Scene, Shot.scene_id == Scene.id)
        .join(Episode, Scene.episode_id == Episode.id)
        .join(Series, Episode.series_id == Series.id)
        .outerjoin(Review, Review.generation_attempt_id == GenerationAttempt.id)
        .where(
            Series.workspace_id == owner.workspace_id,
            Shot.status == "review", GenerationAttempt.status == "review", Review.id.is_(None),
        )
        .order_by(GenerationAttempt.completed_at, GenerationAttempt.id)
    ).all()
    return [
        ReviewQueueItem(
            attempt=AttemptRead.model_validate(attempt), shot=ShotRead.model_validate(shot),
            series_title=series_title, episode_number=episode_number, scene_number=scene_number,
        )
        for attempt, shot, series_title, episode_number, scene_number in rows
    ]


@router.post("/attempts/{attempt_id}/reviews", response_model=ReviewRead, status_code=201)
def submit_review(
    attempt_id: UUID, payload: ReviewCreate, owner: CurrentUser = Depends(current_user),
    db: Session = Depends(get_db),
):
    try:
        return record_review(
            db, workspace_id=owner.workspace_id, reviewer_id=owner.id,
            attempt_id=attempt_id, decision=payload.decision,
            failure_reason=payload.failure_reason, notes=payload.notes,
        )
    except ReviewError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.post("/shots/{shot_id}/retry", response_model=AttemptRead, status_code=202)
async def retry_shot(
    shot_id: UUID, payload: RetryCreate,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=120),
    owner: CurrentUser = Depends(current_user), db: Session = Depends(get_db),
    dispatcher: TemporalDispatcher = Depends(get_dispatcher),
):
    try:
        shot = scoped_shot(db, shot_id, owner.workspace_id)
    except GenerationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    existing = db.scalar(select(GenerationAttempt).where(GenerationAttempt.idempotency_key == idempotency_key))
    if existing is not None and existing.shot_id == shot_id:
        prior = db.scalar(
            select(GenerationAttempt).where(
                GenerationAttempt.shot_id == shot_id,
                GenerationAttempt.attempt_number == existing.attempt_number - 1,
            )
        )
        if prior is None or prior.review is None or prior.review.decision != "rejected":
            raise HTTPException(status_code=409, detail="Idempotency key was not used for a review retry")
        source = existing
    else:
        if shot.status != "rejected":
            raise HTTPException(status_code=409, detail="Shot must be Rejected before retry")
        source = db.scalar(
            select(GenerationAttempt).where(GenerationAttempt.shot_id == shot_id)
            .order_by(GenerationAttempt.attempt_number.desc()).limit(1)
        )
        if source is None or source.review is None or source.review.decision != "rejected":
            raise HTTPException(status_code=409, detail="Latest attempt must have a rejection")
    provider_name = payload.provider or source.provider
    try:
        default_model = providers.get(provider_name).capabilities().models[0]
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    model = payload.model or (source.model if provider_name == source.provider else default_model)
    structured = db.get(ShotSpec, shot_id) is not None
    prompt = payload.prompt if payload.prompt is not None else (source.prompt if source.prompt_source == "manual" and not structured else None)
    direction = payload.creative_direction if payload.creative_direction is not None else source.creative_direction
    try:
        attempt, _ = create_attempt(
            db, workspace_id=owner.workspace_id, shot_id=shot_id, provider_name=provider_name,
            model=model, prompt=prompt, creative_direction=direction, idempotency_key=idempotency_key,
            registry=providers, allowed_states=("rejected",),
        )
    except GenerationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Retry already exists; use the same Idempotency-Key") from exc
    if attempt.status == "queued":
        try:
            await dispatcher.start(attempt.id)
        except Exception as exc:
            raise HTTPException(status_code=503, detail="Workflow dispatch unavailable; retry with the same Idempotency-Key") from exc
        db.refresh(attempt)
    return attempt
