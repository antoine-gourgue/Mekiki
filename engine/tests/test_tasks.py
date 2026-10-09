from datetime import date

from fastapi.testclient import TestClient
from test_api import create_reference_lot
from test_sales_import import ENGLISH_REPORT

from mekiki_engine.services import tasks
from mekiki_engine.services.settings_service import load_settings


def tasks_on(client: TestClient, today: date, **kwargs: object) -> list[dict[str, object]]:
    user_id = client.get("/auth/me").json()["id"]
    with client.app.state.session_factory() as session:  # type: ignore[attr-defined]
        settings = load_settings(session, user_id)
        found = tasks.list_tasks(session, user_id, settings, today=today, **kwargs)  # type: ignore[arg-type]
        return [task.model_dump() for task in found]


def set_up_business(client: TestClient) -> dict[str, object]:
    settings = client.get("/settings").json()
    settings["business"]["siret"] = "12345678900012"
    client.put("/settings", json=settings)
    lot = create_reference_lot(client)
    client.patch(
        f"/lots/{lot['id']}",
        json={"status": "received", "ordered_on": "2026-01-05", "received_on": "2026-01-10"},
    )
    sale = {"platform": "ebay", "sold_on": "2026-02-20", "sale_price_cents": 9000}
    client.put(f"/items/{lot['items'][0]['id']}/sale", json=sale)
    return lot


def test_the_day_s_tasks(client: TestClient) -> None:
    set_up_business(client)

    found = {task["id"]: task for task in tasks_on(client, date(2026, 4, 10))}

    declaration = found["declaration:2026-01-01"]
    assert declaration["title"] == "Déclarer le chiffre d'affaires : 1er trimestre 2026"
    assert declaration["detail"] == "Avant le 30/04/2026 · 90,00 € de chiffre d'affaires"
    assert (declaration["tone"], declaration["notify"]) == ("info", False)
    ship = found["ship"]
    assert (ship["title"], ship["notify"], ship["to"]) == ("1 vente à expédier", True, "/ventes")
    assert found["list"]["title"] == "9 cartes à mettre en vente"
    assert found["dormant"]["title"] == "9 cartes dorment en stock"


def test_a_declaration_asks_to_match_the_period_s_ebay_sales_first(client: TestClient) -> None:
    set_up_business(client)
    client.post("/sales/import/ebay", json={"content": ENGLISH_REPORT})

    found = {task["id"]: task for task in tasks_on(client, date(2027, 1, 10))}

    assert found["declaration:2026-10-01"]["detail"] == (
        "Avant le 31/01/2027 · 0,00 € de chiffre d'affaires · d'abord 2 ventes eBay à rapprocher"
    )


def test_a_close_deadline_is_worth_a_notification(client: TestClient) -> None:
    set_up_business(client)

    declaration = next(
        task for task in tasks_on(client, date(2026, 4, 25)) if task["id"].startswith("decl")
    )

    assert (declaration["tone"], declaration["notify"]) == ("warning", True)


def test_shipped_lots_wait_to_be_received(client: TestClient) -> None:
    lot = create_reference_lot(client)
    client.patch(
        f"/lots/{lot['id']}",
        json={"status": "shipped", "shipped_on": "2026-10-01", "tracking_number": "EG123456789JP"},
    )

    found = client.get("/tasks").json()

    receive = next(task for task in found if task["id"] == f"receive:{lot['id']}")
    assert receive["title"] == "Réceptionner le lot « Colis 1 »"
    assert receive["detail"] == "Expédié le 01/10/2026 · suivi EG123456789JP"
    assert receive["to"] == f"/lots/{lot['id']}"
    # Without a business profile, no declaration is asked for.
    assert not any(task["id"].startswith("declaration") for task in found)


def test_a_failed_backup_comes_first(client: TestClient) -> None:
    found = tasks_on(client, date(2026, 4, 10), backup_error="disque plein")

    assert (found[0]["id"], found[0]["tone"], found[0]["notify"]) == ("backup", "error", True)
