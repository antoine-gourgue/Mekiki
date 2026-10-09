"""Per-account app settings, stored as one JSON document so new fields need no migration."""

from __future__ import annotations

from sqlalchemy.orm import Session

from mekiki_engine.models import SettingRow
from mekiki_engine.schemas import AppSettings, EbayKeys


def settings_key(user_id: int) -> str:
    return f"app:{user_id}"


def load_settings(session: Session, user_id: int) -> AppSettings:
    """Saved settings of the account, or the defaults when nothing has been saved yet."""
    row = session.get(SettingRow, settings_key(user_id))
    if row is None:
        return AppSettings()
    return AppSettings.model_validate_json(row.value)


def ebay_keys_key(user_id: int) -> str:
    return f"ebay:{user_id}"


def load_ebay_keys(session: Session, user_id: int) -> EbayKeys | None:
    """The account's own eBay keys; kept apart from the settings, which the app reads whole."""
    row = session.get(SettingRow, ebay_keys_key(user_id))
    return EbayKeys.model_validate_json(row.value) if row is not None else None


def save_ebay_keys(session: Session, user_id: int, keys: EbayKeys | None) -> None:
    row = session.get(SettingRow, ebay_keys_key(user_id))
    if keys is None:
        if row is not None:
            session.delete(row)
    elif row is None:
        session.add(SettingRow(key=ebay_keys_key(user_id), value=keys.model_dump_json()))
    else:
        row.value = keys.model_dump_json()
    session.commit()


def deepl_key_key(user_id: int) -> str:
    return f"deepl:{user_id}"


def load_deepl_key(session: Session, user_id: int) -> str | None:
    """The account's DeepL API key; like the eBay keys, never part of the settings sent out."""
    row = session.get(SettingRow, deepl_key_key(user_id))
    return row.value if row is not None else None


def save_deepl_key(session: Session, user_id: int, key: str | None) -> None:
    row = session.get(SettingRow, deepl_key_key(user_id))
    if key is None:
        if row is not None:
            session.delete(row)
    elif row is None:
        session.add(SettingRow(key=deepl_key_key(user_id), value=key))
    else:
        row.value = key
    session.commit()


def save_settings(session: Session, user_id: int, settings: AppSettings) -> AppSettings:
    payload = settings.model_dump_json()
    row = session.get(SettingRow, settings_key(user_id))
    if row is None:
        session.add(SettingRow(key=settings_key(user_id), value=payload))
    else:
        row.value = payload
    session.commit()
    return settings
