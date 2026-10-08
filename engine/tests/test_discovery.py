from dataclasses import replace
from typing import Any

import httpx
from conftest import FakeMarketplace
from fastapi.testclient import TestClient

from mekiki_engine.domain import Game, ListingCondition, SourcePlatform
from mekiki_engine.models import CardmarketProduct
from mekiki_engine.scanner.identify import identify
from mekiki_engine.scanner.resolver import CatalogResolver
from mekiki_engine.scanner.sources.base import FoundListing


def mercari(item_id: str, title: str, price: int) -> FoundListing:
    return FoundListing(
        source=SourcePlatform.MERCARI,
        external_id=item_id,
        title=title,
        price_jpy=price,
        url=f"https://jp.mercari.com/item/{item_id}",
        shipping_included=True,
    )


def rakuma(item_id: str, title: str, price: int) -> FoundListing:
    return FoundListing(
        source=SourcePlatform.RAKUMA,
        external_id=item_id,
        title=title,
        price_jpy=price,
        url=f"https://item.fril.jp/{item_id}",
        shipping_included=True,
    )


def index_pokemon_cards(client: TestClient) -> None:
    """Downloads the fake Cardmarket files and TCGdex archive (see conftest)."""
    client.post("/cardmarket/refresh", json={})


def discover(client: TestClient, **request: Any) -> dict[str, Any]:
    response = client.post(
        "/discovery",
        json={"game": "pokemon", "sources": ["mercari"], **request},
    )
    assert response.status_code == 202
    return client.get("/discovery").json()


# The fake price guide prices the double rare Charizard ex (SV2a 006) at 90 €.
LISTINGS = [
    mercari("m1", "リザードンex RR SV2a 006/165 ポケモンカード151", 4000),
    mercari("m2", "リザードンex 006/165 美品", 5000),
    mercari("m3", "リザードンex RR 006/165 PSA10", 30000),
    mercari("m4", "フシギダネ 001/165", 300),
    mercari("m5", "まとめ売り リザードン 006/165", 2000),
    mercari("m6", "謎のカード 999/999", 1000),
]


def test_discovery_composes_a_parcel_from_recognised_cards(
    client: TestClient, marketplace: FakeMarketplace
) -> None:
    index_pokemon_cards(client)
    marketplace.listings[SourcePlatform.MERCARI] = LISTINGS

    run = discover(client, budget_cents=15000, card_count=2, min_roi_percent=10)

    assert run["status"] == "done"
    assert run["searches_done"] == run["searches_total"] > 1
    assert run["listings_seen"] == 6
    # Both Charizards and the Bulbasaur are recognised; the graded copy and the lot are not.
    assert run["listings_identified"] == 3
    assert [p["external_id"] for p in run["picks"]] == ["m1", "m2"]
    first = run["picks"][0]
    assert first["card_label"] == "SV2a 006/165 · RR"
    assert first["confidence"] == "high"
    assert first["product"]["id_product"] == 719448
    assert first["sale"]["roi"] > 0.3

    totals = run["totals"]
    assert totals["card_count"] == 2
    assert totals["purchase_jpy"] == 9000
    assert totals["landed_cents"] == sum(p["landed_cost"]["total_cents"] for p in run["picks"])
    assert totals["landed_cents"] <= 15000
    assert totals["margin_cents"] == totals["net_cents"] - totals["landed_cents"]
    # The Bulbasaur would sell at a loss once fees are paid: it is not even an alternative.
    assert run["alternatives"] == []


def test_discovery_respects_the_budget(client: TestClient, marketplace: FakeMarketplace) -> None:
    index_pokemon_cards(client)
    marketplace.listings[SourcePlatform.MERCARI] = LISTINGS

    run = discover(client, budget_cents=8000, card_count=2, min_roi_percent=10)

    # Only one card fits; alone, it carries all the fixed costs of the parcel and still fits.
    assert [p["external_id"] for p in run["picks"]] == ["m1"]
    assert run["totals"]["landed_cents"] <= 8000
    assert [a["external_id"] for a in run["alternatives"]] == ["m2"]


def test_discovery_explains_a_budget_below_the_parcel_costs(
    client: TestClient, marketplace: FakeMarketplace
) -> None:
    index_pokemon_cards(client)
    marketplace.listings[SourcePlatform.MERCARI] = LISTINGS

    run = discover(client, budget_cents=5000, card_count=2, min_roi_percent=10)

    assert run["picks"] == []
    assert run["errors"][0].startswith("Budget trop serré")


def test_discovery_uses_the_requested_roi(client: TestClient, marketplace: FakeMarketplace) -> None:
    index_pokemon_cards(client)
    marketplace.listings[SourcePlatform.MERCARI] = LISTINGS

    run = discover(client, budget_cents=15000, card_count=2, min_roi_percent=1000)

    assert run["picks"] == []
    assert run["totals"] is None
    # Nothing reaches the target: the budget is not to blame.
    assert run["errors"] == []
    assert run["log"][-1]["text"] == "Terminé : aucun colis ne remplit les conditions."


def test_discovery_reports_failing_sources(
    client: TestClient, marketplace: FakeMarketplace
) -> None:
    marketplace.failures.add(SourcePlatform.MERCARI)

    run = discover(client, budget_cents=15000, card_count=2)

    assert run["status"] == "done"
    assert run["errors"] == ["Mercari : bloqué (test)"]


def test_one_piece_versions_follow_price_order(client: TestClient) -> None:
    with client.app.state.session_factory() as session:  # type: ignore[attr-defined]
        for id_product, expansion, price in (
            (1, 10, 430),
            (2, 10, 17532),
            (3, 10, 264004),
            (4, 20, 99999),  # an English printing, ignored
            (5, 30, 307),  # a later Japanese reprint, outside the home set
        ):
            session.add(
                CardmarketProduct(
                    id_product=id_product,
                    game="one_piece",
                    name="Monkey.D.Luffy (OP05-119)",
                    id_expansion=expansion,
                    expansion_name={
                        10: "Awakening of the New Era (Non-English)",
                        20: "Awakening of the New Era",
                        30: "The Best (Non-English)",
                    }[expansion],
                    avg30_cents=price,
                )
            )
        session.add(
            CardmarketProduct(
                id_product=6,
                game="one_piece",
                name="Nami (OP05-001)",
                id_expansion=10,
                expansion_name="Awakening of the New Era (Non-English)",
                avg30_cents=150,
            )
        )
        session.commit()

        resolver = CatalogResolver(session)

        def resolve(title: str) -> tuple[int, str]:
            result = resolver.resolve(identify(title, Game.ONE_PIECE))
            assert result is not None
            return result.product.id_product, result.label

        assert resolve("ルフィ OP05-119") == (1, "OP05-119 · normale")
        assert resolve("ルフィ OP05-119 パラレル") == (2, "OP05-119 · parallèle")
        assert resolve("ルフィ OP05-119 コミパラ") == (3, "OP05-119 · manga")
        assert resolver.resolve(identify("ナミ OP05-001", Game.ONE_PIECE)).confidence == "high"  # type: ignore[union-attr]
        assert resolver.resolve(identify("ゾロ OP01-001", Game.ONE_PIECE)) is None


def test_listings_far_below_the_market_are_flagged_not_picked(
    client: TestClient, marketplace: FakeMarketplace
) -> None:
    index_pokemon_cards(client)
    marketplace.listings[SourcePlatform.MERCARI] = [
        mercari("fake", "リザードンex RR SV2a 006/165", 500),
        *LISTINGS,
    ]

    run = discover(client, budget_cents=15000, card_count=2, min_roi_percent=10)

    assert "fake" not in [p["external_id"] for p in run["picks"]]
    [flagged] = [a for a in run["alternatives"] if a["external_id"] == "fake"]
    assert flagged["warning"].startswith("Prix à moins de 20 % de la cote")


def test_deeper_searches_add_pages_and_valuable_sets(
    client: TestClient, marketplace: FakeMarketplace
) -> None:
    index_pokemon_cards(client)
    marketplace.listings[SourcePlatform.MERCARI] = LISTINGS

    quick = discover(client, budget_cents=15000, card_count=2)
    quick_queries = list(marketplace.queries)
    marketplace.queries.clear()
    deep = discover(client, budget_cents=15000, card_count=2, depth="deep")

    assert (SourcePlatform.MERCARI, "sv2a") not in quick_queries
    # The fake index has two SV2a cards priced over 10 €: the set gets its own search.
    assert (SourcePlatform.MERCARI, "sv2a") in marketplace.queries
    assert deep["searches_total"] > quick["searches_total"]
    # Fake sources return nothing after the first page, which ends each search early.
    assert deep["searches_done"] == deep["searches_total"]


def test_a_stopped_discovery_keeps_what_it_found(client: TestClient) -> None:
    from mekiki_engine.scanner.discovery import discover as run_discovery
    from mekiki_engine.schemas import DiscoveryRequest

    app = client.app  # type: ignore[attr-defined]
    with app.state.session_factory() as session:
        run = run_discovery(
            session,
            app.state.http,
            1,
            DiscoveryRequest(budget_cents=15000, card_count=2, sources=[SourcePlatform.MERCARI]),
            source_factory=app.state.source_factory,
            should_stop=lambda: True,
        )

    assert run.status == "done"
    assert run.stopped is True
    assert run.listings_seen == 0


def test_promo_and_two_letter_sets_are_not_searched() -> None:
    from mekiki_engine.scanner.discovery import _searchable_set_code

    assert _searchable_set_code("sv2a")
    assert _searchable_set_code("sm9")
    assert not _searchable_set_code("sv-p")
    assert not _searchable_set_code("s-p")
    assert not _searchable_set_code("mc")


def test_one_failed_search_does_not_end_a_site(
    client: TestClient, marketplace: FakeMarketplace
) -> None:
    index_pokemon_cards(client)
    marketplace.listings[SourcePlatform.MERCARI] = LISTINGS
    marketplace.failing_queries = {"SAR", "SR"}

    run = discover(client, budget_cents=15000, card_count=2)

    searched = [query for _platform, query in marketplace.queries]
    assert searched[-1] == "HR"
    assert run["errors"] == ["Mercari : page en erreur (test)"]
    assert run["searches_done"] == run["searches_total"]
    assert run["picks"]


def test_rakuma_pages_past_the_end_are_empty() -> None:
    from mekiki_engine.scanner.sources.base import PoliteClient
    from mekiki_engine.scanner.sources.rakuma import RakumaSource

    transport = httpx.MockTransport(lambda _request: httpx.Response(404, text="not found"))
    client = PoliteClient(intervals_s={}, default_interval_s=0, transport=transport)

    assert RakumaSource(client, Game.POKEMON).search("sv2a", page=29) == []


def test_discovery_keeps_listings_in_the_condition_asked(
    client: TestClient, marketplace: FakeMarketplace
) -> None:
    index_pokemon_cards(client)
    marketplace.listings[SourcePlatform.MERCARI] = [
        replace(LISTINGS[0], condition=ListingCondition.FAIR),
        replace(LISTINGS[1], condition=ListingCondition.LIKE_NEW),
        # No condition given: it cannot be vouched for.
        mercari("m7", "リザードンex RR 006/165", 4500),
    ]

    run = discover(
        client, budget_cents=15000, card_count=2, min_roi_percent=10, min_condition="good"
    )

    assert [p["external_id"] for p in run["picks"]] == ["m2"]
    assert run["picks"][0]["condition"] == "like_new"


def test_sold_listings_give_their_place_in_the_parcel(
    client: TestClient, marketplace: FakeMarketplace
) -> None:
    index_pokemon_cards(client)
    marketplace.listings[SourcePlatform.MERCARI] = [
        mercari("m100000001", "リザードンex RR SV2a 006/165", 4000),
        mercari("m100000002", "リザードンex RR 006/165 美品", 4500),
        mercari("m100000003", "リザードンex RR 006/165", 5000),
    ]
    marketplace.sold.add("m100000001")

    run = discover(client, budget_cents=15000, card_count=2, min_roi_percent=10)

    assert [p["external_id"] for p in run["picks"]] == ["m100000002", "m100000003"]
    assert marketplace.checked == ["m100000001", "m100000002", "m100000003"]
    assert (run["listings_checked"], run["listings_gone"]) == (3, 1)
    assert run["verifying"] is False
    # The sold listing is not offered as an alternative either.
    assert run["alternatives"] == []


def test_a_short_parcel_is_completed_and_explained(
    client: TestClient, marketplace: FakeMarketplace
) -> None:
    index_pokemon_cards(client)
    marketplace.listings[SourcePlatform.MERCARI] = LISTINGS

    run = discover(client, budget_cents=50000, card_count=3, min_roi_percent=45)

    # Only m1 reaches 45 % as a card of a 3-card parcel; alone, it would carry every fixed
    # cost of the parcel. m2, under the target on its own, shares them and lifts the return.
    assert [p["external_id"] for p in run["picks"]] == ["m1", "m2"]
    assert run["totals"]["roi"] < 0.45
    [message] = run["errors"]
    assert message.startswith(
        "Le colis n'atteint pas les 45 % demandés : une seule annonce les dépasse"
    )
    assert "1 carte un peu moins rentable le complète" in message
    # A filler is not offered as another profitable listing.
    assert run["alternatives"] == []


def test_discovery_logs_each_step(client: TestClient, marketplace: FakeMarketplace) -> None:
    index_pokemon_cards(client)
    marketplace.listings[SourcePlatform.MERCARI] = LISTINGS

    run = discover(client, budget_cents=15000, card_count=2, min_roi_percent=10)

    log = [line["text"] for line in run["log"]]
    assert log[0] == (
        "Recherche lancée : Pokémon, budget 150,00 €, 2 cartes, profondeur rapide, sur Mercari."
    )
    assert "Mercari : « toutes les cartes », page 1 : 6 annonces, 6 nouvelles." in log
    assert "Mercari : « SAR », page 1 : 6 annonces, 0 nouvelle." in log
    assert (
        "Écartées : 2 annonces en lot, gradée ou avec un mot exclu, "
        "1 annonce sans carte reconnue dans le titre." in log
    )
    assert any(line.startswith("Colis proposé : 2 cartes, coût ") for line in log)
    assert log[-1].startswith("Terminé")
    assert all(line["at"].endswith("Z") for line in run["log"])


def test_rakuma_listings_are_checked_on_their_page_for_the_minimum_condition(
    client: TestClient, marketplace: FakeMarketplace
) -> None:
    index_pokemon_cards(client)
    worn, mint = "a" * 32, "b" * 32
    # Rakuma's search results leave the condition out: only the listing's page gives it.
    marketplace.listings[SourcePlatform.RAKUMA] = [
        rakuma(worn, "リザードンex RR SV2a 006/165", 4000),
        rakuma(mint, "リザードンex RR 006/165 美品", 5000),
    ]
    marketplace.rakuma_conditions = {worn: "やや傷や汚れあり", mint: "未使用に近い"}

    run = discover(
        client,
        budget_cents=15000,
        card_count=2,
        min_roi_percent=10,
        sources=["rakuma"],
        min_condition="like_new",
    )

    assert [p["external_id"] for p in run["picks"]] == [mint]
    assert run["picks"][0]["condition"] == "like_new"
    assert marketplace.checked == [worn, mint]
    assert any("avec de légères traces, sous l'état demandé" in line["text"] for line in run["log"])


def test_no_budget_complaint_when_every_listing_failed_its_check(
    client: TestClient, marketplace: FakeMarketplace
) -> None:
    index_pokemon_cards(client)
    worn = "c" * 32
    marketplace.listings[SourcePlatform.RAKUMA] = [rakuma(worn, "リザードンex RR 006/165", 4000)]
    marketplace.rakuma_conditions = {worn: "全体的に状態が悪い"}

    run = discover(
        client,
        budget_cents=15000,
        card_count=2,
        min_roi_percent=10,
        sources=["rakuma"],
        min_condition="good",
    )

    assert run["picks"] == []
    assert run["errors"] == []
    assert run["alternatives"] == []
