"""One Chrome window per account, and the prices it read lately."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from mekiki_engine.browser import markets
from mekiki_engine.browser.chrome import ChromeError, ChromeSession, find_chrome
from mekiki_engine.browser.markets import MarketListing, Site

# Prices read in Chrome are reused for an hour: reading them again means loading the page.
CACHE_S = 60 * 60


@dataclass(frozen=True, slots=True)
class MarketPrices:
    site: Site
    query: str
    listings: list[MarketListing]
    median_cents: int | None
    fetched_at: str
    error: str | None = None

    @property
    def relevant(self) -> list[MarketListing]:
        return [listing for listing in self.listings if listing.relevant]


@dataclass(slots=True)
class _Cached:
    at: float
    prices: MarketPrices


@dataclass(slots=True)
class Browsers:
    """The Chrome session of each account, kept in the data folder (``chrome/<user>``)."""

    data_dir: Path
    session_factory: Callable[[Path], ChromeSession] = ChromeSession
    _sessions: dict[int, ChromeSession] = field(default_factory=dict)
    _cache: dict[tuple[int, Site, str], _Cached] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    @staticmethod
    def chrome_installed() -> bool:
        return find_chrome() is not None

    def session(self, user_id: int) -> ChromeSession:
        with self._lock:
            if user_id not in self._sessions:
                profile = self.data_dir / "chrome" / str(user_id)
                self._sessions[user_id] = self.session_factory(profile)
            return self._sessions[user_id]

    def running(self, user_id: int) -> bool:
        with self._lock:
            session = self._sessions.get(user_id)
        return session is not None and session.running

    def open_login(self, user_id: int, site: Site) -> None:
        """Shows the site's sign-in page in the window, for the user to sign in."""
        with self.session(user_id).page() as tab:
            tab.navigate(markets.LOGIN_URLS[site])

    def is_connected(self, user_id: int, site: Site) -> bool:
        with self.session(user_id).page() as tab:
            return markets.is_connected(tab, site)

    def prices(
        self,
        user_id: int,
        site: Site,
        query: str,
        card_number: str | None = None,
        names: list[str] | None = None,
    ) -> MarketPrices:
        key = (user_id, site, query.strip().lower())
        with self._lock:
            cached = self._cache.get(key)
        if cached and time.monotonic() - cached.at < CACHE_S:
            return cached.prices
        try:
            with self.session(user_id).page() as tab:
                raw = markets.read_listings(tab, site, query)
        except ChromeError as error:
            return MarketPrices(site, query, [], None, markets.utc_now(), error=str(error))
        listings = markets.parse_listings(site, raw, card_number, names)
        prices = MarketPrices(
            site=site,
            query=query,
            listings=listings,
            median_cents=markets.median_cents(listings),
            fetched_at=markets.utc_now(),
        )
        with self._lock:
            self._cache[key] = _Cached(time.monotonic(), prices)
        return prices

    def cached(self, user_id: int, query: str) -> dict[Site, MarketPrices]:
        """Prices already read for ``query``, by site; nothing is loaded."""
        now = time.monotonic()
        found: dict[Site, MarketPrices] = {}
        with self._lock:
            for site in ("vinted", "ebay"):
                entry = self._cache.get((user_id, site, query.strip().lower()))
                if entry and now - entry.at < CACHE_S:
                    found[site] = entry.prices
        return found

    def stop_all(self) -> None:
        with self._lock:
            sessions = list(self._sessions.values())
        for session in sessions:
            session.stop()
