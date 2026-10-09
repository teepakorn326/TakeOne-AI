"""Attempt state and accounting live here; HTTP and Temporal call the same rules."""

from datetime import timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker
from temporalio import activity

from .models import CostEvent, Episode, GenerationAttempt, Scene, Series, Shot, ShotSpec, utc_now
from .providers import GenerationSpec, ProviderJobStatus, ProviderRegistry


class GenerationError(Exception):
    def __init__(self, message: str, status_code: int = 409):
        super().__init__(message)
        self.status_code = status_code


def spec_from_shot(shot: Shot) -> GenerationSpec:
    return GenerationSpec(
        description=shot.description, shot_type=shot.shot_type,
        duration_seconds=shot.duration_seconds, number_of_characters=shot.number_of_characters,
        dialogue_present=shot.dialogue_present, object_interaction=shot.object_interaction,
        motion_complexity=shot.motion_complexity, camera_motion=shot.camera_motion,
        quality_threshold=shot.quality_threshold,
    )


def scoped_shot(db: Session, shot_id: UUID, workspace_id: UUID, lock: bool = False) -> Shot:
    query = select(Shot).join(Scene).join(Episode).join(Series).where(Shot.id == shot_id, Series.workspace_id == workspace_id)
    if lock:
        query = query.with_for_update(of=Shot)
    shot = db.scalar(query)
    if shot is None:
        raise GenerationError("Shot not found", 404)
    return shot


def create_attempt(
    db: Session, *, workspace_id: UUID, shot_id: UUID, provider_name: str,
    model: str, prompt: str | None, idempotency_key: str, registry: ProviderRegistry,
    creative_direction: str | None = None,
    allowed_states: tuple[str, ...] = ("ready", "failed"),
) -> tuple[GenerationAttempt, bool]:
    direction = (creative_direction or "").strip()

    def same_inputs(existing: GenerationAttempt) -> bool:
        if (existing.provider, existing.model) != (provider_name, model):
            return False
        if existing.prompt_source == "structured":
            return existing.creative_direction == direction and not (prompt or "").strip()
        return existing.prompt == (prompt or "").strip() and not direction

    existing = db.scalar(select(GenerationAttempt).where(GenerationAttempt.idempotency_key == idempotency_key))
    if existing is not None:
        if existing.shot_id != shot_id:
            raise GenerationError("Idempotency key was used for another shot")
        scoped_shot(db, shot_id, workspace_id)
        if not same_inputs(existing):
            raise GenerationError("Idempotency key was used with different generation inputs")
        return existing, False

    shot = scoped_shot(db, shot_id, workspace_id, lock=True)
    existing = db.scalar(select(GenerationAttempt).where(GenerationAttempt.idempotency_key == idempotency_key))
    if existing is not None:
        if existing.shot_id != shot_id:
            raise GenerationError("Idempotency key was used for another shot")
        if not same_inputs(existing):
            raise GenerationError("Idempotency key was used with different generation inputs")
        return existing, False
    if shot.status not in allowed_states:
        raise GenerationError("Shot status does not allow this generation request")
    saved_spec = db.get(ShotSpec, shot.id)
    if saved_spec is not None:
        if (prompt or "").strip():
            raise GenerationError("Saved shot specs compile prompts; use creative_direction for additions", 422)
        from .shot_specs import compile_prompt, continuity_for, spec_read
        continuity = continuity_for(db, shot, saved_spec)
        shot_spec = spec_read(db, shot)
        compiled_prompt = compile_prompt(shot_spec, continuity, provider_name, direction)
        prompt_source = "structured"
    else:
        compiled_prompt = (prompt or "").strip()
        prompt_source = "manual"
        continuity = []
        shot_spec = None
        if not compiled_prompt:
            raise GenerationError("Prompt is required until a shot spec is saved", 422)
        if direction:
            raise GenerationError("Save a shot spec before adding creative direction", 422)
    try:
        provider = registry.get(provider_name)
        spec = spec_from_shot(shot)
        estimate = provider.estimate_cost(spec, model)
    except ValueError as exc:
        raise GenerationError(str(exc), 422) from exc
    if shot.budget_limit is not None and estimate > shot.budget_limit:
        raise GenerationError(f"Estimated cost ${estimate} exceeds shot budget ${shot.budget_limit}", 422)

    last_number = db.scalar(select(func.max(GenerationAttempt.attempt_number)).where(GenerationAttempt.shot_id == shot_id)) or 0
    snapshot = spec.snapshot()
    if shot_spec is not None:
        snapshot.update({"structured_spec": shot_spec, "continuity": continuity})
    attempt = GenerationAttempt(
        shot_id=shot.id, attempt_number=last_number + 1, idempotency_key=idempotency_key,
        provider=provider_name, model=model, prompt=compiled_prompt, creative_direction=direction if saved_spec else None,
        prompt_source=prompt_source, shot_snapshot=snapshot,
        status="queued", estimated_cost=estimate,
    )
    shot.status = "generating"
    db.add(attempt)
    db.commit()
    db.refresh(attempt)
    return attempt, True


def mark_dispatch_failed(db: Session, attempt_id: UUID, message: str) -> None:
    attempt = db.get(GenerationAttempt, attempt_id)
    if attempt is None or attempt.status != "queued":
        return
    shot = db.get(Shot, attempt.shot_id)
    attempt.status = "dispatch_failed"
    attempt.error_message = message[:1000]
    attempt.completed_at = utc_now()
    if shot is not None:
        shot.status = "ready"
    db.commit()


def _ledger_event(db: Session, attempt: GenerationAttempt, amount: Decimal, kind: str) -> None:
    event_key = f"generation:{attempt.id}:final"
    if db.scalar(select(CostEvent.id).where(CostEvent.event_key == event_key)) is not None:
        return
    shot = db.get(Shot, attempt.shot_id)
    scene = db.get(Scene, shot.scene_id)
    episode = db.get(Episode, scene.episode_id)
    series = db.get(Series, episode.series_id)
    db.add(CostEvent(
        workspace_id=series.workspace_id, series_id=series.id, shot_id=shot.id,
        generation_attempt_id=attempt.id, provider=attempt.provider, model=attempt.model,
        operation="generation", amount_usd=amount, amount_kind=kind, event_key=event_key,
    ))


def finish_attempt(db: Session, attempt_id: UUID, result: ProviderJobStatus, registry: ProviderRegistry) -> str:
    attempt = db.scalar(select(GenerationAttempt).where(GenerationAttempt.id == attempt_id).with_for_update())
    if attempt is None:
        raise GenerationError("Attempt not found", 404)
    if attempt.status in ("review", "failed", "cancelled", "dispatch_failed"):
        return attempt.status
    if result.state in ("queued", "running"):
        attempt.status = "running"
        db.commit()
        return "pending"
    if result.state == "cancelled":
        attempt.status = "cancelled"
        attempt.completed_at = utc_now()
        db.get(Shot, attempt.shot_id).status = "ready"
        db.commit()
        return "cancelled"

    amount: Decimal | None = None
    kind: str | None = None
    if result.actual_cost is not None:
        amount, kind = result.actual_cost, "actual"
    elif result.state == "succeeded" and registry.get(attempt.provider).capabilities().is_mock:
        amount, kind = attempt.estimated_cost, "simulated"
    elif result.state == "succeeded":
        amount, kind = attempt.estimated_cost, "estimated"
    if amount is not None and kind is not None:
        _ledger_event(db, attempt, amount, kind)
    attempt.actual_cost = amount if kind in ("actual", "simulated") else None
    attempt.cost_kind = kind
    attempt.completed_at = utc_now()
    created_at = attempt.created_at.replace(tzinfo=timezone.utc) if attempt.created_at.tzinfo is None else attempt.created_at
    attempt.generation_time_seconds = Decimal(str(max(0, (attempt.completed_at - created_at).total_seconds()))).quantize(Decimal("0.01"))
    shot = db.get(Shot, attempt.shot_id)
    if result.state == "succeeded" and result.output_url:
        attempt.status = "review"
        attempt.output_url = result.output_url
        attempt.output_media_type = result.media_type
        shot.status = "review"
    else:
        attempt.status = "failed"
        attempt.error_message = result.error_message or ("Provider succeeded without output" if result.state == "succeeded" else "Provider generation failed")
        shot.status = "failed"
    db.commit()
    return attempt.status


def fail_attempt(db: Session, attempt_id: UUID, message: str) -> None:
    attempt = db.scalar(select(GenerationAttempt).where(GenerationAttempt.id == attempt_id).with_for_update())
    if attempt is None or attempt.status in ("review", "failed", "cancelled", "dispatch_failed"):
        return
    attempt.status = "failed"
    attempt.error_message = message[:1000]
    attempt.completed_at = utc_now()
    db.get(Shot, attempt.shot_id).status = "failed"
    db.commit()


class GenerationActivities:
    def __init__(self, session_factory: sessionmaker[Session], registry: ProviderRegistry):
        self.session_factory = session_factory
        self.registry = registry

    @activity.defn(name="generation_submit")
    def submit(self, attempt_id: str) -> str:
        with self.session_factory() as db:
            attempt = db.get(GenerationAttempt, UUID(attempt_id))
            if attempt is None:
                raise GenerationError("Attempt not found", 404)
            if attempt.provider_job_id:
                return attempt.provider_job_id
            if attempt.status in ("failed", "cancelled", "dispatch_failed", "review"):
                return ""
            attempt.status = "submitting"
            db.commit()
            spec = GenerationSpec.from_snapshot(attempt.shot_snapshot)
            provider_name, prompt, model = attempt.provider, attempt.prompt, attempt.model

        provider = self.registry.get(provider_name)
        job_id = provider.generate(spec, prompt, model, attempt_id)
        with self.session_factory() as db:
            attempt = db.scalar(select(GenerationAttempt).where(GenerationAttempt.id == UUID(attempt_id)).with_for_update())
            if not attempt.provider_job_id:
                attempt.provider_job_id = job_id
                attempt.status = "running"
                db.commit()
            return attempt.provider_job_id

    @activity.defn(name="generation_poll")
    def poll(self, attempt_id: str) -> str:
        with self.session_factory() as db:
            attempt = db.get(GenerationAttempt, UUID(attempt_id))
            if attempt is None:
                raise GenerationError("Attempt not found", 404)
            if attempt.status in ("review", "failed", "cancelled", "dispatch_failed"):
                return attempt.status
            if not attempt.provider_job_id:
                raise GenerationError("Provider job was not submitted")
            provider_name, job_id = attempt.provider, attempt.provider_job_id
        result = self.registry.get(provider_name).get_status(job_id)
        with self.session_factory() as db:
            return finish_attempt(db, UUID(attempt_id), result, self.registry)

    @activity.defn(name="generation_cancel")
    def cancel(self, attempt_id: str) -> None:
        with self.session_factory() as db:
            attempt = db.get(GenerationAttempt, UUID(attempt_id))
            if attempt is None or attempt.status in ("review", "failed", "cancelled", "dispatch_failed"):
                return
            if attempt.provider_job_id:
                self.registry.get(attempt.provider).cancel(attempt.provider_job_id)
            finish_attempt(db, UUID(attempt_id), ProviderJobStatus(state="cancelled"), self.registry)

    @activity.defn(name="generation_fail")
    def fail(self, attempt_id: str, message: str) -> None:
        with self.session_factory() as db:
            fail_attempt(db, UUID(attempt_id), message)
