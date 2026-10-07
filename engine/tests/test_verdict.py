from typing import Any

from fastapi.testclient import TestClient

# The fake Cardmarket price guide: the double rare Charizard ex (SV2a 006) at 90 €.
CHARIZARD = 719448


def verdict(client: TestClient, **params: Any) -> dict[str, Any]:
    response = client.get("/resale/verdict", params=params)
    assert response.status_code == 200, response.text
    return response.json()  # type: ignore[no-any-return]


def test_a_catalog_card_gets_the_most_to_pay_in_japan(client: TestClient) -> None:
    client.post("/cardmarket/refresh", json={})

    result = verdict(client, product_id=CHARIZARD, label="SV2a 006/165 · RR")

    assert result["verdict"] == "limit"
    [cardmarket] = result["outlets"]
    assert cardmarket["platform"] == "cardmarket"
    assert cardmarket["sale_cents"] == 9000
    assert cardmarket["max_buy_jpy"] > 0
    assert cardmarket["margin_cents"] is None
    assert result["headline"].startswith("À acheter")
    assert result["prices"]["query"].endswith("006/165")
    assert any("eBay" in signal["text"] for signal in result["signals"])


def test_a_listing_is_judged_against_the_target_roi(client: TestClient) -> None:
    client.post("/cardmarket/refresh", json={})

    cheap = verdict(client, product_id=CHARIZARD, price_jpy=4000, shipping_included=True)
    dear = verdict(client, product_id=CHARIZARD, price_jpy=40000, shipping_included=True)
    fake = verdict(client, product_id=CHARIZARD, price_jpy=200, shipping_included=True)

    assert cheap["verdict"] == "good"
    assert cheap["outlets"][0]["roi"] >= cheap["target_roi"]
    assert cheap["headline"].startswith("Bonne affaire")
    assert dear["verdict"] == "bad"
    assert dear["outlets"][0]["margin_cents"] < 0
    assert fake["verdict"] == "suspicious"
    assert fake["signals"][0]["tone"] == "negative"


def test_a_card_in_stock_is_judged_on_its_real_cost(client: TestClient) -> None:
    client.post("/cardmarket/refresh", json={})
    lot = client.post("/lots", json={"label": "Colis"}).json()
    item = client.post(
        f"/lots/{lot['id']}/items",
        json={
            "game": "pokemon",
            "name": "Dracaufeu ex",
            "card_number": "006/165",
            "price_jpy": 8000,
            "cardmarket_product_id": CHARIZARD,
        },
    ).json()

    result = verdict(client, item_id=item["id"])

    assert result["landed_cents"] == item["landed_cost"]["total_cents"]
    assert result["outlets"][0]["margin_cents"] == (
        result["outlets"][0]["net_cents"] - item["landed_cost"]["total_cents"]
    )
    assert result["prices"]["query"] == "Dracaufeu ex 006/165"
    # Bought alone, the card carries the whole parcel's costs: the verdict is about selling.
    assert result["headline"].startswith(("À vendre sur", "Marge faible", "Perte de"))


def test_an_unknown_card_cannot_be_judged(client: TestClient) -> None:
    assert client.get("/resale/verdict").status_code == 422
    assert client.get("/resale/verdict", params={"product_id": 1}).status_code == 422
    unpriced = verdict(client, q="carte inconnue 001/001")
    assert unpriced["verdict"] == "unknown"
    assert unpriced["outlets"] == []
