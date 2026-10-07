"""Listing text for eBay and Vinted, written from what the stock knows about a card.

The user reviews it, pastes it into the site and publishes: nothing is posted for them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from mekiki_engine.domain import Game, SalePlatform
from mekiki_engine.models import CardmarketProduct, Item
from mekiki_engine.scanner.pricing import reference_price

# eBay refuses longer titles; Vinted's are cut in search results past that.
TITLE_MAX = 80
GAME_LABELS = {Game.POKEMON: "Pokémon", Game.ONE_PIECE: "One Piece"}
LANGUAGE_LABELS = {"ja": "japonaise", "en": "anglaise", "fr": "française"}
# Cardmarket names carry attack names or the code: "Kyogre EX [Tidal Storm]", "Nami (OP05-001)".
_NAME_EXTRAS = re.compile(r"\s*[\[(][^\])]*[\])]")
_ONE_PIECE_CODE = re.compile(r"\b(?:OP|EB|PRB|ST|P)\d{0,2}-\d{3}\b", re.IGNORECASE)
_CARD_NUMBER = re.compile(r"\b\d{1,3}/\d{1,3}\b")


@dataclass(frozen=True, slots=True)
class Draft:
    title: str
    description: str
    price_cents: int | None
    # "listing" for the price already set, else the Cardmarket field it comes from.
    price_source: str | None


def clean_card_name(name: str) -> str:
    return _NAME_EXTRAS.sub("", name).strip()


def search_query(name: str, number: str | None = None) -> str:
    """Words to search a card on eBay or Vinted: its name and printed number or code."""
    query = clean_card_name(name)
    if number and number.lower() not in query.lower():
        query = f"{query} {number}"
    return query


def number_in_label(label: str | None) -> str | None:
    """The printed number ("201/165") or One Piece code ("OP05-119") of a card label."""
    if not label:
        return None
    match = _ONE_PIECE_CODE.search(label) or _CARD_NUMBER.search(label)
    return match[0].upper() if match else None


def item_query(item: Item) -> str:
    return search_query(item.name, item.card_number)


def item_draft(item: Item, product: CardmarketProduct | None, platform: SalePlatform) -> Draft:
    game = Game(item.game)
    language = LANGUAGE_LABELS.get(item.language.lower())
    price_cents, price_source = _price(item, product)
    return Draft(
        title=_title(item, game, language),
        description=_description(item, game, language, platform),
        price_cents=price_cents,
        price_source=price_source,
    )


def _title(item: Item, game: Game, language: str | None) -> str:
    set_code = (item.set_code or "").upper()
    number = item.card_number or ""
    if set_code and set_code.lower() in number.lower():
        set_code = ""
    parts = [item.grading, clean_card_name(item.name), number, item.rarity, set_code]
    head = " ".join(part.strip() for part in parts if part and part.strip())
    tail = f" - Carte {GAME_LABELS[game]}" + (f" {language}" if language else "")
    if len(head) + len(tail) > TITLE_MAX:
        # The card itself matters more than the generic suffix.
        tail = f" {GAME_LABELS[game]}"
    return (head + tail)[:TITLE_MAX].rstrip()


def _description(item: Item, game: Game, language: str | None, platform: SalePlatform) -> str:
    lines = [
        f"Carte {GAME_LABELS[game]}" + (f" {language}" if language else "") + f" : {item.name}."
    ]
    details = [
        ("Série", item.set_code.upper() if item.set_code else None),
        ("Numéro", item.card_number),
        ("Rareté", item.rarity),
        ("État", item.condition),
        ("Gradation", item.grading),
    ]
    lines += [f"{label} : {value}" for label, value in details if value]
    lines.append("")
    lines.append("Carte achetée au Japon. Photos non contractuelles : recto et verso en annonce.")
    if platform is SalePlatform.VINTED:
        lines.append("Envoi soigné sous sleeve et toploader, en enveloppe à bulles.")
    else:
        lines.append("Envoi soigné et suivi : sleeve, toploader et enveloppe à bulles.")
    return "\n".join(lines)


def _price(item: Item, product: CardmarketProduct | None) -> tuple[int | None, str | None]:
    """The price already set for the listing, else the Cardmarket reference price."""
    if item.listing_price_cents is not None:
        return item.listing_price_cents, "listing"
    reference = reference_price(product)
    return reference if reference else (None, None)
