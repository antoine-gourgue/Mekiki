from pathlib import Path

import httpx
import pytest
from conftest import FakeMarketplace, cardmarket_handler, sign_in
from fastapi.testclient import TestClient
from sqlalchemy import update

from mekiki_engine.app import create_app
from mekiki_engine.auth import hash_password, verify_password
from mekiki_engine.config import load_config
from mekiki_engine.models import AuthSession, Lot, SettingRow

PASSWORD = "pikachu-2026"


@pytest.fixture
def anonymous(tmp_path: Path, marketplace: FakeMarketplace):  # type: ignore[no-untyped-def]
    app = create_app(
        load_config(data_dir=str(tmp_path), background_jobs=False),
        http_transport=httpx.MockTransport(cardmarket_handler),
        source_factory=marketplace.factory(),
    )
    with TestClient(app, base_url="http://127.0.0.1:18421") as client:
        yield client


def test_password_hashes_are_salted_and_verifiable() -> None:
    first, second = hash_password("secret-1234"), hash_password("secret-1234")

    assert first != second
    assert first.startswith("scrypt$")
    assert verify_password("secret-1234", first)
    assert not verify_password("secret-1235", first)
    assert not verify_password("secret-1234", "garbage")


def test_data_routes_require_a_session(anonymous: TestClient) -> None:
    assert anonymous.get("/health").status_code == 200
    response = anonymous.get("/lots")
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert anonymous.get("/lots", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_register_login_and_logout(anonymous: TestClient) -> None:
    registered = sign_in(anonymous, "Ash@Example.com ")
    assert registered["user"]["email"] == "ash@example.com"  # type: ignore[index]
    assert anonymous.get("/auth/me").json()["display_name"] == "Ash"

    duplicate = anonymous.post(
        "/auth/register",
        json={"email": "ASH@example.com", "password": PASSWORD, "display_name": "Other"},
    )
    assert duplicate.status_code == 409

    wrong = anonymous.post("/auth/login", json={"email": "ash@example.com", "password": "nope"})
    assert wrong.status_code == 401
    login = anonymous.post("/auth/login", json={"email": "ASH@example.com", "password": PASSWORD})
    assert login.status_code == 200
    token = login.json()["token"]

    headers = {"Authorization": f"Bearer {token}"}
    assert anonymous.post("/auth/logout", headers=headers).status_code == 204
    assert anonymous.get("/auth/me", headers=headers).status_code == 401


def test_register_validates_its_input(anonymous: TestClient) -> None:
    short = {"email": "ash@example.com", "password": "short", "display_name": "Ash"}
    bad_email = {"email": "not-an-email", "password": PASSWORD, "display_name": "Ash"}

    assert anonymous.post("/auth/register", json=short).status_code == 422
    assert anonymous.post("/auth/register", json=bad_email).status_code == 422


def test_repeated_failures_are_throttled(anonymous: TestClient) -> None:
    sign_in(anonymous, "ash@example.com")
    wrong = {"email": "ash@example.com", "password": "wrong-password"}
    statuses = [anonymous.post("/auth/login", json=wrong).status_code for _ in range(6)]

    assert statuses == [401] * 5 + [429]
    right = {"email": "ash@example.com", "password": PASSWORD}
    assert anonymous.post("/auth/login", json=right).status_code == 429


def test_expired_sessions_are_refused(anonymous: TestClient) -> None:
    sign_in(anonymous, "ash@example.com")
    with anonymous.app.state.session_factory() as session:  # type: ignore[attr-defined]
        session.execute(update(AuthSession).values(expires_at="2000-01-01T00:00:00Z"))
        session.commit()

    assert anonymous.get("/auth/me").status_code == 401


def test_password_change_needs_the_current_one_and_signs_out_elsewhere(
    anonymous: TestClient,
) -> None:
    sign_in(anonymous, "ash@example.com")
    other = anonymous.post("/auth/login", json={"email": "ash@example.com", "password": PASSWORD})
    other_headers = {"Authorization": f"Bearer {other.json()['token']}"}

    refused = anonymous.patch(
        "/auth/me", json={"current_password": "wrong", "new_password": "new-secret-1"}
    )
    assert refused.status_code == 403
    changed = anonymous.patch(
        "/auth/me",
        json={
            "current_password": PASSWORD,
            "new_password": "new-secret-1",
            "display_name": "Sacha",
        },
    )
    assert changed.json()["display_name"] == "Sacha"

    assert anonymous.get("/auth/me").status_code == 200
    assert anonymous.get("/auth/me", headers=other_headers).status_code == 401
    new_login = {"email": "ash@example.com", "password": "new-secret-1"}
    assert anonymous.post("/auth/login", json=new_login).status_code == 200


def test_accounts_never_see_each_others_data(anonymous: TestClient) -> None:
    sign_in(anonymous, "ash@example.com")
    lot = anonymous.post("/lots", json={"label": "Colis d'Ash"}).json()
    item = anonymous.post(
        f"/lots/{lot['id']}/items", json={"game": "pokemon", "name": "Pikachu", "price_jpy": 1000}
    ).json()
    card = anonymous.post("/tracked-cards", json={"game": "pokemon", "name": "Pikachu"}).json()
    favorite = anonymous.post(
        "/favorites",
        json={
            "game": "pokemon",
            "source": "mercari",
            "external_id": "m1",
            "title": "ピカチュウ",
            "price_jpy": 1000,
            "url": "https://jp.mercari.com/item/m1",
        },
    ).json()["items"][0]
    settings = anonymous.get("/settings").json()
    settings["fx_jpy_per_eur"] = 160
    anonymous.put("/settings", json=settings)

    sign_in(anonymous, "misty@example.com")

    assert anonymous.get("/lots").json() == []
    assert anonymous.get("/inventory").json() == []
    assert anonymous.get("/tracked-cards").json() == []
    assert anonymous.get("/favorites").json() == {"items": [], "cart": None}
    assert anonymous.get("/settings").json()["fx_jpy_per_eur"] == 170
    assert anonymous.get(f"/lots/{lot['id']}").status_code == 404
    assert anonymous.delete(f"/lots/{lot['id']}").status_code == 404
    assert anonymous.patch(f"/items/{item['id']}", json={"name": "x"}).status_code == 404
    assert anonymous.patch(f"/tracked-cards/{card['id']}", json={"name": "x"}).status_code == 404
    assert anonymous.delete(f"/favorites/{favorite['id']}").status_code == 404
    # Moving one's own card into someone else's lot is refused too.
    mine = anonymous.post("/lots", json={"label": "Colis d'Ondine"}).json()
    own_item = anonymous.post(
        f"/lots/{mine['id']}/items", json={"game": "pokemon", "name": "Psykokwak", "price_jpy": 500}
    ).json()
    moved = anonymous.patch(f"/items/{own_item['id']}", json={"lot_id": lot["id"]})
    assert moved.status_code == 404


def test_the_first_account_inherits_existing_data(anonymous: TestClient) -> None:
    with anonymous.app.state.session_factory() as session:  # type: ignore[attr-defined]
        session.add(Lot(label="Colis d'avant les comptes", fx_jpy_per_eur="168"))
        session.add(SettingRow(key="app", value='{"fx_jpy_per_eur": 165}'))
        session.commit()

    sign_in(anonymous, "ash@example.com")
    assert [lot["label"] for lot in anonymous.get("/lots").json()] == ["Colis d'avant les comptes"]
    assert anonymous.get("/settings").json()["fx_jpy_per_eur"] == 165

    sign_in(anonymous, "misty@example.com")
    assert anonymous.get("/lots").json() == []
