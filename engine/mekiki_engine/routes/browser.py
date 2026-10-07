from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from mekiki_engine.browser.chrome import ChromeError
from mekiki_engine.browser.service import Browsers, MarketPrices
from mekiki_engine.deps import UserDep
from mekiki_engine.schemas import (
    BrowserPricesOut,
    BrowserPricesRequest,
    BrowserSite,
    BrowserStatus,
    MarketListingOut,
    SiteConnection,
)

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


@router.post("/{site}/prices")
def site_prices(
    site: BrowserSite, payload: BrowserPricesRequest, request: Request, user: UserDep
) -> BrowserPricesOut:
    """Reads a search on the site in Chrome: Vinted listings, or eBay sold listings."""
    prices = _browsers(request).prices(
        user.id, site, payload.query, payload.card_number, payload.names
    )
    return prices_out(prices)


def prices_out(prices: MarketPrices) -> BrowserPricesOut:
    relevant = sorted(listing.price_cents for listing in prices.relevant)
    return BrowserPricesOut(
        site=prices.site,
        query=prices.query,
        listings=[MarketListingOut.model_validate(listing) for listing in prices.listings],
        relevant_count=len(relevant),
        median_cents=prices.median_cents,
        min_cents=relevant[0] if relevant else None,
        max_cents=relevant[-1] if relevant else None,
        fetched_at=prices.fetched_at,
        error=prices.error,
    )
