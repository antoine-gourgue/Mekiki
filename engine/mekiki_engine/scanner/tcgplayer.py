"""Japanese card lists from TCGplayer, to link the cards TCGdex lacks to Cardmarket.

TCGdex holds no Japanese data for many sets (Pokémon GO, Eevee Heroes, Time Gazer…: only
their Chinese printing), and Cardmarket's catalog gives its Japanese products no number.
TCGplayer lists every Japanese card with its number and English name; TCGCSV (tcgcsv.com)
publishes that list as a free daily export. A number is linked to a Cardmarket product only
when the card's versions line up the same way twice: by number against product id
(Cardmarket adds a set's cards in number order), and by price on both sites. Checked on sets
TCGdex does link, this got 627 cards out of 628 right; anything less clear stays unlinked.
"""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from mekiki_engine.domain import Game
from mekiki_engine.models import CardmarketProduct
from mekiki_engine.scanner.pricing import reference_price
from mekiki_engine.scanner.sources.base import PoliteClient

# Category 85: Pokémon cards printed in Japanese.
TCGCSV_URL = "https://tcgcsv.com/tcgplayer/85"
# TCGplayer's rarities → the abbreviations printed on Japanese cards and used in titles.
RARITIES = {
    "Double Rare": "RR",
    "Triple Rare": "RRR",
    "Super Rare": "SR",
    "Hyper Rare": "HR",
    "Ultra Rare": "UR",
    "Art Rare": "AR",
    "Special Art Rare": "SAR",
    "Character Rare": "CHR",
    "Character Super Rare": "CSR",
    "Kagayaku": "K",
    "ACE Rare": "ACE",
    "Shiny Rare": "S",
    "Shiny Super Rare": "SSR",
}
_NUMBER = re.compile(r"^\s*0*(\d+)")
# TCGplayer writes the number after the name: "Umbreon V - 085/069".
_NUMBER_AFTER_NAME = re.compile(r"\s+-\s+\S+/\S+$")


@dataclass(frozen=True, slots=True)
class Link:
    number: int
    id_product: int
    # English, as TCGplayer writes it: "Umbreon V".
    name: str
    rarity: str | None


def japanese_groups(client: PoliteClient) -> dict[str, tuple[int, str]]:
    """TCGplayer's Japanese sets by code ("S10B") → (group id, English name of the set)."""
    found: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for row in _results(client, "groups"):
        code, _, name = str(row.get("name") or "").partition(":")
        if name and isinstance(row.get("groupId"), int):
            found[code.strip().upper()].append((row["groupId"], name.strip()))
    # A code two groups start with is not a set code.
    return {code: groups[0] for code, groups in found.items() if len(groups) == 1}


def find_expansion(session: Session, english_name: str) -> int | None:
    """The Cardmarket expansion named like TCGplayer's set, when only one is."""
    wanted = _key(english_name)
    rows = session.execute(
        select(CardmarketProduct.id_expansion, CardmarketProduct.expansion_name)
        .where(
            CardmarketProduct.game == Game.POKEMON.value,
            CardmarketProduct.expansion_name.is_not(None),
        )
        .distinct()
    )
    matches = {expansion for expansion, name in rows if name and _key(name) == wanted}
    return matches.pop() if len(matches) == 1 else None


def has_products(session: Session, expansion: int) -> bool:
    count = session.scalar(
        select(func.count())
        .select_from(CardmarketProduct)
        .where(CardmarketProduct.id_expansion == expansion)
    )
    return bool(count)


def link_set(session: Session, client: PoliteClient, group: int, expansion: int) -> list[Link]:
    """The cards of a TCGplayer set linked to products of a Cardmarket expansion."""
    prices: dict[int, float] = {}
    for row in _results(client, f"{group}/prices"):
        price = next(
            (
                row[key]
                for key in ("marketPrice", "midPrice", "lowPrice")
                if _positive(row.get(key))
            ),
            None,
        )
        product_id = row.get("productId")
        if price is not None and isinstance(product_id, int):
            # One price per finish ("Normal", "Holofoil"): the card's own is the highest.
            prices[product_id] = max(price, prices.get(product_id, 0.0))

    cards: dict[str, list[tuple[int, float, str, str | None]]] = defaultdict(list)
    for product in _results(client, f"{group}/products"):
        details = {
            item.get("name"): item.get("value") for item in product.get("extendedData") or []
        }
        number = _NUMBER.match(str(details.get("Number") or ""))
        name = _NUMBER_AFTER_NAME.sub("", str(product.get("name") or "")).strip()
        # Boosters and boxes have no number.
        if number is None or not name:
            continue
        rarity = str(details.get("Rarity") or "")
        cards[_key(name)].append(
            (
                int(number[1]),
                prices.get(product.get("productId"), 0.0),
                name,
                RARITIES.get(rarity, rarity if rarity and rarity != "None" else None),
            )
        )

    products: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for product in session.scalars(
        select(CardmarketProduct).where(CardmarketProduct.id_expansion == expansion)
    ):
        reference = reference_price(product)
        # Cardmarket writes the attacks after the name: "Umbreon V [Mean Look | …]".
        name = (product.name or "").split(" [")[0]
        products[_key(name)].append((product.id_product, reference[0] if reference else 0))

    links: list[Link] = []
    for key, versions in cards.items():
        found = products.get(key, [])
        numbers = [number for number, *_ in versions]
        if len(found) != len(versions) or len(set(numbers)) != len(numbers):
            continue
        by_order = dict(
            zip(sorted(numbers), sorted(id_product for id_product, _ in found), strict=True)
        )
        by_price = dict(
            zip(
                [number for number, *_ in sorted(versions, key=lambda v: (v[1], v[0]))],
                [id_product for id_product, _ in sorted(found, key=lambda p: (p[1], p[0]))],
                strict=True,
            )
        )
        # Regular, full art and alternate art of a card cost very different prices: when
        # both orders disagree, a version could get another's price.
        if by_order != by_price:
            continue
        links += [
            Link(number, by_order[number], name, rarity) for number, _, name, rarity in versions
        ]
    return links


def _results(client: PoliteClient, path: str) -> list[dict[str, Any]]:
    payload = client.request("GET", f"{TCGCSV_URL}/{path}", timeout=60).json()
    results = payload.get("results") if isinstance(payload, dict) else None
    return [row for row in results or [] if isinstance(row, dict)]


def _positive(value: object) -> bool:
    return isinstance(value, int | float) and value > 0


def _key(name: str) -> str:
    """Letters and digits only: "Professor's Research" ≡ "Professors Research"."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", ascii_name.lower())
