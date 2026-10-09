import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from test_photos import JPEG, encoded, new_item

from mekiki_engine.browser import publish, service
from mekiki_engine.browser.chrome import ChromeError
from mekiki_engine.browser.publish import _html, condition_grade, euros
from mekiki_engine.browser.service import Browsers


class FakeSession:
    def __init__(self) -> None:
        self.opened = 0
        self.closed: list[str] = []
        self.running = True
        self.visible = False

    @contextmanager
    def new_tab(self, url: str = "about:blank") -> Iterator[tuple[object, str]]:
        self.opened += 1
        yield object(), f"tab-{self.opened}"

    def close_tab(self, target_id: str) -> None:
        self.closed.append(target_id)

    def stop(self) -> None:
        self.running = False

    def set_visible(self, visible: bool) -> None:
        self.visible = visible


@pytest.fixture
def chrome(client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    session = FakeSession()
    client.app.state.browsers = Browsers(
        tmp_path, session_factory=lambda _profile: session, pause_s=(0, 0)
    )  # type: ignore[attr-defined,arg-type,return-value]
    seen: dict[str, Any] = {"session": session, "listings": []}

    def fake_vinted(_tab: object, listing: publish.Listing, **_options: object) -> str:
        seen["listings"].append(listing)
        return "https://www.vinted.fr/items/42-pikachu"

    def failing_ebay(_tab: object, _listing: publish.Listing, **_options: object) -> str:
        raise ChromeError("mise en vente eBay : le site n'a pas confirmé la publication")

    monkeypatch.setitem(service.PUBLISHERS, "vinted", fake_vinted)
    monkeypatch.setitem(service.PUBLISHERS, "ebay", failing_ebay)
    return seen


def card(client: TestClient, condition: str | None = "Near Mint") -> dict[str, Any]:
    item = new_item(client)
    return client.patch(f"/items/{item['id']}", json={"condition": condition}).json()  # type: ignore[no-any-return]


def wait_job(client: TestClient, site: str, item_id: int) -> dict[str, Any]:
    for _ in range(50):
        job = client.get(f"/browser/{site}/publish/{item_id}").json()
        if job and job["status"] != "running":
            return job  # type: ignore[no-any-return]
        time.sleep(0.05)
    raise AssertionError("the job never ended")


@pytest.mark.parametrize(
    ("condition", "grade"),
    [
        ("Near Mint", "mint"),
        ("NM", "mint"),
        ("MT", "mint"),
        ("Comme neuve", "mint"),
        ("Très bon état", "excellent"),
        ("EX", "excellent"),
        ("LP", "excellent"),
        ("Light Played", "excellent"),
        ("Bon état", "good"),
        ("GD", "good"),
        ("Rayures", "good"),
        ("Near Mint, légères rayures", "good"),
        ("Played", "played"),
        ("PL", "played"),
        ("PO", "played"),
        ("Etat correct", "played"),
        ("Satisfaisant", "played"),
        ("HP, coin abîmé", "played"),
        (None, None),
        ("", None),
        ("Superbe", None),
    ],
)
def test_conditions_map_to_the_sites_grades(condition: str | None, grade: str | None) -> None:
    assert condition_grade(condition) == grade


def test_listing_text_is_written_as_the_sites_take_it() -> None:
    assert euros(1250) == "12,50"
    assert _html("Carte : Pikachu.\nÉtat : NM\n\nEnvoi <soigné>") == (
        "<p>Carte : Pikachu.<br>État : NM</p><p>Envoi &lt;soigné&gt;</p>"
    )


def test_a_published_card_is_marked_for_sale(client: TestClient, chrome: dict[str, Any]) -> None:
    item = card(client)
    client.post(f"/items/{item['id']}/photos", json=encoded(JPEG))
    body = {"title": "Pikachu 025/165", "description": "Carte japonaise.", "price_cents": 1500}

    started = client.post(f"/browser/vinted/publish/{item['id']}", json=body)
    job = wait_job(client, "vinted", item["id"])

    assert started.status_code == 202
    assert job["status"] == "done"
    assert job["url"] == "https://www.vinted.fr/items/42-pikachu"
    [listing] = chrome["listings"]
    assert listing.title == "Pikachu 025/165"
    assert len(listing.photos) == 1 and listing.photos[0].is_file()
    assert chrome["session"].closed == ["tab-1"]
    stored = client.get(f"/items/{item['id']}").json()
    assert (stored["listing_platform"], stored["listing_price_cents"]) == ("vinted", 1500)


def test_a_failed_publication_leaves_the_form_open(
    client: TestClient, chrome: dict[str, Any]
) -> None:
    item = card(client)
    body = {"title": "Pikachu 025/165", "description": "Carte japonaise.", "price_cents": 1500}

    client.post(f"/browser/ebay/publish/{item['id']}", json=body)
    job = wait_job(client, "ebay", item["id"])

    assert job["status"] == "failed"
    assert "n'a pas confirmé" in job["error"]
    assert chrome["session"].closed == []
    # The form left open shows, for the user to finish it.
    assert chrome["session"].visible is True
    assert client.get(f"/items/{item['id']}").json()["listing_platform"] is None
    assert client.get("/browser/ebay/publish/999").json() is None
    other = client.post("/browser/vinted/publish/999", json=body)
    assert other.status_code == 404


@pytest.mark.parametrize("condition", [None, "Superbe"])
def test_a_card_whose_condition_is_unknown_is_not_published_as_near_mint(
    client: TestClient, chrome: dict[str, Any], condition: str | None
) -> None:
    item = card(client, condition)
    body = {"title": "Pikachu 025/165", "description": "Carte japonaise.", "price_cents": 1500}

    refused = client.post(f"/browser/vinted/publish/{item['id']}", json=body)

    assert refused.status_code == 422
    assert "indiquez l'état de la carte" in refused.json()["detail"]
    if condition:
        assert f"« {condition} »" in refused.json()["detail"]
    assert chrome["session"].opened == 0
    assert chrome["listings"] == []
    assert client.get(f"/browser/vinted/publish/{item['id']}").json() is None
