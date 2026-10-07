"""Mercari Japan search, through the JSON API its website uses for anonymous visitors.

The API is undocumented: every call carries a DPoP proof (an ES256-signed JWT) made with a
key pair generated locally, exactly like jp.mercari.com does in the browser. No account is
involved. ``ecdsa`` is pure Python, unlike ``cryptography`` whose compiled module Windows
Smart App Control may block.
"""

from __future__ import annotations

import base64
import hashlib
import json
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from ecdsa import NIST256p, SigningKey
from ecdsa.util import sigencode_string

from mekiki_engine.domain import Game, SourcePlatform
from mekiki_engine.scanner.sources.base import FoundListing, PoliteClient, SourceError

SEARCH_URL = "https://api.mercari.jp/v2/entities:search"
ITEM_URL = "https://jp.mercari.com/item/{id}"
# Leaf categories: ポケモンカードゲーム and ワンピース カードゲーム. Without them a card
# search also returns sleeves, figures and books.
CATEGORY_IDS = {Game.POKEMON: 1289, Game.ONE_PIECE: 1409}
SHIPPING_INCLUDED = "2"  # shippingPayerId: 1 = buyer pays (着払い), 2 = 送料込み


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64json(value: dict[str, Any]) -> str:
    return _b64url(json.dumps(value, separators=(",", ":")).encode())


class DPoPSigner:
    """One key pair and device id per session, a fresh proof per request, as the site does."""

    def __init__(self) -> None:
        self._key = SigningKey.generate(curve=NIST256p)
        point = self._key.get_verifying_key().to_string()  # x (32 bytes) || y (32 bytes)
        self.jwk = {"crv": "P-256", "kty": "EC", "x": _b64url(point[:32]), "y": _b64url(point[32:])}
        self.device_uuid = str(uuid.uuid4())

    def proof(self, method: str, url: str) -> str:
        header = {"typ": "dpop+jwt", "alg": "ES256", "jwk": self.jwk}
        claims = {
            "iat": int(time.time()),
            "jti": str(uuid.uuid4()),
            "htu": url,
            "htm": method,
            "uuid": self.device_uuid,
        }
        signing_input = f"{_b64json(header)}.{_b64json(claims)}".encode()
        # JWS wants the raw r || s signature (64 bytes), not DER.
        signature = self._key.sign_deterministic(
            signing_input, hashfunc=hashlib.sha256, sigencode=sigencode_string
        )
        return f"{signing_input.decode()}.{_b64url(signature)}"


class MercariSource:
    platform = SourcePlatform.MERCARI

    def __init__(self, client: PoliteClient, game: Game) -> None:
        self.client = client
        self.game = game
        self.signer = DPoPSigner()

    def search(
        self,
        query: str,
        *,
        limit: int = 60,
        price_min_jpy: int | None = None,
        price_max_jpy: int | None = None,
        page: int = 0,
    ) -> list[FoundListing]:
        body = search_body(query, CATEGORY_IDS[self.game], limit, self.signer.device_uuid)
        body["searchCondition"]["priceMin"] = price_min_jpy or 0
        body["searchCondition"]["priceMax"] = price_max_jpy or 0
        # The site pages with "v1:1", "v1:2"… after an empty first token.
        body["pageToken"] = f"v1:{page}" if page else ""
        response = self.client.request(
            "POST",
            SEARCH_URL,
            json=body,
            headers={
                "DPoP": self.signer.proof("POST", SEARCH_URL),
                "X-Platform": "web",
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "ja",
            },
        )
        try:
            items = response.json().get("items") or []
        except ValueError as error:
            raise SourceError("Mercari a renvoyé une réponse illisible") from error
        return [listing for item in items if (listing := parse_item(item)) is not None]


def search_body(query: str, category_id: int, page_size: int, device_uuid: str) -> dict[str, Any]:
    """The body jp.mercari.com sends; only ``searchSessionId`` proved strictly required."""
    return {
        "userId": "",
        "config": {"responseToggles": ["QUERY_SUGGESTION_WEB_1"]},
        "pageSize": page_size,
        "pageToken": "",
        "searchSessionId": uuid.uuid4().hex,
        "source": "BaseSerp",
        "indexRouting": "INDEX_ROUTING_UNSPECIFIED",
        "thumbnailTypes": [],
        "searchCondition": {
            "keyword": query,
            "excludeKeyword": "",
            # Despite its name this returns the most recently *updated* listings first.
            "sort": "SORT_CREATED_TIME",
            "order": "ORDER_DESC",
            "status": ["STATUS_ON_SALE"],
            "sizeId": [],
            "categoryId": [category_id],
            "brandId": [],
            "sellerId": [],
            "priceMin": 0,
            "priceMax": 0,
            "itemConditionId": [],
            "shippingPayerId": [],
            "shippingFromArea": [],
            "shippingMethod": [],
            "colorId": [],
            "hasCoupon": False,
            "attributes": [],
            "itemTypes": [],
            "skuIds": [],
            "shopIds": [],
            "excludeShippingMethodIds": [],
        },
        "serviceFrom": "suruga",
        "withItemBrand": True,
        "withItemSize": False,
        "withItemPromotions": True,
        "withItemSizes": True,
        "withShopname": False,
        "useDynamicAttribute": True,
        "withSuggestedItems": True,
        "withOfferPricePromotion": True,
        "withProductSuggest": True,
        "withParentProducts": False,
        "withProductArticles": True,
        "withSearchConditionId": False,
        "withAuction": True,
        "laplaceDeviceUuid": device_uuid,
    }


def parse_item(item: dict[str, Any]) -> FoundListing | None:
    """One search result, or None for what a proxy cannot buy or has no real price."""
    item_id = str(item.get("id") or "")
    # Mercari Shops products (ITEM_TYPE_BEYOND) have other ids and pages that proxies do not
    # reliably support; "no price" listings carry a placeholder price of 9 999 999.
    if item.get("itemType") != "ITEM_TYPE_MERCARI" or not item_id.startswith("m"):
        return None
    if item.get("isNoPrice") or item.get("status") != "ITEM_STATUS_ON_SALE":
        return None
    try:
        price = int(item["price"])
    except (KeyError, TypeError, ValueError):
        return None

    auction = item.get("auction") or None
    thumbnails = item.get("thumbnails") or []
    return FoundListing(
        source=SourcePlatform.MERCARI,
        external_id=item_id,
        title=str(item.get("name") or ""),
        price_jpy=price,
        url=ITEM_URL.format(id=item_id),
        thumbnail_url=thumbnails[0] if thumbnails else None,
        shipping_included=str(item.get("shippingPayerId")) == SHIPPING_INCLUDED,
        listed_at=_epoch_to_iso(item.get("created")),
        ends_at=auction.get("bidDeadline") if auction else None,
        bids=int(auction["totalBid"]) if auction and auction.get("totalBid") else None,
    )


def _epoch_to_iso(value: object) -> str | None:
    try:
        return datetime.fromtimestamp(int(value), UTC).strftime("%Y-%m-%dT%H:%M:%SZ")  # type: ignore[arg-type]
    except (TypeError, ValueError, OverflowError):
        return None
