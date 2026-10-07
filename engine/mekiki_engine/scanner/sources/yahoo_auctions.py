"""Yahoo! Auctions search, read from the data-* attributes of its results page.

Yahoo! JAPAN refuses visitors from the European Economic Area and the UK (HTTP 403), so
this source only works from elsewhere; ``PoliteClient`` turns that refusal into a clear error.
"""

from __future__ import annotations

import html
import re
from datetime import UTC, datetime

from mekiki_engine.domain import Game, SourcePlatform
from mekiki_engine.scanner.sources.base import FoundListing, PoliteClient

SEARCH_URL = "https://auctions.yahoo.co.jp/search/search"
ITEM_URL = "https://auctions.yahoo.co.jp/jp/auction/{id}"
# Pokémon has a real category; One Piece cards are scattered, its brand id finds them.
CATEGORY_PARAMS = {
    Game.POKEMON: {"auccat": 2084241343},
    Game.ONE_PIECE: {"brand_id": 167521},
}

_PRODUCT = re.compile(r'<li class="Product[" ](.*?)(?=<li class="Product[" ]|$)', re.S)


def _attribute(name: str) -> re.Pattern[str]:
    return re.compile(rf'{name}="([^"]*)"')


_ID = _attribute("data-auction-id")
_TITLE = _attribute("data-auction-title")
_PRICE = _attribute("data-auction-price")
_END = _attribute("data-auction-endtime")
_FREE_SHIPPING = _attribute("data-auction-isfreeshipping")
_IMAGE = re.compile(
    r'class="Product__imageData"[^>]*?src="([^"]+)"|src="([^"]+)"[^>]*class="Product__imageData"'
)
_BIDS = re.compile(r'<dd class="Product__bid">\s*(\d+)\s*</dd>')
_VALID_ID = re.compile(r"^[a-z]?\d{9,10}$")


class YahooAuctionsSource:
    platform = SourcePlatform.YAHOO_AUCTIONS

    def __init__(self, client: PoliteClient, game: Game) -> None:
        self.client = client
        self.game = game

    def search(
        self,
        query: str,
        *,
        limit: int = 60,
        price_min_jpy: int | None = None,
        price_max_jpy: int | None = None,
        page: int = 0,
    ) -> list[FoundListing]:
        params: dict[str, str | int] = {
            "p": query,
            "s1": "new",
            "o1": "d",
            "n": (per_page := 100 if limit > 50 else 50),
            # 1-based offset of the first result.
            "b": page * per_page + 1,
            **CATEGORY_PARAMS[self.game],
        }
        if price_min_jpy or price_max_jpy:
            params["price_type"] = "currentprice"
            if price_min_jpy:
                params["min"] = price_min_jpy
            if price_max_jpy:
                params["max"] = price_max_jpy
        response = self.client.request("GET", SEARCH_URL, params=params)
        return parse_results(response.text)[:limit]


def parse_results(page: str) -> list[FoundListing]:
    listings: list[FoundListing] = []
    seen: set[str] = set()
    for block in _PRODUCT.findall(page):
        # The first results of a keyword search are paid placements, often repeated below.
        if "_cl_vmodule:sfdu" in block:
            continue
        item_id, title, price = _ID.search(block), _TITLE.search(block), _PRICE.search(block)
        if not (item_id and title and price) or not _VALID_ID.match(item_id[1]):
            continue
        if item_id[1] in seen:
            continue
        seen.add(item_id[1])
        end, image, bids = _END.search(block), _IMAGE.search(block), _BIDS.search(block)
        free_shipping = _FREE_SHIPPING.search(block)
        listings.append(
            FoundListing(
                source=SourcePlatform.YAHOO_AUCTIONS,
                external_id=item_id[1],
                title=html.unescape(title[1]),
                price_jpy=int(price[1]),
                url=ITEM_URL.format(id=item_id[1]),
                thumbnail_url=html.unescape(image[1] or image[2]) if image else None,
                # Shipping is usually extra on Yahoo Auctions unless flagged free.
                shipping_included=bool(free_shipping and free_shipping[1] == "1"),
                ends_at=_epoch(end[1]) if end else None,
                bids=int(bids[1]) if bids else None,
            )
        )
    return listings


def _epoch(value: str) -> str | None:
    try:
        return datetime.fromtimestamp(int(value), UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (ValueError, OverflowError):
        return None
