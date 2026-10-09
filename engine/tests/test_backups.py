from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
from conftest import cardmarket_handler
from fastapi.testclient import TestClient

from mekiki_engine.app import create_app
from mekiki_engine.config import load_config
from mekiki_engine.services import backups


def set_fx(client: TestClient, fx: int) -> None:
    settings = client.get("/settings").json()
    settings["fx_jpy_per_eur"] = fx
    assert client.put("/settings", json=settings).status_code == 200


def test_a_backup_can_be_put_back(client: TestClient) -> None:
    set_fx(client, 160)
    saved = client.post("/backups").json()
    set_fx(client, 150)

    before = client.post(f"/backups/{saved['name']}/restore")

    assert before.status_code == 200
    assert client.get("/settings").json()["fx_jpy_per_eur"] == 160
    listed = client.get("/backups").json()
    # The database as it was before the restore is kept too, so a restore can be undone.
    assert {b["name"] for b in listed["backups"]} == {saved["name"], before.json()["name"]}
    assert listed["restore_allowed"] is True
    assert listed["folder"].endswith("backups")


def test_only_the_latest_copies_are_kept(client: TestClient, tmp_path: Path) -> None:
    engine = client.app.state.db_engine  # type: ignore[attr-defined]
    start = datetime(2026, 1, 1, tzinfo=UTC)
    for day in range(backups.KEEP + 2):
        backups.create_backup(engine, tmp_path, now=start + timedelta(days=day))

    kept = backups.list_backups(tmp_path)

    assert len(kept) == backups.KEEP
    assert kept[0].name == "mekiki-20260201-000000-000.sqlite3"
    assert kept[-1].name == "mekiki-20260103-000000-000.sqlite3"
    assert not list((tmp_path / "backups").glob("*.partial"))


def test_the_daily_copy_waits_a_day(client: TestClient, tmp_path: Path) -> None:
    engine = client.app.state.db_engine  # type: ignore[attr-defined]
    now = datetime(2026, 10, 9, 8, tzinfo=UTC)

    assert backups.backup_if_due(engine, tmp_path, now=now) is True
    assert backups.backup_if_due(engine, tmp_path, now=now + timedelta(hours=23)) is False
    assert backups.backup_if_due(engine, tmp_path, now=now + timedelta(hours=25)) is True


def test_only_a_listed_copy_is_restored(client: TestClient) -> None:
    assert client.post("/backups/mekiki-20260101-000000-000.sqlite3/restore").status_code == 404
    assert client.post("/backups/settings.json/restore").status_code == 404


def test_a_served_engine_never_restores(client: TestClient) -> None:
    app = client.app
    saved = client.post("/backups").json()
    app.state.config = replace(app.state.config, host="0.0.0.0")  # type: ignore[attr-defined]

    refused = client.post(f"/backups/{saved['name']}/restore")

    assert refused.status_code == 403
    assert client.get("/backups").json()["restore_allowed"] is False


def test_the_sign_in_page_knows_when_no_account_exists(tmp_path: Path, client: TestClient) -> None:
    assert client.get("/auth/status").json() == {"accounts_exist": True}
    empty = create_app(
        load_config(data_dir=str(tmp_path / "empty"), background_jobs=False),
        http_transport=httpx.MockTransport(cardmarket_handler),
    )
    with TestClient(empty, base_url="http://127.0.0.1:18421") as fresh:
        assert fresh.get("/auth/status").json() == {"accounts_exist": False}
