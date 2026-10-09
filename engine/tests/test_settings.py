import json
import logging

import pytest
from fastapi.testclient import TestClient

from mekiki_engine.models import SettingRow


def save_raw(client: TestClient, value: str) -> None:
    """Writes the account's settings document as another version of Mekiki might have."""
    user_id = client.get("/auth/me").json()["id"]
    with client.app.state.session_factory() as session:  # type: ignore[attr-defined]
        row = session.get(SettingRow, f"app:{user_id}")
        assert row is not None
        row.value = value
        session.commit()


def test_a_refused_value_takes_its_default_and_the_rest_is_kept(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    save_raw(
        client,
        json.dumps(
            {
                "fx_jpy_per_eur": 160,
                "vat_rate_percent": 150,
                "platform_fees": {
                    "ebay": {"percent": 9, "fixed_cents": 30},
                    # A platform since removed, and a rate out of bounds.
                    "depop": {"percent": 5},
                    "vinted": {"percent": 500},
                },
                "scanner": {
                    "enabled": True,
                    "sources": ["mercari", "jumble", "rakuma"],
                    "interval_minutes": 5,
                },
                "business": "nope",
            }
        ),
    )

    with caplog.at_level(logging.WARNING):
        settings = client.get("/settings").json()
        client.get("/settings")

    assert settings["fx_jpy_per_eur"] == 160
    assert settings["vat_rate_percent"] == 20
    assert settings["platform_fees"]["ebay"]["percent"] == 9
    assert "depop" not in settings["platform_fees"]
    assert settings["platform_fees"]["vinted"]["percent"] == 0
    assert (settings["scanner"]["enabled"], settings["scanner"]["sources"]) == (
        True,
        ["mercari", "rakuma"],
    )
    assert settings["scanner"]["interval_minutes"] == 60
    assert settings["business"]["declaration"] == "quarterly"
    # The account keeps working, and the damaged document is reported once.
    assert client.get("/tasks").status_code == 200
    assert len([r for r in caplog.records if "paramètres du compte" in r.getMessage()]) == 1


def test_an_unreadable_document_gives_the_defaults(client: TestClient) -> None:
    save_raw(client, "{not json")

    response = client.get("/settings")

    assert response.status_code == 200
    assert response.json()["fx_jpy_per_eur"] == 170
