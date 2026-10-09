from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from mekiki_engine.browser import markets, publish
from mekiki_engine.browser.chrome import ChromeError
from mekiki_engine.browser.service import Browsers, MarketPrices
from mekiki_engine.deps import DataDirDep, SessionDep, UserDep
from mekiki_engine.domain import Game, SalePlatform
from mekiki_engine.schemas import (
    BrowserActivity,
    BrowserPricesOut,
    BrowserPricesRequest,
    BrowserSite,
    BrowserStatus,
    LogLine,
    MarketListingOut,
    PublishJobOut,
    PublishRequest,
    SiteConnection,
)
from mekiki_engine.services import photos, sales_import
from mekiki_engine.services.portfolio import get_item

router = APIRouter(prefix="/browser", tags=["browser"])


def _browsers(request: Request) -> Browsers:
    return request.app.state.browsers  # type: ignore[no-any-return]


def _unavailable(error: ChromeError) -> HTTPException:
    return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error))


@router.get("/status")
def browser_status(request: Request, user: UserDep) -> BrowserStatus:
    browsers = _browsers(request)
    return BrowserStatus(
        chrome_installed=browsers.chrome_installed(), running=browsers.running(user.id)
    )


@router.get("/activity")
def browser_activity(request: Request, user: UserDep) -> BrowserActivity:
    current = _browsers(request).activity(user.id)
    return BrowserActivity(
        activity=current.doing,
        running=current.running,
        visible=current.visible,
        log=[LogLine(at=line.at, text=line.text) for line in current.log],
    )


@router.post("/show")
def show_window(request: Request, user: UserDep) -> BrowserActivity:
    _browsers(request).set_visible(user.id, True)
    return browser_activity(request, user)


@router.post("/hide")
def hide_window(request: Request, user: UserDep) -> BrowserActivity:
    _browsers(request).set_visible(user.id, False)
    return browser_activity(request, user)


@router.post("/{site}/open")
def open_site(site: BrowserSite, request: Request, user: UserDep) -> BrowserStatus:
    """Opens the site's sign-in page in the Mekiki Chrome window."""
    try:
        _browsers(request).open_login(user.id, site)
    except ChromeError as error:
        raise _unavailable(error) from error
    return browser_status(request, user)


@router.post("/{site}/check")
def check_site(site: BrowserSite, request: Request, user: UserDep) -> SiteConnection:
    try:
        connected = _browsers(request).is_connected(user.id, site)
    except ChromeError as error:
        raise _unavailable(error) from error
    return SiteConnection(site=site, connected=connected)


@router.post("/ebay/sold")
def ebay_sold(payload: BrowserPricesRequest, request: Request, user: UserDep) -> BrowserPricesOut:
    """Reads a card's sales on eBay's sold search, in Chrome."""
    prices = _browsers(request).sold_prices(
        user.id, payload.query, payload.card_number, payload.names
    )
    return prices_out(prices)


@router.post("/{site}/publish/{item_id}", status_code=status.HTTP_202_ACCEPTED)
def publish_item(
    site: BrowserSite,
    item_id: int,
    payload: PublishRequest,
    request: Request,
    session: SessionDep,
    user: UserDep,
    data_dir: DataDirDep,
) -> PublishJobOut:
    """Fills and sends the site's listing form in Chrome, in the background."""
    item = get_item(session, user.id, item_id)
    listing = publish.Listing(
        game=Game(item.game),
        title=payload.title,
        description=payload.description,
        price_cents=payload.price_cents,
        photos=photos.item_photo_files(session, data_dir, user.id, item_id),
        condition=item.condition,
        grading=item.grading,
    )
    factory = request.app.state.session_factory

    def mark_listed(url: str) -> None:
        # The card shows as for sale on this site, at this price; its eBay item number will
        # match the line of its sale in eBay's orders report.
        with factory() as listed:
            card = get_item(listed, user.id, item_id)
            card.listing_platform = SalePlatform(site).value
            card.listing_price_cents = payload.price_cents
            card.listing_url = url
            card.listing_ref = sales_import.listing_ref(url)
            listed.commit()

    job = _browsers(request).publish(user.id, item_id, site, listing, mark_listed)
    return PublishJobOut.model_validate(job)


@router.get("/{site}/publish/{item_id}")
def publish_status(
    site: BrowserSite, item_id: int, request: Request, user: UserDep
) -> PublishJobOut | None:
    job = _browsers(request).publish_job(user.id, item_id, site)
    return PublishJobOut.model_validate(job) if job else None


def prices_out(prices: MarketPrices) -> BrowserPricesOut:
    relevant = sorted(listing.price_cents for listing in prices.relevant)
    ebay = prices.site == "ebay"
    return BrowserPricesOut(
        site=prices.site,
        query=prices.query,
        listings=[MarketListingOut.model_validate(listing) for listing in prices.listings],
        relevant_count=len(relevant),
        median_cents=prices.median_cents,
        min_cents=relevant[0] if relevant else None,
        max_cents=relevant[-1] if relevant else None,
        sales_30_days=markets.sales_within(prices.listings, 30) if ebay else None,
        sales_90_days=markets.sales_within(prices.listings, 90) if ebay else None,
        fetched_at=prices.fetched_at,
        error=prices.error,
    )
