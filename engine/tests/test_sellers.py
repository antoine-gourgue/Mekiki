from dataclasses import replace

import pytest
from conftest import FakeMarketplace
from fastapi.testclient import TestClient
from test_discovery import LISTINGS, discover, index_pokemon_cards

from mekiki_engine.domain import SourcePlatform
from mekiki_engine.scanner.sellers import seller_problem

GOOD_SELLER = {"id": 7, "num_ratings": 1507, "ratings": {"good": 1506, "bad": 1}}


@pytest.mark.parametrize(
    "description",
    [
        "代行業者様のご購入はお断りしております。",
        "転送業者NGです",
        "海外からのご購入はご遠慮ください",
        "業者お断り",
        "購入代行サービスでのご購入はできません",
    ],
)
def test_sellers_refusing_proxies_are_seen(description: str) -> None:
    problem = seller_problem({"description": description, "seller": GOOD_SELLER})

    assert problem is not None
    assert problem.startswith("refuse les achats par un intermédiaire")


@pytest.mark.parametrize(
    "description",
    ["海外発送不可です", "配送業者の指定はできません", "即購入OK、プレイ用でお願いします"],
)
def test_other_restrictions_are_no_refusal(description: str) -> None:
    assert seller_problem({"description": description, "seller": GOOD_SELLER}) is None


def test_ratings_and_suspended_accounts() -> None:
    def seller(**fields: object) -> dict[str, object]:
        return {"description": "", "seller": fields}

    assert seller_problem(seller(num_ratings=100, ratings={"bad": 10})) == (
        "trop d'évaluations négatives (10 sur 100)"
    )
    # One bad rating out of two says little.
    assert seller_problem(seller(num_ratings=2, ratings={"bad": 1})) is None
    assert seller_problem(seller(is_inactive=True)) == "compte du vendeur suspendu ou inactif"


def test_a_blocked_seller_is_left_out_of_discoveries(
    client: TestClient, marketplace: FakeMarketplace
) -> None:
    index_pokemon_cards(client)
    marketplace.listings[SourcePlatform.MERCARI] = [
        replace(LISTINGS[0], seller_id="42"),
        *LISTINGS[1:],
    ]
    blocked = client.post(
        "/sellers/blocked", json={"source": "mercari", "external_id": "m1", "seller_id": "42"}
    )

    run = discover(client, budget_cents=15000, card_count=2, min_roi_percent=10)

    assert blocked.status_code == 201
    assert "m1" not in [pick["external_id"] for pick in run["picks"]]
    assert any("1 annonce d'un vendeur bloqué par Neokyo" in line["text"] for line in run["log"])


def test_a_seller_refusing_proxies_gives_up_its_place_and_is_remembered(
    client: TestClient, marketplace: FakeMarketplace
) -> None:
    index_pokemon_cards(client)
    # Item ids as Mercari writes them: the check refuses others.
    marketplace.listings[SourcePlatform.MERCARI] = [
        replace(listing, external_id=f"m100000{index}") for index, listing in enumerate(LISTINGS)
    ]
    marketplace.item_details["m1000000"] = {
        "description": "代行業者様のご購入はお断りします",
        "seller": {"id": 99, "num_ratings": 50, "ratings": {"bad": 0}},
    }

    run = discover(client, budget_cents=15000, card_count=2, min_roi_percent=10)

    assert [pick["external_id"] for pick in run["picks"]] == ["m1000001"]
    assert any("vendeur à éviter, refuse les achats" in line["text"] for line in run["log"])
    blocked = client.get("/sellers/blocked").json()
    assert [(row["seller_id"], row["source"]) for row in blocked] == [("99", "mercari")]


def test_a_seller_is_blocked_from_its_listing_and_unblocked(
    client: TestClient, marketplace: FakeMarketplace
) -> None:
    marketplace.item_details["m1234567"] = {"seller": {"id": 5}}

    blocked = client.post("/sellers/blocked", json={"source": "mercari", "external_id": "m1234567"})
    unknown = client.post("/sellers/blocked", json={"source": "rakuma", "external_id": "x"})
    client.delete("/sellers/blocked/mercari/5")

    assert (blocked.status_code, blocked.json()["seller_id"]) == (201, "5")
    assert blocked.json()["reason"] == "bloqué par Neokyo"
    assert unknown.status_code == 422
    assert client.get("/sellers/blocked").json() == []


RAKUMA_ITEM = "0123456789abcdef0123456789abcdef"
RAKUMA_SHOP = "5507d4dd830da1c486defe12789d8bf4"


def test_rakuma_listings_name_their_seller_and_their_ratings(
    client: TestClient, marketplace: FakeMarketplace
) -> None:
    marketplace.rakuma_sellers[RAKUMA_ITEM] = (RAKUMA_SHOP, 90, 5, 6)

    checked = client.get(f"/listings/rakuma/{RAKUMA_ITEM}/availability").json()

    assert checked["seller_id"] == RAKUMA_SHOP
    assert checked["seller_warning"] == "trop d'évaluations négatives (6 sur 101)"


def test_a_rakuma_seller_is_blocked_from_their_listing(
    client: TestClient, marketplace: FakeMarketplace
) -> None:
    marketplace.rakuma_sellers[RAKUMA_ITEM] = (RAKUMA_SHOP, 12, 0, 0)

    blocked = client.post(
        "/sellers/blocked",
        json={"source": "rakuma", "external_id": RAKUMA_ITEM, "reason": "bloqué par Neokyo"},
    )

    assert blocked.status_code == 201
    assert blocked.json()["seller_id"] == RAKUMA_SHOP


def test_a_blocked_rakuma_seller_is_found_on_the_parcel_check(
    client: TestClient, marketplace: FakeMarketplace
) -> None:
    index_pokemon_cards(client)
    # Rakuma's results do not name the seller: the parcel's check reads it on the page.
    marketplace.listings[SourcePlatform.RAKUMA] = [
        replace(LISTINGS[0], source=SourcePlatform.RAKUMA, external_id=RAKUMA_ITEM),
        replace(LISTINGS[1], source=SourcePlatform.RAKUMA, external_id="f" * 32),
    ]
    marketplace.rakuma_sellers[RAKUMA_ITEM] = (RAKUMA_SHOP, 12, 0, 0)
    client.post(
        "/sellers/blocked",
        json={
            "source": "rakuma",
            "external_id": RAKUMA_ITEM,
            "seller_id": RAKUMA_SHOP,
            "reason": "bloqué par Neokyo",
        },
    )

    run = discover(client, budget_cents=15000, card_count=2, min_roi_percent=10, sources=["rakuma"])

    assert [pick["external_id"] for pick in run["picks"]] == ["f" * 32]
    [blocked] = run["blocked"]
    assert (blocked["external_id"], blocked["blocked_reason"]) == (RAKUMA_ITEM, "bloqué par Neokyo")
