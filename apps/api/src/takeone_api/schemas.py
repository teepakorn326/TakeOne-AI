from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ReadModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    owner_name: str = Field(min_length=1, max_length=160)
    owner_email: EmailStr


class WorkspaceRead(ReadModel):
    id: UUID
    name: str
    created_at: datetime


class WorkspaceBootstrap(BaseModel):
    workspace: WorkspaceRead
    owner_id: UUID


class SeriesCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = ""
    genre: str = Field(default="", max_length=80)


class SeriesUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    genre: str | None = Field(default=None, max_length=80)
    status: Literal["draft", "active", "complete"] | None = None


class SeriesRead(ReadModel):
    id: UUID
    workspace_id: UUID
    title: str
    description: str
    genre: str
    status: str
    created_at: datetime


class EpisodeCreate(BaseModel):
    episode_number: int = Field(gt=0)
    title: str = Field(min_length=1, max_length=200)


class EpisodeUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    status: Literal["draft", "active", "complete"] | None = None


class EpisodeRead(ReadModel):
    id: UUID
    series_id: UUID
    episode_number: int
    title: str
    status: str


class SceneCreate(BaseModel):
    scene_number: int = Field(gt=0)
    description: str = ""
    location: str = Field(default="", max_length=160)
    time_of_day: str = Field(default="", max_length=80)


class SceneUpdate(BaseModel):
    description: str | None = None
    location: str | None = Field(default=None, max_length=160)
    time_of_day: str | None = Field(default=None, max_length=80)


class SceneRead(ReadModel):
    id: UUID
    episode_id: UUID
    scene_number: int
    description: str
    location: str
    time_of_day: str


class ShotCreate(BaseModel):
    shot_number: int = Field(gt=0)
    description: str = ""
    shot_type: str = Field(default="", max_length=80)
    duration_seconds: Decimal = Field(gt=0, max_digits=8, decimal_places=2)
    number_of_characters: int = Field(default=0, ge=0)
    dialogue_present: bool = False
    object_interaction: bool = False
    motion_complexity: Literal["low", "medium", "high"] = "low"
    camera_motion: str = Field(default="static", max_length=80)
    quality_threshold: Literal["draft", "standard", "high"] = "standard"
    budget_limit: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=4)


class ShotUpdate(BaseModel):
    description: str | None = None
    shot_type: str | None = Field(default=None, max_length=80)
    duration_seconds: Decimal | None = Field(default=None, gt=0, max_digits=8, decimal_places=2)
    number_of_characters: int | None = Field(default=None, ge=0)
    dialogue_present: bool | None = None
    object_interaction: bool | None = None
    motion_complexity: Literal["low", "medium", "high"] | None = None
    camera_motion: str | None = Field(default=None, max_length=80)
    quality_threshold: Literal["draft", "standard", "high"] | None = None
    budget_limit: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=4)
    status: Literal["draft", "ready"] | None = None


class ShotRead(ReadModel):
    id: UUID
    scene_id: UUID
    shot_number: int
    description: str
    shot_type: str
    duration_seconds: Decimal
    number_of_characters: int
    dialogue_present: bool
    object_interaction: bool
    motion_complexity: str
    camera_motion: str
    quality_threshold: str
    budget_limit: Decimal | None
    status: str


class ReviewRead(ReadModel):
    id: UUID
    generation_attempt_id: UUID
    reviewer_id: UUID
    decision: Literal["accepted", "rejected"]
    failure_reason: str | None
    notes: str
    created_at: datetime
