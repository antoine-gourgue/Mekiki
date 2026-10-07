"""Rakuma (fril.jp) search, read from its server-rendered results page."""

from __future__ import annotations

import html
import re

from mekiki_engine.domain import Game, SourcePlatform
from mekiki_engine.scanner.sources.base import FoundListing, PoliteClient

SEARCH_URL = "https://fril.jp/s"
# Rakuma has no card-game category worth filtering on; the game name narrows the results.
GAME_KEYWORDS = {Game.POKEMON: "ポケモンカード", Game.ONE_PIECE: "ワンピースカード"}
PAGE_SIZE = 40

_ITEM_BOX = re.compile(r'<div class="item-box">(.*?)(?=<div class="item-box">|$)', re.S)
_URL = re.compile(r'href="(https://item\.fril\.jp/([0-9a-f]{32}))"')
_NAME = re.compile(r'data-rat-item_name="([^"]*)"')
_PRICE = re.compile(r'data-rat-price="(\d+)"')
_IMAGE = re.compile(r'data-original="([^"]+)"')


class RakumaSource:
    platform = SourcePlatform.RAKUMA

    def __init__(self, client: PoliteClient, game: Game) -> None:
        self.client = client
        self.game = game

    def search(
        self,
        query: str,
        *,
        limit: int = 40,
        price_min_jpy: int | None = None,
        price_max_jpy: int | None = None,
        page: int = 0,
    ) -> list[FoundListing]:
        params: dict[str, str | int] = {
            "query": f"{GAME_KEYWORDS[self.game]} {query}".strip(),
            "sort": "created_at",
            "order": "desc",
            "transaction": "selling",
        }
        if price_min_jpy:
            params["min"] = price_min_jpy
        if price_max_jpy:
            params["max"] = price_max_jpy
        if page:
            params["page"] = page + 1
        # Rakuma answers 404 for a page past the last result.
        response = self.client.request("GET", SEARCH_URL, params=params, accept=(404,))
        if response.status_code == 404:
            return []
        return parse_results(response.text)[:limit]


def parse_results(page: str) -> list[FoundListing]:
    listings: list[FoundListing] = []
    seen: set[str] = set()
    for box in _ITEM_BOX.findall(page):
        url, name, price = _URL.search(box), _NAME.search(box), _PRICE.search(box)
        if not (url and name and price) or url[2] in seen:
            continue
        seen.add(url[2])
        image = _IMAGE.search(box)
        listings.append(
            FoundListing(
                source=SourcePlatform.RAKUMA,
                external_id=url[2],
                title=html.unescape(name[1]),
                price_jpy=int(price[1]),
                url=url[1],
                thumbnail_url=html.unescape(image[1]) if image else None,
                # Rakuma listings are almost all 送料込み, but the results page does not say.
                shipping_included=None,
            )
        )
    return listings
