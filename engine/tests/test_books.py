from datetime import date

from fastapi.testclient import TestClient
from test_api import create_reference_lot

from mekiki_engine.services import books
from mekiki_engine.services.settings_service import load_settings


def sell(client: TestClient, item_id: int, sold_on: str, price: int, **extra: object) -> None:
    sale = {"platform": "cardmarket", "sold_on": sold_on, "sale_price_cents": price, **extra}
    assert client.put(f"/items/{item_id}/sale", json=sale).status_code == 200


def books_fixture(client: TestClient) -> dict[str, object]:
    lot = create_reference_lot(client)
    client.patch(f"/lots/{lot['id']}", json={"status": "received", "ordered_on": "2026-02-10"})
    ids = [item["id"] for item in lot["items"]]
    sell(client, ids[0], "2026-02-20", 9000)
    sell(client, ids[1], "2026-05-03", 5000, platform="ebay", shipping_charged_cents=300)
    sell(client, ids[2], "2025-12-30", 7000)
    return lot


def summary_on(client: TestClient, today: date) -> dict[str, object]:
    user_id = client.get("/auth/me").json()["id"]
    with client.app.state.session_factory() as session:  # type: ignore[attr-defined]
        settings = load_settings(session, user_id)
        return books.summary(session, user_id, settings, 2026, today=today).model_dump()


def test_turnover_and_contributions_by_quarter(client: TestClient) -> None:
    books_fixture(client)

    summary = summary_on(client, date(2026, 5, 15))

    q1, q2, q3, _q4 = summary["periods"]  # type: ignore[misc]
    assert (q1["label"], q1["turnover_cents"], q1["contributions_cents"]) == (
        "1er trimestre 2026",
        9000,
        1107,
    )
    # Shipping paid by the buyer is turnover too.
    assert (q2["turnover_cents"], q2["contributions_cents"]) == (5300, 652)
    assert (q1["due_on"], q1["state"]) == ("2026-04-30", "past")
    assert (q2["state"], q3["turnover_cents"]) == ("upcoming", 0)
    assert summary["turnover_cents"] == 14300
    assert summary["turnover_limit_cents"] == 18_870_000
    assert summary["next_declaration"] is None
    assert summary_on(client, date(2026, 4, 10))["next_declaration"]["label"] == (  # type: ignore[index]
        "1er trimestre 2026"
    )


def test_monthly_declarations(client: TestClient) -> None:
    settings = client.get("/settings").json()
    settings["business"]["declaration"] = "monthly"
    settings["income_tax_rate_percent"] = 1
    client.put("/settings", json=settings)
    books_fixture(client)

    summary = client.get("/books/summary", params={"year": 2026}).json()

    february = summary["periods"][1]
    assert len(summary["periods"]) == 12
    assert (february["label"], february["due_on"]) == ("Février 2026", "2026-03-31")
    assert (february["turnover_cents"], february["income_tax_cents"]) == (9000, 90)
    assert summary["periods"][11]["due_on"] == "2027-01-31"


def test_book_of_receipts_for_excel(client: TestClient) -> None:
    books_fixture(client)

    response = client.get("/books/receipts.csv", params={"year": 2026})

    assert 'filename="livre-des-recettes-2026.csv"' in response.headers["content-disposition"]
    lines = response.content.decode("utf-8").splitlines()
    assert lines[0] == ("﻿Date;Pièce;Client;Nature;Montant encaissé (€);Mode de règlement")
    assert (
        lines[1]
        == "20/02/2026;V-00001;Client Cardmarket;Carte Pikachu ex SAR;90,00;Virement Cardmarket"
    )
    assert lines[2] == "03/05/2026;V-00002;Client eBay;Carte Pikachu ex SAR;53,00;Virement eBay"
    assert len(lines) == 3


def test_register_of_purchases_for_excel(client: TestClient) -> None:
    books_fixture(client)

    lines = client.get("/books/purchases.csv", params={"year": 2026}).content.decode().splitlines()

    assert lines[0].endswith("Date;Pièce;Fournisseur;Nature;Montant (€);Mode de règlement")
    # The reference case: each card of the parcel costs 62,67 € all included.
    assert (
        lines[1]
        == "10/02/2026;Lot Colis 1;Neokyo (Mercari);Carte Pikachu ex SAR;62,67;Paiement Neokyo"
    )
    assert len(lines) == 11
    assert client.get("/books/purchases.csv", params={"year": 2025}).text.count("\n") == 1


def set_rates(client: TestClient, contribution: float, income_tax: float) -> None:
    settings = client.get("/settings").json()
    settings["contribution_rate_percent"] = contribution
    settings["income_tax_rate_percent"] = income_tax
    assert client.put("/settings", json=settings).status_code == 200


def test_each_sale_counts_at_the_rates_frozen_on_it(client: TestClient) -> None:
    lot = create_reference_lot(client)
    ids = [item["id"] for item in lot["items"]]
    set_rates(client, 12.3, 1)
    sell(client, ids[0], "2026-02-20", 10000)
    # ACRE ends, or the law changes: the rates of the next sales differ.
    set_rates(client, 6.2, 0)
    sell(client, ids[1], "2026-03-02", 10000)

    q1 = summary_on(client, date(2026, 4, 10))["periods"][0]  # type: ignore[index]

    assert (q1["turnover_cents"], q1["contributions_cents"]) == (20000, 1230 + 620)
    assert q1["income_tax_cents"] == 100
