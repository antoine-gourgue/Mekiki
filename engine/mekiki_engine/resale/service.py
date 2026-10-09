from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from mekiki_engine.browser import markets
from mekiki_engine.browser.markets import MarketListing
from mekiki_engine.browser.service import Browsers, MarketPrices
from mekiki_engine.domain import Game, SalePlatform
from mekiki_engine.models import CardmarketProduct
from mekiki_engine.resale import drafts, links
from mekiki_engine.resale.ebay import EbayBrowse, EbaySale
from mekiki_engine.resale.verdict import card_verdict
from mekiki_engine.scanner import names, tracking
from mekiki_engine.scanner.sources.base import SourceError
from mekiki_engine.schemas import (
    AppSettings,
    CardVerdict,
    EbayListingOut,
    EbayPrices,
    ListingDraftOut,
    ResaleLinks,
    ResalePrices,
)
from mekiki_engine.services.portfolio import get_item, item_detail
from mekiki_engine.services.settings_service import load_ebay_keys


def resale_links(query: str) -> ResaleLinks:
    return ResaleLinks(
        ebay_listings=links.ebay_search_url(query),
        ebay_sold=links.ebay_search_url(query, sold=True),
        ebay_research=links.ebay_research_url(query),
        vinted=links.vinted_search_url(query),
    )


def product_query(session: Session, product_id: int, label: str | None) -> str | None:
    product = session.get(CardmarketProduct, product_id)
    if product is None or not product.name:
        return None
    return drafts.search_query(product.name, drafts.number_in_label(label))


def ebay_for(state: Any, session: Session, user_id: int) -> tuple[EbayBrowse | None, str | None]:
    """The eBay client of the account's own keys, else the engine's (its .env), with where
    the keys come from: "account", "server" or None."""
    keys = load_ebay_keys(session, user_id)
    if keys is None:
        return state.ebay, ("server" if state.ebay is not None else None)
    key = (keys.client_id, keys.client_secret, keys.marketplace)
    if key not in state.ebay_clients:
        state.ebay_clients[key] = EbayBrowse(state.http, *key)
    return state.ebay_clients[key], "account"


def ebay_sold(
    state: Any,
    session: Session,
    user_id: int,
    query: str,
    card_number: str | None = None,
    names: list[str] | None = None,
) -> MarketPrices:
    """A card's sales on eBay: through Marketplace Insights when the keys may read them,
    else in Chrome; kept six hours either way."""
    browsers: Browsers = state.browsers
    if (cached := browsers.cached(user_id, query, log=True)) is not None:
        return cached
    ebay, _source = ebay_for(state, session, user_id)
    if ebay is not None:
        try:
            listings = _api_sales(ebay, query, card_number, names)
        except SourceError:
            # eBay's API is out of reach for now: Chrome still reads the sales.
            listings = None
        if listings is not None:
            prices = MarketPrices(
                site="ebay",
                query=query,
                listings=listings,
                median_cents=markets.median_cents(listings),
                fetched_at=markets.utc_now(),
                source="api",
            )
            browsers.remember(user_id, query, prices)
            return prices
    return browsers.sold_prices(user_id, query, card_number, names)


def _api_sales(
    ebay: EbayBrowse, query: str, card_number: str | None, names: list[str] | None
) -> list[MarketListing] | None:
    """The searches Chrome would make, through the API; None when the keys may not."""
    found: dict[str, EbaySale] = {}
    for each in markets.search_queries(query, card_number, names)[: markets.MAX_QUERIES]:
        sales = ebay.sold(each)
        if sales is None:
            return None
        for sale in sales:
            found.setdefault(sale.item_id or sale.url, sale)
    ordered = sorted(found.values(), key=lambda sale: sale.sold_on or "", reverse=True)
    return [
        MarketListing(
            site="ebay",
            external_id=sale.item_id or sale.url,
            title=sale.title,
            price_cents=sale.price_cents,
            url=sale.url,
            image_url=sale.image_url,
            detail=markets.sold_caption(sale.sold_on),
            sold_on=sale.sold_on,
            relevant=markets.is_relevant(sale.title, card_number, names),
        )
        for sale in ordered
    ]


def resale_prices(
    ebay: EbayBrowse | None,
    query: str,
    card_number: str | None = None,
    names: list[str] | None = None,
) -> ResalePrices:
    return ResalePrices(
        query=query,
        links=resale_links(query),
        ebay=ebay_prices(ebay, query, card_number, names),
    )


def ebay_prices(
    ebay: EbayBrowse | None,
    query: str,
    card_number: str | None = None,
    names: list[str] | None = None,
) -> EbayPrices:
    if ebay is None:
        return EbayPrices(configured=False)
    try:
        search = ebay.search(query)
    except SourceError as error:
        return EbayPrices(configured=True, error=str(error))
    listings = search.listings
    # As for the listings read in Chrome, once the card's number is known only its own
    # single, ungraded copies count: a search also brings other printings, lots and slabs.
    if card_number:
        listings = [
            listing
            for listing in listings
            if markets.is_relevant(listing.title, card_number, names)
        ]
    prices = sorted(listing.price_cents for listing in listings)
    return EbayPrices(
        configured=True,
        total=search.total,
        min_cents=prices[0] if prices else None,
        median_cents=markets.robust_median(prices),
        max_cents=prices[-1] if prices else None,
        listings=[EbayListingOut.model_validate(listing) for listing in listings],
    )


def verdict(
    session: Session,
    settings: AppSettings,
    ebay: EbayBrowse | None,
    user_id: int,
    *,
    item_id: int | None = None,
    product_id: int | None = None,
    label: str | None = None,
    query: str = "",
    price_jpy: int | None = None,
    shipping_included: bool | None = None,
    browsers: Browsers | None = None,
) -> CardVerdict | None:
    """The verdict on a card in stock (``item_id``), a Japanese listing (``price_jpy``) or
    a catalog product; None when there is nothing to search for."""
    landed_cents = None
    typed_name = None
    card_number = drafts.number_in_label(label) or drafts.number_in_label(query)
    if item_id is not None:
        item = get_item(session, user_id, item_id)
        typed_name = item.name
        landed_cents = item_detail(session, user_id, settings, item_id).landed_cost.total_cents
        product_id = item.cardmarket_product_id
        query = query or drafts.item_query(item)
        card_number = item.card_number or card_number
    product = session.get(CardmarketProduct, product_id) if product_id is not None else None
    if product is not None and card_number is None:
        printing = tracking.printing_of(session, product)
        card_number = printing.card_number if printing else None
    if not query and product is not None and product.name:
        query = drafts.search_query(product.name, card_number)
    if not query:
        return None
    market = {}
    if browsers is not None and (sold := browsers.cached(user_id, query)) is not None:
        market["ebay"] = sold
    names_of_card = card_names(session, product, typed_name)
    result = card_verdict(
        settings,
        product,
        resale_prices(ebay, query, card_number, names_of_card),
        price_jpy=price_jpy,
        shipping_included=shipping_included,
        landed_cents=landed_cents,
        selling=item_id is not None,
        market=market,
    )
    result.card_number = card_number
    result.card_names = names_of_card
    result.market_queries = {"ebay": query}
    return result


def card_names(
    session: Session, product: CardmarketProduct | None, typed: str | None = None
) -> list[str]:
    """The card's name in French, English and Japanese: its first word is enough to tell
    it from another card sharing its number ("Dracaufeu", "Charizard", "リザードンex")."""
    found: list[str] = []
    english = drafts.clean_card_name(product.name) if product and product.name else None
    if product is not None and english:
        game = Game(product.game)
        found += [english, names.translate(session, game, english, "fr") or ""]
        printing = tracking.printing_of(session, product)
        if printing and printing.japanese_name:
            found.append(printing.japanese_name)
    if typed:
        found.append(typed)
    words = [name.split()[0] for name in found if name and name.split()]
    return list(dict.fromkeys(word for word in words if len(word) > 2))


def listing_draft(
    session: Session, user_id: int, item_id: int, platform: SalePlatform
) -> ListingDraftOut:
    item = get_item(session, user_id, item_id)
    product = (
        session.get(CardmarketProduct, item.cardmarket_product_id)
        if item.cardmarket_product_id
        else None
    )
    draft = drafts.item_draft(item, product, platform)
    query = drafts.item_query(item)
    return ListingDraftOut(
        platform=platform.value,  # type: ignore[arg-type]
        title=draft.title,
        description=draft.description,
        price_cents=draft.price_cents,
        price_source=draft.price_source,
        new_listing_url=links.NEW_LISTING_URLS[platform],
        query=query,
        links=resale_links(query),
    )
