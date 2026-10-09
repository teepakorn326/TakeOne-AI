from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from takeone_api.analytics import AnalyticsNotFound, build_report
from takeone_api.db import Base, get_db
from takeone_api.main import app
from takeone_api.models import (
    CostEvent, Episode, GenerationAttempt, Review, Scene, Series, Shot, User, Workspace,
)


@pytest.fixture
def seeded():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        studio = Workspace(name="Studio")
        other = Workspace(name="Other")
        db.add_all([studio, other])
        db.flush()
        owner = User(workspace_id=studio.id, name="Producer", email="producer@example.com")
        outsider = User(workspace_id=other.id, name="Other", email="other@example.com")
        db.add_all([owner, outsider])
        db.flush()

        def new_series(workspace, title):
            value = Series(workspace_id=workspace.id, title=title)
            db.add(value)
            db.flush()
            return value

        def new_episode(series, number):
            episode = Episode(series_id=series.id, episode_number=number, title=f"Episode {number}")
            db.add(episode)
            db.flush()
            scene = Scene(episode_id=episode.id, scene_number=1)
            db.add(scene)
            db.flush()
            return episode, scene

        def new_shot(scene, number, status):
            shot = Shot(scene_id=scene.id, shot_number=number, description="A scene", duration_seconds=Decimal("4"), status=status)
            db.add(shot)
            db.flush()
            return shot

        def add_attempt(shot, workspace, series, number, provider, amount, kind=None, decision=None, reason=None, time=None):
            model = "mock-v1" if provider == "mock" else "mock-alt-v1"
            attempt = GenerationAttempt(
                shot_id=shot.id, attempt_number=number, idempotency_key=str(uuid4()),
                provider=provider, model=model, prompt="Generate", shot_snapshot={},
                status="review" if amount is not None else "running",
                estimated_cost=Decimal("99.0000"), actual_cost=Decimal("99.0000"),
                generation_time_seconds=Decimal(time) if time is not None else None,
            )
            db.add(attempt)
            db.flush()
            if amount is not None:
                db.add(CostEvent(
                    workspace_id=workspace.id, series_id=series.id, shot_id=shot.id,
                    generation_attempt_id=attempt.id, provider=provider, model=model,
                    operation="generation", amount_usd=Decimal(amount),
                    amount_kind=kind, event_key=f"generation:{attempt.id}:final",
                ))
            if decision:
                db.add(Review(
                    generation_attempt_id=attempt.id, reviewer_id=owner.id if workspace.id == studio.id else outsider.id,
                    decision=decision, failure_reason=reason, notes="",
                ))
            return attempt

        first = new_series(studio, "First")
        ep1, scene1 = new_episode(first, 1)
        ep2, scene2 = new_episode(first, 2)
        second = new_series(studio, "Second")
        ep3, scene3 = new_episode(second, 1)
        foreign = new_series(other, "Private")
        _, foreign_scene = new_episode(foreign, 1)

        accepted_retry = new_shot(scene1, 1, "accepted")
        add_attempt(accepted_retry, studio, first, 1, "mock", "0.20", "simulated", "rejected", "bad_motion", "2.0")
        add_attempt(accepted_retry, studio, first, 2, "mock-alt", "0.30", "simulated", "accepted", time="4.0")
        first_pass = new_shot(scene1, 2, "accepted")
        first_pass_attempt = add_attempt(first_pass, studio, first, 1, "mock", "0.40", "actual", "accepted", time="6.0")
        db.add(CostEvent(
            workspace_id=studio.id, series_id=first.id, shot_id=first_pass.id,
            generation_attempt_id=first_pass_attempt.id, provider="mock", model="mock-v1",
            operation="storage", amount_usd=Decimal("5.0000"), amount_kind="actual",
            event_key=f"storage:{first_pass_attempt.id}",
        ))
        rejected = new_shot(scene2, 1, "rejected")
        add_attempt(rejected, studio, first, 1, "mock-alt", "0.10", "actual", "rejected", "identity_drift", "8.0")
        pending_review = new_shot(scene3, 1, "review")
        add_attempt(pending_review, studio, second, 1, "mock", "0.15", "estimated", time="10.0")
        generating = new_shot(scene3, 2, "generating")
        add_attempt(generating, studio, second, 1, "mock-alt", None)
        new_shot(scene3, 3, "draft")
        foreign_shot = new_shot(foreign_scene, 1, "accepted")
        add_attempt(foreign_shot, other, foreign, 1, "mock", "10.00", "actual", "accepted")
        db.commit()
        ids = {
            "workspace": studio.id, "owner": owner.id, "first": first.id,
            "second": second.id, "foreign": foreign.id, "other_workspace": other.id,
            "other_user": outsider.id, "ep1": ep1.id, "ep2": ep2.id, "ep3": ep3.id,
        }
    yield engine, ids
    engine.dispose()


def test_mixed_provider_economics_and_denominators(seeded):
    engine, ids = seeded
    with Session(engine) as db:
        report = build_report(db, ids["workspace"])
    summary = report.summary
    assert (summary.total_shots, summary.accepted_shots, summary.pending_shots) == (6, 2, 4)
    assert summary.attempted_shots == 5
    assert (summary.generation_attempts, summary.reviewed_attempts, summary.rejected_attempts) == (6, 4, 2)
    assert (summary.retries, summary.chargeable_attempts) == (1, 5)
    assert summary.total_spend == Decimal("1.1500")
    assert summary.retry_spend == Decimal("0.3000")
    assert summary.retry_waste == Decimal("0.3000")
    assert summary.average_cost_per_attempted_shot == Decimal("0.2300")
    assert summary.cost_per_accepted_shot == Decimal("0.5750")
    assert summary.first_pass_acceptance_rate == Decimal("0.3333")
    assert (summary.first_pass_accepted_shots, summary.first_pass_reviewed_shots) == (1, 3)
    assert summary.retries_per_shot == Decimal("0.2000")
    assert summary.average_attempt_cost == Decimal("0.2300")
    assert summary.spend_by_kind == {
        "actual": Decimal("0.5000"), "simulated": Decimal("0.5000"), "estimated": Decimal("0.1500"),
    }

    providers = {item.provider: item for item in report.providers}
    assert providers["mock"].attempts == 3
    assert providers["mock"].reviewed_attempts == 2
    assert providers["mock"].acceptance_rate == Decimal("0.5000")
    assert providers["mock"].total_spend == Decimal("0.7500")
    assert providers["mock"].cost_per_accepted_shot == Decimal("0.7500")
    assert providers["mock"].average_generation_time_seconds == Decimal("6.00")
    assert providers["mock-alt"].attempts == 3
    assert providers["mock-alt"].total_spend == Decimal("0.4000")
    assert providers["mock-alt"].cost_per_accepted_shot == Decimal("0.4000")
    assert len(report.models) == 2
    failures = {item.reason: item for item in report.failures}
    assert failures["bad_motion"].waste == Decimal("0.2000")
    assert failures["identity_drift"].waste == Decimal("0.1000")
    episodes = {item.episode_id: item for item in report.episodes}
    assert episodes[ids["ep1"]].total_spend == Decimal("0.9000")
    assert episodes[ids["ep1"]].cost_per_accepted_shot == Decimal("0.4500")
    assert episodes[ids["ep2"]].cost_per_accepted_shot is None
    assert episodes[ids["ep3"]].total_spend == Decimal("0.1500")
    series = {item.series_id: item for item in report.series}
    assert series[ids["first"]].total_spend == Decimal("1.0000")
    assert series[ids["first"]].retry_waste == Decimal("0.3000")
    assert series[ids["second"]].cost_per_accepted_shot is None


def test_series_scope_zero_denominators_and_isolation(seeded):
    engine, ids = seeded
    with Session(engine) as db:
        first = build_report(db, ids["workspace"], ids["first"])
        assert first.scope.series_title == "First"
        assert first.summary.total_spend == Decimal("1.0000")
        assert first.summary.cost_per_accepted_shot == Decimal("0.5000")
        assert first.summary.first_pass_acceptance_rate == Decimal("0.3333")
        second = build_report(db, ids["workspace"], ids["second"])
        assert second.summary.total_shots == 3
        assert second.summary.cost_per_accepted_shot is None
        assert second.summary.first_pass_acceptance_rate is None
        assert second.summary.retry_waste == Decimal("0.0000")
        assert len(second.providers) == 2
        other = build_report(db, ids["other_workspace"])
        assert other.summary.total_spend == Decimal("10.0000")
        assert other.summary.accepted_shots == 1
        with pytest.raises(AnalyticsNotFound):
            build_report(db, ids["workspace"], ids["foreign"])


def test_empty_report_has_no_misleading_rates(seeded):
    engine, _ = seeded
    with Session(engine) as db:
        report = build_report(db, uuid4())
    assert report.summary.total_shots == 0
    assert report.summary.total_spend == Decimal("0.0000")
    assert report.summary.cost_per_accepted_shot is None
    assert report.summary.average_cost_per_attempted_shot is None
    assert report.summary.first_pass_acceptance_rate is None
    assert report.summary.average_attempt_cost is None
    assert report.summary.retries_per_shot is None
    assert report.series == report.providers == report.episodes == []


def test_analytics_endpoints_are_scoped_and_consistent(seeded):
    engine, ids = seeded

    def session_override():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = session_override
    try:
        with TestClient(app) as client:
            headers = {"X-Workspace-Id": str(ids["workspace"]), "X-User-Id": str(ids["owner"])}
            dashboard = client.get("/api/v1/dashboard", headers=headers)
            assert dashboard.status_code == 200, dashboard.text
            assert Decimal(dashboard.json()["summary"]["total_spend"]) == Decimal("1.1500")
            assert dashboard.json()["scope"]["series_id"] is None
            providers = client.get("/api/v1/analytics/providers", headers=headers).json()
            assert len(providers["providers"]) == 2 and len(providers["models"]) == 2
            failures = client.get("/api/v1/analytics/failures", headers=headers).json()
            assert sum(item["rejected_attempts"] for item in failures["failures"]) == 2
            episodes = client.get("/api/v1/analytics/episodes", headers=headers).json()
            assert len(episodes["episodes"]) == 3
            filtered = client.get(f"/api/v1/dashboard?series_id={ids['first']}", headers=headers).json()
            assert Decimal(filtered["summary"]["total_spend"]) == Decimal("1.0000")
            assert len(filtered["series"]) == 1
            detail = client.get(f"/api/v1/analytics/series/{ids['first']}", headers=headers).json()
            assert detail["summary"] == filtered["summary"]
            assert client.get(f"/api/v1/analytics/series/{ids['foreign']}", headers=headers).status_code == 404
            other_headers = {"X-Workspace-Id": str(ids["other_workspace"]), "X-User-Id": str(ids["other_user"])}
            assert Decimal(client.get("/api/v1/dashboard", headers=other_headers).json()["summary"]["total_spend"]) == Decimal("10.0000")
    finally:
        app.dependency_overrides.clear()
