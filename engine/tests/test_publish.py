import re
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
from mekiki_engine.browser.publish import EBAY_SUCCESS, _html, condition_grade, euros
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
        raise seen["ebay_error"]

    seen["ebay_error"] = ChromeError(
        "choix de l'état eBay : la page n'a pas affiché « Non gradée »"
    )

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
    assert "Non gradée" in job["error"]
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


BODY = {"title": "Pikachu 025/165", "description": "Carte japonaise.", "price_cents": 1500}


def test_a_card_already_for_sale_on_the_site_is_not_published_twice(
    client: TestClient, chrome: dict[str, Any]
) -> None:
    item = card(client)
    client.post(f"/browser/vinted/publish/{item['id']}", json=BODY)
    wait_job(client, "vinted", item["id"])

    again = client.post(f"/browser/vinted/publish/{item['id']}", json=BODY)
    elsewhere = client.patch(f"/items/{item['id']}", json={"listing_platform": "ebay"})
    withdrawn_here = client.post(f"/browser/vinted/publish/{item['id']}", json=BODY)
    forced = client.post(f"/browser/vinted/publish/{item['id']}", json=BODY | {"force": True})
    wait_job(client, "vinted", item["id"])

    assert again.status_code == 409
    listed = "déjà en vente sur Vinted (https://www.vinted.fr/items/42-pikachu)"
    assert listed in again.json()["detail"]
    assert elsewhere.status_code == 200
    # The card no longer says so, but the job remembers it was published.
    assert withdrawn_here.status_code == 409
    assert "déjà été publiée sur Vinted" in withdrawn_here.json()["detail"]
    assert forced.status_code == 202
    assert len(chrome["listings"]) == 2


def test_a_failure_once_the_form_is_sent_is_left_to_check(
    client: TestClient, chrome: dict[str, Any]
) -> None:
    item = card(client)
    chrome["ebay_error"] = publish.PublishUnconfirmed(
        "mise en vente eBay : le site n'a pas confirmé la publication"
    )

    client.post(f"/browser/ebay/publish/{item['id']}", json=BODY)
    job = wait_job(client, "ebay", item["id"])
    again = client.post(f"/browser/ebay/publish/{item['id']}", json=BODY)
    forced = client.post(f"/browser/ebay/publish/{item['id']}", json=BODY | {"force": True})

    assert job["status"] == "to_check"
    assert "vérifiez vos annonces eBay avant de réessayer" in job["error"]
    assert chrome["session"].visible is True
    assert client.get(f"/items/{item['id']}").json()["listing_platform"] is None
    assert again.status_code == 409
    assert "n'a pas été confirmée" in again.json()["detail"]
    assert forced.status_code == 202


def test_errors_after_the_form_is_sent_say_the_listing_may_be_online() -> None:
    sent = publish._sending()
    with pytest.raises(publish.PublishUnconfirmed, match="Chrome a fermé la page"), sent:
        raise ChromeError("Chrome a fermé la page")


@pytest.mark.parametrize(
    ("url", "published"),
    [
        ("https://www.ebay.fr/sl/success?itemId=1", True),
        ("https://www.ebay.fr/lstng/success", True),
        ("https://www.ebay.fr/itm/123456789012", True),
        ("https://www.ebay.fr/lstng?draftId=1&mode=AddItem&success=0", False),
        ("https://signin.ebay.fr/ws?ru=https%3A%2F%2Fwww.ebay.fr%2Fsl%2Fsuccess", False),
        ("https://www.ebay.fr/sl/prelist/suggest?from=success", False),
    ],
)
def test_ebay_s_confirmation_is_its_own_address(url: str, published: bool) -> None:
    assert bool(re.search(EBAY_SUCCESS, url)) is published
