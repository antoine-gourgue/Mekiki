"""Cardmarket's public catalog and price guide files, imported into SQLite.

Cardmarket publishes, without any account, one JSON file per game for the singles catalog,
the sealed products and the daily price guide. They are only downloaded again when their
ETag changed (the server answers 304 otherwise).
"""

from __future__ import annotations

import json
import re
import threading
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from mekiki_engine.costing.money import to_cents
from mekiki_engine.domain import Game
from mekiki_engine.models import (
    CardmarketPriceHistory,
    CardmarketProduct,
    Item,
    SettingRow,
    TrackedCard,
)
from mekiki_engine.scanner import card_index
from mekiki_engine.scanner.sources.base import PoliteClient, SourceError
from mekiki_engine.schemas import CardmarketStatus

BASE_URL = "https://downloads.s3.cardmarket.com/productCatalog"
GAME_IDS = {Game.POKEMON: 6, Game.ONE_PIECE: 18}
SINGLES_CATEGORY = {Game.POKEMON: 51, Game.ONE_PIECE: 1621}
# Sealed product categories whose names give the expansion name: boosters, then boxes.
BOOSTER_CATEGORIES = {Game.POKEMON: (52, 53), Game.ONE_PIECE: (1622, 1624)}

CATALOG_MAX_AGE = timedelta(days=3)
PRICES_MAX_AGE = timedelta(hours=6)

PRICE_FIELDS = ("avg", "low", "trend", "avg1", "avg7", "avg30")

# The background worker and the "update now" button must not import the same file twice.
_refresh_lock = threading.Lock()


@dataclass(slots=True)
class SyncState:
    etag: str | None = None
    created_at: str | None = None
    fetched_at: str | None = None
    error: str | None = None


def file_url(kind: str, game: Game) -> str:
    folder = "priceGuide" if kind == "price_guide" else "productList"
    return f"{BASE_URL}/{folder}/{kind}_{GAME_IDS[game]}.json"


def load_state(session: Session, game: Game, kind: str) -> SyncState:
    row = session.get(SettingRow, _state_key(game, kind))
    return SyncState(**json.loads(row.value)) if row else SyncState()


def save_state(session: Session, game: Game, kind: str, state: SyncState) -> None:
    key = _state_key(game, kind)
    row = session.get(SettingRow, key)
    value = json.dumps(asdict(state))
    if row is None:
        session.add(SettingRow(key=key, value=value))
    else:
        row.value = value
    session.commit()


def refresh(
    session: Session, client: PoliteClient, game: Game, *, force: bool = False
) -> list[str]:
    """Brings the catalog and prices of ``game`` up to date; returns the errors met.

    Files are checked again after ``CATALOG_MAX_AGE`` / ``PRICES_MAX_AGE``, or right away
    with ``force``; either way they are only downloaded when their ETag changed.
    """
    errors: list[str] = []
    with _refresh_lock:
        now = datetime.now(UTC)
        for kind, max_age in (
            ("products_singles", CATALOG_MAX_AGE),
            ("price_guide", PRICES_MAX_AGE),
        ):
            state = load_state(session, game, kind)
            if force or state.fetched_at is None or _older_than(state.fetched_at, max_age, now):
                errors += _sync(session, client, game, kind, state)
    return errors


def import_catalog(
    session: Session, game: Game, singles: dict[str, Any], sealed: dict[str, Any]
) -> int:
    """Upserts the singles of ``game``; returns how many were imported."""
    expansions = expansion_names(game, sealed.get("products", []))
    category = SINGLES_CATEGORY[game]
    rows = [
        {
            "id_product": product["idProduct"],
            "game": game.value,
            "name": clean_name(product.get("name")),
            "id_category": product.get("idCategory"),
            "id_expansion": product.get("idExpansion"),
            "expansion_name": expansions.get(product.get("idExpansion")),
            "id_metacard": product.get("idMetacard") or None,
            "date_added": _date_added(product.get("dateAdded")),
        }
        for product in singles.get("products", [])
        if product.get("idCategory") == category
    ]
    if rows:
        statement = insert(CardmarketProduct)
        statement = statement.on_conflict_do_update(
            index_elements=[CardmarketProduct.id_product],
            set_={
                column: statement.excluded[column]
                for column in (
                    "name",
                    "id_category",
                    "id_expansion",
                    "expansion_name",
                    "id_metacard",
                    "date_added",
                )
            },
        )
        session.execute(statement, rows)
    session.commit()
    return len(rows)


def import_prices(session: Session, game: Game, guide: dict[str, Any]) -> int:
    """Stores the latest prices of the known singles, and today's prices of the cards tracked
    or ever in stock, whose history the app charts."""
    prices_date = guide.get("createdAt")
    known = set(
        session.scalars(
            select(CardmarketProduct.id_product).where(CardmarketProduct.game == game.value)
        )
    )
    rows = [
        {
            "id_product": entry["idProduct"],
            "prices_date": prices_date,
            **{f"{field}_cents": price_cents(entry.get(field)) for field in PRICE_FIELDS},
        }
        for entry in guide.get("priceGuides", [])
        if entry.get("idProduct") in known
    ]
    if rows:
        session.execute(update(CardmarketProduct), rows)

    followed = set(
        session.scalars(
            select(TrackedCard.cardmarket_product_id).where(
                TrackedCard.cardmarket_product_id.is_not(None)
            )
        )
    ) | set(
        session.scalars(
            select(Item.cardmarket_product_id).where(Item.cardmarket_product_id.is_not(None))
        )
    )
    day = (prices_date or "")[:10]
    history = [
        {
            "id_product": row["id_product"],
            "price_date": day,
            **{f"{f}_cents": row[f"{f}_cents"] for f in ("avg", "trend", "avg1", "avg7", "avg30")},
        }
        for row in rows
        if row["id_product"] in followed
    ]
    if history and day:
        statement = insert(CardmarketPriceHistory)
        session.execute(statement.on_conflict_do_nothing(), history)
    session.commit()
    return len(rows)


def status(session: Session) -> list[CardmarketStatus]:
    result = []
    for game in GAME_IDS:
        products, priced = session.execute(
            select(
                func.count(CardmarketProduct.id_product),
                func.count(CardmarketProduct.prices_date),
            ).where(CardmarketProduct.game == game.value)
        ).one()
        prices = load_state(session, game, "price_guide")
        catalog = load_state(session, game, "products_singles")
        entry = CardmarketStatus(
            game=game,
            products=products,
            priced_products=priced,
            prices_date=prices.created_at,
            fetched_at=prices.fetched_at,
            last_error=prices.error or catalog.error,
        )
        if game is Game.POKEMON:
            entry.indexed_cards = card_index.indexed_count(session)
            entry.index_error = card_index.load_error(session)
        result.append(entry)
    return result


def price_cents(value: object) -> int | None:
    # Prices come as JSON ints or floats; going through str keeps 279.1 exact.
    if value is None:
        return None
    return to_cents(Decimal(str(value)))


def clean_name(name: str | None) -> str | None:
    if name is None:
        return None
    name = name.replace('""', '"')
    return re.sub(r"\(\s+", "(", re.sub(r"\s+", " ", name)).strip()


_BOOSTER_SUFFIX = re.compile(r"\s+Booster(?: Box)?(?=\s*\(|$)")


def expansion_names(game: Game, sealed: list[dict[str, Any]]) -> dict[int, str]:
    """Expansion names guessed from sealed products: "Romance Dawn Booster" → "Romance Dawn"."""
    names: dict[int, str] = {}
    for category in BOOSTER_CATEGORIES[game]:
        for product in sealed:
            expansion = product.get("idExpansion")
            name = product.get("name") or ""
            if product.get("idCategory") != category or expansion in names:
                continue
            if _BOOSTER_SUFFIX.search(name) and "Case" not in name:
                names[expansion] = _BOOSTER_SUFFIX.sub("", name).strip()
    return names


def _sync(
    session: Session,
    client: PoliteClient,
    game: Game,
    kind: str,
    state: SyncState,
) -> list[str]:
    try:
        payload, etag = _download(client, file_url(kind, game), state.etag)
        if payload is not None:
            if kind == "price_guide":
                import_prices(session, game, payload)
            else:
                sealed, _ = _download(client, file_url("products_nonsingles", game), None)
                import_catalog(session, game, payload, sealed or {})
            state.etag = etag
            state.created_at = payload.get("createdAt")
        state.fetched_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        state.error = None
    except (SourceError, ValueError) as error:
        session.rollback()
        state.error = f"Cardmarket ({kind}) : {error}"
    save_state(session, game, kind, state)
    return [state.error] if state.error else []


def _download(
    client: PoliteClient, url: str, etag: str | None
) -> tuple[dict[str, Any] | None, str | None]:
    headers = {"If-None-Match": etag} if etag else {}
    response = client.request("GET", url, headers=headers)
    if response.status_code == 304:
        return None, etag
    return response.json(), response.headers.get("ETag")


def _date_added(raw: str | None) -> str | None:
    # Thousands of old products carry "0000-00-00 00:00:00".
    return None if not raw or raw.startswith("0000") else raw


def _older_than(timestamp: str, age: timedelta, now: datetime) -> bool:
    return datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC) < now - age


def _state_key(game: Game, kind: str) -> str:
    return f"cardmarket:{game.value}:{kind}"
