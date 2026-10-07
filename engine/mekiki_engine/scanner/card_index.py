"""Index of Japanese Pokémon cards: (set code, collector number) → Cardmarket product.

Cardmarket's catalog names Pokémon cards after their attacks, with no number, so a listing
title such as "SV2a 201/165" cannot be matched to it directly. TCGdex's open card database
(github.com/tcgdex/cards-database, MIT licence) records the Cardmarket product of each
Japanese card; its repository is downloaded as one zip archive, at most weekly and only
when it changed, and its TypeScript card files are read with a few regular expressions.
"""

from __future__ import annotations

import io
import json
import re
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from mekiki_engine.domain import Game
from mekiki_engine.models import CardIndexEntry, SettingRow
from mekiki_engine.scanner.sources.base import PoliteClient, SourceError

ARCHIVE_URL = "https://codeload.github.com/tcgdex/cards-database/zip/refs/heads/master"
COMMIT_URL = "https://api.github.com/repos/tcgdex/cards-database/commits/master"
MAX_AGE = timedelta(days=7)
STATE_KEY = "card_index:pokemon"

# TCGdex rarity labels → the abbreviations printed on Japanese cards and used in titles.
RARITIES = {
    "Special illustration rare": "SAR",
    "Illustration rare": "AR",
    "Ultra Rare": "SR",
    "Double rare": "RR",
    "Triple Rare": "RRR",
    "Character Rare": "CHR",
    "Character Super Rare": "CSR",
    "ACE SPEC Rare": "ACE",
    "Radiant Rare": "K",
    "Black White Rare": "BWR",
    "Hyper rare": "UR",
    "Secret Rare": "UR",
    "Mega Hyper Rare": "MUR",
    "Shiny rare": "S",
    "Shiny Ultra Rare": "SSR",
}

_SET_ID = re.compile(r"""\bid:\s*['"]([^'"]+)['"]""")
_OFFICIAL = re.compile(r"\bofficial:\s*(\d+)")
_RARITY = re.compile(r"""^\s*rarity:\s*['"]([^'"]+)['"]""", re.M)
_JA_NAME = re.compile(r"""\bja:\s*['"]([^'"]+)['"]""")
_TYPE = re.compile(r"""['"]?type['"]?\s*:\s*['"]([^'"]+)['"]""")
_FOIL = re.compile(r"""['"]?foil['"]?\s*:\s*['"]([^'"]+)['"]""")
_CARDMARKET = re.compile(r"""cardmarket['"]?\s*:\s*(\d+)""")


@dataclass(frozen=True, slots=True)
class IndexedCard:
    set_code: str
    number: int
    set_total: int | None
    rarity: str | None
    name: str | None
    # "normal", "holo", "reverse", "reverse-pokeball", "reverse-masterball"…
    variant: str
    id_product: int


def refresh(session: Session, client: PoliteClient, *, force: bool = False) -> str | None:
    """Rebuilds the index when it is older than a week; returns an error message, if any."""
    state = _load_state(session)
    fetched_at = state.get("fetched_at")
    if not force and fetched_at and _age(fetched_at) < MAX_AGE and indexed_count(session):
        return None
    try:
        commit = client.request(
            "GET", COMMIT_URL, headers={"Accept": "application/vnd.github.sha"}
        ).text.strip()
        if commit != state.get("commit") or not indexed_count(session):
            archive = client.request("GET", ARCHIVE_URL, timeout=180).content
            replace_index(session, parse_archive(archive))
            state["commit"] = commit
        state["fetched_at"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        state["error"] = None
    except (SourceError, zipfile.BadZipFile) as error:
        session.rollback()
        state["error"] = f"Index des cartes Pokémon (TCGdex) : {error}"
    _save_state(session, state)
    return state["error"]


def load_error(session: Session) -> str | None:
    return _load_state(session).get("error")


def indexed_count(session: Session) -> int:
    return (
        session.scalar(
            select(func.count())
            .select_from(CardIndexEntry)
            .where(CardIndexEntry.game == Game.POKEMON.value)
        )
        or 0
    )


def replace_index(session: Session, cards: list[IndexedCard]) -> None:
    session.execute(delete(CardIndexEntry).where(CardIndexEntry.game == Game.POKEMON.value))
    unique = {(card.set_code, card.number, card.id_product): card for card in cards}
    session.add_all(
        CardIndexEntry(
            game=Game.POKEMON.value,
            set_code=card.set_code,
            number=card.number,
            set_total=card.set_total,
            rarity=card.rarity,
            name=card.name,
            variant=card.variant,
            id_product=card.id_product,
        )
        for card in unique.values()
    )
    session.commit()


def parse_archive(archive: bytes) -> list[IndexedCard]:
    with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
        files = {
            name: name.split("/data-asia/", 1)[1].split("/")
            for name in zipped.namelist()
            if "/data-asia/" in name and name.endswith(".ts")
        }
        sets: dict[tuple[str, str], tuple[str, int | None]] = {}
        for name, parts in files.items():
            if len(parts) == 2:
                text = zipped.read(name).decode("utf-8")
                set_id = _SET_ID.search(text)
                official = _OFFICIAL.search(text)
                if set_id:
                    sets[(parts[0], parts[1][:-3])] = (
                        set_id[1].lower(),
                        int(official[1]) if official else None,
                    )
        cards: list[IndexedCard] = []
        for name, parts in files.items():
            if len(parts) != 3 or (parts[0], parts[1]) not in sets:
                continue
            set_code, total = sets[(parts[0], parts[1])]
            cards.extend(
                parse_card(zipped.read(name).decode("utf-8"), set_code, total, parts[2][:-3])
            )
    return cards


def parse_card(
    text: str, set_code: str, set_total: int | None, local_id: str
) -> Iterator[IndexedCard]:
    """Cards of one TypeScript file; nothing for non-Japanese or non-numbered cards."""
    names = _block(text, "name") or ""
    japanese_name = _JA_NAME.search(names)
    # Sets are shared with the Chinese, Thai and Indonesian printings.
    if japanese_name is None or not local_id.isdigit():
        return
    rarity = _RARITY.search(text)
    common = {
        "set_code": set_code,
        "number": int(local_id),
        "set_total": set_total,
        "rarity": RARITIES.get(rarity[1], rarity[1]) if rarity and rarity[1] != "None" else None,
        "name": japanese_name[1],
    }
    variants = _block(text, "variants") or ""
    found = False
    for variant in _objects(variants):
        product = _CARDMARKET.search(variant)
        if product:
            found = True
            yield IndexedCard(**common, variant=_variant_name(variant), id_product=int(product[1]))
    if not found:
        # MEGA-era files carry the product on the card rather than on its variants.
        rest = _block(text.replace(variants, ""), "thirdParty") or ""
        product = _CARDMARKET.search(rest)
        if product:
            first = next(iter(_objects(variants)), "")
            yield IndexedCard(**common, variant=_variant_name(first), id_product=int(product[1]))


def _variant_name(variant: str) -> str:
    kind = _TYPE.search(variant)
    foil = _FOIL.search(variant)
    name = kind[1] if kind else "normal"
    return f"{name}-{foil[1]}" if foil else name


def _block(text: str, key: str) -> str | None:
    """The bracketed value following ``key:``, braces included."""
    match = re.search(rf"(?:^|\n)\s*{key}\s*:\s*([\[{{])", text)
    if not match:
        return None
    start = match.end() - 1
    opening = text[start]
    closing = "]" if opening == "[" else "}"
    depth = 0
    for index in range(start, len(text)):
        if text[index] == opening:
            depth += 1
        elif text[index] == closing:
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


def _objects(array: str) -> list[str]:
    """Top-level ``{…}`` objects of an array literal."""
    objects: list[str] = []
    depth = 0
    start = 0
    for index, char in enumerate(array[1:-1], start=1):
        if char == "{":
            if depth == 0:
                start = index
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                objects.append(array[start : index + 1])
    return objects


def _load_state(session: Session) -> dict[str, str | None]:
    row = session.get(SettingRow, STATE_KEY)
    return json.loads(row.value) if row else {}


def _save_state(session: Session, state: dict[str, str | None]) -> None:
    row = session.get(SettingRow, STATE_KEY)
    if row is None:
        session.add(SettingRow(key=STATE_KEY, value=json.dumps(state)))
    else:
        row.value = json.dumps(state)
    session.commit()


def _age(timestamp: str) -> timedelta:
    return datetime.now(UTC) - datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=UTC
    )
