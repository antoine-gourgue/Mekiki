"""Yahoo! Fleamarket (ex-PayPay Fleamarket) search, through the JSON API of its website.

Yahoo! JAPAN refuses visitors from the European Economic Area and the UK (HTTP 403), so
this source only works from elsewhere; ``PoliteClient`` turns that refusal into a clear error.
"""

from __future__ import annotations

from typing import Any

from mekiki_engine.domain import Game, ListingCondition, SourcePlatform
from mekiki_engine.scanner.sources.base import FoundListing, PoliteClient, SourceError

SEARCH_URL = "https://paypayfleamarket.yahoo.co.jp/api/v1/search"
ITEM_URL = "https://paypayfleamarket.yahoo.co.jp/item/{id}"
TRADING_CARDS_CATEGORY = 2420
BRAND_IDS = {Game.POKEMON: 167473, Game.ONE_PIECE: 167521}
# The API's codes for the six conditions, best first.
CONDITIONS = dict(
    zip(("new", "used10", "used20", "used40", "used60", "used80"), ListingCondition, strict=True)
)


class YahooFleamarketSource:
    platform = SourcePlatform.YAHOO_FLEAMARKET

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
            "query": query,
            "results": min(limit, 100),
            "offset": page * min(limit, 100),
            # The API defaults to sold items.
            "itemStatus": "open",
            "sort": "openTime",
            "order": "DESC",
            "categoryIds": TRADING_CARDS_CATEGORY,
            "brandIds": BRAND_IDS[self.game],
        }
        if price_min_jpy:
            params["minPrice"] = price_min_jpy
        if price_max_jpy:
            params["maxPrice"] = price_max_jpy
        response = self.client.request(
            "GET",
            SEARCH_URL,
            params=params,
            headers={
                "Accept": "application/json",
                "Referer": "https://paypayfleamarket.yahoo.co.jp/",
            },
        )
        try:
            items = response.json().get("items") or []
        except ValueError as error:
            raise SourceError("Yahoo Fleamarket a renvoyé une réponse illisible") from error
        return [listing for item in items if (listing := parse_item(item)) is not None]


def parse_item(item: dict[str, Any]) -> FoundListing | None:
    item_id = str(item.get("id") or "")
    if item.get("itemStatus", "OPEN") != "OPEN" or not item_id:
        return None
    try:
        price = int(item["price"])
    except (KeyError, TypeError, ValueError):
        return None
    return FoundListing(
        source=SourcePlatform.YAHOO_FLEAMARKET,
        external_id=item_id,
        title=str(item.get("title") or ""),
        price_jpy=price,
        url=ITEM_URL.format(id=item_id),
        thumbnail_url=item.get("thumbnailImageUrl"),
        # Yahoo Fleamarket prices include shipping.
        shipping_included=True,
        listed_at=item.get("openTime"),
        condition=CONDITIONS.get(str(item.get("condition")).lower()),
    )
