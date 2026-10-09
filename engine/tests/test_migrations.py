from pathlib import Path

import pytest
from sqlalchemy import inspect

from mekiki_engine import migrations
from mekiki_engine.db import create_db_engine


def test_a_migration_failing_halfway_leaves_no_trace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = create_db_engine(f"sqlite:///{tmp_path / 'mekiki.sqlite3'}")
    broken = (
        "CREATE TABLE half_done (id INTEGER PRIMARY KEY);"
        "ALTER TABLE users ADD COLUMN half_done TEXT;"
        "INSERT INTO no_such_table VALUES (1)"
    )
    monkeypatch.setattr(migrations, "MIGRATIONS", (*migrations.MIGRATIONS, (999, broken)))

    with pytest.raises(Exception, match="no_such_table"), engine.begin() as connection:
        migrations.apply_migrations(connection)

    tables = inspect(engine).get_table_names()
    columns = {column["name"] for column in inspect(engine).get_columns("users")}
    assert "half_done" not in tables
    assert "half_done" not in columns
    monkeypatch.undo()
    # The next start applies what is left, as if nothing had happened.
    with engine.begin() as connection:
        assert migrations.apply_migrations(connection) == []
