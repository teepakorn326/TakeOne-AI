from test_generation_api import api, setup_shot  # noqa: F401
from test_review import api as review_api, studio, shot_for  # noqa: F401

from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from takeone_api.generation import finish_attempt
from takeone_api.providers import GenerationSpec, ProviderJobStatus, providers
from takeone_api.shot_specs import choose_provider
from takeone_api.models import Shot


def test_structured_generation_freezes_continuity_and_versions(api):
    client, dispatcher = api
    headers, shot_id = setup_shot(client)
    scene_id = client.get(f"/api/v1/shots/{shot_id}", headers=headers).json()["scene_id"]
    episode_id = client.get(f"/api/v1/scenes/{scene_id}", headers=headers).json()["episode_id"]
    series_id = client.get(f"/api/v1/episodes/{episode_id}", headers=headers).json()["series_id"]
    character = client.post(f"/api/v1/series/{series_id}/characters", headers=headers, json={"name": "Mara", "description": "Short hair"})
    assert character.status_code == 201, character.text
    cid = character.json()["id"]
    state = client.post(f"/api/v1/characters/{cid}/states", headers=headers, json={"episode_start": 1, "episode_end": 2, "wardrobe": "Blue coat"})
    assert state.status_code == 201, state.text
    assert client.post(f"/api/v1/characters/{cid}/states", headers=headers, json={"episode_start": 2, "episode_end": 3}).status_code == 409
    saved = client.put(f"/api/v1/shots/{shot_id}/spec", headers=headers, json={"character_ids": [cid], "location": "Kitchen", "action": "Mara turns", "dialogue": "Hello", "continuity_notes": "Keep coat dry"})
    assert saved.status_code == 200, saved.text
    assert saved.json()["version"] == 1
    assert client.put(f"/api/v1/shots/{shot_id}/spec", headers=headers, json={"expected_version": 0, "action": "Stale"}).status_code == 409
    assert saved.json()["number_of_characters"] == 1
    decision = client.post(f"/api/v1/shots/{shot_id}/recommendation", headers=headers)
    assert decision.status_code == 201, decision.text
    assert decision.json()["spec_version"] == 1
    assert decision.json()["is_mock"] is True
    assert decision.json()["confidence"] == "low"
    assert len(client.get(f"/api/v1/shots/{shot_id}/recommendations", headers=headers).json()) == 1
    assert client.patch(f"/api/v1/shots/{shot_id}", headers=headers, json={"motion_complexity": "high"}).status_code == 200
    assert client.get(f"/api/v1/shots/{shot_id}/spec", headers=headers).json()["version"] == 2
    alt = client.post(f"/api/v1/shots/{shot_id}/recommendation", headers=headers).json()
    assert alt["provider"] == "mock-alt"
    key = {**headers, "Idempotency-Key": "structured-shot-123"}
    assert client.post(f"/api/v1/shots/{shot_id}/attempts", headers=key, json={"prompt": "This would be ignored"}).status_code == 422
    request = {"provider": alt["provider"], "model": alt["model"], "creative_direction": "Warm light"}
    first = client.post(f"/api/v1/shots/{shot_id}/attempts", headers=key, json=request)
    assert first.status_code == 202, first.text
    attempt = first.json()
    assert attempt["prompt_source"] == "structured"
    assert "Blue coat" in attempt["prompt"] and "Warm light" in attempt["prompt"]
    assert attempt["shot_snapshot"]["structured_spec"]["version"] == 2
    assert attempt["shot_snapshot"]["continuity"][0]["state"]["wardrobe"] == "Blue coat"
    assert GenerationSpec.from_snapshot(attempt["shot_snapshot"]).duration_seconds == Decimal("4.00")
    assert client.post(f"/api/v1/shots/{shot_id}/attempts", headers=key, json=request).json()["id"] == attempt["id"]
    assert len(dispatcher.started) == 2
    assert client.post(f"/api/v1/shots/{shot_id}/attempts", headers=key, json={**request, "creative_direction": "Cold light"}).status_code == 409
    assert client.put(f"/api/v1/shots/{shot_id}/spec", headers=headers, json={"action": "Changed"}).status_code == 409


def test_scoping_budget_and_character_deletion(api):
    client, _ = api
    headers, shot_id = setup_shot(client)
    scene_id = client.get(f"/api/v1/shots/{shot_id}", headers=headers).json()["scene_id"]
    episode_id = client.get(f"/api/v1/scenes/{scene_id}", headers=headers).json()["episode_id"]
    series_id = client.get(f"/api/v1/episodes/{episode_id}", headers=headers).json()["series_id"]
    own = client.post(f"/api/v1/series/{series_id}/characters", headers=headers, json={"name": "Mara"}).json()["id"]
    other = client.post("/api/v1/workspaces", json={"name": "Other", "owner_name": "Other", "owner_email": "other@example.com"}).json()
    foreign_headers = {"X-Workspace-Id": other["workspace"]["id"], "X-User-Id": other["owner_id"]}
    foreign_series = client.post("/api/v1/series", headers=foreign_headers, json={"title": "Foreign"}).json()["id"]
    foreign_character = client.post(f"/api/v1/series/{foreign_series}/characters", headers=foreign_headers, json={"name": "Else"}).json()["id"]
    assert client.put(f"/api/v1/shots/{shot_id}/spec", headers=headers, json={"character_ids": [foreign_character]}).status_code == 422
    assert client.get(f"/api/v1/shots/{shot_id}/spec", headers=foreign_headers).status_code == 404
    assert client.get(f"/api/v1/characters/{own}/states", headers=foreign_headers).status_code == 404
    assert client.put(f"/api/v1/shots/{shot_id}/spec", headers=headers, json={"character_ids": [own]}).status_code == 200
    assert client.delete(f"/api/v1/characters/{own}", headers=headers).status_code == 409
    assert client.patch(f"/api/v1/shots/{shot_id}", headers=headers, json={"budget_limit": "0.01"}).status_code == 200
    assert client.post(f"/api/v1/shots/{shot_id}/recommendation", headers=headers).status_code == 422


def test_structured_retry_recompiles_from_updated_spec(review_api):
    client, engine, _ = review_api
    headers = studio(client, "Studio")
    shot_id = shot_for(client, headers)
    assert client.put(f"/api/v1/shots/{shot_id}/spec", headers=headers, json={"action": "Walk in"}).status_code == 200
    first = client.post(f"/api/v1/shots/{shot_id}/attempts", headers={**headers, "Idempotency-Key": "first-structured-123"}, json={"creative_direction": "Blue light"})
    assert first.status_code == 202, first.text
    first_id = first.json()["id"]
    with Session(engine) as db:
        finish_attempt(db, UUID(first_id), ProviderJobStatus(state="succeeded", output_url="/mock-frame.svg", media_type="image/svg+xml"), providers)
    assert client.post(f"/api/v1/attempts/{first_id}/reviews", headers=headers, json={"decision": "rejected", "failure_reason": "story_mismatch"}).status_code == 201
    changed = client.put(f"/api/v1/shots/{shot_id}/spec", headers=headers, json={"action": "Run out"})
    assert changed.status_code == 200 and changed.json()["version"] == 2
    retry = client.post(f"/api/v1/shots/{shot_id}/retry", headers={**headers, "Idempotency-Key": "second-structured-123"}, json={"provider": "mock-alt"})
    assert retry.status_code == 202, retry.text
    assert "Run out" in retry.json()["prompt"] and "Blue light" in retry.json()["prompt"]
    assert retry.json()["prompt"].startswith("SCENE BRIEF")
    assert "Run out" not in first.json()["prompt"]
    assert retry.json()["shot_snapshot"]["structured_spec"]["version"] == 2


def test_demo_routing_prefers_close_dialogue_and_respects_budget():
    shot = Shot(description="Talk", shot_type="Close-up", duration_seconds=Decimal("4.00"),
                number_of_characters=1, dialogue_present=True, object_interaction=False,
                motion_complexity="low", camera_motion="static", quality_threshold="standard")
    provider, model, cost, reason, is_mock = choose_provider(shot, providers)
    assert (provider, model, cost, is_mock) == ("mock-alt", "mock-alt-v1", Decimal("0.3000"), True)
    assert "no measured quality advantage" in reason
    shot.budget_limit = Decimal("0.27")
    provider, _, cost, reason, _ = choose_provider(shot, providers)
    assert provider == "mock" and cost == Decimal("0.2600")
    assert "fallback" in reason
