from conftest import FakeMarketplace
from fastapi.testclient import TestClient

from mekiki_engine.domain import Game, SourcePlatform
from mekiki_engine.scanner import names
from mekiki_engine.scanner.names import Name, NameBook, key, parse_species

SPECIES = """pokemon_species_id,local_language_id,name,genus
6,1,リザードン,かえんポケモン
6,5,Dracaufeu,Pokémon Flamme
6,9,Charizard,Flame Pokémon
25,1,ピカチュウ,ねずみポケモン
25,5,Pikachu,Pokémon Souris
25,9,Pikachu,Mouse Pokémon
37,1,ロコン,きつねポケモン
37,5,Goupix,Pokémon Renard
37,9,Vulpix,Fox Pokémon
122,1,バリヤード,バリヤーポケモン
122,5,M. Mime,Pokémon Bloqueur
122,9,Mr. Mime,Barrier Pokémon
"""


def pokemon_book() -> NameBook:
    return NameBook(
        (typed, Name(ja=row["ja"], en=row["en"]))
        for row in parse_species(SPECIES).values()
        for language in ("en", "fr")
        if (typed := row.get(language))
    )


def test_french_and_english_names_become_japanese() -> None:
    book = pokemon_book()

    assert book.translate("Dracaufeu ex 201/165", "ja") == "リザードンex 201/165"
    assert book.translate("charizard EX", "ja") == "リザードンex"
    assert book.translate("Goupix d'Alola", "ja") == "アローラロコン"
    assert book.translate("Alolan Vulpix V", "ja") == "アローラロコンV"
    assert book.translate("M. Mime", "ja") == "バリヤード"
    assert book.translate("Méga Dracaufeu", "en") == "Mega Charizard"
    assert book.translate("Dracaufeu", "en") == "Charizard"


def test_unknown_or_japanese_text_is_left_alone() -> None:
    book = pokemon_book()

    assert book.translate("Carte mystère", "ja") is None
    assert book.translate("リザードン", "ja") is None
    assert key("Pokémon M. Mime") == "pokemon m mime"


def test_one_piece_characters_are_spelled_out(client: TestClient) -> None:
    with client.app.state.session_factory() as session:  # type: ignore[attr-defined]
        assert names.translate(session, Game.ONE_PIECE, "Luffy OP05-119", "ja") == "ルフィ OP05-119"
        assert names.translate(session, Game.ONE_PIECE, "Barbe Blanche", "ja") == "ニューゲート"
        assert names.translate(session, Game.ONE_PIECE, "Monkey D. Luffy", "en") == "Luffy"


def test_pokemon_names_are_downloaded_once(client: TestClient) -> None:
    app = client.app  # type: ignore[attr-defined]
    with app.state.session_factory() as session:
        assert names.refresh(session, app.state.http) is None
        assert names.species_count(session) == 4
        assert names.translate(session, Game.POKEMON, "Pikachu", "ja") == "ピカチュウ"
        # Fresh names are not downloaded again.
        assert names.refresh(session, app.state.http) is None


def test_french_names_find_the_catalog_and_japanese_printings_come_first(
    client: TestClient,
) -> None:
    client.post("/cardmarket/refresh", json={})

    products = client.get("/cardmarket/products", params={"q": "Dracaufeu"}).json()

    assert {p["id_product"] for p in products} >= {719448, 719654}
    assert products[0]["japanese"] is True


def test_one_off_searches_go_out_in_japanese(
    client: TestClient, marketplace: FakeMarketplace
) -> None:
    response = client.post(
        "/search", json={"query": "Dracaufeu ex 201/165", "game": "pokemon", "sources": ["mercari"]}
    ).json()

    assert response["searched_query"] == "リザードンex 201/165"
    assert marketplace.queries == [(SourcePlatform.MERCARI, "リザードンex 201/165")]
