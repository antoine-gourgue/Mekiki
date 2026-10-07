from typing import Any

from conftest import FakeMarketplace
from fastapi.testclient import TestClient

from mekiki_engine.domain import SourcePlatform
from mekiki_engine.scanner.sources.base import FoundListing


def mercari(item_id: str, title: str, price: int, **extra: Any) -> FoundListing:
    return FoundListing(
        source=SourcePlatform.MERCARI,
        external_id=item_id,
        title=title,
        price_jpy=price,
        url=f"https://jp.mercari.com/item/{item_id}",
        shipping_included=True,
        **extra,
    )


def track_charizard(client: TestClient, **overrides: Any) -> dict[str, Any]:
    assert client.post("/cardmarket/refresh", json={}).status_code == 200
    body = {
        "game": "pokemon",
        "name": "Charizard ex SAR",
        "card_number": "201/165",
        "cardmarket_product_id": 719448,
        **overrides,
    }
    response = client.post("/tracked-cards", json=body)
    assert response.status_code == 201
    return response.json()


def scan(client: TestClient) -> dict[str, Any]:
    response = client.post("/scanner/run", json={})
    assert response.status_code == 202
    return response.json()


def test_cardmarket_refresh_imports_singles_and_prices(client: TestClient) -> None:
    statuses = client.post("/cardmarket/refresh", json={}).json()

    pokemon = next(s for s in statuses if s["game"] == "pokemon")
    assert pokemon["products"] == 4
    assert pokemon["priced_products"] == 4
    assert pokemon["prices_date"] == "2026-10-07T02:49:47+0200"
    one_piece = next(s for s in statuses if s["game"] == "one_piece")
    assert one_piece["products"] == 0
    assert "403" in one_piece["last_error"]

    products = client.get("/cardmarket/products", params={"q": "charizard"}).json()
    # Dearest first: the SAR before the double rare.
    assert [p["id_product"] for p in products] == [719654, 719448]
    charizard = products[1]
    assert charizard["avg30_cents"] == 9000
    assert charizard["reference_cents"] == 9000
    assert charizard["reference_field"] == "avg30"
    assert charizard["url"].endswith("/Pokemon/Products?idProduct=719448")
    assert client.get("/cardmarket/products/719448").json() == charizard


def test_price_reference_falls_back_when_avg30_is_missing(client: TestClient) -> None:
    client.post("/cardmarket/refresh", json={})

    [pikachu] = client.get("/cardmarket/products", params={"q": "700737"}).json()

    assert pikachu["reference_cents"] == 916
    assert pikachu["reference_field"] == "avg"


def test_tracked_card_gets_a_query_a_price_and_a_buying_limit(client: TestClient) -> None:
    card = track_charizard(client)

    assert card["search_query"] == "201/165"
    assert card["expected_sale_cents"] == 9000
    assert card["market"]["id_product"] == 719448
    # Highest asking price still giving 30 % ROI on a 90 € Cardmarket resale.
    assert 6000 < card["max_buy_price_jpy"] < 8000
    assert card["listing_count"] == 0


def test_target_price_overrides_cardmarket(client: TestClient) -> None:
    card = track_charizard(client, target_price_cents=5000)

    assert card["expected_sale_cents"] == 5000


def test_scan_keeps_matching_listings_and_finds_the_good_deal(
    client: TestClient, marketplace: FakeMarketplace
) -> None:
    card = track_charizard(client)
    marketplace.listings[SourcePlatform.MERCARI] = [
        mercari("m1", "リザードンex SAR 201/165 ポケモンカード151", 4000),
        mercari("m2", "リザードンex SAR 201/165 美品", 12000),
        mercari("m3", "リザードンex SAR 201/165 PSA10", 30000),
        mercari("m4", "フシギバナex SAR 200/165", 3000),
        mercari("m5", "SAR まとめ売り 201/165", 2000),
    ]

    status = scan(client)

    assert status["running"] is False
    assert status["cards_scanned"] == 1
    assert status["new_listings"] == 2
    assert status["new_deals"] == 1
    assert (SourcePlatform.MERCARI, "201/165") in marketplace.queries

    good = client.get("/deals", params={"min_roi_percent": 30}).json()
    assert [d["external_id"] for d in good] == ["m1"]
    assert good[0]["triage"] == "new"
    assert good[0]["neokyo_url"]
    assert good[0]["sale"]["roi"] > 0.3

    every = client.get("/deals").json()
    assert [d["external_id"] for d in every] == ["m1", "m2"]
    assert every[1]["sale"]["margin_cents"] < 0

    refreshed = client.get("/tracked-cards").json()[0]
    assert refreshed["id"] == card["id"]
    assert refreshed["listing_count"] == 2
    assert refreshed["best_roi"] == good[0]["sale"]["roi"]


def test_sold_listings_go_offline_on_the_next_scan(
    client: TestClient, marketplace: FakeMarketplace
) -> None:
    track_charizard(client)
    marketplace.listings[SourcePlatform.MERCARI] = [
        mercari("m1", "リザードンex 201/165", 4000),
        mercari("m2", "リザードンex 201/165", 5000),
    ]
    scan(client)
    marketplace.listings[SourcePlatform.MERCARI] = [mercari("m2", "リザードンex 201/165", 4500)]

    status = scan(client)

    assert status["new_listings"] == 0
    online = client.get("/deals").json()
    assert [(d["external_id"], d["price_jpy"]) for d in online] == [("m2", 4500)]
    everything = client.get("/deals", params={"include_offline": True}).json()
    assert {d["external_id"]: d["online"] for d in everything} == {"m1": False, "m2": True}


def test_a_failing_source_is_reported_and_keeps_its_listings_online(
    client: TestClient, marketplace: FakeMarketplace
) -> None:
    track_charizard(client)
    marketplace.listings[SourcePlatform.MERCARI] = [mercari("m1", "リザードンex 201/165", 4000)]
    scan(client)
    marketplace.failures.add(SourcePlatform.MERCARI)

    status = scan(client)

    assert "Mercari (Charizard ex SAR) : bloqué (test)" in status["last_error"]
    assert [d["online"] for d in client.get("/deals").json()] == [True]


def test_triage(client: TestClient, marketplace: FakeMarketplace) -> None:
    track_charizard(client)
    marketplace.listings[SourcePlatform.MERCARI] = [
        mercari("m1", "リザードンex 201/165", 4000),
        mercari("m2", "リザードンex 201/165", 4100),
    ]
    scan(client)
    first, second = client.get("/deals").json()

    dismissed = client.patch(f"/deals/{first['id']}", json={"triage": "dismissed"}).json()
    assert dismissed["triage"] == "dismissed"
    assert [d["id"] for d in client.get("/deals").json()] == [second["id"]]
    assert [d["id"] for d in client.get("/deals", params={"triage": "dismissed"}).json()] == [
        first["id"]
    ]

    assert client.post("/deals/mark-seen", json={}).json() == {"updated": 1}
    assert client.get("/deals").json()[0]["triage"] == "seen"


def test_inactive_cards_are_not_scanned(client: TestClient, marketplace: FakeMarketplace) -> None:
    card = track_charizard(client)
    client.patch(f"/tracked-cards/{card['id']}", json={"active": False})

    assert scan(client)["cards_scanned"] == 0
    assert marketplace.queries == []


def test_deleting_a_tracked_card_deletes_its_listings(
    client: TestClient, marketplace: FakeMarketplace
) -> None:
    card = track_charizard(client)
    marketplace.listings[SourcePlatform.MERCARI] = [mercari("m1", "リザードンex 201/165", 4000)]
    scan(client)

    assert client.delete(f"/tracked-cards/{card['id']}").status_code == 204
    assert client.get("/deals").json() == []


def test_one_off_search_prices_every_result(
    client: TestClient, marketplace: FakeMarketplace
) -> None:
    client.post("/cardmarket/refresh", json={})
    marketplace.listings[SourcePlatform.MERCARI] = [
        mercari("m9", "フシギバナex 200/165", 1000),
        mercari("m1", "リザードンex 201/165", 4000),
    ]
    marketplace.failures.add(SourcePlatform.YAHOO_AUCTIONS)

    response = client.post(
        "/search",
        json={
            "query": "リザードン",
            "card_number": "201/165",
            "cardmarket_product_id": 719448,
            "sources": ["mercari", "yahoo_auctions"],
        },
    ).json()

    assert response["expected_sale_cents"] == 9000
    assert response["errors"] == {"yahoo_auctions": "bloqué (test)"}
    assert [(r["external_id"], r["matched"]) for r in response["results"]] == [
        ("m1", True),
        ("m9", False),
    ]
    assert response["results"][1]["reject_reason"] == "numéro de carte absent"
    # Nothing is stored by a one-off search.
    assert client.get("/deals").json() == []


def test_scanner_settings_are_validated(client: TestClient) -> None:
    settings = client.get("/settings").json()
    assert settings["scanner"]["enabled"] is False
    assert settings["scanner"]["min_roi_percent"] == 30
    assert settings["scanner"]["sources"] == ["mercari", "rakuma"]

    settings["scanner"]["sources"] = ["mercari", "other"]
    assert client.put("/settings", json=settings).status_code == 422
