from __future__ import annotations

from fastapi import APIRouter

from mekiki_engine.deps import SessionDep, SettingsDep, UserDep
from mekiki_engine.schemas import AppSettings
from mekiki_engine.services.settings_service import save_settings

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("")
def read_settings(settings: SettingsDep) -> AppSettings:
    return settings


@router.put("")
def replace_settings(payload: AppSettings, session: SessionDep, user: UserDep) -> AppSettings:
    return save_settings(session, user.id, payload)
