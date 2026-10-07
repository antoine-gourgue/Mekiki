"""Turns a card read from a listing title into the Cardmarket product it sells as."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from mekiki_engine.domain import Game
from mekiki_engine.models import CardIndexEntry, CardmarketProduct
from mekiki_engine.scanner.identify import CardIdentity
from mekiki_engine.scanner.pricing import reference_price

# Japanese One Piece printings sit in expansions named "… (Non-English)" or
# "… (Asia Region Legal)"; the English ones are priced very differently.
JAPANESE_EXPANSION = re.compile(r"non-english|asia", re.IGNORECASE)
_CODE_IN_NAME = re.compile(r"\(\s*((?:OP|ST|EB|PRB)\d{2}|P)-(\d{3})\s*\)", re.IGNORECASE)


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

    def resolve(self, identity: CardIdentity) -> Resolution | None:
        if not identity.identified:
            return None
        if identity.game is Game.ONE_PIECE:
            return self._resolve_one_piece(identity)
        return self._resolve_pokemon(identity)

    def _resolve_pokemon(self, identity: CardIdentity) -> Resolution | None:
        statement = select(CardIndexEntry).where(
            CardIndexEntry.game == Game.POKEMON.value,
            CardIndexEntry.number == identity.number,
        )
        if identity.set_code:
            statement = statement.where(CardIndexEntry.set_code == identity.set_code)
        else:
            statement = statement.where(CardIndexEntry.set_total == identity.total)
        rows = self.session.scalars(statement).all()
        # Without a set code, two sets of the same size make the number ambiguous.
        if not rows or len({row.set_code for row in rows}) > 1:
            return None
        rows = _matching_printing(rows, identity.mirror)
        products = self._priced({row.id_product for row in rows})
        if not products:
            return None
        row = rows[0]
        label = f"{_printed_code(row.set_code)} {identity.number:03d}"
        if row.set_total:
            label += f"/{row.set_total:03d}"
        if row.rarity:
            label += f" · {row.rarity}"
        if identity.mirror:
            label += " · miroir"
        if len(products) == 1:
            return Resolution(products[0], label, "high")
        # Unclear printing: the cheapest price never makes a listing look better than it is.
        return Resolution(
            products[0],
            label,
            "medium",
            f"{len(products)} versions sur Cardmarket : vérifiez la cote",
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
    """ "sv2a" → "SV2a", "s8b" → "S8b": the series letters are capitals on the cards."""
    return re.sub(r"^[a-z]+", lambda match: match[0].upper(), set_code)
