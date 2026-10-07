from typing import Any

from conftest import FakeMarketplace
from fastapi.testclient import TestClient

from mekiki_engine.domain import Game, SourcePlatform
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
