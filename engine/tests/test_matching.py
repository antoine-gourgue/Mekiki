import pytest

from mekiki_engine.scanner.matching import CardNumber, build_rule, match_title, normalize

GLOBAL = ("まとめ", "オリパ", "英語")


def rule(card_number: str | None = "205/187", **kwargs: str | None):
    return build_rule(
        card_number=card_number,
        required=kwargs.get("required"),
        excluded=kwargs.get("excluded"),
        grading=kwargs.get("grading"),
        global_excluded=GLOBAL,
    )


def test_normalize_folds_full_width_and_dashes() -> None:
    assert normalize("ＳＶ８ａ　２０５／１８７") == "sv8a 205/187"
    assert normalize("OP05－119 ルフィ") == "op05-119 ルフィ"
    assert normalize("OP05ー119") == "op05-119"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("205/187", CardNumber(None, 205, 187)),
        ("005 / 078", CardNumber(None, 5, 78)),
        ("OP05-119", CardNumber("op05", 119)),
        ("ST10-005", CardNumber("st10", 5)),
        ("P-001", CardNumber("p", 1)),
        ("42", CardNumber(None, 42)),
        ("", None),
        (None, None),
    ],
)
def test_card_number_parsing(raw: str | None, expected: CardNumber | None) -> None:
    assert CardNumber.parse(raw) == expected


def test_matches_the_card_number_in_any_width() -> None:
    assert match_title("ピカチュウex SAR ２０５／１８７ テラスタルフェス", rule()).matched
    assert match_title("ピカチュウex SAR 205 / 187 美品", rule()).matched


def test_rejects_another_card_of_the_same_set() -> None:
    result = match_title("イーブイex SAR 206/187", rule())
    assert not result.matched
    assert result.reason == "numéro de carte absent"


def test_number_without_total_matches_any_total() -> None:
    assert match_title("リザードン 201/165", rule("201")).matched


def test_one_piece_codes_with_odd_dashes() -> None:
    luffy = rule("OP05-119")
    assert match_title("ワンピースカード ルフィ OP05ー119 コミパラ", luffy).matched
    assert not match_title("ルフィ OP05-118", luffy).matched
    assert not match_title("ルフィ OP06-119", luffy).matched


def test_global_and_card_exclusions() -> None:
    assert match_title("SAR 205/187 まとめ売り", rule()).reason == "mot exclu : まとめ"
    assert not match_title("205/187 オリパ", rule()).matched
    assert not match_title("ピカチュウ 205/187 英語版", rule()).matched
    assert not match_title("205/187 傷あり", rule(excluded="傷")).matched


def test_required_keywords_split_parallels_apart() -> None:
    comic = rule("OP05-119", required="コミパラ")
    assert match_title("ルフィ OP05-119 コミパラ", comic).matched
    assert match_title("ルフィ OP05-119 コミ パラ", comic).matched
    assert not match_title("ルフィ OP05-119 パラレル", comic).matched


def test_graded_listings_only_match_graded_cards() -> None:
    assert match_title("ピカチュウ 205/187 PSA10", rule()).reason == "carte gradée"
    assert not match_title("ピカチュウ 205/187 鑑定品", rule()).matched
    assert match_title("Pokemon cards ピカチュウ 205/187", rule()).matched

    psa10 = rule(grading="PSA 10")
    assert match_title("ピカチュウ 205/187 PSA10", psa10).matched
    assert match_title("ピカチュウ 205/187 ＰＳＡ １０", psa10).matched
    assert not match_title("ピカチュウ 205/187 PSA9", psa10).matched


def test_no_card_number_relies_on_keywords_only() -> None:
    assert match_title("なんでも SAR", rule(None, required="sar")).matched


@pytest.mark.parametrize(
    "title",
    [
        "リザードンex 205/187 ボブ様専用",
        "リザードンex 205/187 お取り置き中",
        "リザードンex 205/187 売約済み",
        "リザードンex 205/187 即購入不可",
    ],
)
def test_reserved_listings_are_rejected(title: str) -> None:
    result = match_title(title, rule())

    assert not result.matched
    assert result.reason and result.reason.startswith("annonce réservée")
