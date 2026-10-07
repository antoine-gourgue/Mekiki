from mekiki_engine.domain import Game
from mekiki_engine.scanner.identify import identify


def test_pokemon_title_with_set_code_and_number() -> None:
    card = identify("リザードンex SAR SV2a 201/165 ポケモンカード151", Game.POKEMON)

    assert (card.set_code, card.number, card.total, card.rarity) == ("sv2a", 201, 165, "sar")
    assert card.identified
    assert not card.graded


def test_pokemon_full_width_and_no_set_code() -> None:
    card = identify("ピカチュウ ＡＲ ０９８／０７１ 美品", Game.POKEMON)

    assert (card.set_code, card.number, card.total, card.rarity) == (None, 98, 71, "ar")
    # The set size alone can still pin the set down later.
    assert card.identified


def test_pokemon_codes_of_older_and_mega_eras() -> None:
    assert identify("リザードンVSTAR SAR（S12a 212/172）", Game.POKEMON).set_code == "s12a"
    assert identify("メガリザードンX ex MUR M2a 250/193", Game.POKEMON).set_code == "m2a"
    assert identify("リーリエの全力 SR SM11b 068/049", Game.POKEMON).set_code == "sm11b"


def test_titles_with_several_cards_are_not_identified() -> None:
    card = identify("リザードン 201/165 フシギバナ 200/165 セット", Game.POKEMON)

    assert card.number is None
    assert not card.identified


def test_graded_cards_are_flagged() -> None:
    assert identify("リザードンex 201/165psa10", Game.POKEMON).graded
    assert identify("リザードン 鑑定品 201/165", Game.POKEMON).graded
    assert not identify("Pokemon cards リザードン 201/165", Game.POKEMON).graded


def test_dates_are_not_card_numbers() -> None:
    assert identify("2024/10 発売 ピカチュウ", Game.POKEMON).number is None


def test_one_piece_code_and_versions() -> None:
    manga = identify("ワンピースカード ルフィ OP05ー119 コミパラ", Game.ONE_PIECE)
    assert (manga.code, manga.parallel, manga.manga) == ("op05-119", True, True)

    parallel = identify("ナミ SR パラレル OP01-016", Game.ONE_PIECE)
    assert (parallel.code, parallel.parallel, parallel.manga, parallel.rarity) == (
        "op01-016",
        True,
        False,
        "sr",
    )

    normal = identify("ゾロ リーダー ST01-001", Game.ONE_PIECE)
    assert (normal.code, normal.parallel) == ("st01-001", False)
    assert identify("プロモ P-001 ルフィ", Game.ONE_PIECE).code == "p-001"


def test_one_piece_bundles_are_not_identified() -> None:
    assert identify("OP05-119 OP05-118 セット", Game.ONE_PIECE).code is None
