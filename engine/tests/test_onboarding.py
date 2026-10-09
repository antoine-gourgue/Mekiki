import json

from fastapi.testclient import TestClient

from mekiki_engine.models import SettingRow
from mekiki_engine.services.settings_service import settings_key


def task_ids(client: TestClient) -> list[str]:
    return [task["id"] for task in client.get("/tasks").json()]


def test_a_new_account_is_led_through_the_setup_until_it_finishes(client: TestClient) -> None:
    settings = client.get("/settings").json()
    assert settings["onboarded"] is False
    assert task_ids(client)[0] == "onboarding"

    client.put("/settings", json=settings | {"onboarded": True})

    assert client.get("/settings").json()["onboarded"] is True
    assert "onboarding" not in task_ids(client)


def test_settings_saved_before_the_setup_existed_count_as_set_up(client: TestClient) -> None:
    settings = client.get("/settings").json()
    del settings["onboarded"]
    with client.app.state.session_factory() as session:  # type: ignore[attr-defined]
        user_id = client.get("/auth/me").json()["id"]
        row = session.get(SettingRow, settings_key(user_id))
        assert row is not None
        row.value = json.dumps(settings)
        session.commit()

    assert client.get("/settings").json()["onboarded"] is True
    assert "onboarding" not in task_ids(client)
