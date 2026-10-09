"""Whether a Japanese listing is still for sale, asked of its marketplace when opened.

Search results age: a discovery is kept until the next one and a favorite until removed,
and the cards sell meanwhile. One request per listing opened, never in bulk.
"""

from __future__ import annotations

import html
import re
from datetime import UTC, datetime

from mekiki_engine.domain import SourcePlatform
from mekiki_engine.scanner import sellers
from mekiki_engine.scanner.sources.base import JAPANESE_CONDITIONS, PoliteClient, SourceError
from mekiki_engine.scanner.sources.mercari import CONDITIONS as MERCARI_CONDITIONS
from mekiki_engine.scanner.sources.mercari import DPoPSigner
from mekiki_engine.schemas import ListingAvailability

MERCARI_ITEM_URL = "https://api.mercari.jp/items/get"
RAKUMA_ITEM_URL = "https://item.fril.jp/{id}"
# Ids end up in URLs: anything else than the marketplace's own shape is refused.
VALID_IDS = {
    SourcePlatform.MERCARI: re.compile(r"^m\d{6,14}$"),
    SourcePlatform.RAKUMA: re.compile(r"^[0-9a-f]{32}$"),
}
MERCARI_STATUSES = {
    "on_sale": (True, "en vente"),
    "trading": (False, "vendue, transaction en cours"),
    "sold_out": (False, "vendue"),
    "stop": (False, "mise en pause par le vendeur"),
}

_RAKUMA_AVAILABILITY = re.compile(r'<meta property="product:availability" content="([^"]*)"')
_RAKUMA_PRICE = re.compile(r'<meta property="product:price:amount" content="(\d+)"')
_RAKUMA_CONDITION = re.compile(r"商品の状態\s*</th>\s*<td>\s*([^<]+?)\s*</td>")
_RAKUMA_DESCRIPTION = re.compile(
    r'class="item__description only__pc">.*?class="item__description__line-limited">(.*?)</div>',
    re.DOTALL,
)
_RAKUMA_PROFILE = re.compile(r'class="shop__profile__line-limited"[^>]*>(.*?)</div>', re.DOTALL)
# The seller's shop, whose id stays the same across their listings.
_RAKUMA_SHOP = re.compile(
    r'class="shopinfo-wrap shop_link[^"]*"\s+href="https://fril\.jp/shop/([0-9a-f]+)"'
)
# Rakuma's ratings: sun (good), cloud (fair) and rain (bad).
_RAKUMA_RATINGS = {
    kind: re.compile(rf'icon_review_{kind}"></i>\s*<span>(\d+)</span>')
    for kind in ("sun", "cloud", "rain")
}
_LINE_BREAK = re.compile(r"<br\s*/?>", re.IGNORECASE)
_TAG = re.compile(r"<[^>]+>")


def check_listing(
    client: PoliteClient, source: SourcePlatform, external_id: str
) -> ListingAvailability:
    pattern = VALID_IDS.get(source)
    if pattern is None:
        return _unknown(
            "vérification impossible depuis l'Europe : ouvrez l'annonce sur Neokyo"
            if source in (SourcePlatform.YAHOO_AUCTIONS, SourcePlatform.YAHOO_FLEAMARKET)
            else "vérification impossible pour ce site"
        )
    if not pattern.match(external_id):
        return _unknown("identifiant d'annonce inconnu")
    try:
        if source is SourcePlatform.MERCARI:
            return _mercari(client, external_id)
        return _rakuma(client, external_id)
    except SourceError as error:
        return _unknown(f"vérification impossible : {error}")
    # A changed page or API costs the check, not the listing panel.
    except (ValueError, KeyError, TypeError) as error:
        return _unknown(f"réponse inattendue ({error.__class__.__name__})")


def _mercari(client: PoliteClient, item_id: str) -> ListingAvailability:
    response = client.request(
        "GET",
        MERCARI_ITEM_URL,
        params={"id": item_id},
        headers={
            "DPoP": DPoPSigner().proof("GET", MERCARI_ITEM_URL),
            "X-Platform": "web",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "ja",
        },
        accept=(404,),
    )
    if response.status_code == 404:
        return ListingAvailability(available=False, status="supprimée", checked_at=_now())
    data = response.json().get("data") or {}
    status = str(data.get("status") or "")
    available, label = MERCARI_STATUSES.get(status, (False, f"plus en vente ({status})"))
    condition = (data.get("item_condition") or {}).get("id")
    price = data.get("price")
    seller = (data.get("seller") or {}).get("id")
    return ListingAvailability(
        available=available,
        status=label,
        condition=MERCARI_CONDITIONS.get(str(condition)),
        price_jpy=int(price) if price is not None else None,
        checked_at=_now(),
        seller_id=str(seller) if seller else None,
        seller_warning=sellers.seller_problem(data),
        description=_clean(str(data.get("description") or "")),
    )


def _rakuma(client: PoliteClient, item_id: str) -> ListingAvailability:
    response = client.request("GET", RAKUMA_ITEM_URL.format(id=item_id), accept=(404,))
    if response.status_code == 404:
        return ListingAvailability(available=False, status="supprimée", checked_at=_now())
    page = response.text
    availability = _RAKUMA_AVAILABILITY.search(page)
    if availability is None:
        return _unknown("page Rakuma illisible")
    available = availability[1].strip().lower() == "in stock"
    condition = _RAKUMA_CONDITION.search(page)
    price = _RAKUMA_PRICE.search(page)
    text = _page_text(_RAKUMA_DESCRIPTION.search(page))
    profile = _page_text(_RAKUMA_PROFILE.search(page))
    shop = _RAKUMA_SHOP.search(page)
    ratings = {
        kind: int(found[1]) if (found := pattern.search(page)) else 0
        for kind, pattern in _RAKUMA_RATINGS.items()
    }
    return ListingAvailability(
        available=available,
        status="en vente" if available else "vendue",
        condition=JAPANESE_CONDITIONS.get(html.unescape(condition[1])) if condition else None,
        price_jpy=int(price[1]) if price else None,
        checked_at=_now(),
        seller_id=shop[1] if shop else None,
        seller_warning=sellers.refusal_in(text or "", profile or "")
        or sellers.ratings_problem(ratings["rain"], sum(ratings.values())),
        description=text,
    )


def _page_text(found: re.Match[str] | None) -> str | None:
    """The text of an HTML fragment of the page, with its line breaks."""
    return _clean(_TAG.sub("", _LINE_BREAK.sub("\n", found[1]))) if found else None


def _clean(text: str) -> str | None:
    """A description's text, unescaped, without blank lines at either end."""
    lines = [line.strip() for line in html.unescape(text).splitlines()]
    return "\n".join(lines).strip() or None


def _unknown(status: str) -> ListingAvailability:
    return ListingAvailability(available=None, status=status, checked_at=_now())


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
