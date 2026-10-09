"""Per-account app settings, stored as one JSON document so new fields need no migration."""

from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from mekiki_engine.models import SettingRow
from mekiki_engine.schemas import AppSettings, EbayKeys

logger = logging.getLogger(__name__)
# Documents already reported, so a damaged one is logged once rather than on every request.
_reported: set[tuple[int, str]] = set()
_INVALID = object()


def settings_key(user_id: int) -> str:
    return f"app:{user_id}"


def load_settings(session: Session, user_id: int) -> AppSettings:
    """Saved settings of the account, or the defaults when nothing has been saved yet.

    Never fails: a value this version refuses (a choice since removed, a document from
    another version) takes its default, and the rest of the document is kept. Failing would
    break every request of the account and stop its scans.
    """
    row = session.get(SettingRow, settings_key(user_id))
    if row is None:
        return AppSettings()
    try:
        return AppSettings.model_validate_json(row.value)
    except ValidationError as error:
        problem = str(error)
    try:
        settings = _lenient(AppSettings, json.loads(row.value))
    except ValueError as error:
        problem, settings = str(error), AppSettings()
    if (user_id, row.value) not in _reported:
        _reported.add((user_id, row.value))
        logger.warning(
            "Mekiki, paramètres du compte %s : valeurs refusées remplacées par défaut (%s)",
            user_id,
            problem,
        )
    return settings


def _lenient[M: BaseModel](model: type[M], data: object) -> M:
    """``model`` from ``data``, keeping what validates: an invalid field takes its default,
    a list or mapping loses its invalid entries, a sub-object is repaired field by field."""
    if not isinstance(data, dict):
        return model()
    kept: dict[str, Any] = {}
    for name, value in data.items():
        if name in model.model_fields:
            repaired = _repaired(model, kept, name, value)
            if repaired is not _INVALID:
                kept[name] = repaired
    try:
        return model.model_validate(kept)
    except ValidationError:
        return model()


def _repaired(model: type[BaseModel], kept: dict[str, Any], name: str, value: Any) -> Any:
    def valid(candidate: Any) -> bool:
        try:
            model.model_validate({**kept, name: candidate})
        except ValidationError:
            return False
        return True

    if valid(value):
        return value
    annotation = model.model_fields[name].annotation
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return _lenient(annotation, value)
    if isinstance(value, list):
        entries: list[Any] = []
        for entry in value:
            if valid([*entries, entry]):
                entries.append(entry)
        return entries
    if isinstance(value, dict):
        mapping: dict[Any, Any] = {}
        for key, entry in value.items():
            if valid({**mapping, key: entry}):
                mapping[key] = entry
        return mapping
    return _INVALID


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
