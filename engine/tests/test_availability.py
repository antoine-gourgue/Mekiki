"""Checking that a listing is still for sale, against answers shaped like the real ones."""

import httpx
from conftest import FakeMarketplace
from fastapi.testclient import TestClient

from mekiki_engine.domain import ListingCondition, SourcePlatform
from mekiki_engine.scanner import availability
from mekiki_engine.scanner.availability import check_listing
from mekiki_engine.scanner.sources.base import PoliteClient

RAKUMA_PAGE = """
<meta property="product:availability" content="{availability}">
<meta property="product:price:amount" content="1680">
<tr>
  <th><i class="icon-status icon_item_status item-status-status"></i> 商品の状態</th>
  <td>目立った傷や汚れなし</td>
</tr>
"""


def client_answering(handler) -> PoliteClient:  # type: ignore[no-untyped-def]
    return PoliteClient(
        transport=httpx.MockTransport(handler), intervals_s={}, default_interval_s=0
    )


def mercari_item(status: str) -> dict[str, object]:
    return {
        "result": "OK",
        "data": {
            "id": "m75393041523",
            "status": status,
            "price": 6000,
            "item_condition": {"id": 2, "name": "未使用に近い"},
        },
    }


def test_mercari_listing_on_sale() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=mercari_item("on_sale"))

    result = check_listing(client_answering(handler), SourcePlatform.MERCARI, "m75393041523")

    assert result.available is True
    assert result.status == "en vente"
    assert result.condition is ListingCondition.LIKE_NEW
    assert result.price_jpy == 6000
    assert seen[0].url.params["id"] == "m75393041523"
    assert "DPoP" in seen[0].headers


def test_mercari_listing_sold_or_deleted() -> None:
    sold = client_answering(lambda _r: httpx.Response(200, json=mercari_item("sold_out")))
    deleted = client_answering(lambda _r: httpx.Response(404, json={"result": "error"}))

    assert check_listing(sold, SourcePlatform.MERCARI, "m1234567").available is False
    gone = check_listing(deleted, SourcePlatform.MERCARI, "m1234567")
    assert (gone.available, gone.status) == (False, "supprimée")


def test_rakuma_listing_reads_its_page() -> None:
    item_id = "5574222e3308dc6ffef0a63a45f13bfe"

    def page(availability: str) -> PoliteClient:
        text = RAKUMA_PAGE.format(availability=availability)
        return client_answering(lambda _r: httpx.Response(200, text=text))

    on_sale = check_listing(page("in stock"), SourcePlatform.RAKUMA, item_id)
    sold = check_listing(page("out of stock"), SourcePlatform.RAKUMA, item_id)

    assert on_sale.available is True
    assert on_sale.condition is ListingCondition.GOOD
    assert on_sale.price_jpy == 1680
    assert (sold.available, sold.status) == (False, "vendue")


def test_unknown_ids_and_yahoo_are_not_requested() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("no request expected")

    client = client_answering(handler)

    assert check_listing(client, SourcePlatform.RAKUMA, "../../admin").available is None
    yahoo = check_listing(client, SourcePlatform.YAHOO_AUCTIONS, "x123456789")
    assert yahoo.available is None
    assert "Neokyo" in yahoo.status


def test_a_failing_marketplace_leaves_the_answer_open() -> None:
    blocked = client_answering(lambda _r: httpx.Response(429))

    result = check_listing(blocked, SourcePlatform.MERCARI, "m1234567")

    assert result.available is None
    assert "429" in result.status


def test_a_changed_page_or_status_is_unknown_not_sold(
    client: TestClient, marketplace: FakeMarketplace
) -> None:
    marketplace.item_details["m1000000"] = {"status": "on_hold_new"}
    page = '<meta property="product:availability" content="preorder">'
    rakuma = PoliteClient(
        intervals_s={},
        default_interval_s=0,
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, text=page)),
    )

    mercari = client.get("/listings/mercari/m1000000/availability").json()
    changed = availability.check_listing(rakuma, SourcePlatform.RAKUMA, "a" * 32)

    assert (mercari["available"], changed.available) == (None, None)


def test_the_rakuma_shop_is_read_whatever_the_attribute_order() -> None:
    page = (
        '<meta property="product:availability" content="in stock">'
        '<a href="https://fril.jp/shop/5507d4dd830da1c486defe12789d8bf4" class="shopinfo-wrap '
        'shop_link clearfix" data-x="1"></a>'
    )
    client = PoliteClient(
        intervals_s={},
        default_interval_s=0,
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, text=page)),
    )

    checked = availability.check_listing(client, SourcePlatform.RAKUMA, "a" * 32)

    assert checked.seller_id == "5507d4dd830da1c486defe12789d8bf4"
