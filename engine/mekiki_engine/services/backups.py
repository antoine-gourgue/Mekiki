"""Daily copies of the database, and putting one back.

The database holds the stock, the sales, the books and the settings of every account on this
computer: a lost or damaged file would cost the business its accounts. A copy is taken each
day the engine runs, with SQLite's online backup (safe while the engine writes), and kept next
to the database. Daily, manual and pre-restore copies are kept apart: clicking "Sauvegarder"
thirty times must not push a month of daily copies out. Photos stay in their own folder.
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from sqlalchemy import Engine

from mekiki_engine.migrations import apply_migrations

FOLDER = "backups"
Kind = Literal["daily", "manual", "before-restore"]
# How many copies of each kind are kept.
KEEP: dict[Kind, int] = {"daily": 30, "manual": 10, "before-restore": 5}
MAX_AGE = timedelta(hours=24)
# The kind is written in the name; daily copies keep the plain name of older versions.
SUFFIXES: dict[Kind, str] = {"daily": "", "manual": "-manuelle", "before-restore": "-avant"}
_NAME = re.compile(r"^mekiki-(\d{8}-\d{6})-\d{3}(-manuelle|-avant)?\.sqlite3$")
_STAMP = "%Y%m%d-%H%M%S"


class BackupNotFoundError(LookupError):
    pass


class BackupUnreadableError(ValueError):
    """The copy is damaged, empty or not a Mekiki database: restoring it would lose data."""


@dataclass(frozen=True, slots=True)
class Backup:
    name: str
    created_at: str
    size_bytes: int
    kind: Kind = "daily"


def folder(data_dir: Path) -> Path:
    return data_dir / FOLDER


def list_backups(data_dir: Path) -> list[Backup]:
    """Newest first."""
    kinds = {suffix: kind for kind, suffix in SUFFIXES.items()}
    found = []
    for path in folder(data_dir).glob("mekiki-*.sqlite3"):
        match = _NAME.match(path.name)
        if match is None:
            continue
        created = datetime.strptime(match[1], _STAMP).replace(tzinfo=UTC)
        found.append(
            Backup(
                path.name,
                created.strftime("%Y-%m-%dT%H:%M:%SZ"),
                path.stat().st_size,
                kinds[match[2] or ""],
            )
        )
    return sorted(found, key=lambda backup: backup.name, reverse=True)


def create_backup(
    engine: Engine,
    data_dir: Path,
    *,
    now: datetime | None = None,
    kind: Kind = "daily",
    protect: Iterable[str] = (),
) -> Backup:
    """Copies the live database, then keeps only the latest copies of that kind; the copies
    named in ``protect`` are never removed."""
    now = now or datetime.now(UTC)
    target = folder(data_dir)
    target.mkdir(parents=True, exist_ok=True)
    name = _name(now, kind)
    # A restore takes a copy of the database just before: it must not replace the one restored.
    while (target / name).exists():
        now += timedelta(milliseconds=1)
        name = _name(now, kind)
    # Written under another name first: a copy cut short must never look like a backup.
    partial = target / f"{name}.partial"
    raw = engine.raw_connection()
    try:
        copy = sqlite3.connect(partial)
        try:
            raw.driver_connection.backup(copy)  # type: ignore[union-attr]
        finally:
            copy.close()
        partial.replace(target / name)
    finally:
        raw.close()
        partial.unlink(missing_ok=True)
    kept = set(protect) | {name}
    same_kind = [backup for backup in list_backups(data_dir) if backup.kind == kind]
    for old in same_kind[KEEP[kind] :]:
        if old.name not in kept:
            (target / old.name).unlink(missing_ok=True)
    return next(backup for backup in list_backups(data_dir) if backup.name == name)


def _name(moment: datetime, kind: Kind) -> str:
    stamp = f"{moment.strftime(_STAMP)}-{moment.microsecond // 1000:03d}"
    return f"mekiki-{stamp}{SUFFIXES[kind]}.sqlite3"


def backup_if_due(engine: Engine, data_dir: Path, *, now: datetime | None = None) -> bool:
    """Takes the day's copy when the latest daily one is older than a day; True when it did."""
    now = now or datetime.now(UTC)
    latest = next((b for b in list_backups(data_dir) if b.kind == "daily"), None)
    if latest is not None:
        taken = datetime.strptime(latest.created_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
        if now - taken < MAX_AGE:
            return False
    create_backup(engine, data_dir, now=now)
    return True


def restore(engine: Engine, data_dir: Path, name: str) -> Backup:
    """Puts a copy back in place of the live database; returns the copy of the database as it
    was just before, so that a restore can itself be undone."""
    source = folder(data_dir) / name
    if _NAME.match(name) is None or not source.is_file():
        raise BackupNotFoundError(name)
    _check_readable(source)
    before = create_backup(engine, data_dir, kind="before-restore", protect={name})
    # Read-only: a copy that vanished must fail, not be recreated empty and restored.
    backup = sqlite3.connect(f"{source.as_uri()}?mode=ro", uri=True)
    raw = engine.raw_connection()
    try:
        backup.backup(raw.driver_connection)  # type: ignore[arg-type]
    finally:
        raw.close()
        backup.close()
    # Pooled connections may hold pages of the replaced file.
    engine.dispose()
    # A copy taken by an older version of Mekiki lacks the latest tables.
    with engine.begin() as connection:
        apply_migrations(connection)
    return before


def _check_readable(source: Path) -> None:
    try:
        copy = sqlite3.connect(f"{source.as_uri()}?mode=ro", uri=True)
        try:
            healthy = copy.execute("PRAGMA quick_check").fetchone()[0] == "ok"
            users = copy.execute(
                "SELECT count(*) FROM sqlite_master WHERE type = 'table' AND name = 'users'"
            ).fetchone()[0]
        finally:
            copy.close()
    except sqlite3.Error as error:
        raise BackupUnreadableError(str(error)) from error
    if not healthy or not users:
        raise BackupUnreadableError("copie abîmée ou vide")
