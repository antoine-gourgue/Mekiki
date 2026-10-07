"""Reading prices on Vinted (listings) and eBay (sold listings) in the user's Chrome.

The pages are read as the user sees them, once per click in the app. Only listings naming
the card's number, ungraded and alone, count towards the median.
"""

from __future__ import annotations

import re
import statistics
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal
from urllib.parse import urlencode

from mekiki_engine.browser.chrome import ChromeError, Tab
from mekiki_engine.resale.links import EBAY_CARDS_CATEGORY, VINTED_SINGLE_CARDS_CATALOG

Site = Literal["vinted", "ebay"]

HOME_URLS: dict[Site, str] = {
    "vinted": "https://www.vinted.fr/",
    "ebay": "https://www.ebay.fr/",
}
LOGIN_URLS: dict[Site, str] = {
    "vinted": "https://www.vinted.fr/member/signup/select_type?ref_url=%2F",
    "ebay": "https://signin.ebay.fr/signin/",
}
SITE_LABELS: dict[Site, str] = {"vinted": "Vinted", "ebay": "eBay"}

# Signed out, Vinted shows a login button and eBay greets with "Connectez-vous".
CONNECTED_CHECKS: dict[Site, str] = {
    "vinted": "document.readyState === 'complete' && "
    "!document.querySelector('[data-testid=\"header--login-button\"]')",
    "ebay": "(() => { const g = document.querySelector('#gh-ug, .gh-identity'); "
    "return !!g && !/connectez-vous/i.test(g.innerText); })()",
}

VINTED_ITEMS = r"""
(() => {
  const roots = [...document.querySelectorAll('[data-testid^="product-item-id-"]')]
    .filter((e) => /^product-item-id-\d+$/.test(e.dataset.testid));
  return roots.map((root) => {
    const part = (suffix) => root.querySelector(`[data-testid="${root.dataset.testid}${suffix}"]`);
    const link = part('--overlay-link');
    return {
      id: root.dataset.testid.replace('product-item-id-', ''),
      // "Title, Marque: Pokémon, État: Très bon état, 65.00 €, 68.95 €"
      summary: link ? link.title : '',
      url: link ? link.href.split('?')[0] : null,
      price: part('--price-text')?.innerText ?? '',
      condition: part('--description-subtitle')?.innerText ?? null,
      image: part('--image--img')?.src ?? null,
    };
  });
})()
"""

EBAY_SOLD_ITEMS = r"""
(() => [...document.querySelectorAll('li[data-listingid]')]
  // The first cards are ads pointing at a placeholder item.
  .filter((li) => li.querySelector('a[href*="/itm/"]')
    && !li.querySelector('a[href*="/itm/123456"]'))
  .map((li) => {
    const price = li.querySelector('.s-card__price');
    return {
      id: li.dataset.listingid,
      title: (li.querySelector('.s-card__title')?.innerText ?? '').split('\n')[0],
      url: li.querySelector('a[href*="/itm/"]').href.split('?')[0],
      price: price?.innerText ?? '',
      // A struck-through price: the seller accepted a lower offer, amount unknown.
      best_offer: !!price && getComputedStyle(price.querySelector('span') ?? price)
        .textDecorationLine.includes('line-through'),
      sold: li.querySelector('.s-card__caption')?.innerText ?? null,
      shipping: [...li.querySelectorAll('span')].map((s) => s.innerText)
        .find((t) => /livraison/i.test(t)) ?? null,
      image: li.querySelector('img')?.src ?? null,
    };
  }))()
"""

# French prices group thousands with narrow or plain no-break spaces: "1\u202f200,00 €".
_SPACES = r"\s" + chr(0x202F) + chr(0x00A0)
_EUROS = re.compile(rf"(\d[\d{_SPACES}.]*,\d{{2}}|\d+)\s*(?:€|EUR)")
_GRADED = re.compile(
    r"\b(psa|bgs|cgc|pca|ccc|sgc|beckett|collect\s?aura|grad(?:e|é|ée|ing)|gem mint)\b",
    re.IGNORECASE,
)
# Other printings of the same number sell for less than the Japanese one.
_OTHER_LANGUAGE = re.compile(
    r"\b(cor[ée]en(ne)?|korean|kor|chinois(e)?|chinese|chn|s-chinese|t-chinese)\b",
    re.IGNORECASE,
)
_SEVERAL = re.compile(r"\b(lot|lots|x\s?[2-9]|[2-9]\s?x|bundle)\b", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class MarketListing:
    site: Site
    external_id: str
    title: str
    price_cents: int
    url: str
    image_url: str | None
    # Vinted: the item's condition. eBay: "Vendu le 6 oct. 2026".
    detail: str | None
    shipping_cents: int | None = None
    best_offer: bool = False
    # Names the card's number, ungraded and alone: counts towards the median.
    relevant: bool = True


def search_url(site: Site, query: str) -> str:
    if site == "vinted":
        params = {"search_text": query, "catalog[]": VINTED_SINGLE_CARDS_CATALOG}
        return f"https://www.vinted.fr/catalog?{urlencode(params)}"
    params = {
        "_nkw": query,
        "_sacat": EBAY_CARDS_CATEGORY,
        "LH_Sold": 1,
        "LH_Complete": 1,
        "_ipg": 120,
    }
    return f"https://www.ebay.fr/sch/i.html?{urlencode(params)}"


def is_connected(tab: Tab, site: Site) -> bool:
    if not tab.url().startswith(HOME_URLS[site].rstrip("/")):
        tab.navigate(HOME_URLS[site])
    try:
        return bool(tab.wait_for(CONNECTED_CHECKS[site], timeout=8))
    except ChromeError:
        return False


def read_listings(tab: Tab, site: Site, query: str) -> list[dict[str, Any]]:
    """The raw listings of a search page, as the page shows them."""
    tab.navigate(search_url(site, query))
    if site == "ebay" and "signin" in tab.url():
        raise ChromeError("connectez-vous à eBay dans la fenêtre Chrome de Mekiki")
    script = VINTED_ITEMS if site == "vinted" else EBAY_SOLD_ITEMS
    # Results render after the page itself: wait for them, or for an empty search.
    try:
        tab.wait_for(f"({script}).length > 0", timeout=10)
    except ChromeError:
        return []
    return list(tab.evaluate(script) or [])


def parse_listings(
    site: Site,
    raw: list[dict[str, Any]],
    card_number: str | None,
    names: list[str] | None = None,
) -> list[MarketListing]:
    listings = []
    for item in raw:
        price = euro_cents(str(item.get("price") or ""))
        url = item.get("url")
        if price is None or not url:
            continue
        title = str(item.get("title") or "")
        if site == "vinted":
            title = str(item.get("summary") or "").split(", Marque:")[0].strip()
        listings.append(
            MarketListing(
                site=site,
                external_id=str(item.get("id") or url),
                title=title,
                price_cents=price,
                url=str(url),
                image_url=item.get("image"),
                detail=item.get("condition") if site == "vinted" else item.get("sold"),
                shipping_cents=euro_cents(str(item.get("shipping") or "")),
                best_offer=bool(item.get("best_offer")),
                relevant=is_relevant(title, card_number, names),
            )
        )
    return listings


def is_relevant(title: str, card_number: str | None, names: list[str] | None = None) -> bool:
    """Whether a listing sells one ungraded copy of the card numbered ``card_number``.

    With ``names`` (the card's name in several languages), the title must also name it: two
    cards of different sets can share a number.
    """
    if _GRADED.search(title) or _SEVERAL.search(title) or _OTHER_LANGUAGE.search(title):
        return False
    compact = _compact(title)
    if card_number and _compact(card_number) not in compact:
        return False
    return not names or any(_compact(name) in compact for name in names if name.strip())


def median_cents(listings: list[MarketListing]) -> int | None:
    """Median of the relevant listings; accepted offers only when nothing else is left."""
    relevant = [listing for listing in listings if listing.relevant]
    priced = [listing for listing in relevant if not listing.best_offer] or relevant
    if not priced:
        return None
    return round(statistics.median(listing.price_cents for listing in priced))


def euro_cents(text: str) -> int | None:
    match = _EUROS.search(text)
    if match is None:
        return None
    digits = re.sub(rf"[{_SPACES}.]", "", match[1]).replace(",", ".")
    try:
        return round(float(digits) * 100)
    except ValueError:
        return None


def utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _compact(text: str) -> str:
    """ "201 / 165" and "201/165" alike; "OP05-119" and "op05 119" alike."""
    text = unicodedata.normalize("NFKC", text).lower()
    return re.sub(r"[\s\-_/]+", "", text)
