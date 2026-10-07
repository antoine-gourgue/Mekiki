"""App settings, stored as a single JSON document so new fields need no migration."""

from __future__ import annotations

from sqlalchemy.orm import Session

from mekiki_engine.models import SettingRow
from mekiki_engine.schemas import AppSettings

SETTINGS_KEY = "app"


def load_settings(session: Session) -> AppSettings:
    """Saved settings, or the defaults when nothing has been saved yet."""
    row = session.get(SettingRow, SETTINGS_KEY)
    if row is None:
        return AppSettings()
    return AppSettings.model_validate_json(row.value)


def save_settings(session: Session, settings: AppSettings) -> AppSettings:
    payload = settings.model_dump_json()
    row = session.get(SettingRow, SETTINGS_KEY)
    if row is None:
        session.add(SettingRow(key=SETTINGS_KEY, value=payload))
    else:
        row.value = payload
    session.commit()
    return settings
