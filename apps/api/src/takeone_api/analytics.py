"""Derive production economics from scoped attempts, reviews, and cost events."""

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from .analytics_schemas import (
    AnalyticsReport, AnalyticsScope, EpisodeSpend, FailureReasonMetric,
    ProductionSummary, ProviderPerformance, SeriesSpend,
)
from .models import CostEvent, Episode, GenerationAttempt, Review, Scene, Series, Shot, utc_now

ZERO = Decimal("0.0000")
MONEY = Decimal("0.0001")
RATE = Decimal("0.0001")
SECONDS = Decimal("0.01")


class AnalyticsNotFound(Exception):
    pass


@dataclass(frozen=True)
class ShotFact:
    id: UUID
    episode_id: UUID
    series_id: UUID


@dataclass(frozen=True)
class AttemptFact:
    id: UUID
    shot_id: UUID
    attempt_number: int
    provider: str
    model: str
    decision: str | None
    failure_reason: str | None
    generation_time_seconds: Decimal | None


@dataclass(frozen=True)
class CostFact:
    attempt_id: UUID
    amount: Decimal
    kind: str


@dataclass(frozen=True)
class Aggregate:
    summary: ProductionSummary
    accepted_attempts: int
    average_generation_time_seconds: Decimal | None


def _divide(numerator: Decimal | int, denominator: int, precision: Decimal = RATE) -> Decimal | None:
    if denominator == 0:
        return None
    return (Decimal(numerator) / Decimal(denominator)).quantize(precision)


def _aggregate(
    shot_ids: set[UUID], attempts: list[AttemptFact],
    cost_by_attempt: dict[UUID, list[CostFact]],
) -> Aggregate:
    accepted_shots: set[UUID] = set()
    first_pass_reviewed: set[UUID] = set()
    first_pass_accepted: set[UUID] = set()
    attempts_per_shot: dict[UUID, int] = defaultdict(int)
    spend_by_kind: dict[str, Decimal] = {
        "actual": ZERO, "simulated": ZERO, "estimated": ZERO,
    }
    total_spend = retry_spend = retry_waste = ZERO
    reviewed = accepted = rejected = chargeable = 0
    generation_times: list[Decimal] = []

    for attempt in attempts:
        attempts_per_shot[attempt.shot_id] += 1
        if attempt.decision is not None:
            reviewed += 1
            if attempt.attempt_number == 1:
                first_pass_reviewed.add(attempt.shot_id)
        if attempt.decision == "accepted":
            accepted += 1
            accepted_shots.add(attempt.shot_id)
            if attempt.attempt_number == 1:
                first_pass_accepted.add(attempt.shot_id)
        elif attempt.decision == "rejected":
            rejected += 1
        if attempt.generation_time_seconds is not None:
            generation_times.append(attempt.generation_time_seconds)
        events = cost_by_attempt.get(attempt.id, [])
        if events:
            chargeable += 1
        for event in events:
            total_spend += event.amount
            spend_by_kind[event.kind] = spend_by_kind.get(event.kind, ZERO) + event.amount
            if attempt.attempt_number > 1:
                retry_spend += event.amount
            if attempt.decision == "rejected":
                retry_waste += event.amount

    retries = sum(max(count - 1, 0) for count in attempts_per_shot.values())
    summary = ProductionSummary(
        total_shots=len(shot_ids), attempted_shots=len(attempts_per_shot),
        accepted_shots=len(accepted_shots),
        pending_shots=len(shot_ids - accepted_shots),
        generation_attempts=len(attempts), reviewed_attempts=reviewed,
        rejected_attempts=rejected, retries=retries, chargeable_attempts=chargeable,
        first_pass_reviewed_shots=len(first_pass_reviewed),
        first_pass_accepted_shots=len(first_pass_accepted),
        total_spend=total_spend.quantize(MONEY),
        retry_spend=retry_spend.quantize(MONEY),
        retry_waste=retry_waste.quantize(MONEY),
        average_cost_per_attempted_shot=_divide(total_spend, len(attempts_per_shot), MONEY),
        cost_per_accepted_shot=_divide(total_spend, len(accepted_shots), MONEY),
        first_pass_acceptance_rate=_divide(len(first_pass_accepted), len(first_pass_reviewed)),
        retries_per_shot=_divide(retries, len(attempts_per_shot)),
        average_attempt_cost=_divide(total_spend, chargeable, MONEY),
        spend_by_kind={kind: amount.quantize(MONEY) for kind, amount in sorted(spend_by_kind.items())},
    )
    average_time = _divide(sum(generation_times, ZERO), len(generation_times), SECONDS)
    return Aggregate(summary, accepted, average_time)


def _provider_performance(
    provider: str, model: str | None, attempts: list[AttemptFact],
    cost_by_attempt: dict[UUID, list[CostFact]],
) -> ProviderPerformance:
    aggregate = _aggregate({attempt.shot_id for attempt in attempts}, attempts, cost_by_attempt)
    summary = aggregate.summary
    return ProviderPerformance(
        provider=provider, model=model, attempts=summary.generation_attempts,
        reviewed_attempts=summary.reviewed_attempts,
        accepted_attempts=aggregate.accepted_attempts,
        rejected_attempts=summary.rejected_attempts,
        accepted_shots=summary.accepted_shots,
        chargeable_attempts=summary.chargeable_attempts,
        total_spend=summary.total_spend, spend_by_kind=summary.spend_by_kind,
        acceptance_rate=_divide(aggregate.accepted_attempts, summary.reviewed_attempts),
        average_attempt_cost=summary.average_attempt_cost,
        cost_per_accepted_shot=summary.cost_per_accepted_shot,
        average_generation_time_seconds=aggregate.average_generation_time_seconds,
    )


def build_report(db: Session, workspace_id: UUID, series_id: UUID | None = None) -> AnalyticsReport:
    series_query = select(Series.id, Series.title).where(Series.workspace_id == workspace_id)
    if series_id is not None:
        series_query = series_query.where(Series.id == series_id)
    series_rows = db.execute(series_query.order_by(Series.title, Series.id)).all()
    if series_id is not None and not series_rows:
        raise AnalyticsNotFound("Series not found")
    series_titles = {row.id: row.title for row in series_rows}
    series_ids = set(series_titles)

    episode_rows = db.execute(
        select(Episode.id, Episode.series_id, Episode.episode_number, Episode.title)
        .where(Episode.series_id.in_(series_ids))
    ).all() if series_ids else []
    episode_series = {row.id: row.series_id for row in episode_rows}
    shot_rows = db.execute(
        select(Shot.id, Scene.episode_id).join(Scene, Shot.scene_id == Scene.id)
        .where(Scene.episode_id.in_(episode_series))
    ).all() if episode_series else []
    shots = [ShotFact(row.id, row.episode_id, episode_series[row.episode_id]) for row in shot_rows]
    shot_ids = {shot.id for shot in shots}

    attempt_rows = db.execute(
        select(
            GenerationAttempt.id, GenerationAttempt.shot_id,
            GenerationAttempt.attempt_number, GenerationAttempt.provider,
            GenerationAttempt.model, Review.decision, Review.failure_reason,
            GenerationAttempt.generation_time_seconds,
        )
        .outerjoin(Review, Review.generation_attempt_id == GenerationAttempt.id)
        .where(GenerationAttempt.shot_id.in_(shot_ids))
    ).all() if shot_ids else []
    attempts = [AttemptFact(*row) for row in attempt_rows]
    attempt_ids = {attempt.id for attempt in attempts}
    # CPAS measures generation economics; unrelated ledger operations stay out.
    cost_rows = db.execute(
        select(CostEvent.generation_attempt_id, CostEvent.amount_usd, CostEvent.amount_kind)
        .where(
            CostEvent.workspace_id == workspace_id, CostEvent.operation == "generation",
            CostEvent.generation_attempt_id.in_(attempt_ids),
        )
    ).all() if attempt_ids else []
    cost_by_attempt: dict[UUID, list[CostFact]] = defaultdict(list)
    for row in cost_rows:
        cost_by_attempt[row.generation_attempt_id].append(
            CostFact(row.generation_attempt_id, row.amount_usd, row.amount_kind)
        )

    shot_by_id = {shot.id: shot for shot in shots}
    by_provider: dict[str, list[AttemptFact]] = defaultdict(list)
    by_model: dict[tuple[str, str], list[AttemptFact]] = defaultdict(list)
    by_series: dict[UUID, list[AttemptFact]] = defaultdict(list)
    by_episode: dict[UUID, list[AttemptFact]] = defaultdict(list)
    by_reason: dict[str, list[AttemptFact]] = defaultdict(list)
    for attempt in attempts:
        shot = shot_by_id[attempt.shot_id]
        by_provider[attempt.provider].append(attempt)
        by_model[(attempt.provider, attempt.model)].append(attempt)
        by_series[shot.series_id].append(attempt)
        by_episode[shot.episode_id].append(attempt)
        if attempt.decision == "rejected" and attempt.failure_reason:
            by_reason[attempt.failure_reason].append(attempt)

    providers = [
        _provider_performance(name, None, group, cost_by_attempt)
        for name, group in by_provider.items()
    ]
    providers.sort(key=lambda item: (-item.total_spend, item.provider))
    models = [
        _provider_performance(name, model, group, cost_by_attempt)
        for (name, model), group in by_model.items()
    ]
    models.sort(key=lambda item: (item.provider, item.model or ""))
    failures = [
        FailureReasonMetric(
            reason=reason, rejected_attempts=len(group),
            waste=sum(
                (event.amount for attempt in group for event in cost_by_attempt.get(attempt.id, [])), ZERO
            ).quantize(MONEY),
        )
        for reason, group in by_reason.items()
    ]
    failures.sort(key=lambda item: (-item.rejected_attempts, item.reason))

    series_shots: dict[UUID, set[UUID]] = defaultdict(set)
    episode_shots: dict[UUID, set[UUID]] = defaultdict(set)
    for shot in shots:
        series_shots[shot.series_id].add(shot.id)
        episode_shots[shot.episode_id].add(shot.id)
    series_metrics = []
    for current_id, title in series_titles.items():
        summary = _aggregate(series_shots[current_id], by_series[current_id], cost_by_attempt).summary
        series_metrics.append(SeriesSpend(
            series_id=current_id, title=title, shots=summary.total_shots,
            accepted_shots=summary.accepted_shots, attempts=summary.generation_attempts,
            retries=summary.retries, total_spend=summary.total_spend,
            retry_waste=summary.retry_waste,
            cost_per_accepted_shot=summary.cost_per_accepted_shot,
        ))
    episode_metrics = []
    for episode in episode_rows:
        summary = _aggregate(episode_shots[episode.id], by_episode[episode.id], cost_by_attempt).summary
        episode_metrics.append(EpisodeSpend(
            episode_id=episode.id, series_id=episode.series_id,
            series_title=series_titles[episode.series_id],
            episode_number=episode.episode_number, title=episode.title,
            shots=summary.total_shots, accepted_shots=summary.accepted_shots,
            attempts=summary.generation_attempts, retries=summary.retries,
            total_spend=summary.total_spend, retry_waste=summary.retry_waste,
            cost_per_accepted_shot=summary.cost_per_accepted_shot,
        ))
    episode_metrics.sort(key=lambda item: (item.series_title, item.episode_number, str(item.episode_id)))

    return AnalyticsReport(
        scope=AnalyticsScope(
            workspace_id=workspace_id, series_id=series_id,
            series_title=series_titles.get(series_id) if series_id else None,
        ),
        generated_at=utc_now(),
        summary=_aggregate(shot_ids, attempts, cost_by_attempt).summary,
        series=series_metrics, providers=providers, models=models,
        failures=failures, episodes=episode_metrics,
    )
