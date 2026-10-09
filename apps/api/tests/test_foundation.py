import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from takeone_api.db import Base, get_db
from takeone_api.main import app
from takeone_api import models  # noqa: F401 - registers all tables


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)

    def session_override():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = session_override
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    engine.dispose()


def bootstrap(client: TestClient, name: str):
    response = client.post("/api/v1/workspaces", json={"name": name, "owner_name": "Producer", "owner_email": "producer@example.com"})
    assert response.status_code == 201, response.text
    body = response.json()
    return {"X-Workspace-Id": body["workspace"]["id"], "X-User-Id": body["owner_id"]}


def create_hierarchy(client: TestClient, headers: dict[str, str]):
    series = client.post("/api/v1/series", headers=headers, json={"title": "Pilot", "genre": "Drama"})
    assert series.status_code == 201, series.text
    sid = series.json()["id"]
    episode = client.post(f"/api/v1/series/{sid}/episodes", headers=headers, json={"episode_number": 1, "title": "Episode 1"})
    assert episode.status_code == 201, episode.text
    eid = episode.json()["id"]
    scene = client.post(f"/api/v1/episodes/{eid}/scenes", headers=headers, json={"scene_number": 1, "location": "Kitchen"})
    assert scene.status_code == 201, scene.text
    cid = scene.json()["id"]
    shot = client.post(f"/api/v1/scenes/{cid}/shots", headers=headers, json={"shot_number": 1, "description": "An actor enters", "duration_seconds": "4.5"})
    assert shot.status_code == 201, shot.text
    return sid, eid, cid, shot.json()["id"]


def test_create_and_update_hierarchy(client: TestClient):
    headers = bootstrap(client, "Studio A")
    sid, eid, cid, shot_id = create_hierarchy(client, headers)
    assert len(client.get("/api/v1/series", headers=headers).json()) == 1
    assert client.get(f"/api/v1/series/{sid}/episodes", headers=headers).json()[0]["id"] == eid
    assert client.get(f"/api/v1/episodes/{eid}/scenes", headers=headers).json()[0]["id"] == cid
    assert client.get(f"/api/v1/scenes/{cid}/shots", headers=headers).json()[0]["id"] == shot_id
    response = client.patch(f"/api/v1/shots/{shot_id}", headers=headers, json={"status": "ready", "budget_limit": "8.25"})
    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert response.json()["budget_limit"] == "8.2500"


def test_workspace_isolation_including_parent_paths(client: TestClient):
    first = bootstrap(client, "Studio A")
    second = bootstrap(client, "Studio B")
    sid, eid, cid, shot_id = create_hierarchy(client, first)
    assert client.get("/api/v1/series", headers=second).json() == []
    for path in [f"/series/{sid}", f"/episodes/{eid}", f"/scenes/{cid}", f"/shots/{shot_id}", f"/series/{sid}/episodes", f"/episodes/{eid}/scenes", f"/scenes/{cid}/shots"]:
        assert client.get(f"/api/v1{path}", headers=second).status_code == 404
    assert client.post(f"/api/v1/scenes/{cid}/shots", headers=second, json={"shot_number": 2, "duration_seconds": 3}).status_code == 404
    assert client.patch(f"/api/v1/shots/{shot_id}", headers=second, json={"status": "ready"}).status_code == 404
    forged = {"X-Workspace-Id": second["X-Workspace-Id"], "X-User-Id": first["X-User-Id"]}
    assert client.get("/api/v1/series", headers=forged).status_code == 403


def test_duplicate_numbers_and_invalid_shots(client: TestClient):
    headers = bootstrap(client, "Studio A")
    sid, eid, cid, _ = create_hierarchy(client, headers)
    assert client.post(f"/api/v1/series/{sid}/episodes", headers=headers, json={"episode_number": 1, "title": "Duplicate"}).status_code == 409
    assert client.post(f"/api/v1/episodes/{eid}/scenes", headers=headers, json={"scene_number": 1}).status_code == 409
    assert client.post(f"/api/v1/scenes/{cid}/shots", headers=headers, json={"shot_number": 1, "duration_seconds": 3}).status_code == 409
    assert client.post(f"/api/v1/scenes/{cid}/shots", headers=headers, json={"shot_number": 2, "duration_seconds": 0}).status_code == 422
    assert client.post(f"/api/v1/scenes/{cid}/shots", headers=headers, json={"shot_number": 2, "duration_seconds": 3, "budget_limit": -1}).status_code == 422


def test_no_nulling_required_fields(client: TestClient):
    headers = bootstrap(client, "Studio A")
    sid, _, _, shot_id = create_hierarchy(client, headers)
    assert client.patch(f"/api/v1/series/{sid}", headers=headers, json={"title": None}).status_code == 422
    assert client.patch(f"/api/v1/shots/{shot_id}", headers=headers, json={"duration_seconds": None}).status_code == 422
