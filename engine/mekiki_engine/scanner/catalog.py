"""What a discovery can be narrowed to: each game's eras, sets and rarities.

Pokémon sets come from the card index (TCGdex and TCGplayer), named after their Cardmarket
expansion; One Piece sets from the codes Cardmarket writes in its Japanese products' names
("(OP05-119)"). Eras follow the set codes printed on the cards: "sv2a" is Scarlet & Violet.
"""

from __future__ import annotations

import re
from collections import Counter

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from mekiki_engine.domain import Game
from mekiki_engine.models import CardIndexEntry, CardmarketProduct
from mekiki_engine.scanner.resolver import JAPANESE_EXPANSION, printed_code
from mekiki_engine.schemas import DiscoveryCatalog, DiscoveryEra, DiscoveryRarity, DiscoverySet

# Newest first; "older" gathers what the index holds from before Black & White.
ERAS = (
    DiscoveryEra(id="mega", label="MEGA", years="depuis 2025"),
    DiscoveryEra(id="sv", label="Écarlate et Violet", years="2023-2025"),
    DiscoveryEra(id="swsh", label="Épée et Bouclier", years="2019-2023"),
    DiscoveryEra(id="sm", label="Soleil et Lune", years="2016-2019"),
    DiscoveryEra(id="xy", label="XY", years="2013-2016"),
    DiscoveryEra(id="bw", label="Noir et Blanc", years="2011-2013"),
    DiscoveryEra(id="older", label="Avant 2011", years="Platine, LEGEND…"),
)
ERA_RANK = {era.id: rank for rank, era in enumerate(ERAS)}
# "mc" and "mf" are MEGA-era decks; "cp" the XY-era concept packs.
_ERA_CODES = (
    ("mega", re.compile(r"^(?:m\d|m-p$|mc$|mf$)")),
    ("sv", re.compile(r"^sv")),
    ("sm", re.compile(r"^sm")),
    ("swsh", re.compile(r"^s(?:\d|-p$)")),
    ("xy", re.compile(r"^(?:xy|cp)")),
    ("bw", re.compile(r"^bw")),
)

POKEMON_RARITIES = (
    DiscoveryRarity(id="sar", label="SAR", description="Special Art Rare"),
    DiscoveryRarity(id="sr", label="SR", description="Super Rare"),
    DiscoveryRarity(id="ar", label="AR", description="Art Rare"),
    DiscoveryRarity(id="ur", label="UR", description="Ultra Rare, dorée"),
    DiscoveryRarity(id="mur", label="MUR", description="Mega Ultra Rare"),
    DiscoveryRarity(id="hr", label="HR", description="Hyper Rare"),
    DiscoveryRarity(id="chr", label="CHR", description="Character Rare"),
    DiscoveryRarity(id="csr", label="CSR", description="Character Super Rare"),
    DiscoveryRarity(id="ssr", label="SSR", description="Shiny Super Rare"),
    DiscoveryRarity(id="rrr", label="RRR", description="Triple Rare"),
    DiscoveryRarity(id="rr", label="RR", description="Double Rare"),
    DiscoveryRarity(id="ace", label="ACE", description="ACE SPEC"),
    DiscoveryRarity(id="s", label="S", description="Shiny, chromatique"),
    DiscoveryRarity(id="k", label="K", description="Radieuse"),
)
ONE_PIECE_RARITIES = (
    DiscoveryRarity(id="sec", label="SEC", description="Secret Rare"),
    DiscoveryRarity(id="sp", label="SP", description="Special"),
    DiscoveryRarity(id="sr", label="SR", description="Super Rare"),
    DiscoveryRarity(id="l", label="L", description="Leader"),
    DiscoveryRarity(id="r", label="R", description="Rare"),
    DiscoveryRarity(id="parallel", label="Parallèle", description="Toutes les parallèles"),
    DiscoveryRarity(id="manga", label="Manga", description="Parallèle manga"),
)
RARITIES = {Game.POKEMON: POKEMON_RARITIES, Game.ONE_PIECE: ONE_PIECE_RARITIES}
# What sellers write for a rarity, to search it; one letter would match anything.
RARITY_SEARCHES = {
    Game.POKEMON: {r.id: r.label for r in POKEMON_RARITIES if len(r.id) > 1},
    Game.ONE_PIECE: {
        "sec": "SEC",
        "sp": "SP",
        "sr": "SR",
        "l": "リーダー",
        "parallel": "パラレル",
        "manga": "コミパラ",
    },
}
_ONE_PIECE_CODE = re.compile(r"\(\s*((?:OP|EB|PRB|ST)\d{2})-\d{3}\s*\)", re.IGNORECASE)
_EXPANSION_SUFFIX = re.compile(r"\s*\((?:non-english|asia region legal)\)\s*$", re.IGNORECASE)
_SET_PARTS = re.compile(r"^([a-z]+)(\d*)(.*)$")


def era_of(set_code: str) -> str:
    return next((era for era, codes in _ERA_CODES if codes.match(set_code)), "older")


def catalog(session: Session, game: Game) -> DiscoveryCatalog:
    sets = _pokemon_sets(session) if game is Game.POKEMON else _one_piece_sets(session)
    return DiscoveryCatalog(
        game=game,
        eras=list(ERAS) if game is Game.POKEMON else [],
        sets=sets,
        rarities=list(RARITIES[game]),
    )


def set_names(session: Session, game: Game, codes: list[str]) -> dict[str, str]:
    """Each set's Japanese name, as listing titles write it, when it is known."""
    if game is not Game.POKEMON or not codes:
        return {}
    rows = session.execute(
        select(CardIndexEntry.set_code, func.max(CardIndexEntry.set_name))
        .where(CardIndexEntry.game == game.value, CardIndexEntry.set_code.in_(codes))
        .group_by(CardIndexEntry.set_code)
    )
    return {code: name for code, name in rows if name}


def newest_first(sets: list[DiscoverySet]) -> list[DiscoverySet]:
    """Newest era first, then the highest set number: "sv11b", "sv9a", "sv9", "sv2a"."""

    def number(code: str) -> int:
        parts = _SET_PARTS.match(code)
        return int(parts[2]) if parts and parts[2] else 0

    # A stable sort keeps the codes' reverse order among sets of the same number.
    by_code = sorted(sets, key=lambda s: s.code, reverse=True)
    return sorted(by_code, key=lambda s: (ERA_RANK.get(s.era or "", 0), -number(s.code)))


def _pokemon_sets(session: Session) -> list[DiscoverySet]:
    counts = session.execute(
        select(CardIndexEntry.set_code, func.max(CardIndexEntry.set_name), func.count())
        .where(CardIndexEntry.game == Game.POKEMON.value)
        .group_by(CardIndexEntry.set_code)
    ).all()
    # The Cardmarket expansion most of a set's cards belong to gives its English name.
    expansions: dict[str, Counter[str]] = {}
    rows = session.execute(
        select(CardIndexEntry.set_code, CardmarketProduct.expansion_name)
        .join(CardmarketProduct, CardmarketProduct.id_product == CardIndexEntry.id_product)
        .where(
            CardIndexEntry.game == Game.POKEMON.value,
            CardmarketProduct.expansion_name.is_not(None),
        )
    )
    for code, expansion in rows:
        expansions.setdefault(code, Counter())[expansion] += 1
    sets = [
        DiscoverySet(
            code=code,
            printed=printed_code(code),
            name=expansions[code].most_common(1)[0][0] if code in expansions else None,
            japanese_name=japanese_name,
            era=era_of(code),
            cards=cards,
        )
        for code, japanese_name, cards in counts
    ]
    return newest_first(sets)


def _one_piece_sets(session: Session) -> list[DiscoverySet]:
    names: dict[str, Counter[str]] = {}
    products = session.execute(
        select(CardmarketProduct.name, CardmarketProduct.expansion_name).where(
            CardmarketProduct.game == Game.ONE_PIECE.value
        )
    )
    for name, expansion in products:
        match = _ONE_PIECE_CODE.search(name or "")
        if match and JAPANESE_EXPANSION.search(expansion or ""):
            clean = _EXPANSION_SUFFIX.sub("", expansion or "")
            names.setdefault(match[1].lower(), Counter())[clean] += 1
    sets = [
        DiscoverySet(
            code=code,
            printed=code.upper(),
            name=counter.most_common(1)[0][0],
            japanese_name=None,
            era=None,
            cards=sum(counter.values()),
        )
        for code, counter in names.items()
    ]
    # Main sets first (OP, then EB and PRB), starter decks last; newest first in each.
    order = {"op": 0, "eb": 1, "prb": 2, "st": 3}
    return sorted(newest_first(sets), key=lambda s: order.get(s.code.rstrip("0123456789"), 4))
