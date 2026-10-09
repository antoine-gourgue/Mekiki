"""What a tracked card looks like in Japanese listings, and whether a listing is that card.

A card tracked through its Cardmarket product is matched like discovery reads listings: the
title must name the same set and number (Pokémon) or code (One Piece), and the same
printing, so a mirror, a parallel or a bundle of the same number never passes for it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from mekiki_engine.domain import Game
from mekiki_engine.models import CardIndexEntry, CardmarketProduct, TrackedCard
from mekiki_engine.scanner import names
from mekiki_engine.scanner.identify import CardIdentity, mirror_of
from mekiki_engine.scanner.resolver import CatalogResolver

Version = Literal["regular", "parallel", "manga"]

_CODE_IN_NAME = re.compile(r"\(\s*((?:OP|ST|EB|PRB)\d{2}|P)-(\d{3})\s*\)", re.IGNORECASE)
# How Japanese titles name the One Piece versions; added to the code to search them.
VERSION_WORDS: dict[Version, str] = {"regular": "", "parallel": "パラレル", "manga": "コミパラ"}
VERSION_LABELS: dict[Version, str] = {
    "regular": "normale",
    "parallel": "parallèle",
    "manga": "manga",
}


@dataclass(frozen=True, slots=True)
class Printing:
    """One Cardmarket product as Japanese titles name it."""

    game: Game
    # Pokémon
    set_code: str | None = None
    number: int | None = None
    total: int | None = None
    # None for the regular printing, else "reverse", "masterball", "pokeball"…
    mirror: str | None = None
    japanese_name: str | None = None
    rarity: str | None = None
    # One Piece: "op05-119"
    code: str | None = None
    version: Version | None = None

    @property
    def card_number(self) -> str | None:
        if self.code:
            return self.code.upper()
        if self.number is None:
            return None
        return f"{self.number:03d}/{self.total:03d}" if self.total else f"{self.number:03d}"


def printing_of(session: Session, product: CardmarketProduct) -> Printing | None:
    """The Japanese printing a product is, or None for an English one or an unknown card."""
    if Game(product.game) is Game.ONE_PIECE:
        return _one_piece_printing(session, product)
    rows = session.scalars(
        select(CardIndexEntry).where(CardIndexEntry.id_product == product.id_product)
    ).all()
    if not rows:
        return None
    row = rows[0]
    mirror = None
    if row.variant.startswith("reverse"):
        mirror = row.variant.partition("-")[2] or "reverse"
    return Printing(
        game=Game.POKEMON,
        set_code=row.set_code,
        number=row.number,
        total=row.set_total,
        mirror=mirror,
        japanese_name=row.name,
        rarity=row.rarity,
    )


def _one_piece_printing(session: Session, product: CardmarketProduct) -> Printing | None:
    match = _CODE_IN_NAME.search(product.name or "")
    if match is None:
        return None
    code = f"{match[1].lower()}-{match[2]}"
    versions = CatalogResolver(session).one_piece_versions(code)
    ids = [version.id_product for version in versions]
    if product.id_product not in ids:
        return None
    position = ids.index(product.id_product)
    # Same order as the resolver: regular, parallel, then the manga parallel when there is one.
    version: Version = "regular"
    if position > 0:
        version = "manga" if position == len(ids) - 1 and len(ids) > 2 else "parallel"
    return Printing(game=Game.ONE_PIECE, code=code, version=version)


def is_printing(printing: Printing, identity: CardIdentity) -> bool:
    """Whether a listing read as ``identity`` sells exactly ``printing``."""
    if identity.several_copies:
        return False
    if printing.game is Game.ONE_PIECE:
        if identity.code != printing.code:
            return False
        if printing.version == "manga":
            return identity.manga
        if printing.version == "parallel":
            return identity.parallel and not identity.manga
        return not identity.parallel
    if identity.number is None or identity.number != printing.number:
        return False
    if identity.set_code:
        if identity.set_code != printing.set_code:
            return False
    elif identity.total is None or identity.total != printing.total:
        return False
    mirror = mirror_of(identity.text, printing.japanese_name) if identity.mirror else None
    if printing.mirror is None:
        return mirror is None
    if printing.mirror == "reverse":
        return mirror == "reverse"
    return mirror == printing.mirror


def printing_queries(printing: Printing) -> list[str]:
    """Searches that find this printing on Japanese marketplaces, most precise first."""
    if printing.game is Game.ONE_PIECE:
        assert printing.code is not None
        code = printing.code.upper()
        word = VERSION_WORDS[printing.version or "regular"]
        return [f"{code} {word}".strip(), code] if word else [code]
    queries = []
    number = printing.card_number
    if printing.japanese_name and number:
        queries.append(f"{printing.japanese_name} {number}")
    if printing.set_code and number:
        queries.append(f"{printing.set_code} {number}")
    if printing.japanese_name:
        queries.append(printing.japanese_name)
    return queries


def search_queries(session: Session, card: TrackedCard, printing: Printing | None) -> list[str]:
    """The card's own search, then the searches its printing adds, without repeats."""
    game = Game(card.game)
    queries = [card.search_query]
    if printing is not None:
        queries += printing_queries(printing)
    else:
        translated = names.translate(session, game, card.name, "ja")
        if translated:
            queries.append(f"{translated} {card.card_number or ''}".strip())
    seen: set[str] = set()
    unique = []
    for query in queries:
        cleaned = " ".join(query.split())
        if cleaned and cleaned.lower() not in seen:
            seen.add(cleaned.lower())
            unique.append(cleaned)
    return unique


@dataclass(frozen=True, slots=True)
class TrackedCardTemplate:
    """Fields to track a product, filled from what Japanese listings write."""

    game: Game
    name: str
    set_code: str | None
    card_number: str | None
    rarity: str | None
    search_query: str
    # Shown to the user: which printing this is ("SV2a 201/165 · SAR", "OP05-119 · parallèle").
    label: str
    japanese: bool


def template_for(session: Session, product: CardmarketProduct) -> TrackedCardTemplate:
    game = Game(product.game)
    printing = printing_of(session, product)
    english = re.sub(r"\s*[\[(][^\])]*[\])]", "", product.name or "").strip()
    if printing is None:
        query = names.translate(session, game, english, "ja") or english
        return TrackedCardTemplate(
            game=game,
            name=english,
            set_code=None,
            card_number=None,
            rarity=None,
            search_query=query,
            label="Impression anglaise : les annonces japonaises vendent une autre carte",
            japanese=False,
        )
    queries = printing_queries(printing)
    if game is Game.ONE_PIECE:
        version = VERSION_LABELS[printing.version or "regular"]
        label = f"{printing.card_number} · {version}"
        name = english
    else:
        label = " · ".join(
            part
            for part in (
                f"{(printing.set_code or '').upper()} {printing.card_number}",
                printing.rarity,
                "miroir" if printing.mirror else None,
            )
            if part
        )
        name = printing.japanese_name or english
    return TrackedCardTemplate(
        game=game,
        name=name,
        set_code=printing.set_code or (printing.code or "").split("-")[0].upper() or None,
        card_number=printing.card_number,
        rarity=printing.rarity,
        search_query=queries[0] if queries else english,
        label=label,
        japanese=True,
    )
