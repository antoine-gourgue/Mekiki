"""Reading eBay's sold listings in the user's Chrome, signed in to eBay.

eBay's API only knows the listings still for sale: what a card really sold for is read on
the sold search page, as the user sees it, when the card's panel opens. Only listings naming
the card's number and printing, ungraded and alone, count towards the median. Vinted is only
signed in to, for publishing: its search pages block an address that reads them.
"""

from __future__ import annotations

import re
import statistics
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal
from urllib.parse import urlencode, urlsplit

from mekiki_engine.browser.chrome import ChromeError, Tab
from mekiki_engine.resale.links import EBAY_CARDS_CATEGORY

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
# Cloudflare's and DataDome's checks, which put a challenge page or frame in front, and
# eBay's own, on its /splashui/ pages ("Security Measure").
CHALLENGE_CHECK = (
    "(() => /^(just a moment|un instant|security measure|mesure de sécurité|pardon our "
    "interruption)/i.test(document.title) || location.pathname.startsWith('/splashui/') || "
    '!!document.querySelector(\'iframe[src*="challenges.cloudflare.com"], '
    'iframe[src*="captcha-delivery.com"], #challenge-form\'))()'
)
# eBay's answer to a search without any result: its "no match" block, or a count of 0.
EBAY_NO_RESULTS = (
    "(() => !!document.querySelector('.srp-save-null-search, .s-message--null-search') || "
    "/^0\\s+r[ée]sultat/i.test((document.querySelector('.srp-controls__count-heading')"
    "?.innerText ?? '').trim()))()"
)
EBAY_RESULTS_SHOWN = f"({EBAY_SOLD_ITEMS}).length > 0 || {EBAY_NO_RESULTS}"


class BotChallenge(ChromeError):
    """A site wants the user to prove they are human before going on."""


class UnexpectedPage(ChromeError):
    """The site showed a page Mekiki does not know: the user looks at it in the window."""


class ResultsMissing(ChromeError):
    """The search page never showed its results, nor that there were none."""


_EUROS = re.compile(rf"(\d[\d{_SPACES}.]*,\d{{2}}|\d+)\s*(?:€|EUR)")
# Sellers glue the grade to the grader ("PSA10", "BGS9.5"). ACE, TAG, ARS and AGS only count
# with a grade: Ace is a One Piece character, and "Tag Team" a kind of Pokémon card.
_GRADE = r"\s?\d{1,2}(?:[.,]5)?"
_GRADED = re.compile(
    rf"\b(?:(?:psa|bgs|cgc|pca|ccc|sgc|beckett|collect\s?aura)(?:{_GRADE})?"
    rf"|(?:ace|tag|ars|ags){_GRADE})(?![a-z\d])"
    r"|\b(?:grad(?:ing|ées|ée|ed|é|e)|gem\s?mint|slabs?)\b",
    re.IGNORECASE,
)
# Other printings of the same number sell for less than the Japanese one.
_OTHER_LANGUAGE = re.compile(
    r"\b(cor[ée]en(ne)?|korean|kor|chinois(e)?|chinese|chn|s-chinese|t-chinese)\b",
    re.IGNORECASE,
)
# "x1" is a single copy; "x4", "x10" and a playset are not. A number followed by a slash
# is the card's own: "Mega Charizard X 110/080".
_SEVERAL = re.compile(
    r"\b(?:lots?|bundle|playsets?|x\s?(?:[2-9]|\d{2,})|(?:[2-9]|\d{2,})\s?x)\b(?!\s?/)",
    re.IGNORECASE,
)
# A dot between two letters, as in One Piece names: "Monkey.D.Luffy".
_INNER_DOT = re.compile(r"(?<=\w)\.(?=\w)")
# One Piece codes, "OP05-119" or "P-001": English cards share them with the Japanese ones.
_ONE_PIECE_CODE = re.compile(r"(?:op|st|eb|prb)\d{2}-\d{3}|p-\d{3}", re.IGNORECASE)
_ENGLISH = re.compile(r"\b(?:english|anglais(?:es?)?|eng)\b", re.IGNORECASE)
# How sellers name the printings sharing a number: One Piece's regular, parallel, manga and
# special (SP) versions, and the mirrors of Pokémon commons.
_PRINTING_WORDS: dict[str, re.Pattern[str]] = {
    "manga": re.compile(r"\b(?:manga|comic|super\s?parall[eèé]le?)\b|コミパラ|スーパーパラレル"),
    "parallel": re.compile(
        r"\b(?:parall[eèé]le?|alt(?:ernate|ernative)?[\s\-]?art|aa|p-(?:sec|sr|r|l|uc|c))\b"
        r"|パラレル"
    ),
    "special": re.compile(r"\bsp\b"),
    "masterball": re.compile(r"master\s?ball|マスターボール"),
    "pokeball": re.compile(r"pok[eé]\s?ball|モンスターボール"),
    "loveball": re.compile(r"love\s?ball|ラブボール"),
    "quickball": re.compile(r"quick\s?ball|クイックボール"),
    "reverse": re.compile(r"\b(?:reverse|invers[eé]e?|mirror|miroir)\b|ミラー"),
}
BALL_MIRRORS = frozenset({"masterball", "pokeball", "loveball", "quickball"})
# eBay.fr dates its sold listings "Vendu le 6 oct. 2026".
_SOLD_ON = re.compile(r"(\d{1,2})\s+([a-zéû]+)\.?\s+(\d{4})", re.IGNORECASE)
FRENCH_MONTHS = {
    month: number
    for number, month in enumerate(
        ("janv", "févr", "mars", "avr", "mai", "juin", "juil", "août", "sept", "oct", "nov", "déc"),
        start=1,
    )
}


# Latin letters, accented ones included, end before this code point.
LATIN_END = 0x250
# Sold searches per card, one page of the 120 latest sales each: that covers 90 days of sales
# for most Japanese cards, and opening a card stays a matter of seconds.
MAX_QUERIES = 3
# Prices this many times away from the median are left out of it, from this many listings.
OUTLIER_RATIO = 5
OUTLIER_MIN_COUNT = 4


@dataclass(frozen=True, slots=True)
class MarketListing:
    site: Site
    external_id: str
    title: str
    price_cents: int
    url: str
    image_url: str | None
    # "Vendu le 6 oct. 2026".
    detail: str | None
    shipping_cents: int | None = None
    # eBay: the sale date, "2026-10-06".
    sold_on: str | None = None
    best_offer: bool = False
    # Names the card's number, ungraded and alone: counts towards the median.
    relevant: bool = True


def search_url(query: str) -> str:
    """eBay.fr's search of the sold listings."""
    params = {
        "_nkw": query,
        "_sacat": EBAY_CARDS_CATEGORY,
        "LH_Sold": 1,
        "LH_Complete": 1,
        "_ipg": 120,
        # Latest sales first: the pages read then cover the last weeks, for the sale count.
        "_sop": 13,
    }
    return f"https://www.ebay.fr/sch/i.html?{urlencode(params)}"


def search_queries(query: str, card_number: str | None, names: list[str] | None) -> list[str]:
    """The search as asked, then the number with each Latin name of the card: Japanese cards
    are rare among the results, and sellers name them in French or in English."""
    queries = [query]
    if card_number:
        queries += [f"{name} {card_number}" for name in names or [] if _latin(name)]
    unique: dict[str, str] = {}
    for each in queries:
        # eBay takes "Monkey.D.Luffy" as one word, which sellers seldom write.
        words = " ".join(spaced_dots(each).split())
        unique.setdefault(words.lower(), words)
    return list(unique.values())


def spaced_dots(text: str) -> str:
    """ "Monkey.D.Luffy" → "Monkey D Luffy"; "Mr. Mime" is left alone."""
    return _INNER_DOT.sub(" ", text)


def is_connected(tab: Tab, site: Site) -> bool:
    if not tab.url().startswith(HOME_URLS[site].rstrip("/")):
        tab.navigate(HOME_URLS[site])
    try:
        return bool(tab.wait_for(CONNECTED_CHECKS[site], timeout=8))
    except ChromeError:
        return False


class SignInRequired(ChromeError):
    """The site sent the window to its sign-in page."""


def read_listings(
    tab: Tab,
    queries: list[str],
    *,
    progress: Callable[[str], None] = lambda _step: None,
    pause: Callable[[], None] = lambda: None,
) -> list[dict[str, Any]]:
    """The raw sold listings of the searches, as the pages show them; ``pause`` runs between
    two searches.

    Every search must show its results or eBay's word that there are none: anything else
    raises, so that a page that failed is never taken for a card without sales.
    """
    found: dict[str, dict[str, Any]] = {}
    for index, query in enumerate(queries[:MAX_QUERIES]):
        if index:
            pause()
        progress(f"eBay : ventes réussies « {query} »")
        tab.navigate(search_url(query))
        check_search_page(tab)
        # Results render after the page itself: wait for them, or for an empty search.
        try:
            tab.wait_for(EBAY_RESULTS_SHOWN, timeout=10)
        except ChromeError as error:
            # A challenge can also come up once the page is there.
            check_search_page(tab)
            raise ResultsMissing(
                "eBay n'a pas affiché les résultats de la recherche : relancez la lecture"
            ) from error
        for item in tab.evaluate(EBAY_SOLD_ITEMS) or []:
            found.setdefault(str(item.get("id")), item)
    return list(found.values())


def check_search_page(tab: Tab) -> None:
    """Stops unless the window shows eBay's search page: its sign-in page, a challenge or
    any other page is left to the user."""
    url = tab.url()
    if "signin" in url:
        raise SignInRequired("connectez-vous à eBay dans la fenêtre Chrome de Mekiki")
    check_bot_challenge(tab)
    parts = urlsplit(url)
    if not (parts.hostname or "").endswith("ebay.fr") or not parts.path.startswith("/sch/"):
        raise UnexpectedPage(
            "eBay a ouvert une page inattendue : regardez la fenêtre Chrome de Mekiki, "
            "puis relancez"
        )


def check_bot_challenge(tab: Tab) -> None:
    """Stops when the site asks to prove a human is there: the user answers it in the
    window, Mekiki never does."""
    if "/splashui/" in tab.url() or tab.evaluate(CHALLENGE_CHECK):
        raise BotChallenge(
            "le site demande une vérification anti-robot : passez-la dans la fenêtre Chrome "
            "de Mekiki, puis relancez"
        )


def parse_listings(
    raw: list[dict[str, Any]],
    card_number: str | None,
    names: list[str] | None = None,
    version: str | None = None,
) -> list[MarketListing]:
    listings = []
    for item in raw:
        price = euro_cents(str(item.get("price") or ""))
        url = item.get("url")
        if price is None or not url:
            continue
        title = str(item.get("title") or "")
        listings.append(
            MarketListing(
                site="ebay",
                external_id=str(item.get("id") or url),
                title=title,
                price_cents=price,
                url=str(url),
                image_url=item.get("image"),
                detail=item.get("sold"),
                shipping_cents=euro_cents(str(item.get("shipping") or "")),
                sold_on=sold_date(str(item.get("sold") or "")),
                best_offer=bool(item.get("best_offer")),
                relevant=is_relevant(title, card_number, names, version),
            )
        )
    return listings


def is_relevant(
    title: str,
    card_number: str | None,
    names: list[str] | None = None,
    version: str | None = None,
) -> bool:
    """Whether a listing sells one ungraded copy of the card numbered ``card_number``;
    never without a number.

    With ``names`` (the card's name in several languages), the title must also name it: two
    cards of different sets can share a number. With ``version`` (see ``same_printing``), it
    must sell that printing, not another sharing the number.
    """
    if not single_copy(title):
        return False
    # Without the number, a name alone matches every printing of the card.
    if not card_number:
        return False
    text = unicodedata.normalize("NFKC", title).lower()
    one_piece = _ONE_PIECE_CODE.fullmatch(card_number.strip()) is not None
    if one_piece and _ENGLISH.search(text):
        return False
    number = re.findall(r"[a-z0-9]+", unicodedata.normalize("NFKC", card_number).lower())
    # Digits around the number make another one: "025" is not in "2025".
    pattern = r"(?<!\d)" + r"[\s\-_/]*".join(map(re.escape, number)) + r"(?!\d)"
    if not number or not re.search(pattern, text):
        return False
    compact = _compact(title)
    if names and not any(_compact(name) in compact for name in names if name.strip()):
        return False
    return version is None or same_printing(text, version, one_piece=one_piece)


def single_copy(title: str) -> bool:
    """Whether a title sells one ungraded copy, in Japanese as far as it tells."""
    return not (_GRADED.search(title) or _SEVERAL.search(title) or _OTHER_LANGUAGE.search(title))


def same_printing(text: str, version: str, *, one_piece: bool) -> bool:
    """Whether a lowercase title names the printing ``version`` and no other sharing its
    number: One Piece's "regular", "parallel" or "manga"; Pokémon's "regular" or a mirror,
    "reverse", "masterball", "pokeball"…"""
    named = {kind for kind, words in _PRINTING_WORDS.items() if words.search(text)}
    if one_piece:
        if version == "manga":
            return "manga" in named
        if named & {"manga", "special"}:
            return False
        return ("parallel" in named) == (version == "parallel")
    balls = named & BALL_MIRRORS
    if version in BALL_MIRRORS:
        return balls == {version}
    if balls:
        return False
    return ("reverse" in named) == (version != "regular")


def number_key(card_number: str | None) -> str:
    """The card number as compared: "201 / 165" and "201/165" alike."""
    return _compact(card_number or "")


def median_cents(listings: list[MarketListing]) -> int | None:
    """Median of the relevant listings, without the prices far from the others.

    Accepted offers only count when nothing else is left. A price five times above or
    below the first median is another product slipping through (a sleeve, a lot, a graded
    copy described without its grade) and is left out.
    """
    relevant = [listing for listing in listings if listing.relevant]
    priced = [listing for listing in relevant if not listing.best_offer] or relevant
    return robust_median([listing.price_cents for listing in priced])


def robust_median(prices: list[int]) -> int | None:
    """Median of ``prices`` once those five times above or below the first median are out."""
    if not prices:
        return None
    first = statistics.median(prices)
    if len(prices) >= OUTLIER_MIN_COUNT:
        kept = [p for p in prices if first / OUTLIER_RATIO <= p <= first * OUTLIER_RATIO]
        prices = kept or prices
    return round(statistics.median(prices))


def sold_date(text: str) -> str | None:
    """ "Vendu le 6 oct. 2026" → "2026-10-06"."""
    match = _SOLD_ON.search(unicodedata.normalize("NFC", text))
    month = FRENCH_MONTHS.get(match[2].lower()) if match else None
    if match is None or month is None:
        return None
    try:
        return date(int(match[3]), month, int(match[1])).isoformat()
    except ValueError:
        return None


def sold_caption(day: str | None) -> str | None:
    """ "2026-10-06" → "Vendu le 6 oct. 2026", as eBay.fr writes it."""
    try:
        sold = date.fromisoformat(day or "")
    except ValueError:
        return None
    month = next(name for name, number in FRENCH_MONTHS.items() if number == sold.month)
    dotted = month if month in ("mars", "mai", "juin", "août") else f"{month}."
    return f"Vendu le {sold.day} {dotted} {sold.year}"


def sales_within(listings: list[MarketListing], days: int, today: date | None = None) -> int:
    """Relevant sales dated within the last ``days`` days."""
    since = ((today or datetime.now(UTC).date()) - timedelta(days=days)).isoformat()
    return sum(
        1
        for listing in listings
        if listing.relevant and listing.sold_on is not None and listing.sold_on > since
    )


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


def _latin(text: str) -> bool:
    """Written in Latin letters, accents included ("Mélofée", not "リザードン")."""
    return all(ord(char) < LATIN_END for char in text)


def _compact(text: str) -> str:
    """ "201 / 165" and "201/165" alike; "OP05-119" and "op05 119" alike; "Monkey.D.Luffy" and
    "Monkey D. Luffy" alike."""
    text = unicodedata.normalize("NFKC", text).lower()
    return re.sub(r"[\s\-_/.]+", "", text)
