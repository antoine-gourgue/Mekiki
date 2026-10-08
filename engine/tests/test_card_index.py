from conftest import FakeMarketplace, tcgdex_archive
from fastapi.testclient import TestClient
from sqlalchemy import select

from mekiki_engine.domain import Game
from mekiki_engine.models import CardIndexEntry
from mekiki_engine.scanner import card_index
from mekiki_engine.scanner.identify import identify
from mekiki_engine.scanner.resolver import CatalogResolver


def test_archive_parsing_keeps_japanese_cards_and_their_printings() -> None:
    cards = card_index.parse_archive(tcgdex_archive())

    by_product = {card.id_product: card for card in cards}
    assert set(by_product) == {719442, 837230, 837231, 719448, 719654}
    charizard = by_product[719654]
    assert (charizard.set_code, charizard.number, charizard.set_total) == ("sv2a", 201, 165)
    assert (charizard.rarity, charizard.name, charizard.variant) == ("SAR", "リザードンex", "holo")
    assert charizard.set_name == "ポケモンカード151"
    assert by_product[837231].variant == "reverse-masterball"


def test_refresh_builds_the_index_once_a_week(client: TestClient) -> None:
    statuses = client.post("/cardmarket/refresh", json={}).json()

    pokemon = next(s for s in statuses if s["game"] == "pokemon")
    # Five cards from TCGdex, three linked through TCGplayer (see below).
    assert pokemon["indexed_cards"] == 8
    assert pokemon["index_error"] is None
    with client.app.state.session_factory() as session:  # type: ignore[attr-defined]
        # Fresh index: nothing is downloaded again before a week.
        assert card_index.refresh(session, client.app.state.http) is None  # type: ignore[attr-defined]
        assert card_index.indexed_count(session) == 8


def test_titles_resolve_to_the_right_printing(client: TestClient) -> None:
    client.post("/cardmarket/refresh", json={})
    with client.app.state.session_factory() as session:  # type: ignore[attr-defined]
        resolver = CatalogResolver(session)

        def product(title: str) -> int | None:
            resolution = resolver.resolve(identify(title, Game.POKEMON))
            return resolution.product.id_product if resolution else None

        assert product("リザードンex SAR SV2a 201/165") == 719654
        assert product("リザードンex RR 006/165") == 719448
        # Only the regular printing is priced in the fake price guide; mirrors are not.
        assert product("フシギダネ 001/165 マスターボールミラー") is None
        assert product("リザードン 201/999") is None


def test_an_index_built_by_an_older_version_is_rebuilt(client: TestClient) -> None:
    client.post("/cardmarket/refresh", json={})
    with client.app.state.session_factory() as session:  # type: ignore[attr-defined]
        state = card_index._load_state(session)
        card_index._save_state(session, {**state, "format": None})
        assert card_index.needs_rebuild(session)

        assert card_index.refresh(session, client.app.state.http) is None  # type: ignore[attr-defined]

        assert not card_index.needs_rebuild(session)
        assert card_index.indexed_count(session) == 8


def test_sets_missing_from_tcgdex_are_linked_through_tcgplayer(client: TestClient) -> None:
    client.post("/cardmarket/refresh", json={})
    with client.app.state.session_factory() as session:  # type: ignore[attr-defined]
        rows = session.scalars(
            select(CardIndexEntry)
            .where(CardIndexEntry.set_code == "s6a")
            .order_by(CardIndexEntry.number)
        ).all()

        # Number order, product order and price order agree for Pikachu V, not for Leafeon V.
        assert [(row.number, row.id_product, row.rarity) for row in rows] == [
            (47, 565900, "RR"),
            (84, 566300, "SR"),
            (85, 566301, "SR"),
        ]
        assert {(row.name, row.set_name, row.set_total) for row in rows} == {
            ("ピカチュウV", "イーブイヒーローズ", 69)
        }
        resolution = CatalogResolver(session).resolve(
            identify("ピカチュウV SR 強化拡張パック イーブイヒーローズ 085/069", Game.POKEMON)
        )
        assert resolution is not None
        assert resolution.product.id_product == 566301


def test_tcgplayer_down_leaves_the_tcgdex_index(
    client: TestClient, marketplace: FakeMarketplace
) -> None:
    marketplace.tcgcsv_down = True

    statuses = client.post("/cardmarket/refresh", json={}).json()

    pokemon = next(s for s in statuses if s["game"] == "pokemon")
    assert pokemon["indexed_cards"] == 5
    assert pokemon["index_error"].startswith(
        "Index des cartes Pokémon : extensions complétées par TCGplayer indisponibles"
    )
