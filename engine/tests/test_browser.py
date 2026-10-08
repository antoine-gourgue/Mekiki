from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mekiki_engine.browser import markets
from mekiki_engine.browser.chrome import ChromeError
from mekiki_engine.browser.markets import is_relevant, median_cents, parse_listings
from mekiki_engine.browser.service import Browsers

# What the page scripts return, shaped like the real Vinted and eBay pages.
VINTED_RAW = [
    {
        "id": "1",
        "summary": "Dracaufeu ex 201/165 SAR japonaise, Marque: Pokémon, État: Très bon état, "
        "65.00 €, 68.95 €",
        "url": "https://www.vinted.fr/items/1-dracaufeu",
        "price": "65,00 €",
        "condition": "Très bon état",
        "image": None,
    },
    {
        "id": "2",
        "summary": "Dracaufeu ex 201 / 165 jap, Marque: Pokémon, État: Neuf, 75.00 €, 79.45 €",
        "url": "https://www.vinted.fr/items/2-dracaufeu",
        "price": "75,00 €",
        "condition": "Neuf",
        "image": None,
    },
    {
        "id": "3",
        "summary": "Dracaufeu ex 201/165 PSA 10, Marque: Pokémon, État: Neuf, 350.00 €, 368 €",
        "url": "https://www.vinted.fr/items/3-dracaufeu-psa",
        "price": "350,00 €",
        "condition": "Neuf",
        "image": None,
    },
    {
        "id": "4",
        "summary": "Dracaufeu ex 006/165, Marque: Pokémon, État: Bon état, 10.00 €, 11 €",
        "url": "https://www.vinted.fr/items/4-dracaufeu-rr",
        "price": "10,00 €",
        "condition": "Bon état",
        "image": None,
    },
]
EBAY_RAW = [
    {
        "id": "377512481554",
        "title": "Charizard ex 201/165 SAR Japanese Pokémon 151 SV2a NM",
        "url": "https://www.ebay.fr/itm/377512481554",
        "price": "355,00 EUR",
        "best_offer": False,
        "sold": "Vendu le 6 oct. 2026",
        "shipping": "Livraison gratuite",
        "image": None,
    },
    {
        "id": "237062610676",
        "title": "Charizard ex 201/165 SAR Japanese Pokémon 151 SV2a NM",
        "url": "https://www.ebay.fr/itm/237062610676",
        "price": "414,70 EUR",
        "best_offer": True,
        "sold": "Vendu le 4 oct. 2026",
        "shipping": "+3,47 EUR pour la livraison",
        "image": None,
    },
]


class FakeTab:
    def __init__(self, pages: dict[str, list[dict[str, Any]]], connected: bool) -> None:
        self.pages = pages
        self.connected = connected
        self.challenge = False
        self.visited: list[str] = []

    def navigate(self, url: str, *, timeout: float = 30) -> None:
        self.visited.append(url)

    def url(self) -> str:
        return self.visited[-1] if self.visited else "about:blank"

    def wait_for(self, condition: str, *, timeout: float = 30) -> Any:
        if condition in markets.CONNECTED_CHECKS.values():
            if not self.connected:
                raise ChromeError("pas connecté")
            return True
        return bool(self._current())

    def evaluate(self, expression: str, *, await_promise: bool = False) -> Any:
        if expression == markets.CHALLENGE_CHECK:
            return self.challenge
        return self._current()

    def _current(self) -> list[dict[str, Any]]:
        url = self.url()
        site = "vinted" if "vinted" in url else "ebay"
        return self.pages.get(site, [])


class FakeSession:
    def __init__(self, tab: FakeTab) -> None:
        self.tab = tab
        self.running = False
        self.visible = False
        self.pages_opened = 0

    @contextmanager
    def page(self) -> Iterator[FakeTab]:
        self.running = True
        self.pages_opened += 1
        yield self.tab

    def stop(self) -> None:
        self.running = False

    def set_visible(self, visible: bool) -> None:
        self.visible = visible

    def screenshot(self) -> bytes | None:
        return b"\xff\xd8\xff fake jpeg" if self.running else None


@pytest.fixture
def chrome(client: TestClient, tmp_path: Path) -> FakeSession:
    session = FakeSession(FakeTab({"vinted": VINTED_RAW, "ebay": EBAY_RAW}, connected=True))
    client.app.state.browsers = Browsers(tmp_path, session_factory=lambda _profile: session)  # type: ignore[attr-defined,arg-type,return-value]
    return session


def test_listings_count_only_ungraded_single_copies_of_the_card() -> None:
    vinted = parse_listings("vinted", VINTED_RAW, "201/165")

    assert vinted[0].title == "Dracaufeu ex 201/165 SAR japonaise"
    assert [listing.relevant for listing in vinted] == [True, True, False, False]
    assert median_cents(vinted) == 7000
    assert not is_relevant("Lot de 3 Dracaufeu ex 201/165", "201/165")
    assert is_relevant("Luffy OP05-119 parallèle", "OP05-119")
    assert not is_relevant("Dracaufeu ex promo 29", None, ["Dracaufeu"])


def test_ebay_accepted_offers_only_count_when_nothing_else_is_left() -> None:
    sold = parse_listings("ebay", EBAY_RAW, "201/165")

    assert sold[1].best_offer is True
    assert sold[1].shipping_cents == 347
    assert sold[0].detail == "Vendu le 6 oct. 2026"
    assert median_cents(sold) == 35500
    assert median_cents(sold[1:]) == 41470


def test_prices_are_read_once_then_kept(client: TestClient, chrome: FakeSession) -> None:
    body = {"query": "Dracaufeu ex 201/165", "card_number": "201/165"}

    first = client.post("/browser/vinted/prices", json=body).json()
    again = client.post("/browser/vinted/prices", json=body).json()

    assert first["relevant_count"] == 2
    assert first["median_cents"] == 7000
    assert (first["min_cents"], first["max_cents"]) == (6500, 7500)
    assert again == first
    assert chrome.pages_opened == 1
    assert chrome.tab.visited[0].startswith("https://www.vinted.fr/catalog?search_text=Dracaufeu")


def test_connection_is_checked_on_the_site(client: TestClient, chrome: FakeSession) -> None:
    assert client.post("/browser/ebay/check").json() == {"site": "ebay", "connected": True}
    chrome.tab.connected = False
    assert client.post("/browser/vinted/check").json() == {"site": "vinted", "connected": False}
    assert client.get("/browser/status").json()["running"] is True
    assert client.post("/browser/leboncoin/check").status_code == 422


def test_prices_read_in_chrome_join_the_verdict(client: TestClient, chrome: FakeSession) -> None:
    client.post("/cardmarket/refresh", json={})
    params = {"product_id": 719654, "label": "SV2a 201/165 · SAR"}
    before = client.get("/resale/verdict", params=params).json()
    assert before["card_number"] == "201/165"
    assert "Dracaufeu" in before["card_names"]
    queries = before["market_queries"]
    assert [o["platform"] for o in before["outlets"]] == ["cardmarket"]

    for site in ("vinted", "ebay"):
        client.post(
            f"/browser/{site}/prices",
            json={"query": queries[site], "card_number": before["card_number"]},
        )
    after = client.get("/resale/verdict", params=params).json()

    outlets = {o["platform"]: o for o in after["outlets"]}
    assert outlets["vinted"]["sale_cents"] == 7000
    assert outlets["ebay"]["sale_cents"] == 35500
    assert "ventes réussies eBay" in outlets["ebay"]["basis"]


def test_other_cards_and_languages_sharing_the_number_are_left_out() -> None:
    names = ["Charizard", "Dracaufeu", "リザードンex"]

    assert is_relevant("Dracaufeu ex SAR 201/165 / Pokémon 151 (Japonais)", "201/165", names)
    assert not is_relevant("Carte Pokémon Alakazam alternative 201/165", "201/165", names)
    assert not is_relevant("Dracaufeu ex SAR – SV2a 201/165 – Coréen", "201/165", names)
    assert not is_relevant("Charizard ex 201/165 sv2a KOR", "201/165", names)


def test_prices_far_from_the_others_are_left_out_of_the_median() -> None:
    raw = [
        {
            "id": str(i),
            "summary": f"Dracaufeu ex 201/165 n°{i}, Marque: Pokémon",
            "url": f"u{i}",
            "price": price,
        }
        for i, price in enumerate(["60,00 €", "65,00 €", "70,00 €", "1,00 €", "2 000,00 €"])
    ]
    listings = parse_listings("vinted", raw, "201/165", ["Dracaufeu"])

    assert median_cents(listings) == 6500


def test_searches_add_the_number_with_each_latin_name() -> None:
    from mekiki_engine.browser.markets import search_queries

    assert search_queries(
        "Dracaufeu ex 201/165", "201/165", ["Charizard", "Dracaufeu", "リザードンex"]
    ) == [
        "Dracaufeu ex 201/165",
        "Charizard 201/165",
        "Dracaufeu 201/165",
    ]
    assert search_queries("Pikachu", None, ["Pikachu"]) == ["Pikachu"]


def test_the_window_shows_to_sign_in_and_hides_once_signed_in(
    client: TestClient, chrome: FakeSession
) -> None:
    client.post("/browser/vinted/open")
    assert chrome.visible is True
    assert client.get("/browser/activity").json() == {
        "activity": None,
        "running": True,
        "visible": True,
    }

    assert client.post("/browser/vinted/check").json()["connected"] is True
    assert chrome.visible is False
    assert client.post("/browser/show").json()["visible"] is True
    assert client.post("/browser/hide").json()["visible"] is False


def test_the_preview_shows_what_chrome_shows(client: TestClient, chrome: FakeSession) -> None:
    assert client.get("/browser/preview").status_code == 204

    client.post("/browser/vinted/check")
    preview = client.get("/browser/preview")

    assert preview.status_code == 200
    assert preview.headers["content-type"] == "image/jpeg"
    assert preview.headers["cache-control"] == "no-store"


def test_a_bot_check_is_left_to_the_user(client: TestClient, chrome: FakeSession) -> None:
    chrome.tab.challenge = True

    read = client.post(
        "/browser/vinted/prices", json={"query": "Pikachu 173/165", "card_number": "173/165"}
    ).json()

    assert "vérification anti-robot" in read["error"]
    assert chrome.visible is True
    assert client.get("/browser/activity").json()["activity"] is None
