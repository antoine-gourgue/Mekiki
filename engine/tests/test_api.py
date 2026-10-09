from typing import Any

from fastapi.testclient import TestClient

from mekiki_engine.models import SettingRow

CARD = {"game": "pokemon", "name": "Pikachu ex SAR", "set_code": "SV8a", "price_jpy": 8000}


def create_reference_lot(client: TestClient) -> dict[str, Any]:
    """Section 4 reference parcel: 10 cards at 8 000 JPY, settings defaults for the rest."""
    response = client.post("/lots", json={"label": "Colis 1", "international_shipping_jpy": 4000})
    assert response.status_code == 201
    lot = response.json()
    for _ in range(10):
        assert client.post(f"/lots/{lot['id']}/items", json=CARD).status_code == 201
    return client.get(f"/lots/{lot['id']}").json()


def test_health(client: TestClient) -> None:
    assert client.get("/health").json()["status"] == "ok"


def test_lot_takes_its_defaults_from_the_settings(client: TestClient) -> None:
    lot = create_reference_lot(client)

    assert lot["fx_jpy_per_eur"] == 170
    assert lot["packing_fee_jpy"] == 500
    assert lot["handling_fee_cents"] == 1000
    assert lot["items"][0]["service_fee_jpy"] == 350


def test_reference_lot_costs(client: TestClient) -> None:
    lot = create_reference_lot(client)
    first = lot["items"][0]

    assert first["status"] == "incoming"
    assert first["landed_cost"] == {
        "purchase_cents": 4706,
        "proxy_fees_cents": 236,
        "shipping_cents": 236,
        "import_taxes_cents": 1089,
        "total_cents": 6267,
        "vat_estimated": True,
    }
    assert lot["item_count"] == 10
    assert lot["goods_jpy"] == 80000
    assert lot["applied_import_vat_cents"] == 9882
    assert lot["vat_estimated"] is True
    # Every cent paid for the parcel lands on a card.
    assert lot["landed_total_cents"] == 47060 + (10 * 206 + 294) + 2353 + (9882 + 1000)
    assert lot["landed_total_cents"] == sum(i["landed_cost"]["total_cents"] for i in lot["items"])


def test_full_cycle_from_purchase_to_dashboard(client: TestClient) -> None:
    lot = create_reference_lot(client)
    first_id = lot["items"][0]["id"]

    received = client.patch(f"/lots/{lot['id']}", json={"status": "received"}).json()
    assert {i["status"] for i in received["items"]} == {"in_stock"}

    listed = client.patch(
        f"/items/{first_id}", json={"listing_platform": "cardmarket", "listing_price_cents": 9000}
    ).json()
    assert listed["status"] == "listed"
    assert listed["listing_projection"]["net_cents"] == 7393
    assert listed["listing_projection"]["margin_cents"] == 1126

    sold = client.put(
        f"/items/{first_id}/sale",
        json={"platform": "cardmarket", "sold_on": "2026-10-05", "sale_price_cents": 9000},
    ).json()
    assert sold["status"] == "sold"
    assert sold["listing_projection"] is None
    sale = sold["sale"]
    assert sale["platform_fee_cents"] == 450
    assert sale["packaging_cents"] == 50
    assert sale["contribution_rate_percent"] == 12.3
    assert sale["breakdown"] == {
        "revenue_cents": 9000,
        "platform_fee_cents": 450,
        "shipping_cost_cents": 0,
        "packaging_cents": 50,
        "contributions_cents": 1107,
        "net_cents": 7393,
        "margin_cents": 1126,
        "roi": 0.1797,
    }

    dashboard = client.get("/dashboard").json()
    assert dashboard["in_stock_count"] == 9
    assert dashboard["listed_count"] == 0
    assert dashboard["incoming_count"] == 0
    assert dashboard["stock_cost_cents"] == lot["landed_total_cents"] - 6267
    assert dashboard["sold_count"] == 1
    assert dashboard["revenue_cents"] == 9000
    assert dashboard["net_cents"] == 7393
    assert dashboard["cost_of_sold_cents"] == 6267
    assert dashboard["margin_cents"] == 1126
    assert dashboard["roi"] == 0.1797
    assert dashboard["monthly"] == [
        {
            "month": "2026-10",
            "sold_count": 1,
            "revenue_cents": 9000,
            "net_cents": 7393,
            "margin_cents": 1126,
        }
    ]

    later = client.get("/dashboard", params={"since": "2026-11-01"}).json()
    assert later["sold_count"] == 0
    assert later["monthly"] == []


def test_settings_changes_do_not_rewrite_past_sales(client: TestClient) -> None:
    lot = create_reference_lot(client)
    first_id = lot["items"][0]["id"]
    client.put(
        f"/items/{first_id}/sale",
        json={"platform": "cardmarket", "sold_on": "2026-10-05", "sale_price_cents": 9000},
    )

    settings = client.get("/settings").json()
    settings["contribution_rate_percent"] = 13.3
    settings["default_packaging_cents"] = 80
    settings["platform_fees"]["cardmarket"]["percent"] = 6
    assert client.put("/settings", json=settings).json()["contribution_rate_percent"] == 13.3

    [item] = client.get("/inventory", params={"status": "sold"}).json()
    assert item["sale"]["breakdown"]["net_cents"] == 7393
    assert item["sale"]["contribution_rate_percent"] == 12.3


def test_ebay_fees_have_a_realistic_default(client: TestClient) -> None:
    ebay = client.get("/settings").json()["platform_fees"]["ebay"]
    user_id = client.get("/auth/me").json()["id"]
    with client.app.state.session_factory() as session:  # type: ignore[attr-defined]
        # Settings saved under the old default keep their own rule.
        row = session.get(SettingRow, f"app:{user_id}")
        assert row is not None
        row.value = '{"platform_fees": {"ebay": {"percent": 0, "fixed_cents": 0}}}'
        session.commit()

    assert ebay == {"percent": 11, "fixed_cents": 35, "applies_to_shipping": True}
    assert client.get("/settings").json()["platform_fees"]["ebay"]["percent"] == 0


def test_actual_vat_replaces_the_estimate_and_null_restores_it(client: TestClient) -> None:
    lot = create_reference_lot(client)

    actual = client.patch(f"/lots/{lot['id']}", json={"import_vat_cents": 12000}).json()
    assert actual["vat_estimated"] is False
    assert actual["applied_import_vat_cents"] == 12000
    assert actual["items"][0]["landed_cost"]["import_taxes_cents"] == 1300
    assert actual["items"][0]["landed_cost"]["total_cents"] == 4706 + 236 + 236 + 1300

    estimated = client.patch(f"/lots/{lot['id']}", json={"import_vat_cents": None}).json()
    assert estimated["vat_estimated"] is True
    assert estimated["items"][0]["landed_cost"]["total_cents"] == 6267


def test_patch_refuses_null_on_required_fields(client: TestClient) -> None:
    lot = create_reference_lot(client)

    assert client.patch(f"/lots/{lot['id']}", json={"label": None}).status_code == 422
    item_id = lot["items"][0]["id"]
    assert client.patch(f"/items/{item_id}", json={"price_jpy": None}).status_code == 422


def test_moving_a_card_reallocates_both_lots(client: TestClient) -> None:
    lot = create_reference_lot(client)
    other = client.post("/lots", json={"label": "Colis 2"}).json()
    item_id = lot["items"][0]["id"]

    moved = client.patch(f"/items/{item_id}", json={"lot_id": other["id"]}).json()

    assert moved["lot_id"] == other["id"]
    assert moved["lot_label"] == "Colis 2"
    assert client.get(f"/lots/{lot['id']}").json()["item_count"] == 9
    assert client.get(f"/lots/{other['id']}").json()["item_count"] == 1


def test_inventory_filters(client: TestClient) -> None:
    create_reference_lot(client)

    assert len(client.get("/inventory").json()) == 10
    assert len(client.get("/inventory", params={"status": "incoming"}).json()) == 10
    assert client.get("/inventory", params={"status": "in_stock"}).json() == []
    assert client.get("/inventory", params={"game": "one_piece"}).json() == []
    assert client.get("/inventory", params={"status": "nope"}).status_code == 422


def test_cancelling_and_deleting(client: TestClient) -> None:
    lot = create_reference_lot(client)
    item_id = lot["items"][0]["id"]
    sale = {"platform": "ebay", "sold_on": "2026-10-05", "sale_price_cents": 5000}

    client.put(f"/items/{item_id}/sale", json=sale)
    assert client.delete(f"/items/{item_id}/sale").json()["sale"] is None

    client.put(f"/items/{item_id}/sale", json=sale)
    # The sale is in the books: deleting its card or lot would erase it.
    refused_item = client.delete(f"/items/{item_id}")
    refused_lot = client.delete(f"/lots/{lot['id']}")
    assert (refused_item.status_code, refused_lot.status_code) == (409, 409)
    assert "annulez d'abord la vente" in refused_item.json()["detail"]
    assert refused_lot.json()["detail"].startswith("ce lot a une carte vendue")
    assert client.get("/dashboard").json()["sold_count"] == 1

    client.delete(f"/items/{item_id}/sale")
    assert client.delete(f"/items/{item_id}").status_code == 204
    assert client.get("/dashboard").json()["sold_count"] == 0

    assert client.delete(f"/lots/{lot['id']}").status_code == 204
    assert client.get("/lots").json() == []
    assert client.get("/inventory").json() == []


def test_unknown_resources_are_404(client: TestClient) -> None:
    assert client.get("/lots/999").status_code == 404
    assert client.patch("/items/999", json={"name": "x"}).status_code == 404
    assert client.post("/lots/999/items", json=CARD).status_code == 404


def test_simulator_reference_case(client: TestClient) -> None:
    result = client.post("/simulate", json={"price_jpy": 8000, "sale_price_cents": 9000}).json()

    assert result["landed_cost"]["total_cents"] == 6267
    assert result["sale"]["net_cents"] == 7393
    assert result["sale"]["margin_cents"] == 1126
    assert result["sale"]["roi"] == 0.1797
    assert result["fx_jpy_per_eur"] == 170


def test_simulator_max_price_is_the_roi_threshold(client: TestClient) -> None:
    request = {"price_jpy": 8000, "sale_price_cents": 9000, "target_roi_percent": 30}
    max_price = client.post("/simulate", json=request).json()["max_price_jpy"]

    at_max = client.post("/simulate", json={**request, "price_jpy": max_price}).json()
    above = client.post("/simulate", json={**request, "price_jpy": max_price + 1}).json()
    assert 0 < max_price < 8000
    assert at_max["sale"]["margin_cents"] >= 0.30 * at_max["landed_cost"]["total_cents"]
    assert above["sale"]["margin_cents"] < 0.30 * above["landed_cost"]["total_cents"]


def test_simulator_without_a_profitable_price(client: TestClient) -> None:
    result = client.post("/simulate", json={"price_jpy": 8000, "sale_price_cents": 100}).json()

    assert result["max_price_jpy"] is None


def test_request_bodies_must_be_json(client: TestClient) -> None:
    response = client.post(
        "/lots", content='{"label": "x"}', headers={"content-type": "text/plain"}
    )

    assert response.status_code == 415


def test_foreign_host_headers_are_rejected(client: TestClient) -> None:
    assert client.get("/health", headers={"host": "evil.example"}).status_code == 400


def test_cors_allows_only_the_app_origins(client: TestClient) -> None:
    preflight = {"access-control-request-method": "POST"}
    allowed = client.options("/lots", headers={"origin": "http://tauri.localhost", **preflight})
    denied = client.options("/lots", headers={"origin": "https://evil.example", **preflight})

    assert allowed.headers["access-control-allow-origin"] == "http://tauri.localhost"
    assert "access-control-allow-origin" not in denied.headers


def test_a_sale_keeps_its_parcel(client: TestClient) -> None:
    lot = create_reference_lot(client)
    item_id = lot["items"][0]["id"]
    sale = {"platform": "ebay", "sold_on": "2026-10-05", "sale_price_cents": 9000}

    to_ship = client.put(f"/items/{item_id}/sale", json=sale).json()["sale"]
    shipped = client.put(
        f"/items/{item_id}/sale",
        json={**sale, "tracking_number": "6A12345678901", "shipped_on": "2026-10-06"},
    ).json()["sale"]

    assert (to_ship["tracking_number"], to_ship["shipped_on"]) == (None, None)
    assert (shipped["tracking_number"], shipped["shipped_on"]) == ("6A12345678901", "2026-10-06")


def test_dashboard_counts_sleeping_cards_and_parcels_to_ship(client: TestClient) -> None:
    lot = create_reference_lot(client)
    client.patch(f"/lots/{lot['id']}", json={"status": "received", "received_on": "2026-01-01"})
    first = lot["items"][0]["id"]
    sale = {"platform": "ebay", "sold_on": "2026-01-21", "sale_price_cents": 9000}
    client.put(f"/items/{first}/sale", json=sale)

    dashboard = client.get("/dashboard").json()

    # Nine unsold cards of a parcel received months ago, and one sale still to ship.
    assert dashboard["dormant_count"] == 9
    assert (
        dashboard["dormant_cost_cents"]
        == lot["landed_total_cents"] - lot["items"][0]["landed_cost"]["total_cents"]
    )
    assert dashboard["average_days_to_sell"] == 20
    assert dashboard["to_ship_count"] == 1


def test_stock_cards_get_a_price_history(client: TestClient) -> None:
    lot = client.post("/lots", json={"label": "Colis"}).json()
    card = {**CARD, "cardmarket_product_id": 719448}
    client.post(f"/lots/{lot['id']}/items", json=card)

    client.post("/cardmarket/refresh", json={})

    history = client.get("/cardmarket/products/719448/history").json()
    assert history == [{"date": "2026-10-07", "cents": 9000}]
    assert client.get("/cardmarket/products/719654/history").json() == []
