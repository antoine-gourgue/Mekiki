"""Reads which card a Japanese listing title is about: set code, number, rarity, version.

Sellers write titles like "リザードンex SAR SV2a 201/165 ポケモンカード151" or
"ルフィ OP05-119 コミパラ"; everything is normalised first (see ``matching.normalize``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from mekiki_engine.domain import Game
from mekiki_engine.scanner.matching import normalize

# Pokémon set codes printed on Japanese cards: sv2a, s12a, sm12a, m2a, cp6, xy11, bw8…
_POKEMON_SET = re.compile(
    r"(?<![a-z0-9])(sv\d{1,2}[a-z]?|sm\d{1,2}[a-z+]?|s\d{1,2}[a-z]?|m\d{1,2}[a-z]?|"
    r"cp\d{1,2}|xy\d{1,2}[a-z]?|bw\d{1,2}[a-z]?)(?![a-z0-9])"
)
_NUMBER_OVER_TOTAL = re.compile(r"(?<!\d)(\d{1,3})\s*/\s*(\d{2,3})(?!\d)")
# One Piece codes: OP05-119, ST10-005, EB01-061, PRB01-001, P-001.
_ONE_PIECE_CODE = re.compile(r"(?<![a-z0-9])((?:op|st|eb|prb)\d{2}|p)-(\d{3})(?!\d)")

POKEMON_RARITIES = (
    "sar",
    "sr",
    "ar",
    "ur",
    "mur",
    "chr",
    "csr",
    "hr",
    "ssr",
    "ace",
    "rrr",
    "rr",
    "ma",
)
ONE_PIECE_RARITIES = ("sec", "sp", "sr", "l", "r")
_RARITY = re.compile(
    r"(?<![a-z])("
    + "|".join(sorted({*POKEMON_RARITIES, *ONE_PIECE_RARITIES}, key=len, reverse=True))
    + r")(?![a-z])"
)
# Manga ("comic") parallels are by far the most expensive One Piece version.
_MANGA = re.compile(r"コミパラ|コミック|マンガ|漫画|manga|スーパーパラレル")
_PARALLEL = re.compile(r"パラレル|パラ(?![a-z])|parallel")
_GRADED = re.compile(r"(?<![a-z])(?:psa|bgs|cgc|ars)(?![a-z])|鑑定")
# Mirror ("reverse") printings of the same number are separate Cardmarket products.
_MIRRORS = (
    ("マスターボール", "masterball"),
    ("モンスターボール", "pokeball"),
    ("ラブボール", "loveball"),
    ("クイックボール", "quickball"),
    ("ミラー", "reverse"),
)
# "4枚", "10枚": several copies in one listing.
_QUANTITY = re.compile(r"(?<!\d)(\d{1,3})\s*枚")


@dataclass(frozen=True, slots=True)
class CardIdentity:
    game: Game
    set_code: str | None = None
    number: int | None = None
    total: int | None = None
    # One Piece: "op05-119".
    code: str | None = None
    rarity: str | None = None
    parallel: bool = False
    manga: bool = False
    graded: bool = False
    several_copies: bool = False
    # Pokémon mirror printing named in the title: "masterball", "pokeball", "reverse"…
    mirror: str | None = None

    @property
    def identified(self) -> bool:
        if self.several_copies:
            return False
        if self.game is Game.ONE_PIECE:
            return self.code is not None
        return self.number is not None and (self.set_code is not None or self.total is not None)


def identify(title: str, game: Game) -> CardIdentity:
    text = normalize(title)
    rarity_match = _RARITY.search(text)
    rarity = rarity_match[1] if rarity_match else None
    graded = _GRADED.search(text) is not None
    several_copies = any(int(count) > 1 for count in _QUANTITY.findall(text))

    if game is Game.ONE_PIECE:
        codes = {f"{prefix}-{number}" for prefix, number in _ONE_PIECE_CODE.findall(text)}
        manga = _MANGA.search(text) is not None
        return CardIdentity(
            game=game,
            # Two different codes in one title means a bundle or a comparison: not one card.
            code=codes.pop() if len(codes) == 1 else None,
            rarity=rarity,
            parallel=manga or _PARALLEL.search(text) is not None,
            manga=manga,
            graded=graded,
            several_copies=several_copies,
        )

    sets = set(_POKEMON_SET.findall(text))
    numbers = {(int(n), int(t)) for n, t in _NUMBER_OVER_TOTAL.findall(text)}
    number = total = None
    if len(numbers) == 1:
        number, total = numbers.pop()
    return CardIdentity(
        game=game,
        set_code=sets.pop() if len(sets) == 1 else None,
        number=number,
        total=total,
        rarity=rarity,
        graded=graded,
        several_copies=several_copies,
        mirror=next((kind for word, kind in _MIRRORS if word in text), None),
    )
