from __future__ import annotations

from sqlalchemy.orm import Session

from mekiki_engine.domain import SalePlatform
from mekiki_engine.models import CardmarketProduct
from mekiki_engine.resale import drafts, links
from mekiki_engine.resale.ebay import EbayBrowse
from mekiki_engine.scanner.sources.base import SourceError
from mekiki_engine.schemas import (
    EbayListingOut,
    EbayPrices,
    ListingDraftOut,
    ResaleLinks,
    ResalePrices,
)
from mekiki_engine.services.portfolio import get_item


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


def resale_prices(ebay: EbayBrowse | None, query: str) -> ResalePrices:
    return ResalePrices(query=query, links=resale_links(query), ebay=ebay_prices(ebay, query))


def ebay_prices(ebay: EbayBrowse | None, query: str) -> EbayPrices:
    if ebay is None:
        return EbayPrices(configured=False)
    try:
        search = ebay.search(query)
    except SourceError as error:
        return EbayPrices(configured=True, error=str(error))
    prices = search.prices
    return EbayPrices(
        configured=True,
        total=search.total,
        min_cents=prices[0] if prices else None,
        median_cents=search.median_cents,
        max_cents=prices[-1] if prices else None,
        listings=[EbayListingOut.model_validate(listing) for listing in search.listings],
    )


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
