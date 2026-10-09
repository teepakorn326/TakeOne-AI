"""Read models for production economics. Rates are fractions from 0 to 1."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel


class AnalyticsScope(BaseModel):
    workspace_id: UUID
    series_id: UUID | None
    series_title: str | None


class ProductionSummary(BaseModel):
    total_shots: int
    attempted_shots: int
    accepted_shots: int
    pending_shots: int
    generation_attempts: int
    reviewed_attempts: int
    rejected_attempts: int
    retries: int
    chargeable_attempts: int
    first_pass_reviewed_shots: int
    first_pass_accepted_shots: int
    total_spend: Decimal
    retry_spend: Decimal
    retry_waste: Decimal
    average_cost_per_attempted_shot: Decimal | None
    cost_per_accepted_shot: Decimal | None
    first_pass_acceptance_rate: Decimal | None
    retries_per_shot: Decimal | None
    average_attempt_cost: Decimal | None
    spend_by_kind: dict[str, Decimal]


class ProviderPerformance(BaseModel):
    provider: str
    model: str | None = None
    attempts: int
    reviewed_attempts: int
    accepted_attempts: int
    rejected_attempts: int
    accepted_shots: int
    chargeable_attempts: int
    total_spend: Decimal
    spend_by_kind: dict[str, Decimal]
    acceptance_rate: Decimal | None
    average_attempt_cost: Decimal | None
    cost_per_accepted_shot: Decimal | None
    average_generation_time_seconds: Decimal | None


class FailureReasonMetric(BaseModel):
    reason: str
    rejected_attempts: int
    waste: Decimal


class SeriesSpend(BaseModel):
    series_id: UUID
    title: str
    shots: int
    accepted_shots: int
    attempts: int
    retries: int
    total_spend: Decimal
    retry_waste: Decimal
    cost_per_accepted_shot: Decimal | None


class EpisodeSpend(BaseModel):
    episode_id: UUID
    series_id: UUID
    series_title: str
    episode_number: int
    title: str
    shots: int
    accepted_shots: int
    attempts: int
    retries: int
    total_spend: Decimal
    retry_waste: Decimal
    cost_per_accepted_shot: Decimal | None


class AnalyticsReport(BaseModel):
    scope: AnalyticsScope
    generated_at: datetime
    summary: ProductionSummary
    series: list[SeriesSpend]
    providers: list[ProviderPerformance]
    models: list[ProviderPerformance]
    failures: list[FailureReasonMetric]
    episodes: list[EpisodeSpend]


class ProviderReport(BaseModel):
    scope: AnalyticsScope
    generated_at: datetime
    providers: list[ProviderPerformance]
    models: list[ProviderPerformance]


class FailureReport(BaseModel):
    scope: AnalyticsScope
    generated_at: datetime
    failures: list[FailureReasonMetric]


class EpisodeReport(BaseModel):
    scope: AnalyticsScope
    generated_at: datetime
    episodes: list[EpisodeSpend]
