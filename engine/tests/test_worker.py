import copy
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from conftest import CARDMARKET_FILES, cardmarket_handler
from fastapi.testclient import TestClient

from mekiki_engine.domain import Game
from mekiki_engine.scanner import card_index, cardmarket, runner
from mekiki_engine.scanner.runner import ScannerWorker
from mekiki_engine.scanner.sources.base import PoliteClient


def worker(client: TestClient, **options: object) -> ScannerWorker:
    app = client.app
    return ScannerWorker(app.state.session_factory, app.state.http, **options)  # type: ignore[attr-defined,arg-type]


def test_the_worker_survives_a_failing_chore(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(*_args: object) -> None:
        raise ArithmeticError("avg30 illisible")

    ticks: list[str] = []
    monkeypatch.setattr(runner, "refresh_reference_data", broken)
    scanner = worker(client, on_tick=lambda: ticks.append("backup"))

    scanner.tick()
    scanner.tick()

    # The daily chores still ran after the reference data failed.
    assert ticks == ["backup", "backup"]


def test_a_crashed_scan_waits_before_trying_again(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def crash(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("titre inattendu")

    monkeypatch.setattr(runner, "scan_tracked_cards", crash)
    scanner = worker(client)
    user_id = client.get("/auth/me").json()["id"]

    scanner.run_now(user_id)

    state = scanner._accounts[user_id]
    assert state.last_error == "Erreur inattendue : titre inattendu"
    assert state.next_run_at is not None
    assert state.next_run_at - datetime.now(UTC) > timedelta(minutes=25)


def test_a_malformed_price_guide_waits_before_asking_again(client: TestClient) -> None:
    files = copy.deepcopy(CARDMARKET_FILES)
    files["price_guide_6.json"]["priceGuides"][0]["avg30"] = ""
    asked: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        name = request.url.path.rsplit("/", 1)[-1]
        asked.append(name)
        if name in files:
            return httpx.Response(200, json=files[name])
        return cardmarket_handler(request)

    http = PoliteClient(
        intervals_s={}, default_interval_s=0, transport=httpx.MockTransport(handler)
    )
    with client.app.state.session_factory() as session:  # type: ignore[attr-defined]
        first = cardmarket.refresh(session, http, Game.POKEMON)
        again = cardmarket.refresh(session, http, Game.POKEMON)

    assert any("price_guide" in error for error in first)
    assert again == [error for error in first if "price_guide" in error]
    assert asked.count("price_guide_6.json") == 1


def test_an_empty_archive_never_wipes_the_index(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    client.post("/cardmarket/refresh", json={})
    with client.app.state.session_factory() as session:  # type: ignore[attr-defined]
        before = card_index.indexed_count(session)
        monkeypatch.setattr(card_index, "parse_archive", lambda _archive: [])
        # As when TCGdex publishes a new commit: the archive is read again.
        monkeypatch.setattr(card_index, "needs_rebuild", lambda _session: True)

        error = card_index.refresh(session, client.app.state.http, force=True)  # type: ignore[attr-defined]

        assert before > 0
        assert error is not None and "l'ancien est gardé" in error
        assert card_index.indexed_count(session) == before
