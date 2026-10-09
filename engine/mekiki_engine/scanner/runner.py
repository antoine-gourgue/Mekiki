"""Runs searches: the scheduled scan of tracked cards and one-off searches from the UI."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from mekiki_engine.domain import Game, SourcePlatform
from mekiki_engine.models import CardmarketProduct, TrackedCard, User
from mekiki_engine.scanner import card_index, cardmarket, links, names, tracking
from mekiki_engine.scanner.matching import build_rule, match_title, split_keywords
from mekiki_engine.scanner.pricing import estimate_listing, expected_sale_cents
from mekiki_engine.scanner.service import (
    landed_cost_out,
    record_found_listings,
    sale_breakdown_out,
    utc_now,
)
from mekiki_engine.scanner.sources.base import (
    FoundListing,
    PoliteClient,
    Source,
    SourceError,
    search_safely,
)
from mekiki_engine.scanner.sources.registry import build_source
from mekiki_engine.schemas import (
    AppSettings,
    ScanStatus,
    SearchRequest,
    SearchResponse,
    SearchResultOut,
)
from mekiki_engine.services.settings_service import load_settings

logger = logging.getLogger(__name__)
# A scan that crashed is tried again after this long, not at the next minute's tick: the same
# crash would otherwise send every search of every card to the sites each minute.
FAILED_SCAN_RETRY = timedelta(minutes=30)

SOURCE_LABELS = {
    SourcePlatform.MERCARI: "Mercari",
    SourcePlatform.RAKUMA: "Rakuma",
    SourcePlatform.YAHOO_AUCTIONS: "Yahoo Auctions",
    SourcePlatform.YAHOO_FLEAMARKET: "Yahoo Fleamarket",
}
RESULTS_PER_SEARCH = 60
# A tracked card is searched several ways, each over a few pages: the listings that name
# it exactly are few among everything the marketplaces return.
TRACKED_RESULTS_PER_PAGE = 120
TRACKED_PAGES_PER_QUERY = 3

SourceFactory = Callable[[SourcePlatform, PoliteClient, Game], Source]


@dataclass(slots=True)
class ScanOutcome:
    cards_scanned: int = 0
    new_listings: int = 0
    new_deals: int = 0
    errors: list[str] = field(default_factory=list)


def refresh_reference_data(session: Session, client: PoliteClient) -> list[str]:
    """Cardmarket prices and the card index, shared by every account."""
    errors: list[str] = []
    for game in Game:
        errors += cardmarket.refresh(session, client, game)
    # Before the card index, which translates the names of the cards it links.
    if error := names.refresh(session, client):
        errors.append(error)
    if error := card_index.refresh(session, client):
        errors.append(error)
    return errors


def scan_tracked_cards(
    session: Session,
    client: PoliteClient,
    user_id: int,
    *,
    source_factory: SourceFactory = build_source,
    should_stop: Callable[[], bool] = lambda: False,
) -> ScanOutcome:
    """Searches every active tracked card of one account on its enabled marketplaces."""
    settings = load_settings(session, user_id)
    outcome = ScanOutcome(errors=refresh_reference_data(session, client))
    cards = session.scalars(
        select(TrackedCard)
        .where(TrackedCard.user_id == user_id, TrackedCard.active.is_(True))
        .order_by(TrackedCard.id)
    ).all()
    for card in cards:
        if should_stop():
            break
        game = Game(card.game)
        product = (
            session.get(CardmarketProduct, card.cardmarket_product_id)
            if card.cardmarket_product_id
            else None
        )
        printing = tracking.printing_of(session, product) if product is not None else None
        queries = tracking.search_queries(session, card, printing)
        found, failed, errors = _search_card(
            client,
            source_factory,
            settings.scanner.sources,
            game,
            queries,
            should_stop=should_stop,
        )
        outcome.errors += [f"{source} ({card.name}) : {error}" for source, error in errors]
        new_listings, new_deals = record_found_listings(
            session, settings, card, found, now=utc_now(), unchecked_sources=failed
        )
        outcome.cards_scanned += 1
        outcome.new_listings += new_listings
        outcome.new_deals += new_deals
    return outcome


def _search_card(
    client: PoliteClient,
    source_factory: SourceFactory,
    platforms: list[SourcePlatform],
    game: Game,
    queries: list[str],
    *,
    should_stop: Callable[[], bool],
) -> tuple[list[FoundListing], set[str], list[tuple[str, str]]]:
    """Every listing the ``queries`` find, over a few pages on each marketplace.

    Returns the listings (each once), the marketplaces that failed and their errors.
    """
    found: dict[tuple[str, str], FoundListing] = {}
    failed: set[str] = set()
    errors: list[tuple[str, str]] = []
    lock = threading.Lock()

    def browse(platform: SourcePlatform) -> None:
        source = source_factory(platform, client, game)
        for query in queries:
            for page in range(TRACKED_PAGES_PER_QUERY):
                if should_stop():
                    return
                try:
                    items = search_safely(source, query, limit=TRACKED_RESULTS_PER_PAGE, page=page)
                except SourceError as error:
                    with lock:
                        failed.add(platform.value)
                        errors.append((SOURCE_LABELS[platform], str(error)))
                    return
                with lock:
                    for item in items:
                        found.setdefault((item.source.value, item.external_id), item)
                # A short page is the last one.
                if len(items) < TRACKED_RESULTS_PER_PAGE:
                    break

    # Each site keeps its own pace (see PoliteClient), so sites are searched side by side.
    with ThreadPoolExecutor(max_workers=len(platforms) or 1) as pool:
        list(pool.map(browse, platforms))
    return list(found.values()), failed, errors


def search_once(
    session: Session,
    settings: AppSettings,
    client: PoliteClient,
    request: SearchRequest,
    *,
    source_factory: SourceFactory = build_source,
) -> SearchResponse:
    """Searches the marketplaces right away and prices every result; nothing is stored."""
    product = (
        session.get(CardmarketProduct, request.cardmarket_product_id)
        if request.cardmarket_product_id
        else None
    )
    expected = expected_sale_cents(request.expected_sale_cents, product)
    query = japanese_query(session, client, request.game, request.query)
    rule = build_rule(
        card_number=request.card_number,
        required=request.required_keywords,
        excluded=request.excluded_keywords,
        grading=request.grading,
        global_excluded=split_keywords(settings.scanner.excluded_keywords),
    )
    results: list[SearchResultOut] = []
    errors: dict[str, str] = {}
    for platform in request.sources or settings.scanner.sources:
        try:
            found = search_safely(
                source_factory(platform, client, request.game),
                query,
                limit=RESULTS_PER_SEARCH,
            )
        except SourceError as error:
            errors[platform.value] = str(error)
            continue
        for item in found:
            match = match_title(item.title, rule)
            estimate = estimate_listing(
                settings,
                price_jpy=item.price_jpy,
                shipping_included=item.shipping_included,
                expected_sale_cents=expected,
            )
            results.append(
                SearchResultOut(
                    source=item.source,
                    external_id=item.external_id,
                    title=item.title,
                    price_jpy=item.price_jpy,
                    shipping_included=item.shipping_included,
                    url=item.url,
                    neokyo_url=links.neokyo_url(item.source, item.external_id),
                    thumbnail_url=item.thumbnail_url,
                    listed_at=item.listed_at,
                    ends_at=item.ends_at,
                    bids=item.bids,
                    condition=item.condition,
                    matched=match.matched,
                    reject_reason=match.reason,
                    landed_cost=landed_cost_out(estimate),
                    sale=sale_breakdown_out(estimate),
                )
            )
    results.sort(
        key=lambda r: (
            not r.matched,
            r.sale is None or r.sale.roi is None,
            -(r.sale.roi if r.sale and r.sale.roi is not None else 0),
        )
    )
    neokyo = {
        platform.value: url
        for platform in SourcePlatform
        if (url := links.neokyo_search_url(platform, query)) is not None
    }
    return SearchResponse(
        searched_query=query,
        expected_sale_cents=expected,
        results=results,
        errors=errors,
        neokyo_search_urls=neokyo,
    )


def japanese_query(session: Session, client: PoliteClient, game: Game, text: str) -> str:
    """``text`` with French or English card names in the Japanese the listings use."""
    if game is Game.POKEMON and not names.species_count(session):
        names.refresh(session, client)
    return names.translate(session, game, text, "ja") or text


@dataclass(slots=True)
class AccountScan:
    """Scan state of one account."""

    running: bool = False
    last_started_at: str | None = None
    last_finished_at: str | None = None
    last_error: str | None = None
    next_run_at: datetime | None = None
    outcome: ScanOutcome = field(default_factory=ScanOutcome)


class ScannerWorker:
    """Background thread: keeps reference prices fresh and runs each account's scans.

    It wakes up every minute, or right away when a scan is requested from the UI, and scans
    the accounts whose scanner is due, one after the other.
    """

    TICK_S = 60.0

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        client: PoliteClient,
        *,
        source_factory: SourceFactory = build_source,
        on_tick: Callable[[], None] = lambda: None,
    ) -> None:
        self._session_factory = session_factory
        self._client = client
        self._source_factory = source_factory
        # Daily chores that are no scan, such as the database's copy.
        self._on_tick = on_tick
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._requested: set[int] = set()
        self._thread: threading.Thread | None = None
        self._accounts: dict[int, AccountScan] = {}

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, name="mekiki-scanner", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout=5)

    def request_scan(self, user_id: int) -> None:
        with self._lock:
            self._requested.add(user_id)
        self._wake.set()

    def run_now(self, user_id: int) -> None:
        """Runs one scan in the calling thread (used when background jobs are off)."""
        self._run(user_id)

    def status(self, user_id: int, settings: AppSettings) -> ScanStatus:
        state = self._accounts.get(user_id) or AccountScan()
        return ScanStatus(
            running=state.running,
            enabled=settings.scanner.enabled,
            last_started_at=state.last_started_at,
            last_finished_at=state.last_finished_at,
            last_error=state.last_error,
            next_run_at=(
                state.next_run_at.strftime("%Y-%m-%dT%H:%M:%SZ")
                if state.next_run_at and settings.scanner.enabled
                else None
            ),
            cards_scanned=state.outcome.cards_scanned,
            new_listings=state.outcome.new_listings,
            new_deals=state.outcome.new_deals,
        )

    def _loop(self) -> None:
        while not self._stop.is_set():
            self.tick()
            self._wake.wait(self.TICK_S)
            self._wake.clear()

    def tick(self) -> None:
        """One round: the scans due, the reference data, the daily chores.

        Each step is guarded: one failing must not end the thread, or scans, prices and the
        daily backup would all stop silently until the app restarts.
        """
        with self._lock:
            requested, self._requested = self._requested, set()
        due = self._guarded("comptes à scanner", self._due_accounts) or set()
        for user_id in sorted(requested | due):
            if self._stop.is_set():
                return
            self._run(user_id)
        # Prices still matter for the watch lists and the stock when no scan runs.
        self._guarded("cotes et index des cartes", self._refresh_references)
        self._guarded("tâches du jour", self._on_tick)

    def _refresh_references(self) -> None:
        with self._session_factory() as session:
            refresh_reference_data(session, self._client)

    @staticmethod
    def _guarded[T](what: str, chore: Callable[[], T]) -> T | None:
        try:
            return chore()
        except Exception:
            logger.exception("Mekiki, %s : erreur inattendue", what)
            return None

    def _due_accounts(self) -> set[int]:
        now = datetime.now(UTC)
        due: set[int] = set()
        with self._session_factory() as session:
            for user_id in session.scalars(select(User.id)):
                settings = load_settings(session, user_id)
                state = self._accounts.get(user_id)
                next_run = state.next_run_at if state else None
                if settings.scanner.enabled and (next_run is None or now >= next_run):
                    due.add(user_id)
        return due

    def _run(self, user_id: int) -> None:
        state = self._accounts.setdefault(user_id, AccountScan())
        state.running = True
        state.last_started_at = utc_now()
        try:
            with self._session_factory() as session:
                state.outcome = scan_tracked_cards(
                    session,
                    self._client,
                    user_id,
                    source_factory=self._source_factory,
                    should_stop=self._stop.is_set,
                )
                interval = load_settings(session, user_id).scanner.interval_minutes
            state.last_error = " · ".join(state.outcome.errors) or None
            state.next_run_at = datetime.now(UTC) + timedelta(minutes=interval)
        # The worker thread must survive any failure, or scans would silently stop.
        except Exception as error:
            logger.exception("Mekiki, scan du compte %s : erreur inattendue", user_id)
            state.last_error = f"Erreur inattendue : {error}"
            state.next_run_at = datetime.now(UTC) + FAILED_SCAN_RETRY
        finally:
            state.running = False
            state.last_finished_at = utc_now()
