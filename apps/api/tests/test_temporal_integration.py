import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from takeone_api.db import Base
from takeone_api.generation import GenerationActivities, create_attempt
from takeone_api.models import CostEvent, Episode, GenerationAttempt, Scene, Series, Shot, Workspace
from takeone_api.providers import MockVideoProvider, ProviderJobStatus, ProviderRegistry
from takeone_api.workflow import GenerateShotWorkflow


@pytest.mark.skipif(os.environ.get("TAKEONE_TEMPORAL_TEST") != "1", reason="Set TAKEONE_TEMPORAL_TEST=1 to start the local Temporal test server")
def test_temporal_workflow_records_output_and_one_charge(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'workflow.sqlite'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    registry = ProviderRegistry([MockVideoProvider()])
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
        shot = Shot(scene_id=scene.id, shot_number=1, duration_seconds=Decimal("4"), status="ready")
        db.add(shot)
        db.commit()
        attempt, _ = create_attempt(
            db, workspace_id=workspace.id, shot_id=shot.id, provider_name="mock",
            model="mock-v1", prompt="Actor enters", idempotency_key="temporal-test-123",
            registry=registry,
        )
        attempt_id = attempt.id

    async def run_workflow():
        async with await WorkflowEnvironment.start_local() as env:
            activities = GenerationActivities(factory, registry)
            with ThreadPoolExecutor(max_workers=4) as executor:
                async with Worker(
                    env.client, task_queue="takeone-test-generation",
                    workflows=[GenerateShotWorkflow],
                    activities=[activities.submit, activities.poll, activities.cancel, activities.fail],
                    activity_executor=executor,
                ):
                    return await env.client.execute_workflow(
                        GenerateShotWorkflow.run, str(attempt_id), id=f"test-generation-{uuid4()}",
                        task_queue="takeone-test-generation",
                    )

    assert asyncio.run(run_workflow()) == "review"
    with factory() as db:
        result = db.get(GenerationAttempt, attempt_id)
        assert result.status == "review"
        assert result.provider_job_id == f"mock:{attempt_id}"
        assert result.output_url == "/mock-frame.svg"
        assert db.get(Shot, result.shot_id).status == "review"
        events = db.scalars(select(CostEvent)).all()
        assert len(events) == 1
        assert events[0].amount_usd == Decimal("0.2600")
    engine.dispose()


class PendingMockProvider(MockVideoProvider):
    def get_status(self, job_id: str) -> ProviderJobStatus:
        return ProviderJobStatus(state="running")


@pytest.mark.skipif(os.environ.get("TAKEONE_TEMPORAL_TEST") != "1", reason="Set TAKEONE_TEMPORAL_TEST=1 to start the local Temporal test server")
def test_temporal_timeout_marks_attempt_failed(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'timeout.sqlite'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    registry = ProviderRegistry([PendingMockProvider()])
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
        shot = Shot(scene_id=scene.id, shot_number=1, duration_seconds=Decimal("4"), status="ready")
        db.add(shot)
        db.commit()
        attempt, _ = create_attempt(db, workspace_id=workspace.id, shot_id=shot.id, provider_name="mock", model="mock-v1", prompt="Actor enters", idempotency_key="timeout-test-123", registry=registry)
        attempt_id = attempt.id

    async def run_workflow():
        async with await WorkflowEnvironment.start_local() as env:
            activities = GenerationActivities(factory, registry)
            with ThreadPoolExecutor(max_workers=4) as executor:
                async with Worker(env.client, task_queue="takeone-test-timeout", workflows=[GenerateShotWorkflow], activities=[activities.submit, activities.poll, activities.cancel, activities.fail], activity_executor=executor):
                    return await env.client.execute_workflow(GenerateShotWorkflow.run, args=[str(attempt_id), 2], id=f"test-timeout-{uuid4()}", task_queue="takeone-test-timeout")

    assert asyncio.run(run_workflow()) == "failed"
    with factory() as db:
        assert db.get(GenerationAttempt, attempt_id).status == "failed"
        assert db.get(Shot, shot.id).status == "failed"
        assert db.scalars(select(CostEvent)).all() == []
    engine.dispose()
