from dataclasses import replace

import pytest
from conftest import FakeMarketplace
from fastapi.testclient import TestClient
from test_discovery import discover, index_pokemon_cards, mercari

from mekiki_engine.domain import SourcePlatform
from mekiki_engine.scanner import sellers
from mekiki_engine.scanner.catalog import era_of

# Charizard ex SV2a 006 (RR, 90 €) and 201 (SAR, 357 €); Pikachu V S6a 085 (SR, 200 €),
# linked through TCGplayer.
CARDS = [
    mercari("m1000001", "リザードンex RR SV2a 006/165 ポケモンカード151", 4000),
    mercari("m1000002", "リザードンex SAR 201/165 ポケモンカード151", 30000),
    mercari("m1000003", "ピカチュウV SR 085/069 イーブイヒーローズ", 15000),
]


def ids(run: dict[str, object], key: str = "picks") -> set[str]:
    return {pick["external_id"] for pick in run[key]}  # type: ignore[attr-defined,index]


def everything(run: dict[str, object]) -> set[str]:
    return ids(run) | ids(run, "alternatives")


@pytest.fixture
def cards(client: TestClient, marketplace: FakeMarketplace) -> FakeMarketplace:
    index_pokemon_cards(client)
    marketplace.listings[SourcePlatform.MERCARI] = list(CARDS)
    return marketplace


BUDGET = {"budget_cents": 100000, "card_count": 3, "min_roi_percent": 10}


def test_without_filters_every_recognised_card_counts(
    client: TestClient, cards: FakeMarketplace
) -> None:
    assert everything(discover(client, **BUDGET)) == {"m1000001", "m1000002", "m1000003"}


def test_rarities_keep_their_cards_and_replace_the_broad_searches(
    client: TestClient, cards: FakeMarketplace
) -> None:
    run = discover(client, **BUDGET, rarities=["sar", "sr"])

    assert everything(run) == {"m1000002", "m1000003"}
    searched = {query for _site, query in cards.queries}
    assert {"SAR", "SR"} <= searched
    assert "" not in searched
    assert "Filtres : raretés SAR, SR." in [line["text"] for line in run["log"]]


def test_sets_are_searched_by_code_and_japanese_name(
    client: TestClient, cards: FakeMarketplace
) -> None:
    run = discover(client, **BUDGET, sets=["s6a"])

    assert everything(run) == {"m1000003"}
    assert {"s6a", "イーブイヒーローズ"} <= {query for _site, query in cards.queries}


def test_eras_keep_the_cards_of_their_sets(client: TestClient, cards: FakeMarketplace) -> None:
    assert everything(discover(client, **BUDGET, eras=["sv"])) == {"m1000001", "m1000002"}
    assert everything(discover(client, **BUDGET, eras=["swsh"])) == {"m1000003"}


def test_a_name_is_searched_in_japanese(client: TestClient, cards: FakeMarketplace) -> None:
    run = discover(client, **BUDGET, name="Dracaufeu")

    assert everything(run) == {"m1000001", "m1000002"}
    assert (SourcePlatform.MERCARI, "リザードン") in cards.queries


def test_market_price_and_age_bounds(client: TestClient, cards: FakeMarketplace) -> None:
    pricey = discover(client, **BUDGET, min_market_cents=15000)
    cheap = discover(client, **BUDGET, max_market_cents=10000)
    cards.listings[SourcePlatform.MERCARI] = [
        replace(CARDS[0], listed_at="2020-01-01T00:00:00Z"),
        replace(CARDS[1], listed_at="2099-01-01T00:00:00Z"),
        CARDS[2],
    ]
    recent = discover(client, **BUDGET, max_age_days=7)

    assert everything(pricey) == {"m1000002", "m1000003"}
    assert everything(cheap) == {"m1000001"}
    # A listing without a date is kept: nothing says it is old.
    assert everything(recent) == {"m1000002", "m1000003"}


def test_listings_of_blocked_sellers_are_shown_apart(
    client: TestClient, cards: FakeMarketplace
) -> None:
    cards.listings[SourcePlatform.MERCARI] = [
        replace(CARDS[1], seller_id="555"),
        *(card for card in CARDS if card is not CARDS[1]),
    ]
    with client.app.state.session_factory() as session:  # type: ignore[attr-defined]
        sellers.block(session, "mercari", "555", "refuse les intermédiaires")

    run = discover(client, **BUDGET)

    assert "m1000002" not in everything(run)
    [blocked] = run["blocked"]
    assert blocked["external_id"] == "m1000002"
    assert (blocked["seller_id"], blocked["blocked_reason"]) == (
        "555",
        "refuse les intermédiaires",
    )


def test_the_catalog_lists_eras_sets_and_rarities(
    client: TestClient, cards: FakeMarketplace
) -> None:
    pokemon = client.get("/discovery/catalog", params={"game": "pokemon"}).json()

    codes = [s["code"] for s in pokemon["sets"]]
    assert codes.index("sv2a") < codes.index("s6a")
    [sv2a] = [s for s in pokemon["sets"] if s["code"] == "sv2a"]
    assert (sv2a["printed"], sv2a["japanese_name"], sv2a["era"]) == (
        "SV2a",
        "ポケモンカード151",
        "sv",
    )
    assert [era["id"] for era in pokemon["eras"]][:2] == ["mega", "sv"]
    assert "sar" in [r["id"] for r in pokemon["rarities"]]
    one_piece = client.get("/discovery/catalog", params={"game": "one_piece"}).json()
    assert one_piece["eras"] == []
    assert "manga" in [r["id"] for r in one_piece["rarities"]]


@pytest.mark.parametrize(
    ("code", "era"),
    [
        ("m2a", "mega"),
        ("mc", "mega"),
        ("sv-p", "sv"),
        ("sv2a", "sv"),
        ("s12a", "swsh"),
        ("s-p", "swsh"),
        ("sm12a", "sm"),
        ("smp2", "sm"),
        ("cp6", "xy"),
        ("bw9", "bw"),
        ("pt1", "older"),
    ],
)
def test_eras_follow_the_set_codes(code: str, era: str) -> None:
    assert era_of(code) == era


def test_an_auction_never_enters_the_parcel(client: TestClient, cards: FakeMarketplace) -> None:
    cards.listings[SourcePlatform.MERCARI] = [
        replace(CARDS[1], ends_at="2099-01-01T00:00:00Z", bids=3),
        CARDS[0],
    ]

    run = discover(client, **BUDGET)

    assert "m1000002" not in ids(run)
    [auction] = [a for a in run["alternatives"] if a["external_id"] == "m1000002"]
    assert auction["warning"].startswith("Enchère en cours")


def test_many_sets_never_make_a_quick_search_long(
    client: TestClient, cards: FakeMarketplace
) -> None:
    from mekiki_engine.scanner.discovery import MAX_PAGES, search_plan
    from mekiki_engine.schemas import DiscoveryRequest

    codes = [f"sv{n}" for n in range(1, 12)] + [f"s{n}" for n in range(1, 13)]
    request = DiscoveryRequest(budget_cents=100000, sets=codes * 2, depth="quick")
    with client.app.state.session_factory() as session:  # type: ignore[attr-defined]
        plan = search_plan(session, request)

    assert sum(pages for _query, pages in plan) <= MAX_PAGES["quick"]
