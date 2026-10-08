"""One Chrome window per account, and the prices it read lately."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from mekiki_engine.browser import markets, publish
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
class PublishJob:
    """A listing being published in Chrome, and how it ended."""

    site: Site
    item_id: int
    started_at: str
    status: Literal["running", "done", "failed"] = "running"
    url: str | None = None
    error: str | None = None


PUBLISHERS: dict[Site, Callable[..., str]] = {
    "vinted": publish.publish_vinted,
    "ebay": publish.publish_ebay,
}


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
    _jobs: dict[tuple[int, int, Site], PublishJob] = field(default_factory=dict)
    # What Chrome is doing for each account, shown with the live preview.
    _activity: dict[int, str] = field(default_factory=dict)
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
        """Brings the window on screen on the site's sign-in page, for the user to sign in."""
        session = self.session(user_id)
        with session.page() as tab:
            tab.navigate(markets.LOGIN_URLS[site])
        session.set_visible(True)

    def is_connected(self, user_id: int, site: Site) -> bool:
        session = self.session(user_id)
        with session.page() as tab:
            connected = markets.is_connected(tab, site)
        # Signed in: the window can work out of sight again.
        if connected:
            session.set_visible(False)
        return connected

    def activity(self, user_id: int) -> tuple[str | None, bool, bool]:
        """(what Chrome is doing, whether it is open, whether its window shows)."""
        with self._lock:
            session = self._sessions.get(user_id)
            doing = self._activity.get(user_id)
        if session is None:
            return doing, False, False
        return doing, session.running, session.visible

    def preview(self, user_id: int) -> bytes | None:
        with self._lock:
            session = self._sessions.get(user_id)
        return session.screenshot() if session is not None else None

    def set_visible(self, user_id: int, visible: bool) -> None:
        self.session(user_id).set_visible(visible)

    def _doing(self, user_id: int, step: str | None) -> None:
        with self._lock:
            if step is None:
                self._activity.pop(user_id, None)
            else:
                self._activity[user_id] = step

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
            queries = markets.search_queries(query, card_number, names)
            with self.session(user_id).page() as tab:
                raw = markets.read_listings(
                    tab,
                    site,
                    queries,
                    pages=markets.PAGES[site],
                    progress=lambda step: self._doing(user_id, step),
                )
        except ChromeError as error:
            if isinstance(error, markets.BotChallenge):
                self.session(user_id).set_visible(True)
            return MarketPrices(site, query, [], None, markets.utc_now(), error=str(error))
        finally:
            self._doing(user_id, None)
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

    def publish(
        self,
        user_id: int,
        item_id: int,
        site: Site,
        listing: publish.Listing,
        on_published: Callable[[str], None],
    ) -> PublishJob:
        """Starts publishing in the background; a running job for the same card is reused.

        On success the tab closes and ``on_published`` gets the listing's address; on failure
        the tab stays open on the form, for the user to finish by hand.
        """
        key = (user_id, item_id, site)
        with self._lock:
            running = self._jobs.get(key)
            if running is not None and running.status == "running":
                return running
            job = PublishJob(site=site, item_id=item_id, started_at=markets.utc_now())
            self._jobs[key] = job
        session = self.session(user_id)

        def run() -> None:
            try:
                with session.new_tab() as (tab, target):
                    url = PUBLISHERS[site](
                        tab, listing, progress=lambda step: self._doing(user_id, step)
                    )
                session.close_tab(target)
                job.url = url
                # The card is marked for sale before the job reads as done.
                try:
                    on_published(url)
                # The listing is online whatever happens to the card's record.
                except Exception as error:
                    job.error = f"annonce publiée, mais la carte n'a pas été mise à jour : {error}"
                job.status = "done"
            except ChromeError as error:
                job.error = str(error)
                job.status = "failed"
                # The form stays open: show it for the user to finish.
                session.set_visible(True)
            # A job must always end, or the app would wait on it forever.
            except Exception as error:
                job.error = f"erreur inattendue : {error}"
                job.status = "failed"
            finally:
                self._doing(user_id, None)

        threading.Thread(target=run, name=f"publish-{site}-{item_id}", daemon=True).start()
        return job

    def publish_job(self, user_id: int, item_id: int, site: Site) -> PublishJob | None:
        with self._lock:
            return self._jobs.get((user_id, item_id, site))

    def stop_all(self) -> None:
        with self._lock:
            sessions = list(self._sessions.values())
        for session in sessions:
            session.stop()
