"""Per-account app settings, stored as one JSON document so new fields need no migration."""

from __future__ import annotations

from sqlalchemy.orm import Session

from mekiki_engine.models import SettingRow
from mekiki_engine.schemas import AppSettings


def settings_key(user_id: int) -> str:
    return f"app:{user_id}"


def load_settings(session: Session, user_id: int) -> AppSettings:
    """Saved settings of the account, or the defaults when nothing has been saved yet."""
    row = session.get(SettingRow, settings_key(user_id))
    if row is None:
        return AppSettings()
    return AppSettings.model_validate_json(row.value)


def save_settings(session: Session, user_id: int, settings: AppSettings) -> AppSettings:
    payload = settings.model_dump_json()
    row = session.get(SettingRow, settings_key(user_id))
    if row is None:
        session.add(SettingRow(key=settings_key(user_id), value=payload))
    else:
        row.value = payload
    session.commit()
    return settings
