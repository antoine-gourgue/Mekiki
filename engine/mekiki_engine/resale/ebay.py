"""Live eBay listings through the official Browse API, and sold ones through Marketplace Insights.

It needs the keys of an eBay developer application (the account's own, or
``MEKIKI_EBAY_CLIENT_ID`` and ``MEKIKI_EBAY_CLIENT_SECRET``); without them the UI only offers
links to eBay. Marketplace Insights is a limited release: eBay grants it to the applications it
approves, so most keys are refused its scope and sold prices are read in Chrome instead.
"""

from __future__ import annotations

import statistics
import threading
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from mekiki_engine.resale.links import EBAY_CARDS_CATEGORY
from mekiki_engine.scanner.sources.base import PoliteClient, SourceError

TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"
SEARCH_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"
PUBLIC_SCOPE = "https://api.ebay.com/oauth/api_scope"
INSIGHTS_URL = "https://api.ebay.com/buy/marketplace_insights/v1_beta/item_sales/search"
INSIGHTS_SCOPE = "https://api.ebay.com/oauth/api_scope/buy.marketplace.insights"
# What eBay answers for a scope the application was not granted.
SCOPE_REFUSALS = frozenset({"invalid_scope", "unauthorized_client"})
RESULTS = 50
SOLD_RESULTS = 100
CACHE_S = 30 * 60
# Renew the application token a little before eBay expires it.
TOKEN_MARGIN_S = 120


class EbayKeysRefused(SourceError):
    """eBay turned the application keys down; ``code`` is its OAuth error, "invalid_client"."""

    def __init__(self, code: str, description: str | None) -> None:
        super().__init__(f"{code} : {description}" if description else code)
        self.code = code


@dataclass(frozen=True, slots=True)
class EbayListing:
    item_id: str
    title: str
    price_cents: int
    shipping_cents: int | None
    url: str
    image_url: str | None
    condition: str | None
    country: str | None


@dataclass(frozen=True, slots=True)
class EbaySale:
    """A sold listing of the last 90 days, as Marketplace Insights gives it."""

    item_id: str
    title: str
    price_cents: int
    url: str
    image_url: str | None
    # "2026-10-06".
    sold_on: str | None
    quantity: int


@dataclass(frozen=True, slots=True)
class EbaySearch:
    total: int
    listings: list[EbayListing]

    @property
    def prices(self) -> list[int]:
        return sorted(listing.price_cents for listing in self.listings)

    @property
    def median_cents(self) -> int | None:
        return round(statistics.median(self.prices)) if self.listings else None


class EbayBrowse:
    """Searches eBay with an application token, caching answers for half an hour."""

    def __init__(
        self, client: PoliteClient, client_id: str, client_secret: str, marketplace: str
    ) -> None:
        self.client = client
        self.credentials = (client_id, client_secret)
        self.marketplace = marketplace
        self._tokens: dict[str, tuple[str, float]] = {}
        self._cache: dict[str, tuple[float, EbaySearch]] = {}
        self._lock = threading.Lock()
        # Whether eBay granted these keys Marketplace Insights; None until asked.
        self.insights: bool | None = None

    def search(self, query: str) -> EbaySearch:
        key = query.strip().lower()
        with self._lock:
            cached = self._cache.get(key)
        if cached and time.monotonic() - cached[0] < CACHE_S:
            return cached[1]
        response = self.client.request(
            "GET",
            SEARCH_URL,
            params={
                "q": query,
                "category_ids": EBAY_CARDS_CATEGORY,
                "filter": "buyingOptions:{FIXED_PRICE},priceCurrency:EUR",
                "limit": RESULTS,
            },
            headers={
                "Authorization": f"Bearer {self._app_token()}",
                "X-EBAY-C-MARKETPLACE-ID": self.marketplace,
                "Accept-Language": "fr-FR",
            },
        )
        result = parse_search(_payload(response))
        with self._lock:
            self._cache[key] = (time.monotonic(), result)
        return result

    def check(self) -> None:
        """Asks eBay for an application token: raises ``SourceError`` when it refuses the keys."""
        self._app_token()

    def sold_allowed(self) -> bool:
        """Whether these keys may read sold listings; eBay is asked once, then remembered.

        Raises ``SourceError`` when eBay cannot be reached: nothing is remembered then.
        """
        if self.insights is None:
            try:
                self._app_token(INSIGHTS_SCOPE)
            except EbayKeysRefused as error:
                if error.code not in SCOPE_REFUSALS:
                    raise
                self.insights = False
            else:
                self.insights = True
        return self.insights

    def sold(self, query: str) -> list[EbaySale] | None:
        """The card's sales of the last 90 days, or None when the keys may not read them."""
        if not self.sold_allowed():
            return None
        response = self.client.request(
            "GET",
            INSIGHTS_URL,
            params={
                "q": query,
                "category_ids": EBAY_CARDS_CATEGORY,
                "filter": "priceCurrency:EUR",
                "limit": SOLD_RESULTS,
            },
            headers={
                "Authorization": f"Bearer {self._app_token(INSIGHTS_SCOPE)}",
                "X-EBAY-C-MARKETPLACE-ID": self.marketplace,
                "Accept-Language": "fr-FR",
            },
            accept=(403,),
        )
        if response.status_code == 403:
            # The scope was granted but not this marketplace, or the access was withdrawn.
            self.insights = False
            return None
        return parse_sales(_payload(response))

    def _app_token(self, scope: str = PUBLIC_SCOPE) -> str:
        with self._lock:
            cached = self._tokens.get(scope)
            if cached and time.monotonic() < cached[1]:
                return cached[0]
        response = self.client.request(
            "POST",
            TOKEN_URL,
            auth=self.credentials,
            data={"grant_type": "client_credentials", "scope": scope},
            accept=(400, 401),
        )
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        if response.status_code in (400, 401):
            raise EbayKeysRefused(
                str(payload.get("error") or response.status_code),
                payload.get("error_description"),
            )
        token = payload.get("access_token")
        if not isinstance(token, str):
            raise SourceError("eBay n'a pas fourni de jeton : vérifiez les clés de l'application")
        lifetime = float(payload.get("expires_in", 7200)) - TOKEN_MARGIN_S
        with self._lock:
            self._tokens[scope] = (token, time.monotonic() + lifetime)
        return token


def _payload(response: httpx.Response) -> dict[str, Any]:
    """eBay's JSON answer; a page in its place (a portal, a maintenance notice) is an eBay
    error like any other."""
    try:
        payload = response.json()
    except ValueError as error:
        raise SourceError("eBay a répondu par une page au lieu de ses résultats") from error
    if not isinstance(payload, dict):
        raise SourceError("eBay a répondu par des résultats illisibles")
    return payload


def parse_search(payload: dict[str, Any]) -> EbaySearch:
    listings = []
    for raw in payload.get("itemSummaries") or []:
        price = _cents(raw.get("price"))
        if price is None or not raw.get("itemWebUrl"):
            continue
        listings.append(
            EbayListing(
                item_id=str(raw.get("itemId", "")),
                title=str(raw.get("title", "")),
                price_cents=price,
                shipping_cents=_shipping_cents(raw.get("shippingOptions")),
                url=str(raw["itemWebUrl"]),
                image_url=(raw.get("image") or {}).get("imageUrl"),
                condition=raw.get("condition"),
                country=(raw.get("itemLocation") or {}).get("country"),
            )
        )
    return EbaySearch(total=int(payload.get("total") or len(listings)), listings=listings)


def parse_sales(payload: dict[str, Any]) -> list[EbaySale]:
    sales = []
    for raw in payload.get("itemSales") or []:
        price = _cents(raw.get("lastSoldPrice"))
        if price is None or not raw.get("itemWebUrl"):
            continue
        sold_on = str(raw.get("lastSoldDate") or "")[:10] or None
        quantity = raw.get("totalSoldQuantity")
        sales.append(
            EbaySale(
                item_id=str(raw.get("itemId", "")),
                title=str(raw.get("title", "")),
                price_cents=price,
                url=str(raw["itemWebUrl"]),
                image_url=(raw.get("image") or {}).get("imageUrl"),
                sold_on=sold_on,
                quantity=quantity if isinstance(quantity, int) and quantity > 0 else 1,
            )
        )
    return sales


def _cents(amount: object) -> int | None:
    if not isinstance(amount, dict) or amount.get("currency") != "EUR":
        return None
    try:
        return int((Decimal(str(amount.get("value"))) * 100).to_integral_value())
    except (InvalidOperation, ValueError):
        return None


def _shipping_cents(options: object) -> int | None:
    costs = [
        cost
        for option in options or []
        if isinstance(option, dict) and (cost := _cents(option.get("shippingCost"))) is not None
    ]
    return min(costs) if costs else None
