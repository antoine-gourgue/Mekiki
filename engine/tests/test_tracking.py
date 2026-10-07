from typing import Any

from conftest import FakeMarketplace
from fastapi.testclient import TestClient
from test_scanner_api import mercari, scan

from mekiki_engine.domain import Game, SourcePlatform
from mekiki_engine.scanner.identify import identify
from mekiki_engine.scanner.tracking import Printing, is_printing, printing_queries

# The fake card index: SV2a 001 (normal 719442, Poké Ball mirror 837230, Master Ball
# mirror 837231), 006 (719448) and 201 (719654).
CHARIZARD_SAR = 719654
BULBASAUR = 719442
BULBASAUR_MASTER_BALL = 837231


def template(client: TestClient, product_id: int) -> dict[str, Any]:
    response = client.get("/tracked-cards/template", params={"product_id": product_id})
    assert response.status_code == 200, response.text
    return response.json()  # type: ignore[no-any-return]


def test_a_product_is_tracked_with_its_japanese_name_and_number(client: TestClient) -> None:
    client.post("/cardmarket/refresh", json={})

    sar = template(client, CHARIZARD_SAR)

    assert sar["name"] == "リザードンex"
    assert sar["card_number"] == "201/165"
    assert sar["search_query"] == "リザードンex 201/165"
    assert sar["japanese"] is True
    assert sar["label"].startswith("SV2A 201/165")
    assert client.get("/tracked-cards/template", params={"product_id": 1}).status_code == 404


def test_listings_must_name_the_exact_printing() -> None:
    sar = Printing(game=Game.POKEMON, set_code="sv2a", number=201, total=165)
    master_ball = Printing(
        game=Game.POKEMON, set_code="sv2a", number=1, total=165, mirror="masterball"
    )

    def matches(printing: Printing, title: str) -> bool:
        return is_printing(printing, identify(title, Game.POKEMON))

    assert matches(sar, "リザードンex SAR 201/165 sv2a")
    assert matches(sar, "リザードンex 201/165")
    assert not matches(sar, "リザードンex 006/165")
    assert not matches(sar, "リザードンex 201/165 4枚セット")
    assert not matches(sar, "リザードンex 201/165 sv3")
    assert matches(master_ball, "フシギダネ 001/165 マスターボールミラー")
    assert not matches(master_ball, "フシギダネ 001/165")
    assert not matches(master_ball, "フシギダネ 001/165 モンスターボールミラー")


def test_one_piece_versions_are_told_apart() -> None:
    parallel = Printing(game=Game.ONE_PIECE, code="op05-119", version="parallel")
    regular = Printing(game=Game.ONE_PIECE, code="op05-119", version="regular")

    def matches(printing: Printing, title: str) -> bool:
        return is_printing(printing, identify(title, Game.ONE_PIECE))

    assert matches(parallel, "ルフィ OP05-119 パラレル")
    assert not matches(parallel, "ルフィ OP05-119")
    assert not matches(parallel, "ルフィ OP05-119 コミパラ")
    assert matches(regular, "ルフィ OP05-119 SEC")
    assert printing_queries(parallel) == ["OP05-119 パラレル", "OP05-119"]


def test_a_scan_keeps_only_the_tracked_printing(
    client: TestClient, marketplace: FakeMarketplace
) -> None:
    client.post("/cardmarket/refresh", json={})
    client.post(
        "/tracked-cards",
        json={
            "game": "pokemon",
            "name": "Dracaufeu ex SAR",
            "cardmarket_product_id": CHARIZARD_SAR,
        },
    )
    marketplace.listings[SourcePlatform.MERCARI] = [
        mercari("m1", "リザードンex SAR 201/165 美品", 30000),
        mercari("m2", "リザードンex RR 006/165", 3000),
        mercari("m3", "リザードンex 201/165 PSA10", 90000),
        mercari("m4", "リザードンex 201/165 2枚", 50000),
    ]

    status = scan(client)

    assert status["new_listings"] == 1
    assert [d["external_id"] for d in client.get("/deals").json()] == ["m1"]
    queries = [query for _platform, query in marketplace.queries]
    assert queries[:2] == ["リザードンex 201/165", "sv2a 201/165"]
