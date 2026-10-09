import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from mekiki_engine.browser import chrome as chrome_module
from mekiki_engine.browser import markets
from mekiki_engine.browser.chrome import ChromeError
from mekiki_engine.browser.markets import (
    is_relevant,
    median_cents,
    parse_listings,
    sales_within,
    sold_date,
)
from mekiki_engine.browser.service import Browsers


# What the page script returns, shaped like eBay.fr's sold listings.
def sale(item_id: str, title: str, price: str) -> dict[str, object]:
    return {
        "id": item_id,
        "title": title,
        "url": f"https://www.ebay.fr/itm/{item_id}",
        "price": price,
        "best_offer": False,
        "sold": "Vendu le 6 oct. 2026",
        "shipping": "Livraison gratuite",
        "image": None,
    }


FRENCH_SALES = [
    sale("1", "Dracaufeu ex 201/165 SAR japonaise", "65,00 EUR"),
    sale("2", "Dracaufeu ex 201 / 165 jap", "75,00 EUR"),
    sale("3", "Dracaufeu ex 201/165 PSA 10", "350,00 EUR"),
    sale("4", "Dracaufeu ex 006/165", "10,00 EUR"),
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
        # eBay sends signed-out visitors of its sold searches to its sign-in page.
        self.signed_out = False
        # Where eBay sends a search instead, e.g. its /splashui/ challenge.
        self.redirect: str | None = None
        # eBay says the search found nothing.
        self.no_results = False
        self.visited: list[str] = []

    def navigate(self, url: str, *, timeout: float = 30) -> None:
        if self.signed_out and "ebay.fr/sch" in url:
            url = "https://signin.ebay.fr/ws/eBayISAPI.dll?SignIn"
        elif self.redirect and "ebay.fr/sch" in url:
            url = self.redirect
        self.visited.append(url)

    def url(self) -> str:
        return self.visited[-1] if self.visited else "about:blank"

    def wait_for(self, condition: str, *, timeout: float = 30) -> Any:
        if condition in markets.CONNECTED_CHECKS.values():
            if not self.connected:
                raise ChromeError("pas connecté")
            return True
        if condition == markets.EBAY_RESULTS_SHOWN:
            if not (self._current() or self.no_results):
                raise ChromeError("la page n'a pas affiché ce qui était attendu à temps")
            return True
        return bool(self._current())

    def evaluate(self, expression: str, *, await_promise: bool = False) -> Any:
        if expression == markets.CHALLENGE_CHECK:
            return self.challenge
        return self._current()

    def _current(self) -> list[dict[str, Any]]:
        return self.pages.get("ebay", []) if "ebay.fr/sch" in self.url() else []


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


@pytest.fixture
def chrome(client: TestClient, tmp_path: Path) -> FakeSession:
    session = FakeSession(FakeTab({"ebay": EBAY_RAW}, connected=True))
    client.app.state.browsers = Browsers(
        tmp_path, session_factory=lambda _profile: session, pause_s=(0, 0)
    )  # type: ignore[attr-defined,arg-type,return-value]
    return session


def test_sales_count_only_ungraded_single_copies_of_the_card() -> None:
    sold = parse_listings(FRENCH_SALES, "201/165")

    assert sold[0].title == "Dracaufeu ex 201/165 SAR japonaise"
    assert [listing.relevant for listing in sold] == [True, True, False, False]
    assert median_cents(sold) == 7000
    assert not is_relevant("Lot de 3 Dracaufeu ex 201/165", "201/165")
    assert is_relevant("Luffy OP05-119 parallèle", "OP05-119")
    assert not is_relevant("Dracaufeu ex promo 29", None, ["Dracaufeu"])


@pytest.mark.parametrize(
    "title",
    [
        "Pikachu 025/165 PSA10",
        "Pikachu 025/165 PSA 9",
        "Pikachu 025/165 BGS9.5",
        "Pikachu 025/165 CGC10",
        "Pikachu 025/165 Graded 10",
        "Pikachu 025/165 carte gradée",
        "Pikachu 025/165 slab",
        "Pikachu 025/165 ARS10",
        "Pikachu 025/165 ACE 10",
        "Pikachu 025/165 TAG 9",
        "Pikachu 025/165 AGS 9.5",
        "Pikachu 025/165 x10",
        "Pikachu 025/165 x 4",
        "Pikachu 025/165 4x",
        "Pikachu 025/165 playset",
    ],
)
def test_graded_copies_and_several_copies_never_count(title: str) -> None:
    assert not is_relevant(title, "025/165", ["Pikachu"])


@pytest.mark.parametrize(
    "title",
    [
        "Pikachu 025/165 x1",
        "Pikachu & Zekrom GX Tag Team 025/165",
        "Mega Charizard X 025/165",
    ],
)
def test_names_close_to_a_grader_or_a_quantity_still_count(title: str) -> None:
    assert is_relevant(title, "025/165")


def test_ace_is_a_card_not_a_grader() -> None:
    assert is_relevant("Portgas D. Ace OP02-013 SR", "OP02-013", ["Ace"])


def test_dotted_one_piece_names_match_their_spaced_forms() -> None:
    from mekiki_engine.browser.markets import search_queries

    title = "Monkey D. Luffy OP05-119 SEC Japanese"
    assert is_relevant(title, "OP05-119", ["Monkey.D.Luffy"])
    assert is_relevant(title, "OP05-119", ["Luffy"])
    assert is_relevant("Monkey.D.Luffy OP05-119", "OP05-119", ["Luffy"])
    assert is_relevant("Luffy OP05-119 SEC", "OP05-119", ["Luffy"])
    queries = search_queries("Monkey.D.Luffy OP05-119", "OP05-119", ["Monkey.D.Luffy", "Luffy"])
    assert queries == ["Monkey D Luffy OP05-119", "Luffy OP05-119"]
    assert search_queries("Mr. Mime 122/165", "122/165", []) == ["Mr. Mime 122/165"]


def test_ebay_accepted_offers_only_count_when_nothing_else_is_left() -> None:
    sold = parse_listings(EBAY_RAW, "201/165")

    assert sold[1].best_offer is True
    assert sold[1].shipping_cents == 347
    assert sold[0].detail == "Vendu le 6 oct. 2026"
    assert median_cents(sold) == 35500
    assert median_cents(sold[1:]) == 41470


def test_sales_are_read_once_then_kept(client: TestClient, chrome: FakeSession) -> None:
    chrome.tab.pages["ebay"] = FRENCH_SALES
    body = {"query": "Dracaufeu ex 201/165", "card_number": "201/165"}

    first = client.post("/browser/ebay/sold", json=body).json()
    again = client.post("/browser/ebay/sold", json=body).json()

    assert first["relevant_count"] == 2
    assert first["median_cents"] == 7000
    assert (first["min_cents"], first["max_cents"]) == (6500, 7500)
    assert again == first
    assert chrome.pages_opened == 1
    assert chrome.tab.visited[0].startswith("https://www.ebay.fr/sch/i.html?_nkw=Dracaufeu")
    # Vinted's search pages are no longer read: they block an address that does.
    assert client.post("/browser/vinted/prices", json=body).status_code == 404


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
    assert set(queries) == {"ebay"}

    assert before["card_version"] == "regular"
    client.post(
        "/browser/ebay/sold",
        json={
            "query": queries["ebay"],
            "card_number": before["card_number"],
            "version": before["card_version"],
        },
    )
    after = client.get("/resale/verdict", params=params).json()

    outlets = {o["platform"]: o for o in after["outlets"]}
    assert set(outlets) == {"cardmarket", "ebay"}
    assert outlets["ebay"]["sale_cents"] == 35500
    assert "ventes réussies eBay" in outlets["ebay"]["basis"]


def test_other_cards_and_languages_sharing_the_number_are_left_out() -> None:
    names = ["Charizard", "Dracaufeu", "リザードンex"]

    assert is_relevant("Dracaufeu ex SAR 201/165 / Pokémon 151 (Japonais)", "201/165", names)
    assert not is_relevant("Carte Pokémon Alakazam alternative 201/165", "201/165", names)
    assert not is_relevant("Dracaufeu ex SAR – SV2a 201/165 – Coréen", "201/165", names)
    assert not is_relevant("Charizard ex 201/165 sv2a KOR", "201/165", names)


@pytest.mark.parametrize(
    ("title", "version", "expected"),
    [
        ("Monkey D. Luffy OP05-119 SEC Japanese", "regular", True),
        ("Monkey D. Luffy OP05-119 SEC Parallel", "regular", False),
        ("Monkey D. Luffy OP05-119 Alt Art", "regular", False),
        ("Monkey D. Luffy OP05-119 Manga", "regular", False),
        ("Monkey D. Luffy OP05-119 SP", "regular", False),
        ("Monkey D. Luffy OP05-119 SEC Parallel", "parallel", True),
        ("Monkey D. Luffy OP05-119 P-SEC", "parallel", True),
        ("Monkey D. Luffy OP05-119 SEC parallèle", "parallel", True),
        ("Monkey D. Luffy OP05-119 SEC", "parallel", False),
        ("Monkey D. Luffy OP05-119 Manga Parallel", "parallel", False),
        ("Monkey D. Luffy OP05-119 Manga Rare", "manga", True),
        ("Monkey D. Luffy OP05-119 SEC Parallel", "manga", False),
    ],
)
def test_one_piece_versions_sharing_a_code_are_told_apart(
    title: str, version: str, expected: bool
) -> None:
    assert is_relevant(title, "OP05-119", ["Luffy"], version) is expected


@pytest.mark.parametrize(
    ("title", "version", "expected"),
    [
        ("Pikachu 025/165 Pokémon 151", "regular", True),
        ("Pikachu 025/165 Master Ball Reverse", "regular", False),
        ("Pikachu 025/165 Poké Ball", "regular", False),
        ("Pikachu 025/165 Reverse Holo", "regular", False),
        ("Pikachu 025/165 Master Ball Reverse", "masterball", True),
        ("Pikachu 025/165 Masterball", "masterball", True),
        ("Pikachu 025/165 Pokeball Reverse", "masterball", False),
        ("Pikachu 025/165", "masterball", False),
        ("Pikachu 025/165 Pokeball Reverse", "pokeball", True),
        ("Pikachu 025/165 Reverse Holo", "reverse", True),
        ("Pikachu 025/165 Master Ball Reverse", "reverse", False),
    ],
)
def test_pokemon_mirrors_sharing_a_number_are_told_apart(
    title: str, version: str, expected: bool
) -> None:
    assert is_relevant(title, "025/165", ["Pikachu"], version) is expected


def test_english_one_piece_cards_share_the_code_but_do_not_count() -> None:
    assert not is_relevant("Monkey D. Luffy OP05-119 SEC English", "OP05-119", ["Luffy"])
    assert not is_relevant("Luffy OP05-119 SEC version anglaise", "OP05-119", ["Luffy"])
    assert is_relevant("Luffy OP05-119 SEC japonaise", "OP05-119", ["Luffy"])


def test_a_number_needs_its_own_digits() -> None:
    assert not is_relevant("Pikachu promo 2025", "025", ["Pikachu"])
    assert not is_relevant("Pikachu 1025/165", "025/165", ["Pikachu"])
    assert not is_relevant("Pikachu 025/1650", "025/165", ["Pikachu"])
    assert is_relevant("Pikachu n°025 promo", "025", ["Pikachu"])
    assert is_relevant("Pikachu 025 / 165", "025/165", ["Pikachu"])
    assert is_relevant("Luffy OP05 119", "OP05-119", ["Luffy"])


def test_sales_are_kept_for_one_number_and_printing(
    client: TestClient, chrome: FakeSession
) -> None:
    chrome.tab.pages["ebay"] = FRENCH_SALES
    body = {"query": "Dracaufeu ex", "card_number": "201/165", "version": "regular"}

    first = client.post("/browser/ebay/sold", json=body).json()
    other_number = client.post("/browser/ebay/sold", json=body | {"card_number": "006/165"})
    other_printing = client.post("/browser/ebay/sold", json=body | {"version": "masterball"})
    again = client.post("/browser/ebay/sold", json=body).json()

    assert first["relevant_count"] == 2
    assert other_number.json()["relevant_count"] == 1
    assert other_printing.json()["relevant_count"] == 0
    assert again == first
    assert chrome.pages_opened == 3
    cached = client.post("/browser/ebay/sold/cached", json=body | {"version": None}).json()
    assert cached is None


def test_prices_far_from_the_others_are_left_out_of_the_median() -> None:
    raw = [
        sale(str(i), f"Dracaufeu ex 201/165 n°{i}", price)
        for i, price in enumerate(["60,00 €", "65,00 €", "70,00 €", "1,00 €", "2 000,00 €"])
    ]
    listings = parse_listings(raw, "201/165", ["Dracaufeu"])

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
    activity = client.get("/browser/activity").json()
    assert (activity["activity"], activity["running"], activity["visible"]) == (None, True, True)
    assert activity["log"][-1]["text"] == "Vinted : page de connexion ouverte"

    assert client.post("/browser/vinted/check").json()["connected"] is True
    assert chrome.visible is False
    assert client.post("/browser/show").json()["visible"] is True
    assert client.post("/browser/hide").json()["visible"] is False


def test_the_log_lists_each_step_and_its_outcome(client: TestClient, chrome: FakeSession) -> None:
    assert client.get("/browser/activity").json()["log"] == []

    chrome.tab.pages["ebay"] = FRENCH_SALES
    body = {"query": "Dracaufeu ex 201/165", "card_number": "201/165"}
    client.post("/browser/ebay/sold", json=body)
    client.post("/browser/ebay/sold", json=body)

    log = [line["text"] for line in client.get("/browser/activity").json()["log"]]
    assert log[0] == "eBay : ventes réussies « Dracaufeu ex 201/165 »"
    assert "eBay : 4 ventes lues, 2 de cette carte" in log
    assert log[-1] == "eBay : ventes déjà lues il y a moins de six heures"


def test_a_bot_check_is_left_to_the_user(client: TestClient, chrome: FakeSession) -> None:
    chrome.tab.challenge = True

    read = client.post(
        "/browser/ebay/sold", json={"query": "Pikachu 173/165", "card_number": "173/165"}
    ).json()

    assert "vérification anti-robot" in read["error"]
    assert chrome.visible is True
    assert client.get("/browser/activity").json()["activity"] is None


SOLD = {"query": "Dracaufeu ex 201/165", "card_number": "201/165"}


def test_ebay_s_own_challenge_page_is_left_to_the_user(
    client: TestClient, chrome: FakeSession
) -> None:
    chrome.tab.redirect = "https://www.ebay.fr/splashui/challenge?ap=1&appName=orch"

    read = client.post("/browser/ebay/sold", json=SOLD).json()

    assert "vérification anti-robot" in read["error"]
    assert chrome.visible is True
    assert client.get("/browser/status").json()["connections"] == {}


def test_an_unknown_page_is_shown_to_the_user_and_not_kept(
    client: TestClient, chrome: FakeSession
) -> None:
    chrome.tab.redirect = "https://www.ebay.fr/n/error"

    read = client.post("/browser/ebay/sold", json=SOLD).json()

    assert "page inattendue" in read["error"]
    assert chrome.visible is True
    assert client.post("/browser/ebay/sold/cached", json=SOLD).json() is None


def test_results_that_never_show_are_an_error_not_a_card_without_sales(
    client: TestClient, chrome: FakeSession
) -> None:
    chrome.tab.pages["ebay"] = []

    failed = client.post("/browser/ebay/sold", json=SOLD).json()
    chrome.tab.pages["ebay"] = FRENCH_SALES
    read = client.post("/browser/ebay/sold", json=SOLD).json()

    assert "n'a pas affiché les résultats" in failed["error"]
    assert failed["listings"] == []
    assert read["error"] is None
    assert read["relevant_count"] == 2
    # The failed read was not kept: the second one loaded the page again.
    assert chrome.pages_opened == 2


def test_ebay_s_word_that_nothing_sold_is_kept(client: TestClient, chrome: FakeSession) -> None:
    chrome.tab.pages["ebay"] = []
    chrome.tab.no_results = True

    read = client.post("/browser/ebay/sold", json=SOLD).json()
    again = client.post("/browser/ebay/sold", json=SOLD).json()

    assert read["error"] is None
    assert (read["relevant_count"], read["median_cents"]) == (0, None)
    assert again == read
    assert chrome.pages_opened == 1
    assert client.get("/browser/status").json()["connections"] == {"ebay": True}


class FakeSocket:
    """A DevTools websocket: answers each command with ``results[method]``, after the events
    queued for it."""

    def __init__(self, results: dict[str, dict[str, Any]] | None = None) -> None:
        self.results = results or {}
        self.events: list[dict[str, Any]] = []
        self.sent: list[dict[str, Any]] = []
        self._answers: list[str] = []

    def send(self, data: str) -> None:
        message = json.loads(data)
        self.sent.append(message)
        if message["method"] == "Page.handleJavaScriptDialog":
            return
        self._answers += [json.dumps(event) for event in self.events]
        self.events = []
        result = self.results.get(message["method"], {})
        self._answers.append(json.dumps({"id": message["id"], "result": result}))

    def recv(self) -> str:
        return self._answers.pop(0)

    def close(self) -> None:
        pass


class FakeDevTools:
    """Chrome's /json endpoints, the user's listing form being the most recent tab."""

    def __init__(self) -> None:
        self.pages: list[dict[str, str]] = [self._target("form")]
        self.created = 0

    @staticmethod
    def _target(target_id: str) -> dict[str, str]:
        return {
            "id": target_id,
            "type": "page",
            "url": "about:blank",
            "webSocketDebuggerUrl": f"ws://127.0.0.1:9222/devtools/page/{target_id}",
        }

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/json/version":
            return httpx.Response(200, json={"webSocketDebuggerUrl": "ws://127.0.0.1/browser"})
        if request.url.path == "/json/list":
            return httpx.Response(200, json=self.pages)
        assert request.url.path == "/json/new"
        self.created += 1
        target = self._target(f"mekiki-{self.created}")
        self.pages.insert(0, target)
        return httpx.Response(200, json=target)


def devtools_session(profile: Path, devtools: FakeDevTools) -> chrome_module.ChromeSession:
    session = chrome_module.ChromeSession(profile)
    session._http = httpx.Client(transport=httpx.MockTransport(devtools))
    session.port = 9222
    return session


def test_reading_never_takes_over_another_tab(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    devtools = FakeDevTools()
    sockets: dict[str, FakeSocket] = {}
    monkeypatch.setattr(
        chrome_module.websocket,
        "create_connection",
        lambda url, **_options: sockets.setdefault(url, FakeSocket()),
    )
    session = devtools_session(tmp_path, devtools)

    for _ in range(2):
        with session.page():
            pass
    devtools.pages = [page for page in devtools.pages if page["id"] != "mekiki-1"]
    with session.page():
        pass
    # A later run of the engine finds Mekiki's tab again.
    with devtools_session(tmp_path, devtools).page():
        pass

    assert devtools.created == 2
    assert [url.rsplit("/", 1)[1] for url in sockets] == ["mekiki-1", "mekiki-2"]
    assert session.current_target == "mekiki-2"


def test_only_mekiki_s_own_tab_leaves_a_page_without_asking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handled(tab_kind: str, own: bool) -> bool:
        socket = FakeSocket()
        socket.events = [
            {"method": "Page.javascriptDialogOpening", "params": {"type": tab_kind, "message": ""}}
        ]
        monkeypatch.setattr(chrome_module.websocket, "create_connection", lambda *_a, **_k: socket)
        chrome_module.Tab("ws://127.0.0.1/page", accept_leave_prompts=own).call("Page.reload")
        return any(sent["method"] == "Page.handleJavaScriptDialog" for sent in socket.sent)

    assert handled("beforeunload", own=True)
    # A listing form's prompt is the user's; an alert is not a "leave this page?" prompt.
    assert not handled("beforeunload", own=False)
    assert not handled("alert", own=True)


def test_a_page_chrome_cannot_load_is_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    socket = FakeSocket({"Page.navigate": {"frameId": "1", "errorText": "net::ERR_TIMED_OUT"}})
    monkeypatch.setattr(chrome_module.websocket, "create_connection", lambda *_a, **_k: socket)
    tab = chrome_module.Tab("ws://127.0.0.1:9222/devtools/page/1")

    with pytest.raises(ChromeError, match="ERR_TIMED_OUT"):
        tab.navigate("https://www.ebay.fr/sch/i.html?_nkw=Pikachu")


@pytest.mark.parametrize(
    ("caption", "expected"),
    [
        ("Vendu le 6 oct. 2026", "2026-10-06"),
        ("Vendu le 28 sept. 2026", "2026-09-28"),
        ("Vendu le 1 août 2026", "2026-08-01"),
        ("Vendu le 3 mai 2026", "2026-05-03"),
        ("Vendu le 12 déc. 2025", "2025-12-12"),
        ("Vendu le 31 févr. 2026", None),
        ("Vendu", None),
    ],
)
def test_ebay_sale_dates_are_read(caption: str, expected: str | None) -> None:
    assert sold_date(caption) == expected


def test_ebay_sales_are_counted_over_30_and_90_days() -> None:
    raw = [
        {**EBAY_RAW[0], "id": "1", "sold": "Vendu le 6 oct. 2026"},
        {**EBAY_RAW[0], "id": "2", "sold": "Vendu le 20 sept. 2026"},
        {**EBAY_RAW[0], "id": "3", "sold": "Vendu le 2 août 2026"},
        {**EBAY_RAW[0], "id": "4", "sold": "Vendu le 2 juin 2026"},
        # Another card sold the same day does not count.
        {**EBAY_RAW[0], "id": "5", "title": "Charizard ex 006/165", "sold": "Vendu le 6 oct. 2026"},
    ]
    sold = parse_listings(raw, "201/165")
    today = date(2026, 10, 8)

    assert sold[0].sold_on == "2026-10-06"
    assert sales_within(sold, 30, today) == 2
    assert sales_within(sold, 90, today) == 3


def test_ebay_sold_searches_read_the_latest_sales_first() -> None:
    assert "_sop=13" in markets.search_url("Charizard 201/165")


def test_ebay_sales_frequency_joins_the_verdict(client: TestClient, chrome: FakeSession) -> None:
    client.post("/cardmarket/refresh", json={})
    params = {"product_id": 719654, "label": "SV2a 201/165 · SAR"}
    before = client.get("/resale/verdict", params=params).json()

    prices = client.post(
        "/browser/ebay/sold",
        json={
            "query": before["market_queries"]["ebay"],
            "card_number": "201/165",
            "version": before["card_version"],
        },
    ).json()
    after = client.get("/resale/verdict", params=params).json()

    assert prices["sales_90_days"] is not None
    assert prices["listings"][0]["sold_on"] == "2026-10-06"
    assert any("sur 90 jours" in signal["text"] for signal in after["signals"])


class NewResultsTab(FakeTab):
    """Every page brings listings not seen before."""

    def __init__(self) -> None:
        super().__init__({}, connected=True)

    def _current(self) -> list[dict[str, Any]]:
        return [{"id": self.url()}]


def test_a_card_reads_one_page_of_three_searches_at_most() -> None:
    tab = NewResultsTab()
    pauses: list[None] = []

    markets.read_listings(
        tab, ["a 1/1", "b 1/1", "c 1/1", "d 1/1"], pause=lambda: pauses.append(None)
    )

    assert len(tab.visited) == 3
    assert len(pauses) == 2


def test_the_ebay_sign_in_is_remembered_without_opening_chrome(
    client: TestClient, chrome: FakeSession
) -> None:
    body = {"query": "Dracaufeu ex 201/165", "card_number": "201/165"}
    assert client.get("/browser/status").json()["connections"] == {}

    chrome.tab.signed_out = True
    signed_out = client.post("/browser/ebay/sold", json=body).json()
    status = client.get("/browser/status").json()

    assert "connectez-vous" in signed_out["error"]
    assert status["connections"] == {"ebay": False}
    chrome.tab.signed_out = False
    client.post("/browser/ebay/sold", json=body)
    assert client.get("/browser/status").json()["connections"] == {"ebay": True}
    client.post("/browser/vinted/check")
    assert client.get("/browser/status").json()["connections"] == {"ebay": True, "vinted": True}


def test_sales_already_read_are_given_without_loading_anything(
    client: TestClient, chrome: FakeSession
) -> None:
    chrome.tab.pages["ebay"] = FRENCH_SALES
    body = {"query": "Dracaufeu ex 201/165", "card_number": "201/165"}

    before = client.post("/browser/ebay/sold/cached", json=body).json()
    read = client.post("/browser/ebay/sold", json=body).json()
    after = client.post("/browser/ebay/sold/cached", json=body).json()

    assert before is None
    assert after == read
    assert chrome.pages_opened == 1
