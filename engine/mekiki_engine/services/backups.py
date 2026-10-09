"""Daily copies of the database, and putting one back.

The database holds the stock, the sales, the books and the settings of every account on this
computer: a lost or damaged file would cost the business its accounts. A copy is taken each
day the engine runs, with SQLite's online backup (safe while the engine writes), and the
latest ``KEEP`` are kept next to the database. Photos stay in their own folder.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import Engine

from mekiki_engine.migrations import apply_migrations

FOLDER = "backups"
KEEP = 30
MAX_AGE = timedelta(hours=24)
_NAME = re.compile(r"^mekiki-(\d{8}-\d{6})-\d{3}\.sqlite3$")
_STAMP = "%Y%m%d-%H%M%S"


class BackupNotFoundError(LookupError):
    pass


@dataclass(frozen=True, slots=True)
class Backup:
    name: str
    created_at: str
    size_bytes: int


def folder(data_dir: Path) -> Path:
    return data_dir / FOLDER


def list_backups(data_dir: Path) -> list[Backup]:
    """Newest first."""
    found = []
    for path in folder(data_dir).glob("mekiki-*.sqlite3"):
        match = _NAME.match(path.name)
        if match is None:
            continue
        created = datetime.strptime(match[1], _STAMP).replace(tzinfo=UTC)
        found.append(Backup(path.name, created.strftime("%Y-%m-%dT%H:%M:%SZ"), path.stat().st_size))
    return sorted(found, key=lambda backup: backup.name, reverse=True)


def create_backup(engine: Engine, data_dir: Path, *, now: datetime | None = None) -> Backup:
    """Copies the live database, then keeps only the latest ``KEEP`` copies."""
    now = now or datetime.now(UTC)
    target = folder(data_dir)
    target.mkdir(parents=True, exist_ok=True)
    name = _name(now)
    # A restore takes a copy of the database just before: it must not replace the one restored.
    while (target / name).exists():
        now += timedelta(milliseconds=1)
        name = _name(now)
    # Written under another name first: a copy cut short must never look like a backup.
    partial = target / f"{name}.partial"
    raw = engine.raw_connection()
    try:
        copy = sqlite3.connect(partial)
        try:
            raw.driver_connection.backup(copy)  # type: ignore[union-attr]
        finally:
            copy.close()
    finally:
        raw.close()
    partial.replace(target / name)
    for old in list_backups(data_dir)[KEEP:]:
        (target / old.name).unlink(missing_ok=True)
    return next(backup for backup in list_backups(data_dir) if backup.name == name)


def _name(moment: datetime) -> str:
    return f"mekiki-{moment.strftime(_STAMP)}-{moment.microsecond // 1000:03d}.sqlite3"


def backup_if_due(engine: Engine, data_dir: Path, *, now: datetime | None = None) -> bool:
    """Takes the day's copy when the latest one is older than a day; True when it did."""
    now = now or datetime.now(UTC)
    latest = next(iter(list_backups(data_dir)), None)
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
    before = create_backup(engine, data_dir)
    backup = sqlite3.connect(source)
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
