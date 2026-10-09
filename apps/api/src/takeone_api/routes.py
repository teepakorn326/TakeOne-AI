from typing import TypeVar
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .auth import CurrentUser, current_user, require_local_mode
from .db import get_db
from .models import Episode, Scene, Series, Shot, ShotSpec, User, Workspace, utc_now
from .schemas import (
    EpisodeCreate, EpisodeRead, EpisodeUpdate,
    SceneCreate, SceneRead, SceneUpdate,
    SeriesCreate, SeriesRead, SeriesUpdate,
    ShotCreate, ShotRead, ShotUpdate,
    WorkspaceBootstrap, WorkspaceCreate, WorkspaceRead,
)

router = APIRouter(prefix="/api/v1")
ModelT = TypeVar("ModelT")


def found(value: ModelT | None) -> ModelT:
    if value is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    return value


def commit(db: Session, value: ModelT) -> ModelT:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Number or email already exists in this workspace") from exc
    db.refresh(value)
    return value


def update(value: object, patch: object) -> None:
    for field, field_value in patch.model_dump(exclude_unset=True).items():
        if field_value is None and field != "budget_limit":
            raise HTTPException(status_code=422, detail=f"{field} cannot be null")
        setattr(value, field, field_value)


def series_for(db: Session, owner: CurrentUser, series_id: UUID) -> Series:
    return found(db.scalar(select(Series).where(Series.id == series_id, Series.workspace_id == owner.workspace_id)))


def episode_for(db: Session, owner: CurrentUser, episode_id: UUID) -> Episode:
    return found(db.scalar(select(Episode).join(Series).where(Episode.id == episode_id, Series.workspace_id == owner.workspace_id)))


def scene_for(db: Session, owner: CurrentUser, scene_id: UUID) -> Scene:
    return found(db.scalar(select(Scene).join(Episode).join(Series).where(Scene.id == scene_id, Series.workspace_id == owner.workspace_id)))


def shot_for(db: Session, owner: CurrentUser, shot_id: UUID) -> Shot:
    return found(db.scalar(select(Shot).join(Scene).join(Episode).join(Series).where(Shot.id == shot_id, Series.workspace_id == owner.workspace_id)))


@router.post("/workspaces", response_model=WorkspaceBootstrap, status_code=201)
def create_workspace(payload: WorkspaceCreate, db: Session = Depends(get_db)):
    require_local_mode()
    workspace = Workspace(name=payload.name)
    db.add(workspace)
    db.flush()
    owner = User(workspace_id=workspace.id, name=payload.owner_name, email=str(payload.owner_email), role="owner")
    db.add(owner)
    commit(db, owner)
    return WorkspaceBootstrap(workspace=WorkspaceRead.model_validate(workspace), owner_id=owner.id)


@router.get("/workspaces/current", response_model=WorkspaceRead)
def get_workspace(owner: CurrentUser = Depends(current_user), db: Session = Depends(get_db)):
    return found(db.get(Workspace, owner.workspace_id))


@router.post("/series", response_model=SeriesRead, status_code=201)
def create_series(payload: SeriesCreate, owner: CurrentUser = Depends(current_user), db: Session = Depends(get_db)):
    value = Series(workspace_id=owner.workspace_id, **payload.model_dump())
    db.add(value)
    return commit(db, value)


@router.get("/series", response_model=list[SeriesRead])
def list_series(owner: CurrentUser = Depends(current_user), db: Session = Depends(get_db)):
    return db.scalars(select(Series).where(Series.workspace_id == owner.workspace_id).order_by(Series.created_at.desc(), Series.id)).all()


@router.get("/series/{series_id}", response_model=SeriesRead)
def get_series(series_id: UUID, owner: CurrentUser = Depends(current_user), db: Session = Depends(get_db)):
    return series_for(db, owner, series_id)


@router.patch("/series/{series_id}", response_model=SeriesRead)
def patch_series(series_id: UUID, payload: SeriesUpdate, owner: CurrentUser = Depends(current_user), db: Session = Depends(get_db)):
    value = series_for(db, owner, series_id)
    update(value, payload)
    return commit(db, value)


@router.post("/series/{series_id}/episodes", response_model=EpisodeRead, status_code=201)
def create_episode(series_id: UUID, payload: EpisodeCreate, owner: CurrentUser = Depends(current_user), db: Session = Depends(get_db)):
    series_for(db, owner, series_id)
    value = Episode(series_id=series_id, **payload.model_dump())
    db.add(value)
    return commit(db, value)


@router.get("/series/{series_id}/episodes", response_model=list[EpisodeRead])
def list_episodes(series_id: UUID, owner: CurrentUser = Depends(current_user), db: Session = Depends(get_db)):
    series_for(db, owner, series_id)
    return db.scalars(select(Episode).where(Episode.series_id == series_id).order_by(Episode.episode_number)).all()


@router.get("/episodes/{episode_id}", response_model=EpisodeRead)
def get_episode(episode_id: UUID, owner: CurrentUser = Depends(current_user), db: Session = Depends(get_db)):
    return episode_for(db, owner, episode_id)


@router.patch("/episodes/{episode_id}", response_model=EpisodeRead)
def patch_episode(episode_id: UUID, payload: EpisodeUpdate, owner: CurrentUser = Depends(current_user), db: Session = Depends(get_db)):
    value = episode_for(db, owner, episode_id)
    update(value, payload)
    return commit(db, value)


@router.post("/episodes/{episode_id}/scenes", response_model=SceneRead, status_code=201)
def create_scene(episode_id: UUID, payload: SceneCreate, owner: CurrentUser = Depends(current_user), db: Session = Depends(get_db)):
    episode_for(db, owner, episode_id)
    value = Scene(episode_id=episode_id, **payload.model_dump())
    db.add(value)
    return commit(db, value)


@router.get("/episodes/{episode_id}/scenes", response_model=list[SceneRead])
def list_scenes(episode_id: UUID, owner: CurrentUser = Depends(current_user), db: Session = Depends(get_db)):
    episode_for(db, owner, episode_id)
    return db.scalars(select(Scene).where(Scene.episode_id == episode_id).order_by(Scene.scene_number)).all()


@router.get("/scenes/{scene_id}", response_model=SceneRead)
def get_scene(scene_id: UUID, owner: CurrentUser = Depends(current_user), db: Session = Depends(get_db)):
    return scene_for(db, owner, scene_id)


@router.patch("/scenes/{scene_id}", response_model=SceneRead)
def patch_scene(scene_id: UUID, payload: SceneUpdate, owner: CurrentUser = Depends(current_user), db: Session = Depends(get_db)):
    value = scene_for(db, owner, scene_id)
    update(value, payload)
    return commit(db, value)


@router.post("/scenes/{scene_id}/shots", response_model=ShotRead, status_code=201)
def create_shot(scene_id: UUID, payload: ShotCreate, owner: CurrentUser = Depends(current_user), db: Session = Depends(get_db)):
    scene_for(db, owner, scene_id)
    value = Shot(scene_id=scene_id, **payload.model_dump())
    db.add(value)
    return commit(db, value)


@router.get("/scenes/{scene_id}/shots", response_model=list[ShotRead])
def list_shots(scene_id: UUID, owner: CurrentUser = Depends(current_user), db: Session = Depends(get_db)):
    scene_for(db, owner, scene_id)
    return db.scalars(select(Shot).where(Shot.scene_id == scene_id).order_by(Shot.shot_number)).all()


@router.get("/shots/{shot_id}", response_model=ShotRead)
def get_shot(shot_id: UUID, owner: CurrentUser = Depends(current_user), db: Session = Depends(get_db)):
    return shot_for(db, owner, shot_id)


@router.patch("/shots/{shot_id}", response_model=ShotRead)
def patch_shot(shot_id: UUID, payload: ShotUpdate, owner: CurrentUser = Depends(current_user), db: Session = Depends(get_db)):
    value = shot_for(db, owner, shot_id)
    if value.status not in ("draft", "ready", "failed", "rejected"):
        raise HTTPException(status_code=409, detail="Shot is locked while generation or review is in progress")
    if value.status == "rejected" and "status" in payload.model_fields_set:
        raise HTTPException(status_code=409, detail="Rejected shots can only advance through Retry")
    changed = any(field != "status" and getattr(value, field) != data for field, data in payload.model_dump(exclude_unset=True).items())
    update(value, payload)
    spec = db.get(ShotSpec, value.id)
    if spec is not None and changed:
        spec.version += 1
        spec.updated_at = utc_now()
    return commit(db, value)
