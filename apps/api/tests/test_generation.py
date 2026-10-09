from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from takeone_api.db import Base
from takeone_api.generation import (
    GenerationActivities, GenerationError, create_attempt, finish_attempt,
)
from takeone_api.models import CostEvent, Episode, GenerationAttempt, Scene, Series, Shot, Workspace
from takeone_api.providers import GenerationSpec, MockVideoProvider, ProviderJobStatus, ProviderRegistry


@pytest.fixture
def database():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        workspace = Workspace(name="Studio")
        db.add(workspace)
        db.flush()
        series = Series(workspace_id=workspace.id, title="Pilot")
        db.add(series)
        db.flush()
        episode = Episode(series_id=series.id, episode_number=1, title="Opening")
        db.add(episode)
        db.flush()
        scene = Scene(episode_id=episode.id, scene_number=1)
        db.add(scene)
        db.flush()
        shot = Shot(scene_id=scene.id, shot_number=1, description="Actor enters", duration_seconds=Decimal("4.00"), budget_limit=Decimal("0.30"), status="ready")
        db.add(shot)
        db.commit()
        yield factory, workspace.id, shot.id
    engine.dispose()


def submit(db, workspace_id, shot_id, key="request-12345678"):
    return create_attempt(
        db, workspace_id=workspace_id, shot_id=shot_id,
        provider_name="mock", model="mock-v1", prompt="Actor enters frame",
        idempotency_key=key, registry=ProviderRegistry([MockVideoProvider()]),
    )


def test_mock_provider_price_and_limits():
    provider = MockVideoProvider()
    spec = GenerationSpec("Actor enters", "close-up", Decimal("4"), 1, False, False, "low", "static", "standard")
    assert provider.estimate_cost(spec, "mock-v1") == Decimal("0.2600")
    assert provider.generate(spec, "Actor enters", "mock-v1", "same-key") == provider.generate(spec, "Actor enters", "mock-v1", "same-key")
    assert provider.get_status("mock:same-key").state == "succeeded"
    with pytest.raises(ValueError, match="outside provider limits"):
        provider.estimate_cost(GenerationSpec("", "", Decimal("16"), 0, False, False, "low", "static", "standard"), "mock-v1")


def test_budget_idempotency_and_snapshot(database):
    factory, workspace_id, shot_id = database
    registry = ProviderRegistry([MockVideoProvider()])
    with factory() as db:
        shot = db.get(Shot, shot_id)
        shot.budget_limit = Decimal("0.20")
        db.commit()
        with pytest.raises(GenerationError, match="exceeds shot budget"):
            submit(db, workspace_id, shot_id)
        assert db.scalars(select(GenerationAttempt)).all() == []
        shot.budget_limit = Decimal("0.30")
        db.commit()
        attempt, created = submit(db, workspace_id, shot_id)
        assert created and attempt.attempt_number == 1
        assert attempt.estimated_cost == Decimal("0.2600")
        shot.description = "Changed after submit"
        db.commit()
        assert attempt.shot_snapshot["description"] == "Actor enters"
        duplicate, created = submit(db, workspace_id, shot_id)
        assert not created and duplicate.id == attempt.id
        assert len(db.scalars(select(GenerationAttempt)).all()) == 1
        assert len(db.scalars(select(CostEvent)).all()) == 0


def test_completion_charges_once_and_advances_to_review(database):
    factory, workspace_id, shot_id = database
    registry = ProviderRegistry([MockVideoProvider()])
    with factory() as db:
        attempt, _ = submit(db, workspace_id, shot_id)
        result = ProviderJobStatus(state="succeeded", output_url="/mock-frame.svg", media_type="image/svg+xml")
        assert finish_attempt(db, attempt.id, result, registry) == "review"
        assert finish_attempt(db, attempt.id, result, registry) == "review"
        db.refresh(attempt)
        assert attempt.actual_cost == Decimal("0.2600")
        assert attempt.cost_kind == "simulated"
        assert db.get(Shot, shot_id).status == "review"
        events = db.scalars(select(CostEvent)).all()
        assert len(events) == 1
        assert events[0].amount_usd == Decimal("0.2600")
        assert events[0].workspace_id == workspace_id


def test_failed_charge_and_next_attempt_number(database):
    factory, workspace_id, shot_id = database
    registry = ProviderRegistry([MockVideoProvider()])
    with factory() as db:
        first, _ = submit(db, workspace_id, shot_id)
        assert finish_attempt(db, first.id, ProviderJobStatus(state="failed", actual_cost=Decimal("0.0800"), error_message="Provider failed"), registry) == "failed"
        assert db.get(Shot, shot_id).status == "failed"
        second, _ = submit(db, workspace_id, shot_id, key="request-87654321")
        assert second.attempt_number == 2
        assert first.id != second.id
        events = db.scalars(select(CostEvent)).all()
        assert len(events) == 1
        assert events[0].amount_usd == Decimal("0.0800")


def test_activity_resume_uses_existing_job_and_no_extra_charge(database):
    factory, workspace_id, shot_id = database
    registry = ProviderRegistry([MockVideoProvider()])
    with factory() as db:
        attempt, _ = submit(db, workspace_id, shot_id)
        attempt_id = str(attempt.id)
    activities = GenerationActivities(factory, registry)
    assert activities.submit(attempt_id) == activities.submit(attempt_id)
    assert activities.poll(attempt_id) == "review"
    assert activities.poll(attempt_id) == "review"
    with factory() as db:
        assert len(db.scalars(select(CostEvent)).all()) == 1


def test_activity_cancel_returns_shot_to_ready_without_charge(database):
    factory, workspace_id, shot_id = database
    registry = ProviderRegistry([MockVideoProvider()])
    with factory() as db:
        attempt, _ = submit(db, workspace_id, shot_id)
        attempt_id = str(attempt.id)
    activities = GenerationActivities(factory, registry)
    activities.submit(attempt_id)
    activities.cancel(attempt_id)
    activities.cancel(attempt_id)
    with factory() as db:
        assert db.get(GenerationAttempt, attempt.id).status == "cancelled"
        assert db.get(Shot, shot_id).status == "ready"
        assert db.scalars(select(CostEvent)).all() == []
