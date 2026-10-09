from dataclasses import asdict
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .auth import CurrentUser, current_user
from .db import get_db
from .generation import GenerationError, create_attempt, scoped_shot, spec_from_shot
from .models import CostEvent, Episode, GenerationAttempt, Scene, Series, Shot
from .providers import providers
from .schemas import ReviewRead
from .temporal_dispatch import TemporalDispatcher, get_dispatcher

router = APIRouter(prefix="/api/v1")


class AttemptCreate(BaseModel):
    provider: str = "mock"
    model: str = "mock-v1"
    prompt: str | None = Field(default=None, max_length=10000)
    creative_direction: str | None = Field(default=None, max_length=5000)


class ReadModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class AttemptRead(ReadModel):
    id: UUID
    shot_id: UUID
    attempt_number: int
    provider: str
    model: str
    prompt: str
    creative_direction: str | None
    prompt_source: str
    shot_snapshot: dict
    status: str
    provider_job_id: str | None
    output_url: str | None
    output_media_type: str | None
    estimated_cost: Decimal
    actual_cost: Decimal | None
    cost_kind: str | None
    generation_time_seconds: Decimal | None
    error_message: str | None
    created_at: datetime
    completed_at: datetime | None
    review: ReviewRead | None


class CostEventRead(ReadModel):
    id: UUID
    generation_attempt_id: UUID
    provider: str
    model: str
    operation: str
    amount_usd: Decimal
    amount_kind: str
    created_at: datetime


def attempt_for(db: Session, owner: CurrentUser, attempt_id: UUID) -> GenerationAttempt:
    attempt = db.scalar(
        select(GenerationAttempt).join(Shot).join(Scene).join(Episode).join(Series)
        .where(GenerationAttempt.id == attempt_id, Series.workspace_id == owner.workspace_id)
    )
    if attempt is None:
        raise HTTPException(status_code=404, detail="Attempt not found")
    return attempt


@router.get("/settings/providers")
def list_providers(owner: CurrentUser = Depends(current_user)):
    return [
        {**asdict(item), "max_duration_seconds": str(item.max_duration_seconds)}
        for item in providers.capabilities()
    ]


@router.get("/shots/{shot_id}/estimate")
def estimate_shot(
    shot_id: UUID, provider: str = Query(default="mock"), model: str = Query(default="mock-v1"),
    owner: CurrentUser = Depends(current_user), db: Session = Depends(get_db),
):
    try:
        shot = scoped_shot(db, shot_id, owner.workspace_id)
        amount = providers.get(provider).estimate_cost(spec_from_shot(shot), model)
    except GenerationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"provider": provider, "model": model, "estimated_cost": str(amount), "budget_limit": str(shot.budget_limit) if shot.budget_limit is not None else None, "over_budget": shot.budget_limit is not None and amount > shot.budget_limit}


@router.post("/shots/{shot_id}/attempts", response_model=AttemptRead, status_code=202)
async def submit_attempt(
    shot_id: UUID, payload: AttemptCreate,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=120),
    owner: CurrentUser = Depends(current_user), db: Session = Depends(get_db),
    dispatcher: TemporalDispatcher = Depends(get_dispatcher),
):
    try:
        attempt, _ = create_attempt(
            db, workspace_id=owner.workspace_id, shot_id=shot_id, provider_name=payload.provider,
            model=payload.model, prompt=payload.prompt, creative_direction=payload.creative_direction,
            idempotency_key=idempotency_key,
            registry=providers,
        )
    except GenerationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Attempt already exists; retry with the same idempotency key") from exc
    if attempt.status == "queued":
        try:
            await dispatcher.start(attempt.id)
        except Exception as exc:
            # The start may have reached Temporal. The attempt stays queued and
            # the same idempotency key safely retries its deterministic workflow ID.
            raise HTTPException(status_code=503, detail="Workflow dispatch unavailable; retry with the same Idempotency-Key") from exc
        db.refresh(attempt)
    return attempt


@router.get("/shots/{shot_id}/attempts", response_model=list[AttemptRead])
def list_attempts(shot_id: UUID, owner: CurrentUser = Depends(current_user), db: Session = Depends(get_db)):
    try:
        scoped_shot(db, shot_id, owner.workspace_id)
    except GenerationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return db.scalars(select(GenerationAttempt).where(GenerationAttempt.shot_id == shot_id).order_by(GenerationAttempt.attempt_number)).all()


@router.get("/attempts/{attempt_id}", response_model=AttemptRead)
def get_attempt(attempt_id: UUID, owner: CurrentUser = Depends(current_user), db: Session = Depends(get_db)):
    return attempt_for(db, owner, attempt_id)


@router.get("/attempts/{attempt_id}/cost-events", response_model=list[CostEventRead])
def list_cost_events(attempt_id: UUID, owner: CurrentUser = Depends(current_user), db: Session = Depends(get_db)):
    attempt_for(db, owner, attempt_id)
    return db.scalars(select(CostEvent).where(CostEvent.generation_attempt_id == attempt_id).order_by(CostEvent.created_at)).all()


@router.post("/attempts/{attempt_id}/cancel", status_code=202)
async def cancel_attempt(
    attempt_id: UUID, owner: CurrentUser = Depends(current_user), db: Session = Depends(get_db),
    dispatcher: TemporalDispatcher = Depends(get_dispatcher),
):
    attempt = attempt_for(db, owner, attempt_id)
    if attempt.status in ("review", "failed", "cancelled", "dispatch_failed"):
        raise HTTPException(status_code=409, detail="Attempt has already finished")
    try:
        await dispatcher.cancel(attempt_id)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Workflow cancellation unavailable") from exc
    return {"status": "requested"}
