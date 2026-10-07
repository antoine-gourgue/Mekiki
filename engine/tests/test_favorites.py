from pathlib import Path
from typing import Any

import httpx
from conftest import FakeMarketplace, cardmarket_handler
from fastapi.testclient import TestClient

from mekiki_engine.app import create_app
from mekiki_engine.config import load_config
from mekiki_engine.domain import SourcePlatform
from mekiki_engine.scanner.sources.base import FoundListing


def favorite(item_id: str, price: int, **extra: Any) -> dict[str, Any]:
    return {
        "game": "pokemon",
        "source": "mercari",
        "external_id": item_id,
        "title": f"リザードンex RR 006/165 ({item_id})",
        "price_jpy": price,
        "shipping_included": True,
        "url": f"https://jp.mercari.com/item/{item_id}",
        "card_label": "SV2a 006/165 · RR",
        "cardmarket_product_id": 719448,
        **extra,
    }


def test_favorites_are_priced_and_the_cart_as_one_parcel(client: TestClient) -> None:
    client.post("/cardmarket/refresh", json={})
    client.post("/favorites", json=favorite("m1", 4000, in_cart=True))
    client.post("/favorites", json=favorite("m2", 6000, in_cart=True))
    response = client.post("/favorites", json=favorite("m3", 5000)).json()

    items = {item["external_id"]: item for item in response["items"]}
    assert [item["external_id"] for item in response["items"]] == ["m3", "m2", "m1"]
    assert items["m1"]["expected_sale_cents"] == 9000
    assert items["m1"]["neokyo_url"] == "https://neokyo.com/fr/product/mercari/m1"
    assert items["m1"]["product"]["id_product"] == 719448

    cart = response["cart"]
    assert cart["card_count"] == 2
    assert cart["purchase_jpy"] == 10000
    assert cart["landed_cents"] == (
        items["m1"]["landed_cost"]["total_cents"] + items["m2"]["landed_cost"]["total_cents"]
    )
    assert cart["revenue_cents"] == 18000
    assert cart["margin_cents"] == cart["net_cents"] - cart["landed_cents"]
    # Shared parcel costs follow the price: the dearer card carries more of them.
    assert (
        items["m2"]["landed_cost"]["shipping_cents"] > items["m1"]["landed_cost"]["shipping_cents"]
    )


def test_saving_again_refreshes_but_keeps_user_choices(client: TestClient) -> None:
    client.post("/favorites", json=favorite("m1", 4000, in_cart=True, notes="à surveiller"))

    [item] = client.post("/favorites", json=favorite("m1", 3500)).json()["items"]

    assert item["price_jpy"] == 3500
    assert item["in_cart"] is True
    assert item["notes"] == "à surveiller"


def test_cart_toggles_target_price_and_removal(client: TestClient) -> None:
    [item] = client.post(
        "/favorites", json=favorite("m1", 4000, cardmarket_product_id=None)
    ).json()["items"]
    assert item["sale"] is None

    updated = client.patch(
        f"/favorites/{item['id']}", json={"in_cart": True, "target_price_cents": 5000}
    ).json()
    assert updated["items"][0]["expected_sale_cents"] == 5000
    assert updated["cart"]["card_count"] == 1

    assert client.post("/favorites/empty-cart", json={}).json()["cart"] is None
    assert client.delete(f"/favorites/{item['id']}").json() == {"items": [], "cart": None}
    assert client.delete(f"/favorites/{item['id']}").status_code == 404


def test_unpriced_cart_items_are_counted(client: TestClient) -> None:
    response = client.post(
        "/favorites", json=favorite("m1", 4000, cardmarket_product_id=None, in_cart=True)
    ).json()

    assert response["cart"]["unpriced_count"] == 1
    assert response["cart"]["revenue_cents"] == 0


def test_last_discovery_survives_a_restart(
    tmp_path: Path, client: TestClient, marketplace: FakeMarketplace
) -> None:
    client.post("/cardmarket/refresh", json={})
    marketplace.listings[SourcePlatform.MERCARI] = [
        FoundListing(
            source=SourcePlatform.MERCARI,
            external_id="m1",
            title="リザードンex RR SV2a 006/165",
            price_jpy=4000,
            url="https://jp.mercari.com/item/m1",
            shipping_included=True,
        )
    ]
    client.post(
        "/discovery",
        json={
            "game": "pokemon",
            "budget_cents": 15000,
            "card_count": 1,
            "min_roi_percent": 0,
            "sources": ["mercari"],
        },
    )

    restarted = create_app(
        load_config(data_dir=str(tmp_path), background_jobs=False),
        http_transport=httpx.MockTransport(cardmarket_handler),
        source_factory=marketplace.factory(),
    )
    with TestClient(restarted, base_url="http://127.0.0.1:18421") as again:
        again.headers["Authorization"] = client.headers["Authorization"]
        run = again.get("/discovery").json()

    assert run["status"] == "done"
    assert run["request"]["budget_cents"] == 15000
    assert [p["external_id"] for p in run["picks"]] == ["m1"]
