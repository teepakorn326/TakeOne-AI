from decimal import Decimal
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from takeone_api.db import Base, get_db
from takeone_api.generation import finish_attempt
from takeone_api.main import app
from takeone_api.models import GenerationAttempt, Review, Shot
from takeone_api.providers import ProviderJobStatus, providers
from takeone_api.temporal_dispatch import get_dispatcher


class FakeDispatcher:
    def __init__(self):
        self.started = []

    async def start(self, attempt_id):
        self.started.append(attempt_id)

    async def cancel(self, attempt_id):
        pass


@pytest.fixture
def api():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    dispatcher = FakeDispatcher()

    def session_override():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = session_override
    app.dependency_overrides[get_dispatcher] = lambda: dispatcher
    with TestClient(app) as client:
        yield client, engine, dispatcher
    app.dependency_overrides.clear()
    engine.dispose()


def studio(client, name):
    response = client.post("/api/v1/workspaces", json={
        "name": name, "owner_name": "Producer", "owner_email": f"{name.lower()}@example.com",
    })
    assert response.status_code == 201
    result = response.json()
    return {"X-Workspace-Id": result["workspace"]["id"], "X-User-Id": result["owner_id"]}


def shot_for(client, headers, budget=None):
    series = client.post("/api/v1/series", headers=headers, json={"title": "Pilot"}).json()
    episode = client.post(f"/api/v1/series/{series['id']}/episodes", headers=headers, json={"episode_number": 1, "title": "Opening"}).json()
    scene = client.post(f"/api/v1/episodes/{episode['id']}/scenes", headers=headers, json={"scene_number": 1}).json()
    shot = client.post(f"/api/v1/scenes/{scene['id']}/shots", headers=headers, json={
        "shot_number": 1, "description": "Actor enters", "duration_seconds": "4.00", "budget_limit": budget,
    }).json()
    assert client.patch(f"/api/v1/shots/{shot['id']}", headers=headers, json={"status": "ready"}).status_code == 200
    return shot["id"]


def generated(client, engine, headers, shot_id):
    response = client.post(f"/api/v1/shots/{shot_id}/attempts", headers={
        **headers, "Idempotency-Key": "initial-generation-123",
    }, json={"provider": "mock", "model": "mock-v1", "prompt": "Actor enters frame"})
    assert response.status_code == 202, response.text
    attempt_id = UUID(response.json()["id"])
    with Session(engine) as db:
        assert finish_attempt(db, attempt_id, ProviderJobStatus(
            state="succeeded", output_url="/mock-frame.svg", media_type="image/svg+xml",
        ), providers) == "review"
    return str(attempt_id)


def test_rejection_requires_reason_and_review_is_immutable(api):
    client, engine, _ = api
    headers = studio(client, "Studio")
    shot_id = shot_for(client, headers)
    attempt_id = generated(client, engine, headers, shot_id)
    queue = client.get("/api/v1/review", headers=headers).json()
    assert len(queue) == 1
    assert queue[0]["attempt"]["id"] == attempt_id
    assert queue[0]["series_title"] == "Pilot"
    assert "bad_motion" in client.get("/api/v1/review/failure-reasons", headers=headers).json()
    endpoint = f"/api/v1/attempts/{attempt_id}/reviews"
    assert client.post(endpoint, headers=headers, json={"decision": "rejected"}).status_code == 422
    assert client.post(endpoint, headers=headers, json={"decision": "rejected", "failure_reason": "made_up"}).status_code == 422
    response = client.post(endpoint, headers=headers, json={
        "decision": "rejected", "failure_reason": "bad_motion", "notes": "  Motion stutters  ",
    })
    assert response.status_code == 201, response.text
    assert response.json()["reviewer_id"] == headers["X-User-Id"]
    assert response.json()["notes"] == "Motion stutters"
    assert client.post(endpoint, headers=headers, json={"decision": "accepted"}).status_code == 409
    assert client.get(f"/api/v1/shots/{shot_id}", headers=headers).json()["status"] == "rejected"
    assert client.get(f"/api/v1/attempts/{attempt_id}", headers=headers).json()["review"]["failure_reason"] == "bad_motion"
    assert client.get("/api/v1/review", headers=headers).json() == []
    with Session(engine) as db:
        assert len(db.scalars(select(Review)).all()) == 1


def test_retry_switches_provider_preserves_history_and_accepts(api):
    client, engine, dispatcher = api
    headers = studio(client, "Studio")
    shot_id = shot_for(client, headers)
    attempt_id = generated(client, engine, headers, shot_id)
    assert client.post(f"/api/v1/attempts/{attempt_id}/reviews", headers=headers, json={
        "decision": "rejected", "failure_reason": "story_mismatch",
    }).status_code == 201
    assert client.patch(f"/api/v1/shots/{shot_id}", headers=headers, json={"status": "ready"}).status_code == 409
    changed = client.patch(f"/api/v1/shots/{shot_id}", headers=headers, json={"description": "Actor enters slowly"})
    assert changed.status_code == 200 and changed.json()["status"] == "rejected"
    retry_headers = {**headers, "Idempotency-Key": "provider-switch-123"}
    endpoint = f"/api/v1/shots/{shot_id}/retry"
    response = client.post(endpoint, headers=retry_headers, json={"provider": "mock-alt"})
    assert response.status_code == 202, response.text
    assert response.json()["attempt_number"] == 2
    assert response.json()["provider"] == "mock-alt"
    assert response.json()["model"] == "mock-alt-v1"
    assert response.json()["prompt"] == "Actor enters frame"
    assert response.json()["shot_snapshot"]["description"] == "Actor enters slowly"
    assert client.get(f"/api/v1/attempts/{attempt_id}", headers=headers).json()["shot_snapshot"]["description"] == "Actor enters"
    assert Decimal(response.json()["estimated_cost"]) == Decimal("0.3000")
    assert client.post(endpoint, headers=retry_headers, json={"provider": "mock-alt"}).json()["id"] == response.json()["id"]
    assert client.post(endpoint, headers=retry_headers, json={"provider": "mock"}).status_code == 409
    assert client.post(endpoint, headers={**headers, "Idempotency-Key": "initial-generation-123"}, json={}).status_code == 409
    assert client.post(endpoint, headers={**headers, "Idempotency-Key": "other-retry-123"}, json={}).status_code == 409
    assert len(dispatcher.started) == 3  # initial, retry, idempotent dispatch retry
    second_id = UUID(response.json()["id"])
    with Session(engine) as db:
        assert finish_attempt(db, second_id, ProviderJobStatus(
            state="succeeded", output_url="/mock-frame.svg", media_type="image/svg+xml",
        ), providers) == "review"
    accept = client.post(f"/api/v1/attempts/{second_id}/reviews", headers=headers, json={"decision": "accepted"})
    assert accept.status_code == 201, accept.text
    assert accept.json()["failure_reason"] is None
    assert client.get(f"/api/v1/shots/{shot_id}", headers=headers).json()["status"] == "accepted"
    assert client.patch(f"/api/v1/shots/{shot_id}", headers=headers, json={"description": "Changed"}).status_code == 409
    attempts = client.get(f"/api/v1/shots/{shot_id}/attempts", headers=headers).json()
    assert [(item["attempt_number"], item["review"]["decision"]) for item in attempts] == [(1, "rejected"), (2, "accepted")]
    assert client.post(endpoint, headers={**headers, "Idempotency-Key": "late-retry-123"}, json={}).status_code == 409


def test_review_and_retry_are_workspace_scoped_and_budgeted(api):
    client, engine, _ = api
    headers = studio(client, "Studio")
    other = studio(client, "Other")
    shot_id = shot_for(client, headers, budget="0.28")
    attempt_id = generated(client, engine, headers, shot_id)
    assert client.get("/api/v1/review", headers=other).json() == []
    assert client.post(f"/api/v1/attempts/{attempt_id}/reviews", headers=other, json={"decision": "accepted"}).status_code == 404
    assert client.post(f"/api/v1/attempts/{attempt_id}/reviews", headers=headers, json={
        "decision": "accepted", "failure_reason": "other",
    }).status_code == 422
    assert client.post(f"/api/v1/attempts/{attempt_id}/reviews", headers=headers, json={
        "decision": "rejected", "failure_reason": "low_quality",
    }).status_code == 201
    retry = f"/api/v1/shots/{shot_id}/retry"
    assert client.post(retry, headers={**other, "Idempotency-Key": "foreign-retry-123"}, json={}).status_code == 404
    over_budget = client.post(retry, headers={**headers, "Idempotency-Key": "budget-retry-123"}, json={"provider": "mock-alt"})
    assert over_budget.status_code == 422
    assert "exceeds shot budget" in over_budget.json()["detail"]
    with Session(engine) as db:
        assert db.get(Shot, UUID(shot_id)).status == "rejected"
        assert len(db.scalars(select(GenerationAttempt)).all()) == 1
