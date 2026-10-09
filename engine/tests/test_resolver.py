from fastapi.testclient import TestClient

from mekiki_engine.domain import Game
from mekiki_engine.models import CardIndexEntry, CardmarketProduct
from mekiki_engine.scanner.identify import identify
from mekiki_engine.scanner.resolver import CatalogResolver

# (set code, Japanese set name, number, set total, rarity, Japanese card name); each card is
# its own product.
CARDS = [
    ("sv2d", "クレイバースト", 74, 71, None, "ライチュウ"),
    ("sv2p", "スノーハザード", 74, 71, None, "コオリッポ"),
    ("m6", "ストームエメラルダ", 53, 76, "Common", "ジバコイル"),
    ("m6", "ストームエメラルダ", 112, 76, "MUR", "ヒガナの信頼"),
    ("m1l", "メガブレイブ", 89, 63, "SAR", "メガアブソルex"),
    ("sv5k", "ワイルドフォース", 95, 71, "SAR", "タケルライコex"),
    # The index often leaves secret rares without a rarity: above the set's size, it fits.
    ("sv8a", "テラスタルフェスex", 222, 187, None, "タケルライコex"),
    ("sv8", "超電ブレイカー", 132, 106, "SAR", "ピカチュウex"),
    ("s12a", "VSTARユニバース", 260, 172, "UR", "オリジンディアルガVSTAR"),
    ("s-p", None, 86, 0, "Promo", "マリィ"),
]


def resolver(client: TestClient) -> CatalogResolver:
    session = client.app.state.session_factory()  # type: ignore[attr-defined]
    for index, (set_code, set_name, number, total, rarity, name) in enumerate(CARDS, start=1):
        session.add(
            CardmarketProduct(id_product=index, game="pokemon", name=name, avg30_cents=2000)
        )
        session.add(
            CardIndexEntry(
                game="pokemon",
                set_code=set_code,
                set_name=set_name,
                number=number,
                id_product=index,
                set_total=total or None,
                rarity=rarity,
                name=name,
            )
        )
    session.commit()
    return CatalogResolver(session)


def label(catalog: CatalogResolver, title: str) -> str | None:
    resolution = catalog.resolve(identify(title, Game.POKEMON))
    return resolution.label if resolution else None


def test_the_name_settles_sets_of_the_same_size(client: TestClient) -> None:
    catalog = resolver(client)

    assert label(catalog, "Pokémon.ライチュウ 074/071 AR") == "SV2d 074/071"
    assert label(catalog, "コオリッポ 074/071") == "SV2p 074/071"
    assert label(catalog, "ピカチュウ 074/071") is None


def test_an_older_card_of_the_same_size_is_not_taken_for_a_recent_one(
    client: TestClient,
) -> None:
    catalog = resolver(client)

    assert label(catalog, "ヒガナの信頼 SAR 112/076 154") == "M6 112/076 · MUR"
    # A Black & White card numbered over 76: M6 is the only indexed set of that size.
    assert label(catalog, "ディアルガEX R BW 拡張パック「メガロキャノン」 キラ 053/076") is None


def test_a_title_without_a_number_is_read_by_name_and_rarity(client: TestClient) -> None:
    catalog = resolver(client)

    resolution = catalog.resolve(
        identify("メガアブソルex SAR MEGA 拡張パック メガブレイブ キラ 089/0…", Game.POKEMON)
    )
    assert resolution is not None
    assert resolution.label == "M1l 089/063 · SAR"
    assert resolution.confidence == "medium"
    assert label(catalog, "ポケモンカード ピカチュウex SAR") == "SV8 132/106 · SAR"
    # Two SAR printings of this name and no set named: no guess.
    assert label(catalog, "タケルライコex SAR") is None
    # The rarity must follow the name, or it may be another card's.
    assert label(catalog, "ピカチュウex 30th おまけ SAR") is None
    # "そらをとぶピカチュウex" would be another card than "ピカチュウex".
    assert label(catalog, "そらをとぶピカチュウex SAR") is None


def test_the_set_named_in_the_title_settles_the_printing(client: TestClient) -> None:
    catalog = resolver(client)

    assert label(catalog, "タケルライコex SAR ワイルドフォース") == "SV5k 095/071 · SAR"
    # Titles cut by the seller's listing tool keep only the start of the set's name.
    assert (
        label(catalog, "タケルライコex SAR スカーレット&バイオレット 拡張パック ワイルドフォ…")
        == "SV5k 095/071 · SAR"
    )
    assert label(catalog, "タケルライコex SAR テラスタルフェスex") == "SV8a 222/187"


def test_older_eras_need_the_set_to_be_read_by_name(client: TestClient) -> None:
    catalog = resolver(client)

    # Time Gazer (S10d) has an Origin Dialga VSTAR UR too, and the index lacks that set.
    assert label(catalog, "ポケモンカード オリジンディアルガVSTAR UR") is None
    assert label(catalog, "オリジンディアルガVSTAR UR S12a VSTARユニバース") == "S12a 260/172 · UR"
    assert label(catalog, "オリジンディアルガVSTAR UR VSTARユニバース") == "S12a 260/172 · UR"


def test_promos_are_numbered_over_their_promo_set(client: TestClient) -> None:
    catalog = resolver(client)

    assert (
        label(catalog, "ポケモンカード マリィ プロモ 086/S-P おまけポフィン") == "S-P 086 · Promo"
    )


def test_a_card_linked_to_a_chinese_printing_is_not_priced_by_it(client: TestClient) -> None:
    catalog = resolver(client)
    product = catalog.session.get(CardmarketProduct, 3)
    assert product is not None
    product.expansion_name = "30th Celebration Simplified Chinese"
    catalog.session.commit()

    assert label(catalog, "ジバコイル 053/076 ストームエメラルダ") is None
