from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .analytics import AnalyticsNotFound, build_report
from .analytics_schemas import (
    AnalyticsReport, EpisodeReport, FailureReport, ProviderReport,
)
from .auth import CurrentUser, current_user
from .db import get_db

router = APIRouter(prefix="/api/v1")


def scoped_report(db: Session, owner: CurrentUser, series_id: UUID | None) -> AnalyticsReport:
    try:
        return build_report(db, owner.workspace_id, series_id)
    except AnalyticsNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/dashboard", response_model=AnalyticsReport)
def dashboard(
    series_id: UUID | None = Query(default=None),
    owner: CurrentUser = Depends(current_user), db: Session = Depends(get_db),
):
    return scoped_report(db, owner, series_id)


@router.get("/analytics/providers", response_model=ProviderReport)
def providers(
    series_id: UUID | None = Query(default=None),
    owner: CurrentUser = Depends(current_user), db: Session = Depends(get_db),
):
    report = scoped_report(db, owner, series_id)
    return ProviderReport(
        scope=report.scope, generated_at=report.generated_at,
        providers=report.providers, models=report.models,
    )


@router.get("/analytics/failures", response_model=FailureReport)
def failures(
    series_id: UUID | None = Query(default=None),
    owner: CurrentUser = Depends(current_user), db: Session = Depends(get_db),
):
    report = scoped_report(db, owner, series_id)
    return FailureReport(
        scope=report.scope, generated_at=report.generated_at, failures=report.failures,
    )


@router.get("/analytics/episodes", response_model=EpisodeReport)
def episodes(
    series_id: UUID | None = Query(default=None),
    owner: CurrentUser = Depends(current_user), db: Session = Depends(get_db),
):
    report = scoped_report(db, owner, series_id)
    return EpisodeReport(
        scope=report.scope, generated_at=report.generated_at, episodes=report.episodes,
    )


@router.get("/analytics/series/{series_id}", response_model=AnalyticsReport)
def series_analytics(
    series_id: UUID, owner: CurrentUser = Depends(current_user),
    db: Session = Depends(get_db),
):
    return scoped_report(db, owner, series_id)
