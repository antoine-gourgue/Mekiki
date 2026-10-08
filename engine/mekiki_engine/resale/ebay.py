"""Live eBay listings through the official Browse API.

It needs the keys of an eBay developer application (``MEKIKI_EBAY_CLIENT_ID`` and
``MEKIKI_EBAY_CLIENT_SECRET``); without them the UI only offers links to eBay. Sold
prices have no public API: they stay a link to eBay and Terapeak (see links.py).
"""

from __future__ import annotations

import statistics
import threading
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from mekiki_engine.resale.links import EBAY_CARDS_CATEGORY
from mekiki_engine.scanner.sources.base import PoliteClient, SourceError

TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"
SEARCH_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"
PUBLIC_SCOPE = "https://api.ebay.com/oauth/api_scope"
RESULTS = 50
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
        self._token: tuple[str, float] | None = None
        self._cache: dict[str, tuple[float, EbaySearch]] = {}
        self._lock = threading.Lock()

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
        result = parse_search(response.json())
        with self._lock:
            self._cache[key] = (time.monotonic(), result)
        return result

    def check(self) -> None:
        """Asks eBay for an application token: raises ``SourceError`` when it refuses the keys."""
        self._app_token()

    def _app_token(self) -> str:
        with self._lock:
            if self._token and time.monotonic() < self._token[1]:
                return self._token[0]
        response = self.client.request(
            "POST",
            TOKEN_URL,
            auth=self.credentials,
            data={"grant_type": "client_credentials", "scope": PUBLIC_SCOPE},
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
            self._token = (token, time.monotonic() + lifetime)
        return token


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
