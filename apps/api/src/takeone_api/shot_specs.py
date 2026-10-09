"""Structured shot planning, continuity, prompt compilation, and demo routing."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .auth import CurrentUser, current_user
from .db import get_db
from .generation import GenerationError, scoped_shot, spec_from_shot
from .models import Character, CharacterState, Episode, RoutingDecision, Scene, Series, Shot, ShotSpec, utc_now
from .providers import ProviderRegistry, providers
from .routes import series_for

router = APIRouter(prefix="/api/v1")


class ReadModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class CharacterWrite(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=5000)
    visual_reference_url: str = Field(default="", max_length=2000)
    notes: str = Field(default="", max_length=5000)


class CharacterRead(ReadModel, CharacterWrite):
    id: UUID
    series_id: UUID


class StateWrite(BaseModel):
    episode_start: int = Field(gt=0)
    episode_end: int = Field(gt=0)
    hairstyle: str = Field(default="", max_length=160)
    wardrobe: str = Field(default="", max_length=160)
    injury_state: str = Field(default="", max_length=160)
    props: str = Field(default="", max_length=2000)
    notes: str = Field(default="", max_length=5000)

    @model_validator(mode="after")
    def valid_range(self):
        if self.episode_end < self.episode_start:
            raise ValueError("Episode end must be at least episode start")
        return self


class StateRead(ReadModel, StateWrite):
    id: UUID
    character_id: UUID


class ShotSpecWrite(BaseModel):
    expected_version: int | None = Field(default=None, ge=0)
    character_ids: list[UUID] = Field(default_factory=list, max_length=20)
    location: str = Field(default="", max_length=160)
    action: str = Field(default="", max_length=5000)
    dialogue: str = Field(default="", max_length=5000)
    continuity_notes: str = Field(default="", max_length=5000)

    @model_validator(mode="after")
    def unique_characters(self):
        if len(set(self.character_ids)) != len(self.character_ids):
            raise ValueError("Each character may be selected only once")
        return self


class DecisionRead(ReadModel):
    id: UUID
    shot_id: UUID
    spec_version: int
    provider: str
    model: str
    reason: str
    estimated_cost: Decimal
    confidence: str
    rule_version: str
    is_mock: bool
    created_at: datetime


def series_id_for_shot(db: Session, shot: Shot) -> UUID:
    scene = db.get(Scene, shot.scene_id)
    return db.get(Episode, scene.episode_id).series_id


def owned_shot(db: Session, owner: CurrentUser, shot_id: UUID, lock: bool = False) -> Shot:
    try:
        return scoped_shot(db, shot_id, owner.workspace_id, lock=lock)
    except GenerationError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc


def shot_context(db: Session, shot: Shot) -> tuple[Scene, Episode]:
    scene = db.get(Scene, shot.scene_id)
    return scene, db.get(Episode, scene.episode_id)


def spec_read(db: Session, shot: Shot) -> dict:
    spec = db.get(ShotSpec, shot.id)
    scene, episode = shot_context(db, shot)
    return {
        "shot_id": str(shot.id), "series_id": str(episode.series_id),
        "saved": spec is not None, "version": spec.version if spec else 0,
        "description": shot.description, "shot_type": shot.shot_type,
        "duration_seconds": str(shot.duration_seconds), "number_of_characters": shot.number_of_characters,
        "dialogue_present": shot.dialogue_present, "object_interaction": shot.object_interaction,
        "motion_complexity": shot.motion_complexity, "camera_motion": shot.camera_motion,
        "quality_requirement": shot.quality_threshold,
        "budget_limit_usd": str(shot.budget_limit) if shot.budget_limit is not None else None,
        "character_ids": spec.character_ids if spec else [],
        "location": spec.location if spec else scene.location,
        "action": spec.action if spec else "",
        "dialogue": spec.dialogue if spec else "",
        "continuity_notes": spec.continuity_notes if spec else "",
    }


def character_for(db: Session, owner: CurrentUser, character_id: UUID) -> Character:
    value = db.scalar(select(Character).join(Series).where(
        Character.id == character_id, Series.workspace_id == owner.workspace_id,
    ))
    if value is None:
        raise HTTPException(404, "Character not found")
    return value


def state_for(db: Session, owner: CurrentUser, state_id: UUID) -> CharacterState:
    value = db.scalar(select(CharacterState).join(Character).join(Series).where(
        CharacterState.id == state_id, Series.workspace_id == owner.workspace_id,
    ))
    if value is None:
        raise HTTPException(404, "Character state not found")
    return value


def no_overlap(db: Session, character_id: UUID, start: int, end: int, exclude: UUID | None = None) -> None:
    query = select(CharacterState.id).where(
        CharacterState.character_id == character_id,
        CharacterState.episode_start <= end, CharacterState.episode_end >= start,
    )
    if exclude:
        query = query.where(CharacterState.id != exclude)
    if db.scalar(query) is not None:
        raise HTTPException(409, "Character state overlaps another episode range")


def continuity_for(db: Session, shot: Shot, spec: ShotSpec) -> list[dict]:
    _, episode = shot_context(db, shot)
    if not spec.character_ids:
        return []
    ids = [UUID(value) for value in spec.character_ids]
    characters = db.scalars(select(Character).where(Character.id.in_(ids))).all()
    by_id = {character.id: character for character in characters}
    result = []
    for character_id in ids:
        character = by_id.get(character_id)
        if character is None:
            continue
        state = db.scalar(select(CharacterState).where(
            CharacterState.character_id == character_id,
            CharacterState.episode_start <= episode.episode_number,
            CharacterState.episode_end >= episode.episode_number,
        ))
        result.append({
            "id": str(character.id), "name": character.name, "description": character.description,
            "visual_reference_url": character.visual_reference_url, "notes": character.notes,
            "state": StateRead.model_validate(state).model_dump(mode="json") if state else None,
        })
    return result


def compile_prompt(shot_spec: dict, continuity: list[dict], provider: str, direction: str = "") -> str:
    """Deterministic provider format; the mock variants make formatting observable."""
    lines = [
        f"Shot: {shot_spec['description'] or shot_spec['action']}",
        f"Type: {shot_spec['shot_type'] or 'unspecified'}; duration: {shot_spec['duration_seconds']}s",
        f"Location: {shot_spec['location'] or 'unspecified'}",
        f"Action: {shot_spec['action'] or 'unspecified'}",
        f"Dialogue: {shot_spec['dialogue'] or ('present' if shot_spec['dialogue_present'] else 'none')}",
        f"Camera: {shot_spec['camera_motion']}; motion: {shot_spec['motion_complexity']}; object interaction: {shot_spec['object_interaction']}",
        f"Quality: {shot_spec['quality_requirement']}",
    ]
    for item in continuity:
        state = item["state"] or {}
        details = ", ".join(f"{label}: {state[key]}" for key, label in (
            ("hairstyle", "hair"), ("wardrobe", "wardrobe"), ("injury_state", "injury"), ("props", "props"), ("notes", "state notes"),
        ) if state.get(key))
        lines.append(f"Character {item['name']}: {item['description']}; reference: {item['visual_reference_url']}; {details}")
    if shot_spec["continuity_notes"]:
        lines.append(f"Continuity: {shot_spec['continuity_notes']}")
    if direction.strip():
        lines.append(f"Creative direction: {direction.strip()}")
    if provider == "mock-alt":
        return "SCENE BRIEF\n" + "\n".join(f"- {line}" for line in lines)
    return "SHOT PROMPT\n" + "\n".join(lines)


def choose_provider(shot: Shot, registry: ProviderRegistry) -> tuple[str, str, Decimal, str, bool]:
    options = []
    for capabilities in registry.capabilities():
        for model in capabilities.models:
            try:
                cost = registry.get(capabilities.name).estimate_cost(spec_from_shot(shot), model)
            except ValueError:
                continue
            if shot.budget_limit is None or cost <= shot.budget_limit:
                options.append((capabilities.name, model, cost, capabilities.is_mock))
    if not options:
        raise HTTPException(422, "No provider supports this shot within its duration and budget limits")
    detailed = shot.motion_complexity == "high" or shot.object_interaction or ("close" in shot.shot_type.lower() and shot.dialogue_present)
    preferred = "mock-alt" if detailed else "mock"
    matching = [option for option in options if option[0] == preferred]
    chosen = min(matching or options, key=lambda item: (item[2], item[0], item[1]))
    reason = (
        "Demo heuristic: motion, interaction, or close dialogue selects the alternate mock route. "
        if detailed else "Demo heuristic: simpler shots select the standard mock route. "
    ) if chosen[0] == preferred else "Preferred demo route exceeds this shot's budget or duration; selected an eligible fallback. "
    reason += "Mock routes have no measured quality advantage; compare only workflow and simulated price."
    return *chosen[:3], reason, chosen[3]


@router.post("/series/{series_id}/characters", response_model=CharacterRead, status_code=201)
def create_character(series_id: UUID, payload: CharacterWrite, owner: CurrentUser = Depends(current_user), db: Session = Depends(get_db)):
    series_for(db, owner, series_id)
    value = Character(series_id=series_id, **payload.model_dump())
    db.add(value)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Character name already exists in this series") from exc
    db.refresh(value)
    return value


@router.get("/series/{series_id}/characters", response_model=list[CharacterRead])
def list_characters(series_id: UUID, owner: CurrentUser = Depends(current_user), db: Session = Depends(get_db)):
    series_for(db, owner, series_id)
    return db.scalars(select(Character).where(Character.series_id == series_id).order_by(Character.name)).all()


@router.patch("/characters/{character_id}", response_model=CharacterRead)
def patch_character(character_id: UUID, payload: CharacterWrite, owner: CurrentUser = Depends(current_user), db: Session = Depends(get_db)):
    value = character_for(db, owner, character_id)
    for key, data in payload.model_dump().items():
        setattr(value, key, data)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Character name already exists in this series") from exc
    db.refresh(value)
    return value


@router.delete("/characters/{character_id}", status_code=204)
def delete_character(character_id: UUID, owner: CurrentUser = Depends(current_user), db: Session = Depends(get_db)):
    value = character_for(db, owner, character_id)
    for spec in db.scalars(select(ShotSpec).join(Shot).join(Scene).join(Episode).where(Episode.series_id == value.series_id)):
        if str(character_id) in spec.character_ids:
            raise HTTPException(409, "Remove this character from shot specs before deleting")
    db.delete(value)
    db.commit()


@router.post("/characters/{character_id}/states", response_model=StateRead, status_code=201)
def create_state(character_id: UUID, payload: StateWrite, owner: CurrentUser = Depends(current_user), db: Session = Depends(get_db)):
    character_for(db, owner, character_id)
    no_overlap(db, character_id, payload.episode_start, payload.episode_end)
    value = CharacterState(character_id=character_id, **payload.model_dump())
    db.add(value)
    db.commit()
    db.refresh(value)
    return value


@router.get("/characters/{character_id}/states", response_model=list[StateRead])
def list_states(character_id: UUID, owner: CurrentUser = Depends(current_user), db: Session = Depends(get_db)):
    character_for(db, owner, character_id)
    return db.scalars(select(CharacterState).where(CharacterState.character_id == character_id).order_by(CharacterState.episode_start)).all()


@router.patch("/character-states/{state_id}", response_model=StateRead)
def patch_state(state_id: UUID, payload: StateWrite, owner: CurrentUser = Depends(current_user), db: Session = Depends(get_db)):
    value = state_for(db, owner, state_id)
    no_overlap(db, value.character_id, payload.episode_start, payload.episode_end, state_id)
    for key, data in payload.model_dump().items():
        setattr(value, key, data)
    db.commit()
    db.refresh(value)
    return value


@router.delete("/character-states/{state_id}", status_code=204)
def delete_state(state_id: UUID, owner: CurrentUser = Depends(current_user), db: Session = Depends(get_db)):
    db.delete(state_for(db, owner, state_id))
    db.commit()


@router.get("/shots/{shot_id}/spec")
def get_spec(shot_id: UUID, owner: CurrentUser = Depends(current_user), db: Session = Depends(get_db)):
    return spec_read(db, owned_shot(db, owner, shot_id))


@router.put("/shots/{shot_id}/spec")
def put_spec(shot_id: UUID, payload: ShotSpecWrite, owner: CurrentUser = Depends(current_user), db: Session = Depends(get_db)):
    shot = owned_shot(db, owner, shot_id, lock=True)
    if shot.status not in ("draft", "ready", "failed", "rejected"):
        raise HTTPException(409, "Shot is locked while generation or review is in progress")
    spec = db.get(ShotSpec, shot.id)
    if payload.expected_version is not None and payload.expected_version != (spec.version if spec else 0):
        raise HTTPException(409, "Shot spec changed; reload before saving")
    if payload.character_ids:
        ids = db.scalars(select(Character.id).where(Character.id.in_(payload.character_ids), Character.series_id == series_id_for_shot(db, shot))).all()
        if len(ids) != len(payload.character_ids):
            raise HTTPException(422, "Characters must belong to this shot's series")
        shot.number_of_characters = len(ids)
    if spec is None:
        spec = ShotSpec(shot_id=shot.id, version=1)
        db.add(spec)
    else:
        spec.version += 1
    for key, data in payload.model_dump(exclude={"expected_version"}).items():
        setattr(spec, key, [str(value) for value in data] if key == "character_ids" else data)
    spec.updated_at = utc_now()
    db.commit()
    return spec_read(db, shot)


@router.post("/shots/{shot_id}/recommendation", response_model=DecisionRead, status_code=201)
def recommend(shot_id: UUID, owner: CurrentUser = Depends(current_user), db: Session = Depends(get_db)):
    shot = owned_shot(db, owner, shot_id)
    spec = db.get(ShotSpec, shot_id)
    if spec is None:
        raise HTTPException(409, "Save a shot spec before requesting a recommendation")
    provider, model, cost, reason, is_mock = choose_provider(shot, providers)
    value = RoutingDecision(shot_id=shot_id, spec_version=spec.version, provider=provider, model=model,
                            estimated_cost=cost, reason=reason, confidence="low", rule_version="demo-v1", is_mock=is_mock)
    db.add(value)
    db.commit()
    db.refresh(value)
    return value


@router.get("/shots/{shot_id}/recommendations", response_model=list[DecisionRead])
def recommendations(shot_id: UUID, owner: CurrentUser = Depends(current_user), db: Session = Depends(get_db)):
    owned_shot(db, owner, shot_id)
    return db.scalars(select(RoutingDecision).where(RoutingDecision.shot_id == shot_id).order_by(RoutingDecision.created_at.desc(), RoutingDecision.id.desc())).all()
