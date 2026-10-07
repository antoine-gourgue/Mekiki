"""Links the UI opens in the browser: Cardmarket products and Neokyo purchase pages."""

from __future__ import annotations

from urllib.parse import urlencode

from mekiki_engine.domain import Game, SourcePlatform

_CARDMARKET_GAMES = {Game.POKEMON: "Pokemon", Game.ONE_PIECE: "OnePiece"}

# Neokyo's provider keys in its URLs (it now brands Yahoo as "JDirectItems").
NEOKYO_PROVIDERS = {
    SourcePlatform.MERCARI: "mercari",
    SourcePlatform.YAHOO_AUCTIONS: "yahoo",
    SourcePlatform.YAHOO_FLEAMARKET: "yahooFleaMarket",
    SourcePlatform.RAKUMA: "rakuma",
}
NEOKYO_LANGUAGE = "fr"


def cardmarket_product_url(game: Game, id_product: int) -> str:
    # Cardmarket redirects this to the product page (cardmarket.com itself sits behind
    # Cloudflare: open it in a browser, never fetch it from the engine).
    return (
        f"https://www.cardmarket.com/en/{_CARDMARKET_GAMES[game]}/Products?idProduct={id_product}"
    )


def neokyo_url(source: SourcePlatform, external_id: str) -> str | None:
    """Neokyo page to buy a listing through the proxy, or None when it cannot be built."""
    provider = NEOKYO_PROVIDERS.get(source)
    if provider is None or not external_id:
        return None
    return f"https://neokyo.com/{NEOKYO_LANGUAGE}/product/{provider}/{external_id}"


def neokyo_search_url(source: SourcePlatform, keyword: str) -> str | None:
    """Neokyo's own search on one marketplace, e.g. Yahoo when it is unreachable from Europe."""
    provider = NEOKYO_PROVIDERS.get(source)
    if provider is None:
        return None
    query = urlencode({"keyword": keyword, "provider": provider, "translate": 0})
    return f"https://neokyo.com/{NEOKYO_LANGUAGE}/search/{provider}?{query}"
