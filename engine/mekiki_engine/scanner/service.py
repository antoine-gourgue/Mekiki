"""Tracked cards and the listings found for them, shaped for the API."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from mekiki_engine.costing.sale import roi
from mekiki_engine.domain import Game, ListingCondition, ListingTriage, SourcePlatform
from mekiki_engine.models import (
    CardIndexEntry,
    CardmarketPriceHistory,
    CardmarketProduct,
    Listing,
    TrackedCard,
)
from mekiki_engine.scanner import links, names, sellers, tracking
from mekiki_engine.scanner.identify import identify
from mekiki_engine.scanner.matching import build_rule, match_title, split_keywords
from mekiki_engine.scanner.pricing import (
    DealEstimate,
    estimate_listing,
    expected_sale_cents,
    max_buy_price_jpy,
    meets_target,
    reference_price,
)
from mekiki_engine.scanner.resolver import JAPANESE_EXPANSION
from mekiki_engine.scanner.sources.base import FoundListing
from mekiki_engine.schemas import (
    AppSettings,
    DealOut,
    LandedCostOut,
    MarketPriceOut,
    PricePoint,
    SaleBreakdownOut,
    TrackedCardCreate,
    TrackedCardFields,
    TrackedCardOut,
    TrackedCardUpdate,
)
from mekiki_engine.services.portfolio import NotFoundError


def utc_now() -> str:
    # Microseconds: two scans in the same second must still be told apart.
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def default_search_query(card_number: str | None, name: str) -> str:
    # Japanese titles almost always carry the collector number, rarely the English name.
    return (card_number or name).strip()


def market_price_out(product: CardmarketProduct, *, japanese: bool = False) -> MarketPriceOut:
    reference = reference_price(product)
    return MarketPriceOut(
        japanese=japanese,
        id_product=product.id_product,
        game=Game(product.game),
        name=product.name,
        expansion_name=product.expansion_name,
        url=links.cardmarket_product_url(Game(product.game), product.id_product),
        avg_cents=product.avg_cents,
        low_cents=product.low_cents,
        trend_cents=product.trend_cents,
        avg1_cents=product.avg1_cents,
        avg7_cents=product.avg7_cents,
        avg30_cents=product.avg30_cents,
        prices_date=product.prices_date,
        reference_cents=reference[0] if reference else None,
        reference_field=reference[1] if reference else None,
    )


def search_products(
    session: Session, *, game: Game, query: str, limit: int = 20
) -> list[MarketPriceOut]:
    """Catalog lookup by name or product id: Japanese printings first, then the dearest.

    Cardmarket names cards in English: a French name ("Dracaufeu") is searched in English
    too.
    """
    queries = [query]
    english = names.translate(session, game, query, "en")
    if english and english.lower() != query.lower():
        queries.append(english)
    found: dict[int, CardmarketProduct] = {}
    for text in queries:
        for product in _catalog_matches(session, game, text, limit * 3):
            found.setdefault(product.id_product, product)
    japanese = japanese_printings(session, game, found.values())
    ordered = sorted(
        found.values(),
        key=lambda p: (p.id_product not in japanese, -(p.avg30_cents or p.trend_cents or 0)),
    )
    return [market_price_out(p, japanese=p.id_product in japanese) for p in ordered[:limit]]


def _catalog_matches(
    session: Session, game: Game, query: str, limit: int
) -> list[CardmarketProduct]:
    statement = select(CardmarketProduct).where(CardmarketProduct.game == game.value)
    if query.strip().isdigit():
        statement = statement.where(CardmarketProduct.id_product == int(query))
    else:
        for word in query.split():
            statement = statement.where(CardmarketProduct.name.icontains(word))
    statement = statement.order_by(
        func.coalesce(CardmarketProduct.avg30_cents, CardmarketProduct.trend_cents, 0).desc()
    ).limit(limit)
    return list(session.scalars(statement))


def japanese_printings(
    session: Session, game: Game, products: Iterable[CardmarketProduct]
) -> set[int]:
    """Ids of the Japanese printings among ``products``.

    Pokémon: the ones the TCGdex index links to a Japanese set. One Piece: those of an
    expansion Cardmarket marks "(Non-English)" or "(Asia Region Legal)".
    """
    products = list(products)
    if game is Game.ONE_PIECE:
        return {p.id_product for p in products if JAPANESE_EXPANSION.search(p.expansion_name or "")}
    ids = [p.id_product for p in products]
    if not ids:
        return set()
    return set(
        session.scalars(select(CardIndexEntry.id_product).where(CardIndexEntry.id_product.in_(ids)))
    )


def product_detail(session: Session, id_product: int) -> MarketPriceOut:
    product = session.get(CardmarketProduct, id_product)
    if product is None:
        raise NotFoundError(f"product {id_product} not found")
    japanese = japanese_printings(session, Game(product.game), [product])
    return market_price_out(product, japanese=bool(japanese))


def price_history(session: Session, id_product: int) -> list[PricePoint]:
    """The resale price of each day recorded, oldest first (see cardmarket.import_prices)."""
    rows = session.scalars(
        select(CardmarketPriceHistory)
        .where(CardmarketPriceHistory.id_product == id_product)
        .order_by(CardmarketPriceHistory.price_date)
    )
    points = []
    for row in rows:
        # The same order as the resale price itself: avg30 first, never the lowest offer.
        cents = next(
            (
                value
                for value in (row.avg30_cents, row.avg7_cents, row.avg_cents, row.avg1_cents)
                if value is not None
            ),
            row.trend_cents,
        )
        if cents is not None:
            points.append(PricePoint(date=row.price_date, cents=cents))
    return points


def list_tracked_cards(
    session: Session, user_id: int, settings: AppSettings
) -> list[TrackedCardOut]:
    cards = session.scalars(
        select(TrackedCard)
        .where(TrackedCard.user_id == user_id)
        .options(selectinload(TrackedCard.listings))
        .order_by(TrackedCard.active.desc(), TrackedCard.name)
    ).all()
    products = _products(session, (c.cardmarket_product_id for c in cards))
    return [
        _tracked_card_out(card, products.get(card.cardmarket_product_id), settings)
        for card in cards
    ]


def tracked_card_detail(
    session: Session, user_id: int, settings: AppSettings, card_id: int
) -> TrackedCardOut:
    card = _get_card(session, user_id, card_id)
    product = (
        session.get(CardmarketProduct, card.cardmarket_product_id)
        if card.cardmarket_product_id
        else None
    )
    return _tracked_card_out(card, product, settings)


def create_tracked_card(
    session: Session, user_id: int, settings: AppSettings, payload: TrackedCardCreate
) -> TrackedCardOut:
    values = payload.model_dump()
    values["game"] = payload.game.value
    values["search_query"] = payload.search_query or default_search_query(
        payload.card_number,
        names.translate(session, payload.game, payload.name, "ja") or payload.name,
    )
    product = (
        session.get(CardmarketProduct, payload.cardmarket_product_id)
        if payload.cardmarket_product_id
        else None
    )
    if not payload.search_query and product is not None:
        values["search_query"] = tracking.template_for(session, product).search_query
    card = TrackedCard(**values, user_id=user_id)
    session.add(card)
    session.commit()
    return tracked_card_detail(session, user_id, settings, card.id)


def update_tracked_card(
    session: Session,
    user_id: int,
    settings: AppSettings,
    card_id: int,
    payload: TrackedCardUpdate,
) -> TrackedCardOut:
    card = _get_card(session, user_id, card_id)
    for name, value in payload.model_dump(exclude_unset=True).items():
        setattr(card, name, value.value if isinstance(value, Game) else value)
    session.commit()
    session.expire_all()
    return tracked_card_detail(session, user_id, settings, card_id)


def delete_tracked_card(session: Session, user_id: int, card_id: int) -> None:
    session.delete(_get_card(session, user_id, card_id))
    session.commit()


def list_deals(
    session: Session,
    user_id: int,
    settings: AppSettings,
    *,
    triage: ListingTriage | None = None,
    tracked_card_id: int | None = None,
    min_roi_percent: Decimal | None = None,
    include_offline: bool = False,
) -> list[DealOut]:
    statement = (
        select(Listing)
        .join(Listing.tracked_card)
        .where(TrackedCard.user_id == user_id)
        .options(selectinload(Listing.tracked_card))
    )
    if triage is None:
        statement = statement.where(Listing.triage != ListingTriage.DISMISSED.value)
    else:
        statement = statement.where(Listing.triage == triage.value)
    if tracked_card_id is not None:
        statement = statement.where(Listing.tracked_card_id == tracked_card_id)
    avoided = sellers.blocked(session)
    listings = [
        listing
        for listing in session.scalars(statement)
        if (listing.source, listing.seller_id) not in avoided
    ]
    products = _products(
        session, (listing.tracked_card.cardmarket_product_id for listing in listings)
    )

    deals = [
        _deal_out(listing, products.get(listing.tracked_card.cardmarket_product_id), settings)
        for listing in listings
    ]
    if not include_offline:
        deals = [d for d in deals if d.online]
    if min_roi_percent is not None:
        floor = min_roi_percent / 100
        deals = [d for d in deals if d.sale and d.sale.roi is not None and d.sale.roi >= floor]
    # Best return first; listings without a resale price go last.
    return sorted(
        deals,
        key=lambda d: (
            d.sale is None or d.sale.roi is None,
            -(d.sale.roi if d.sale and d.sale.roi else 0),
        ),
    )


def update_deal(
    session: Session,
    user_id: int,
    settings: AppSettings,
    listing_id: int,
    triage: ListingTriage,
) -> DealOut:
    listing = session.get(Listing, listing_id)
    if listing is None or listing.tracked_card.user_id != user_id:
        raise NotFoundError(f"listing {listing_id} not found")
    listing.triage = triage.value
    session.commit()
    product = (
        session.get(CardmarketProduct, listing.tracked_card.cardmarket_product_id)
        if listing.tracked_card.cardmarket_product_id
        else None
    )
    return _deal_out(listing, product, settings)


def count_unseen_deals(session: Session, user_id: int, settings: AppSettings) -> int:
    return len(
        list_deals(
            session,
            user_id,
            settings,
            triage=ListingTriage.NEW,
            min_roi_percent=settings.scanner.min_roi_percent,
        )
    )


def mark_new_deals_seen(session: Session, user_id: int) -> int:
    listings = session.scalars(
        select(Listing)
        .join(Listing.tracked_card)
        .where(TrackedCard.user_id == user_id, Listing.triage == ListingTriage.NEW.value)
    ).all()
    for listing in listings:
        listing.triage = ListingTriage.SEEN.value
    session.commit()
    return len(listings)


def card_match_rule(card: TrackedCard, settings: AppSettings, *, with_number: bool = True):  # type: ignore[no-untyped-def]
    return build_rule(
        card_number=card.card_number if with_number else None,
        required=card.required_keywords,
        excluded=card.excluded_keywords,
        grading=card.grading,
        global_excluded=split_keywords(settings.scanner.excluded_keywords),
    )


def within_price_bounds(card: TrackedCard, price_jpy: int) -> bool:
    if card.min_price_jpy is not None and price_jpy < card.min_price_jpy:
        return False
    return card.max_price_jpy is None or price_jpy <= card.max_price_jpy


def record_found_listings(
    session: Session,
    settings: AppSettings,
    card: TrackedCard,
    found: Iterable[FoundListing],
    *,
    now: str,
    unchecked_sources: Iterable[str] = (),
) -> tuple[int, int]:
    """Stores the listings that match ``card``; returns (new listings, new good deals).

    Listings of ``unchecked_sources`` (searches that failed this time) keep counting as
    online rather than looking sold.
    """
    product = (
        session.get(CardmarketProduct, card.cardmarket_product_id)
        if card.cardmarket_product_id
        else None
    )
    # A Japanese printing is matched on the title's set, number and version; the keyword
    # rule still applies its exclusions, grading and required words.
    printing = tracking.printing_of(session, product) if product is not None else None
    rule = card_match_rule(card, settings, with_number=printing is None)
    game = Game(card.game)
    expected = expected_sale_cents(card.target_price_cents, product)
    existing = {(listing.source, listing.external_id): listing for listing in card.listings}
    new_listings = new_deals = 0

    for item in found:
        if not within_price_bounds(card, item.price_jpy):
            continue
        if not match_title(item.title, rule).matched:
            continue
        if printing is not None and not tracking.is_printing(printing, identify(item.title, game)):
            continue
        key = (item.source.value, item.external_id)
        listing = existing.get(key)
        if listing is None:
            listing = Listing(
                tracked_card_id=card.id,
                source=item.source.value,
                external_id=item.external_id,
                first_seen_at=now,
                triage=ListingTriage.NEW.value,
            )
            card.listings.append(listing)
            existing[key] = listing
            new_listings += 1
            estimate = estimate_listing(
                settings,
                price_jpy=item.price_jpy,
                shipping_included=item.shipping_included,
                expected_sale_cents=expected,
            )
            if meets_target(settings, estimate):
                new_deals += 1
        listing.title = item.title
        listing.seller_id = item.seller_id or listing.seller_id
        listing.price_jpy = item.price_jpy
        listing.shipping_included = item.shipping_included
        listing.url = item.url
        listing.thumbnail_url = item.thumbnail_url
        listing.listed_at = item.listed_at
        listing.ends_at = item.ends_at
        listing.bids = item.bids
        listing.condition = item.condition.value if item.condition else None
        listing.last_seen_at = now

    unchecked = set(unchecked_sources)
    for listing in card.listings:
        if listing.source in unchecked and _online(listing, card):
            listing.last_seen_at = now
    card.last_scanned_at = now
    session.commit()
    return new_listings, new_deals


def _get_card(session: Session, user_id: int, card_id: int) -> TrackedCard:
    card = session.get(TrackedCard, card_id)
    if card is None or card.user_id != user_id:
        raise NotFoundError(f"tracked card {card_id} not found")
    return card


def _products(session: Session, ids: Iterable[int | None]) -> dict[int | None, CardmarketProduct]:
    wanted = {i for i in ids if i is not None}
    if not wanted:
        return {}
    rows = session.scalars(
        select(CardmarketProduct).where(CardmarketProduct.id_product.in_(wanted))
    )
    return {p.id_product: p for p in rows}


def _tracked_card_out(
    card: TrackedCard, product: CardmarketProduct | None, settings: AppSettings
) -> TrackedCardOut:
    expected = expected_sale_cents(card.target_price_cents, product)
    visible = [
        listing
        for listing in card.listings
        if listing.triage != ListingTriage.DISMISSED.value and _online(listing, card)
    ]
    rois = []
    for listing in visible:
        estimate = estimate_listing(
            settings,
            price_jpy=listing.price_jpy,
            shipping_included=listing.shipping_included,
            expected_sale_cents=expected,
        )
        if (listing_roi := _estimate_roi(estimate)) is not None:
            rois.append(listing_roi)
    return TrackedCardOut(
        **{name: getattr(card, name) for name in TrackedCardFields.model_fields},
        id=card.id,
        last_scanned_at=card.last_scanned_at,
        market=market_price_out(product) if product else None,
        expected_sale_cents=expected,
        max_buy_price_jpy=max_buy_price_jpy(settings, expected),
        listing_count=len(visible),
        best_roi=max(rois) if rois else None,
    )


def _estimate_roi(estimate: DealEstimate) -> Decimal | None:
    margin = estimate.margin_cents
    return None if margin is None else roi(margin, estimate.landed.total_cents)


def _online(listing: Listing, card: TrackedCard) -> bool:
    # Every scan of a card refreshes last_seen_at of the listings still on sale.
    return card.last_scanned_at is None or listing.last_seen_at >= card.last_scanned_at


def _deal_out(
    listing: Listing, product: CardmarketProduct | None, settings: AppSettings
) -> DealOut:
    card = listing.tracked_card
    expected = expected_sale_cents(card.target_price_cents, product)
    estimate = estimate_listing(
        settings,
        price_jpy=listing.price_jpy,
        shipping_included=listing.shipping_included,
        expected_sale_cents=expected,
    )
    source = SourcePlatform(listing.source)
    return DealOut(
        id=listing.id,
        tracked_card_id=card.id,
        card_name=card.name,
        game=Game(card.game),
        cardmarket_product_id=card.cardmarket_product_id,
        target_price_cents=card.target_price_cents,
        source=source,
        external_id=listing.external_id,
        title=listing.title,
        price_jpy=listing.price_jpy,
        shipping_included=listing.shipping_included,
        url=listing.url,
        neokyo_url=links.neokyo_url(source, listing.external_id),
        thumbnail_url=listing.thumbnail_url,
        listed_at=listing.listed_at,
        ends_at=listing.ends_at,
        bids=listing.bids,
        condition=ListingCondition(listing.condition) if listing.condition else None,
        triage=ListingTriage(listing.triage),
        first_seen_at=listing.first_seen_at,
        last_seen_at=listing.last_seen_at,
        online=_online(listing, card),
        expected_sale_cents=expected,
        landed_cost=landed_cost_out(estimate),
        sale=sale_breakdown_out(estimate),
    )


def landed_cost_out(estimate: DealEstimate) -> LandedCostOut:
    landed = estimate.landed
    return LandedCostOut(
        purchase_cents=landed.purchase_cents,
        proxy_fees_cents=landed.proxy_fees_cents,
        shipping_cents=landed.shipping_cents,
        import_taxes_cents=landed.import_taxes_cents,
        total_cents=landed.total_cents,
        vat_estimated=landed.vat_estimated,
    )


def sale_breakdown_out(estimate: DealEstimate) -> SaleBreakdownOut | None:
    sale = estimate.sale
    if sale is None:
        return None
    margin = sale.net_cents - estimate.landed.total_cents
    return SaleBreakdownOut(
        revenue_cents=sale.revenue_cents,
        platform_fee_cents=sale.platform_fee_cents,
        shipping_cost_cents=sale.shipping_cost_cents,
        packaging_cents=sale.packaging_cents,
        contributions_cents=sale.contributions_cents,
        net_cents=sale.net_cents,
        margin_cents=margin,
        roi=roi(margin, estimate.landed.total_cents),
    )
