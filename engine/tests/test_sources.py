"""Marketplace parsers, checked against trimmed copies of real pages (October 2026)."""

import json
from pathlib import Path

import httpx
import pytest

from mekiki_engine.domain import Game, SourcePlatform
from mekiki_engine.scanner import links
from mekiki_engine.scanner.sources import rakuma, yahoo_auctions, yahoo_fleamarket
from mekiki_engine.scanner.sources.base import (
    EEA_BLOCK_MESSAGE,
    PoliteClient,
    SourceError,
    search_safely,
)
from mekiki_engine.scanner.sources.mercari import DPoPSigner, parse_item

FIXTURES = Path(__file__).parent / "fixtures"


def test_rakuma_results() -> None:
    listings = rakuma.parse_results((FIXTURES / "rakuma_search.html").read_text("utf-8"))

    assert len(listings) == 3
    first = listings[0]
    assert first.source is SourcePlatform.RAKUMA
    assert first.external_id == "79f185abd40696dde08a8d672f5e757f"
    assert first.url == "https://item.fril.jp/79f185abd40696dde08a8d672f5e757f"
    assert first.price_jpy == 6180
    assert first.title.startswith("ポケモンカードゲーム")
    assert first.thumbnail_url and first.thumbnail_url.startswith("https://img.fril.jp/")


def test_yahoo_auctions_category_page() -> None:
    page = (FIXTURES / "yahoo_auctions_category.html").read_text("utf-8")

    listings = yahoo_auctions.parse_results(page)

    assert len(listings) == 4
    for listing in listings:
        assert listing.url == f"https://auctions.yahoo.co.jp/jp/auction/{listing.external_id}"
        assert listing.price_jpy > 0
        assert listing.ends_at and listing.ends_at.endswith("Z")
        assert listing.thumbnail_url and listing.thumbnail_url.startswith("https://")
        assert listing.bids is not None


def test_yahoo_auctions_skips_paid_placements() -> None:
    page = (FIXTURES / "yahoo_auctions_search.html").read_text("utf-8")

    listings = yahoo_auctions.parse_results(page)

    # Five products in the excerpt, the first three of them sponsored.
    assert len(listings) == 2
    assert len({listing.external_id for listing in listings}) == 2


def test_yahoo_fleamarket_items() -> None:
    payload = json.loads((FIXTURES / "yahoo_fleamarket_search.json").read_text("utf-8"))

    listings = [yahoo_fleamarket.parse_item(item) for item in payload["items"]]

    assert [listing.external_id for listing in listings if listing] == [
        "z612422448",
        "z612422016",
        "z612382128",
    ]
    first = listings[0]
    assert first is not None
    assert first.price_jpy == 10000
    assert first.shipping_included is True
    assert first.url == "https://paypayfleamarket.yahoo.co.jp/item/z612422448"


def test_mercari_item_parsing() -> None:
    item = {
        "id": "m12596979108",
        "status": "ITEM_STATUS_ON_SALE",
        "name": "かがやくリザードン S10b 011/071",
        "price": "5500",
        "created": "1791377899",
        "thumbnails": ["https://static.mercdn.net/thumb/item/webp/m12596979108_1.jpg"],
        "itemType": "ITEM_TYPE_MERCARI",
        "shippingPayerId": "2",
        "isNoPrice": False,
        "auction": {"bidDeadline": "2026-10-08T11:00:00Z", "totalBid": "5"},
    }

    listing = parse_item(item)

    assert listing is not None
    assert listing.price_jpy == 5500
    assert listing.shipping_included is True
    assert listing.bids == 5
    assert listing.ends_at == "2026-10-08T11:00:00Z"
    assert listing.listed_at is not None
    # Mercari Shops products and placeholder prices are left out.
    assert (
        parse_item({**item, "itemType": "ITEM_TYPE_BEYOND", "id": "2JXpLn8XDAiTfTs9f7YgdD"}) is None
    )
    assert parse_item({**item, "isNoPrice": True}) is None


def test_mercari_dpop_proof_is_a_signed_jwt() -> None:
    proof = DPoPSigner().proof("POST", "https://api.mercari.jp/v2/entities:search")

    header, claims, signature = proof.split(".")
    assert len(signature) == 86  # raw 64-byte ES256 signature, base64url without padding
    assert header and claims


def test_yahoo_europe_block_becomes_a_clear_error() -> None:
    blocked = httpx.MockTransport(
        lambda _request: httpx.Response(403, text="<p>欧州経済領域（EEA）およびイギリスから</p>")
    )
    client = PoliteClient(transport=blocked, intervals_s={}, default_interval_s=0)
    source = yahoo_fleamarket.YahooFleamarketSource(client, Game.POKEMON)

    with pytest.raises(SourceError, match="Europe"):
        search_safely(source, "リザードン", limit=10)
    assert "Neokyo" in EEA_BLOCK_MESSAGE


def test_unexpected_parsing_failures_become_source_errors() -> None:
    class Broken:
        platform = SourcePlatform.MERCARI

        def search(self, query: str, **_kwargs: object) -> list[object]:
            raise KeyError("items")

    with pytest.raises(SourceError, match="KeyError"):
        search_safely(Broken(), "x", limit=1)  # type: ignore[arg-type]


def test_neokyo_links() -> None:
    assert (
        links.neokyo_url(SourcePlatform.MERCARI, "m10009542937")
        == "https://neokyo.com/fr/product/mercari/m10009542937"
    )
    assert links.neokyo_url(SourcePlatform.YAHOO_FLEAMARKET, "z284021328").endswith(
        "/product/yahooFleaMarket/z284021328"
    )
    assert links.neokyo_url(SourcePlatform.OTHER, "x") is None
    search = links.neokyo_search_url(SourcePlatform.YAHOO_AUCTIONS, "リザードン")
    assert search is not None
    assert search.startswith("https://neokyo.com/fr/search/yahoo?keyword=")
    assert "translate=0" in search
