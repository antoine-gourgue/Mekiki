"""Decides whether a Japanese listing title is the tracked card, from the title alone.

Marketplace searches are fuzzy: a query for a card also returns bulk lots, sleeves, graded
copies, foreign printings and other cards of the same set. Titles are normalised (NFKC turns
full-width letters, digits and slashes into ASCII) and then checked against the card number
and keyword lists.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass, field

# Dash-like characters Japanese sellers type in codes such as OP05-119: U+2010 to U+2015,
# the minus sign and the full-width hyphen-minus.
_DASH_CHARS = (*range(0x2010, 0x2016), 0x2212, 0xFF0D)
_DASHES = re.compile("[" + "".join(map(chr, _DASH_CHARS)) + "-]")
# The katakana long vowel mark (U+30FC) also stands in for a dash, but only inside a code:
# elsewhere it belongs to words such as マスターボール or スーパーパラレル.
_LONG_VOWEL_IN_CODE = re.compile("(?<=[a-z0-9])" + chr(0x30FC) + "(?=[0-9])")
_SPACES = re.compile(r"\s+")
# "205/187", "005 / 078": collector number over set size.
_NUMBER_OVER_TOTAL = re.compile(r"(?<!\d)(\d{1,3})\s*/\s*(\d{1,3})(?!\d)")
# One Piece and other code-based numbering: "OP05-119", "ST10-005", "EB01-061", "P-001".
_CODE_NUMBER = re.compile(r"(?<![a-z0-9])([a-z]{1,4}\d{0,2})-(\d{1,3})(?!\d)")

# Whole words only: "ars" (a Japanese grader) also hides inside "cards".
_GRADED = re.compile(r"(?<![a-z])(?:psa|bgs|cgc|ars)(?![a-z])|鑑定")
# Listings kept for one buyer ("〇〇様専用", "お取り置き", "売約済み") or whose seller refuses a
# purchase without a message first ("即購入不可"): a proxy's order would be cancelled.
_RESERVED = re.compile(r"専用|取り?置き?|売約|予約済|購入不可|購入禁止")


def normalize(text: str) -> str:
    """NFKC, lowercase, one kind of dash and single spaces."""
    text = unicodedata.normalize("NFKC", text).lower()
    text = _DASHES.sub("-", _LONG_VOWEL_IN_CODE.sub("-", text))
    return _SPACES.sub(" ", text).strip()


@dataclass(frozen=True, slots=True)
class CardNumber:
    """A collector number in one of the two shapes printed on cards."""

    prefix: str | None  # "op05" for code numbers, None for number-over-total
    number: int
    total: int | None = None

    @classmethod
    def parse(cls, raw: str | None) -> CardNumber | None:
        if not raw:
            return None
        text = normalize(raw)
        if match := _NUMBER_OVER_TOTAL.search(text):
            return cls(prefix=None, number=int(match[1]), total=int(match[2]))
        if match := _CODE_NUMBER.search(text):
            return cls(prefix=match[1], number=int(match[2]))
        if text.isdigit():
            return cls(prefix=None, number=int(text))
        return None

    def found_in(self, normalized_title: str) -> bool:
        if self.prefix is not None:
            return any(
                prefix == self.prefix and int(number) == self.number
                for prefix, number in _CODE_NUMBER.findall(normalized_title)
            )
        return any(
            int(number) == self.number and (self.total is None or int(total) == self.total)
            for number, total in _NUMBER_OVER_TOTAL.findall(normalized_title)
        )


def split_keywords(raw: str | None) -> tuple[str, ...]:
    """Keywords typed by the user, separated by spaces or commas (full-width ones too)."""
    if not raw:
        return ()
    return tuple(k for k in re.split(r"[\s,、]+", normalize(raw)) if k)


@dataclass(frozen=True, slots=True)
class MatchRule:
    card_number: CardNumber | None = None
    required: tuple[str, ...] = ()
    excluded: tuple[str, ...] = ()
    # A graded card ("PSA 10") is a different product: graded listings only match when the
    # tracked card itself is graded, and then only with that grade.
    grading: str | None = None
    global_excluded: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class MatchResult:
    matched: bool
    reason: str | None = None


def match_title(title: str, rule: MatchRule) -> MatchResult:
    text = normalize(title)
    compact = text.replace(" ", "")

    if reserved := _RESERVED.search(compact):
        return MatchResult(False, f"annonce réservée ({reserved[0]})")
    for keyword in (*rule.excluded, *rule.global_excluded):
        if keyword in text or keyword.replace(" ", "") in compact:
            return MatchResult(False, f"mot exclu : {keyword}")
    for keyword in rule.required:
        if keyword not in text and keyword.replace(" ", "") not in compact:
            return MatchResult(False, f"mot manquant : {keyword}")

    if rule.grading:
        wanted = normalize(rule.grading).replace(" ", "")
        if wanted not in compact:
            return MatchResult(False, f"gradation absente : {rule.grading}")
    elif _GRADED.search(text):
        return MatchResult(False, "carte gradée")

    if rule.card_number is not None and not rule.card_number.found_in(text):
        return MatchResult(False, "numéro de carte absent")
    return MatchResult(True)


def build_rule(
    *,
    card_number: str | None,
    required: str | None,
    excluded: str | None,
    grading: str | None,
    global_excluded: Iterable[str] = (),
) -> MatchRule:
    return MatchRule(
        card_number=CardNumber.parse(card_number),
        required=split_keywords(required),
        excluded=split_keywords(excluded),
        grading=grading or None,
        global_excluded=tuple(normalize(k) for k in global_excluded if k.strip()),
    )
