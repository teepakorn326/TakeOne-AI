from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models import User


@dataclass(frozen=True)
class CurrentUser:
    id: UUID
    workspace_id: UUID
    role: str


def require_local_mode() -> None:
    if settings.takeone_env != "local":
        raise HTTPException(status_code=503, detail="Verified authentication is required outside local mode")


def current_user(
    workspace_id: UUID = Header(alias="X-Workspace-Id"),
    user_id: UUID = Header(alias="X-User-Id"),
    db: Session = Depends(get_db),
) -> CurrentUser:
    require_local_mode()
    user = db.scalar(select(User).where(User.id == user_id, User.workspace_id == workspace_id))
    if user is None:
        raise HTTPException(status_code=403, detail="User is not a member of this workspace")
    return CurrentUser(id=user.id, workspace_id=user.workspace_id, role=user.role)

