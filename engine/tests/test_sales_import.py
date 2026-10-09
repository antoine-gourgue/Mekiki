from datetime import date

import pytest
from fastapi.testclient import TestClient
from test_api import create_reference_lot

from mekiki_engine.models import Item
from mekiki_engine.services.ebay_report import money_cents, parse_date, read_report
from mekiki_engine.services.sales_import import listing_ref

# eBay starts its report with a blank line and ends it with a count of the records.
ENGLISH_REPORT = (
    "﻿\n"
    '"Sales Record Number","Order Number","Buyer Username","Item Number","Item Title",'
    '"Quantity","Sold For","Shipping And Handling","Sale Date","Shipped On Date",'
    '"Tracking Number"\n'
    '"1001","12-34567-89012","dresseur75","123456789012","Pikachu ex SAR 132/106 Japanese",'
    '"1","EUR 90,00","EUR 3,50","Oct-05-26","Oct-06-26","6A12345678901"\n'
    '"1002","12-34567-89013","sacha","210987654321","Charizard ex 201/165 SV2a Japanese",'
    '"1","EUR 120,00","EUR 0,00","Oct-07-26","",""\n'
    '"","","","","","","","","","",""\n'
    '"2 record(s) downloaded"\n'
)
FRENCH_REPORT = (
    "Numéro de vente;Numéro de commande;Pseudo de l’acheteur;Numéro de l'objet;"
    "Intitulé de l'objet;Quantité;Vendu pour;Livraison et manutention;Date de vente\n"
    "1;05-11111-22222;lucie;111122223333;Dracaufeu ex;1;1 234,50 €;4,00 €;05-oct.-26\n"
)


@pytest.mark.parametrize(
    ("text", "cents"),
    [("EUR 90,00", 9000), ("1 234,50 €", 123450), ("12.5", 1250), ("EUR 7", 700), ("", None)],
)
def test_amounts(text: str, cents: int | None) -> None:
    assert money_cents(text) == cents


@pytest.mark.parametrize(
    "text",
    ["Oct-05-26", "05-oct.-26", "5 oct. 2026", "05/10/2026", "2026-10-05", "Oct 5, 2026"],
)
def test_dates(text: str) -> None:
    assert parse_date(text) == date(2026, 10, 5)


def test_reports_in_english_and_french() -> None:
    english = read_report(ENGLISH_REPORT)
    french = read_report(FRENCH_REPORT)

    first = english.lines[0]
    assert len(english.lines) == 2
    assert (first.order, first.item, first.price_cents, first.shipping_cents) == (
        "12-34567-89012",
        "123456789012",
        9000,
        350,
    )
    assert (first.shipped_on, first.tracking_number) == (date(2026, 10, 6), "6A12345678901")
    assert english.lines[1].shipped_on is None
    assert (french.lines[0].price_cents, french.lines[0].buyer) == (123450, "lucie")


def test_an_unknown_file_says_what_it_found() -> None:
    report = read_report("Date,Description,Montant\n05/10/2026,Vente,12\n")

    assert report.lines == []
    assert report.headers == ["Date", "Description", "Montant"]
    # "Date" alone is not "Sale date": nothing is guessed.
    assert report.missing == ["order", "item", "title", "price", "sold_on"]


def test_listing_addresses_give_the_item_number() -> None:
    assert listing_ref("https://www.ebay.fr/itm/123456789012?hash=x") == "123456789012"
    assert listing_ref("https://www.ebay.fr/sl/success?itemId=210987654321") == "210987654321"
    assert listing_ref("https://www.ebay.fr/lstng?draftId=5") is None


def listed_on_ebay(client: TestClient, item_id: int, number: str) -> None:
    with client.app.state.session_factory() as session:  # type: ignore[attr-defined]
        item = session.get(Item, item_id)
        assert item is not None
        item.listing_platform = "ebay"
        item.listing_ref = number
        session.commit()


def test_report_lines_become_sales(client: TestClient) -> None:
    lot = create_reference_lot(client)
    first, second = lot["items"][0]["id"], lot["items"][1]["id"]
    listed_on_ebay(client, first, "123456789012")

    result = client.post("/sales/import/ebay", json={"content": ENGLISH_REPORT}).json()
    again = client.post("/sales/import/ebay", json={"content": ENGLISH_REPORT}).json()

    assert (result["lines"], result["imported"], result["pending"]) == (2, 1, 1)
    assert (again["imported"], again["pending"], again["updated"]) == (0, 0, 0)
    sale = client.get(f"/items/{first}").json()["sale"]
    assert (sale["platform"], sale["sold_on"], sale["sale_price_cents"]) == (
        "ebay",
        "2026-10-05",
        9000,
    )
    assert (sale["shipping_charged_cents"], sale["shipped_on"]) == (350, "2026-10-06")
    assert sale["tracking_number"] == "6A12345678901"
    # Fees come from the eBay rule in the settings, as for a sale entered by hand.
    rule = client.get("/settings").json()["platform_fees"]["ebay"]
    assert sale["platform_fee_cents"] == round(9000 * rule["percent"] / 100) + rule["fixed_cents"]

    [pending] = client.get("/sales/pending").json()
    assert pending["title"] == "Charizard ex 201/165 SV2a Japanese"
    tasks = {task["id"]: task for task in client.get("/tasks").json()}
    assert tasks["pending-sales"]["title"] == "1 vente eBay à rapprocher"

    matched = client.post(f"/sales/pending/{pending['id']}/match", json={"item_id": second})
    assert matched.json()["sale"]["sale_price_cents"] == 12000
    assert client.get("/sales/pending").json() == []


def test_a_later_report_brings_shipping_up_to_date(client: TestClient) -> None:
    lot = create_reference_lot(client)
    item_id = lot["items"][0]["id"]
    listed_on_ebay(client, item_id, "210987654321")
    client.post("/sales/import/ebay", json={"content": ENGLISH_REPORT})
    shipped = ENGLISH_REPORT.replace('"Oct-07-26","",""', '"Oct-07-26","Oct-08-26","LB123456789FR"')

    result = client.post("/sales/import/ebay", json={"content": shipped}).json()

    assert result["updated"] == 1
    sale = client.get(f"/items/{item_id}").json()["sale"]
    assert (sale["shipped_on"], sale["tracking_number"]) == ("2026-10-08", "LB123456789FR")


def test_suggestions_and_ignored_lines(client: TestClient) -> None:
    lot = client.post("/lots", json={"label": "Colis"}).json()
    card = {"game": "pokemon", "name": "Dracaufeu ex", "card_number": "201/165", "price_jpy": 9000}
    item = client.post(f"/lots/{lot['id']}/items", json=card).json()
    client.post("/sales/import/ebay", json={"content": ENGLISH_REPORT})

    pending = {p["title"]: p for p in client.get("/sales/pending").json()}
    charizard = pending["Charizard ex 201/165 SV2a Japanese"]
    assert charizard["suggestions"][0]["item_id"] == item["id"]

    client.delete(f"/sales/pending/{charizard['id']}")
    client.post("/sales/import/ebay", json={"content": ENGLISH_REPORT})
    titles = [p["title"] for p in client.get("/sales/pending").json()]
    assert "Charizard ex 201/165 SV2a Japanese" not in titles


def test_a_cancelled_sale_never_comes_back(client: TestClient) -> None:
    lot = create_reference_lot(client)
    item_id = lot["items"][0]["id"]
    listed_on_ebay(client, item_id, "123456789012")
    client.post("/sales/import/ebay", json={"content": ENGLISH_REPORT})

    client.delete(f"/items/{item_id}/sale")
    again = client.post("/sales/import/ebay", json={"content": ENGLISH_REPORT}).json()

    # The card came back to stock (a return): the old report must not sell it again.
    assert again["imported"] == 0
    assert client.get(f"/items/{item_id}").json()["sale"] is None
    titles = [p["title"] for p in client.get("/sales/pending").json()]
    assert "Pikachu ex SAR 132/106 Japanese" not in titles


def test_a_line_repeated_in_one_report_is_booked_once(client: TestClient) -> None:
    lot = create_reference_lot(client)
    listed_on_ebay(client, lot["items"][0]["id"], "123456789012")
    first_line = ENGLISH_REPORT.splitlines()[2]
    doubled = ENGLISH_REPORT.replace(first_line, f"{first_line}\n{first_line}")

    result = client.post("/sales/import/ebay", json={"content": doubled}).json()

    assert (result["imported"], result["pending"]) == (1, 1)
