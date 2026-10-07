import base64
from pathlib import Path

from conftest import sign_in
from fastapi.testclient import TestClient

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def encoded(content: bytes, data_url: bool = False) -> dict[str, str]:
    text = base64.b64encode(content).decode()
    return {"content_base64": f"data:image/jpeg;base64,{text}" if data_url else text}


def new_item(client: TestClient) -> dict[str, object]:
    lot = client.post("/lots", json={"label": "Colis"}).json()
    return client.post(
        f"/lots/{lot['id']}/items", json={"game": "pokemon", "name": "Pikachu", "price_jpy": 900}
    ).json()


def data_dir(client: TestClient) -> Path:
    return client.app.state.config.data_dir  # type: ignore[attr-defined,no-any-return]


def test_photos_are_stored_served_and_ordered(client: TestClient) -> None:
    item = new_item(client)
    url = f"/items/{item['id']}/photos"

    first = client.post(url, json=encoded(JPEG, data_url=True))
    assert first.status_code == 201
    photos = client.post(url, json=encoded(PNG)).json()

    assert [p["content_type"] for p in photos] == ["image/jpeg", "image/png"]
    served = client.get(f"{url}/{photos[1]['id']}")
    assert served.content == PNG
    assert served.headers["content-type"] == "image/png"
    [stored] = client.get(f"/lots/{item['lot_id']}").json()["items"]
    assert stored["photos"] == photos

    reordered = client.post(f"{url}/{photos[1]['id']}/first").json()
    assert [p["id"] for p in reordered] == [photos[1]["id"], photos[0]["id"]]

    remaining = client.delete(f"{url}/{photos[0]['id']}").json()
    assert [p["id"] for p in remaining] == [photos[1]["id"]]
    assert len(list((data_dir(client) / "photos" / str(item["id"])).iterdir())) == 1


def test_only_images_are_accepted(client: TestClient) -> None:
    url = f"/items/{new_item(client)['id']}/photos"

    assert client.post(url, json=encoded(b"%PDF-1.7 not an image")).status_code == 422
    assert client.post(url, json={"content_base64": "***"}).status_code == 422


def test_deleting_a_lot_removes_its_photo_files(client: TestClient) -> None:
    item = new_item(client)
    client.post(f"/items/{item['id']}/photos", json=encoded(JPEG))
    folder = data_dir(client) / "photos" / str(item["id"])
    assert folder.is_dir()

    assert client.delete(f"/lots/{item['lot_id']}").status_code == 204
    assert not folder.exists()


def test_photos_are_private_to_the_account(client: TestClient) -> None:
    item = new_item(client)
    [photo] = client.post(f"/items/{item['id']}/photos", json=encoded(JPEG)).json()

    sign_in(client, "misty@example.com")

    assert client.get(f"/items/{item['id']}/photos/{photo['id']}").status_code == 404
    assert client.post(f"/items/{item['id']}/photos", json=encoded(JPEG)).status_code == 404


def test_one_card_and_one_product_can_be_read(client: TestClient) -> None:
    item = new_item(client)

    assert client.get(f"/items/{item['id']}").json()["name"] == "Pikachu"
    assert client.get("/items/999").status_code == 404
    assert client.get("/cardmarket/products/999999").status_code == 404
