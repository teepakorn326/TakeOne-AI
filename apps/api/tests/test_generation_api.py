import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from takeone_api.db import Base, get_db
from takeone_api.main import app
from takeone_api.temporal_dispatch import get_dispatcher
from takeone_api import models  # noqa: F401 - registers tables


class FakeDispatcher:
    def __init__(self):
        self.started = []
        self.cancelled = []
        self.fail_start = False

    async def start(self, attempt_id):
        self.started.append(attempt_id)
        if self.fail_start:
            raise ConnectionError("Temporal offline")

    async def cancel(self, attempt_id):
        self.cancelled.append(attempt_id)


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
        yield client, dispatcher
    app.dependency_overrides.clear()
    engine.dispose()


def setup_shot(client):
    workspace = client.post("/api/v1/workspaces", json={"name": "Studio", "owner_name": "Producer", "owner_email": "producer@example.com"}).json()
    headers = {"X-Workspace-Id": workspace["workspace"]["id"], "X-User-Id": workspace["owner_id"]}
    series_id = client.post("/api/v1/series", headers=headers, json={"title": "Pilot"}).json()["id"]
    episode_id = client.post(f"/api/v1/series/{series_id}/episodes", headers=headers, json={"episode_number": 1, "title": "Opening"}).json()["id"]
    scene_id = client.post(f"/api/v1/episodes/{episode_id}/scenes", headers=headers, json={"scene_number": 1}).json()["id"]
    shot_id = client.post(f"/api/v1/scenes/{scene_id}/shots", headers=headers, json={"shot_number": 1, "duration_seconds": "4.00"}).json()["id"]
    assert client.patch(f"/api/v1/shots/{shot_id}", headers=headers, json={"status": "ready"}).status_code == 200
    return headers, shot_id


def test_attempt_api_idempotency_and_lock(api):
    client, dispatcher = api
    headers, shot_id = setup_shot(client)
    estimate = client.get(f"/api/v1/shots/{shot_id}/estimate", headers=headers)
    assert estimate.status_code == 200
    assert estimate.json()["estimated_cost"] == "0.2600"
    assert client.get("/api/v1/settings/providers", headers=headers).json()[0]["name"] == "mock"
    submit_headers = {**headers, "Idempotency-Key": "same-request-123"}
    payload = {"provider": "mock", "model": "mock-v1", "prompt": "Actor enters"}
    first = client.post(f"/api/v1/shots/{shot_id}/attempts", headers=submit_headers, json=payload)
    assert first.status_code == 202, first.text
    assert first.json()["attempt_number"] == 1
    second = client.post(f"/api/v1/shots/{shot_id}/attempts", headers=submit_headers, json=payload)
    assert second.status_code == 202 and second.json()["id"] == first.json()["id"]
    assert len(dispatcher.started) == 2
    assert client.post(f"/api/v1/shots/{shot_id}/attempts", headers=submit_headers, json={**payload, "prompt": "Different"}).status_code == 409
    assert client.patch(f"/api/v1/shots/{shot_id}", headers=headers, json={"status": "ready"}).status_code == 409
    attempts = client.get(f"/api/v1/shots/{shot_id}/attempts", headers=headers).json()
    assert len(attempts) == 1
    assert client.get(f"/api/v1/attempts/{first.json()['id']}/cost-events", headers=headers).json() == []
    cancel = client.post(f"/api/v1/attempts/{first.json()['id']}/cancel", headers=headers)
    assert cancel.status_code == 202
    assert len(dispatcher.cancelled) == 1


def test_dispatch_failure_can_retry_same_key(api):
    client, dispatcher = api
    headers, shot_id = setup_shot(client)
    submit_headers = {**headers, "Idempotency-Key": "retry-request-123"}
    dispatcher.fail_start = True
    first = client.post(f"/api/v1/shots/{shot_id}/attempts", headers=submit_headers, json={"prompt": "Actor enters"})
    assert first.status_code == 503
    dispatcher.fail_start = False
    second = client.post(f"/api/v1/shots/{shot_id}/attempts", headers=submit_headers, json={"prompt": "Actor enters"})
    assert second.status_code == 202
    assert second.json()["attempt_number"] == 1
    assert len(client.get(f"/api/v1/shots/{shot_id}/attempts", headers=headers).json()) == 1


def test_attempts_are_workspace_scoped(api):
    client, _ = api
    headers, shot_id = setup_shot(client)
    submit_headers = {**headers, "Idempotency-Key": "scoped-request-123"}
    attempt_id = client.post(f"/api/v1/shots/{shot_id}/attempts", headers=submit_headers, json={"prompt": "Actor enters"}).json()["id"]
    other = client.post("/api/v1/workspaces", json={"name": "Other", "owner_name": "Other", "owner_email": "other@example.com"}).json()
    other_headers = {"X-Workspace-Id": other["workspace"]["id"], "X-User-Id": other["owner_id"]}
    assert client.get(f"/api/v1/shots/{shot_id}/attempts", headers=other_headers).status_code == 404
    assert client.get(f"/api/v1/attempts/{attempt_id}", headers=other_headers).status_code == 404
    assert client.get(f"/api/v1/attempts/{attempt_id}/cost-events", headers=other_headers).status_code == 404
    assert client.post(f"/api/v1/attempts/{attempt_id}/cancel", headers=other_headers).status_code == 404
