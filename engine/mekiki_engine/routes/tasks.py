from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Request

from mekiki_engine.deps import SessionDep, SettingsDep, UserDep
from mekiki_engine.schemas import TaskOut
from mekiki_engine.services import tasks

router = APIRouter(tags=["tasks"])


@router.get("/tasks")
def list_tasks(
    request: Request, session: SessionDep, user: UserDep, settings: SettingsDep
) -> list[TaskOut]:
    """What to do now, most pressing first."""
    return tasks.list_tasks(
        session,
        user.id,
        settings,
        today=date.today(),
        backup_error=request.app.state.backup_error,
    )
