"""Turns a card read from a listing title into the Cardmarket product it sells as."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from mekiki_engine.domain import Game
from mekiki_engine.models import CardIndexEntry, CardmarketProduct
from mekiki_engine.scanner.identify import CardIdentity
from mekiki_engine.scanner.matching import normalize
from mekiki_engine.scanner.pricing import reference_price

# Japanese One Piece printings sit in expansions named "… (Non-English)" or
# "… (Asia Region Legal)"; the English ones are priced very differently.
JAPANESE_EXPANSION = re.compile(r"non-english|asia", re.IGNORECASE)
_CODE_IN_NAME = re.compile(r"\(\s*((?:OP|ST|EB|PRB)\d{2}|P)-(\d{3})\s*\)", re.IGNORECASE)
# Rarities printed above the set's size: the index leaves many of them without a rarity.
SECRET_RARITIES = frozenset({"sar", "sr", "ar", "ur", "hr", "mur", "chr", "csr", "ssr"})
# Card names this short ("ミュウ", "ex") are found inside too many other words.
MIN_NAME_LENGTH = 3
# The index holds every set of the Scarlet & Violet and MEGA eras, but older ones only in
# part: there, a name and a rarity may also fit a card of a set the index lacks.
FULLY_INDEXED_SET = re.compile(r"^(?:sv|m)\d")
NAME_RARITY_NOTE = (
    "Reconnue par son nom et sa rareté, sans numéro dans le titre : vérifiez la version"
)


@dataclass(frozen=True, slots=True)
class Resolution:
    product: CardmarketProduct
    label: str
    confidence: Literal["high", "medium"]
    note: str | None = None


class CatalogResolver:
    """Looks cards up in the card index and the Cardmarket catalog; one per discovery run."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self._one_piece: dict[str, list[CardmarketProduct]] | None = None
        self._names: _NameIndex | None = None

    def resolve(self, identity: CardIdentity) -> Resolution | None:
        if identity.game is Game.ONE_PIECE:
            return self._resolve_one_piece(identity) if identity.identified else None
        if identity.identified:
            return self._resolve_pokemon(identity)
        if identity.rarity and not identity.several_copies and identity.number is None:
            return self._resolve_by_name(identity)
        return None

    def _resolve_pokemon(self, identity: CardIdentity) -> Resolution | None:
        statement = select(CardIndexEntry).where(
            CardIndexEntry.game == Game.POKEMON.value,
            CardIndexEntry.number == identity.number,
        )
        if identity.set_code:
            statement = statement.where(CardIndexEntry.set_code == identity.set_code)
        else:
            statement = statement.where(CardIndexEntry.set_total == identity.total)
        rows = list(self.session.scalars(statement).all())
        if not identity.set_code and any(row.name for row in rows):
            # A number over a total fits every set of that size, and the older sets missing
            # from the index too: the card's name in the title says which one, or none.
            title = compact(identity.text)
            rows = [row for row in rows if row.name and compact(row.name) in title]
        if not rows or len({row.set_code for row in rows}) > 1:
            return None
        return self._resolution(rows, identity)

    def _resolve_by_name(self, identity: CardIdentity) -> Resolution | None:
        """A title without a number, like "タケルライコex SAR ワイルドフォース キラ…".

        Sellers often leave the number out, or their title is cut before it. The card's name
        followed by its rarity still names one card when only one in the index fits both.
        """
        assert identity.rarity is not None
        if self._names is None:
            self._names = _NameIndex(
                self.session.scalars(
                    select(CardIndexEntry).where(CardIndexEntry.game == Game.POKEMON.value)
                ).all()
            )
        rows = [
            row
            for row in self._names.followed_by(compact(identity.text), identity.rarity)
            if _rarity_fits(row, identity.rarity)
            and (identity.set_code is None or row.set_code == identity.set_code)
        ]
        if len({(row.set_code, row.number) for row in rows}) != 1:
            return None
        if not identity.set_code and not FULLY_INDEXED_SET.match(rows[0].set_code):
            return None
        return self._resolution(rows, identity, NAME_RARITY_NOTE)

    def _resolution(
        self, rows: list[CardIndexEntry], identity: CardIdentity, note: str | None = None
    ) -> Resolution | None:
        rows = _matching_printing(rows, identity.mirror)
        products = self._priced({row.id_product for row in rows})
        if not products:
            return None
        row = rows[0]
        label = f"{_printed_code(row.set_code)} {row.number:03d}"
        if row.set_total:
            label += f"/{row.set_total:03d}"
        if row.rarity:
            label += f" · {row.rarity}"
        if identity.mirror:
            label += " · miroir"
        if len(products) == 1:
            return Resolution(products[0], label, "medium" if note else "high", note)
        # Unclear printing: the cheapest price never makes a listing look better than it is.
        return Resolution(
            products[0],
            label,
            "medium",
            note or f"{len(products)} versions sur Cardmarket : vérifiez la cote",
        )

    def _resolve_one_piece(self, identity: CardIdentity) -> Resolution | None:
        assert identity.code is not None
        versions = self._one_piece_index().get(identity.code, [])
        if not versions:
            return None
        code = identity.code.upper()
        if len(versions) == 1:
            return Resolution(versions[0], code, "high")
        # Versions share the same name; in creation order the regular print comes first,
        # then the parallel, then the manga (comic) parallel when there is one.
        if identity.manga:
            product, kind = versions[-1], "manga"
        elif identity.parallel:
            product, kind = versions[1], "parallèle"
        else:
            product, kind = versions[0], "normale"
        return Resolution(
            product,
            f"{code} · {kind}",
            "medium",
            f"{len(versions)} versions japonaises sur Cardmarket : vérifiez laquelle",
        )

    def one_piece_versions(self, code: str) -> list[CardmarketProduct]:
        """Japanese versions of a One Piece code ("op05-119"): regular, parallel, manga."""
        return self._one_piece_index().get(code.lower(), [])

    def _one_piece_index(self) -> dict[str, list[CardmarketProduct]]:
        if self._one_piece is None:
            by_code: dict[str, list[CardmarketProduct]] = {}
            products = self.session.scalars(
                select(CardmarketProduct).where(CardmarketProduct.game == Game.ONE_PIECE.value)
            )
            for product in products:
                match = _CODE_IN_NAME.search(product.name or "")
                japanese = JAPANESE_EXPANSION.search(product.expansion_name or "")
                if match and japanese and reference_price(product):
                    by_code.setdefault(f"{match[1].lower()}-{match[2]}", []).append(product)
            # Cardmarket creates a code's versions in the official order (regular, parallel,
            # manga), so product ids sort them.
            self._one_piece = {
                code: sorted(_home_versions(code, versions, by_code), key=lambda p: p.id_product)
                for code, versions in by_code.items()
            }
        return self._one_piece

    def _priced(self, ids: set[int]) -> list[CardmarketProduct]:
        products = [
            product
            for product_id in ids
            if (product := self.session.get(CardmarketProduct, product_id)) is not None
            and reference_price(product) is not None
        ]
        return sorted(products, key=_price)


def _price(product: CardmarketProduct) -> int:
    reference = reference_price(product)
    return reference[0] if reference else 0


def _home_versions(
    code: str, versions: list[CardmarketProduct], by_code: dict[str, list[CardmarketProduct]]
) -> list[CardmarketProduct]:
    """Versions from the set the code belongs to, leaving out later reprints.

    Reprint sets (The Best, Memorial Collection…) reuse original codes; mixed in, they break
    the "regular < parallel < manga" price order the resolver relies on. The home set of
    "op05" is the expansion holding most "op05-…" products.
    """
    prefix = code.split("-")[0]
    counts: dict[int | None, int] = {}
    for other_code, products in by_code.items():
        if other_code.split("-")[0] == prefix:
            for product in products:
                counts[product.id_expansion] = counts.get(product.id_expansion, 0) + 1
    home = max(counts, key=lambda expansion: counts[expansion])
    return [v for v in versions if v.id_expansion == home] or versions


def compact(text: str) -> str:
    """Normalised, without the spaces and joiners sellers add or drop in card names."""
    return re.sub(r"[\s・&()]", "", normalize(text))


class _NameIndex:
    """The index's Japanese card names, to find them in a title without trying each one."""

    def __init__(self, rows: Iterable[CardIndexEntry]) -> None:
        self.rows: dict[str, list[CardIndexEntry]] = {}
        for row in rows:
            name = compact(row.name or "")
            if len(name) >= MIN_NAME_LENGTH:
                self.rows.setdefault(name, []).append(row)
        # Names by their first two characters, longest first.
        self.heads: dict[str, list[str]] = {}
        for name in sorted(self.rows, key=len, reverse=True):
            self.heads.setdefault(name[:2], []).append(name)

    def followed_by(self, title: str, rarity: str) -> list[CardIndexEntry]:
        """Rows of the longest name the title writes right before the rarity."""
        found: list[str] = []
        for start in range(len(title) - 1):
            # "そらをとぶピカチュウV" is another card than "ピカチュウV": a name glued to a
            # word in hiragana is only part of the card's name.
            if start and "ぁ" <= title[start - 1] <= "ゟ":
                continue
            for name in self.heads.get(title[start : start + 2], ()):
                if title.startswith(name + rarity, start):
                    found.append(name)
                    break
        if not found:
            return []
        return self.rows[max(found, key=len)]


def _rarity_fits(row: CardIndexEntry, rarity: str) -> bool:
    if row.rarity:
        # Hyper rares were printed "UR" in the Sun & Moon era.
        return row.rarity.lower() == rarity or {row.rarity.lower(), rarity} == {"ur", "hr"}
    return rarity in SECRET_RARITIES and bool(row.set_total) and row.number > row.set_total


def _matching_printing(rows: list[CardIndexEntry], mirror: str | None) -> list[CardIndexEntry]:
    """Index rows of the printing a title names: a given mirror, or else the regular one."""
    if mirror == "reverse":
        chosen = [row for row in rows if row.variant.startswith("reverse")]
    elif mirror:
        chosen = [row for row in rows if row.variant.endswith(mirror)]
    else:
        chosen = [row for row in rows if not row.variant.startswith("reverse")]
    return chosen or rows


def _printed_code(set_code: str) -> str:
    """ "sv2a" → "SV2a", "s8b" → "S8b", "s-p" → "S-P": as printed on the cards."""
    if set_code.endswith("-p"):
        return set_code.upper()
    return re.sub(r"^[a-z]+", lambda match: match[0].upper(), set_code)
