"""Runs searches: the scheduled scan of tracked cards and one-off searches from the UI."""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from mekiki_engine.domain import Game, SourcePlatform
from mekiki_engine.models import CardmarketProduct, TrackedCard
from mekiki_engine.scanner import card_index, cardmarket, links
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

SOURCE_LABELS = {
    SourcePlatform.MERCARI: "Mercari",
    SourcePlatform.RAKUMA: "Rakuma",
    SourcePlatform.YAHOO_AUCTIONS: "Yahoo Auctions",
    SourcePlatform.YAHOO_FLEAMARKET: "Yahoo Fleamarket",
}
RESULTS_PER_SEARCH = 60

SourceFactory = Callable[[SourcePlatform, PoliteClient, Game], Source]


@dataclass(slots=True)
class ScanOutcome:
    cards_scanned: int = 0
    new_listings: int = 0
    new_deals: int = 0
    errors: list[str] = field(default_factory=list)


def scan_tracked_cards(
    session: Session,
    client: PoliteClient,
    *,
    source_factory: SourceFactory = build_source,
    should_stop: Callable[[], bool] = lambda: False,
) -> ScanOutcome:
    """Searches every active tracked card on every enabled marketplace."""
    settings = load_settings(session)
    outcome = ScanOutcome()
    for game in Game:
        outcome.errors += cardmarket.refresh(session, client, game)
    if error := card_index.refresh(session, client):
        outcome.errors.append(error)

    cards = session.scalars(
        select(TrackedCard).where(TrackedCard.active.is_(True)).order_by(TrackedCard.id)
    ).all()
    sources: dict[tuple[SourcePlatform, Game], Source] = {}
    for card in cards:
        if should_stop():
            break
        game = Game(card.game)
        found: list[FoundListing] = []
        failed: set[str] = set()
        for platform in settings.scanner.sources:
            source = sources.get((platform, game))
            if source is None:
                source = sources[(platform, game)] = source_factory(platform, client, game)
            try:
                found += search_safely(source, card.search_query, limit=RESULTS_PER_SEARCH)
            except SourceError as error:
                failed.add(platform.value)
                outcome.errors.append(f"{SOURCE_LABELS[platform]} ({card.name}) : {error}")
        new_listings, new_deals = record_found_listings(
            session, settings, card, found, now=utc_now(), unchecked_sources=failed
        )
        outcome.cards_scanned += 1
        outcome.new_listings += new_listings
        outcome.new_deals += new_deals
    return outcome


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
                request.query,
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
        if (url := links.neokyo_search_url(platform, request.query)) is not None
    }
    return SearchResponse(
        expected_sale_cents=expected,
        results=results,
        errors=errors,
        neokyo_search_urls=neokyo,
    )


class ScannerWorker:
    """Background thread: keeps Cardmarket prices fresh and runs the scheduled scans.

    It wakes up every minute, or right away when a scan is requested from the UI.
    """

    TICK_S = 60.0

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        client: PoliteClient,
        *,
        source_factory: SourceFactory = build_source,
    ) -> None:
        self._session_factory = session_factory
        self._client = client
        self._source_factory = source_factory
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._requested = False
        self._thread: threading.Thread | None = None
        self.running = False
        self.last_started_at: str | None = None
        self.last_finished_at: str | None = None
        self.last_error: str | None = None
        self.next_run_at: datetime | None = None
        self.outcome = ScanOutcome()

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, name="mekiki-scanner", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout=5)

    def request_scan(self) -> None:
        with self._lock:
            self._requested = True
        self._wake.set()

    def run_now(self) -> None:
        """Runs one scan in the calling thread (used when background jobs are off)."""
        self._run()

    def status(self, settings: AppSettings) -> ScanStatus:
        return ScanStatus(
            running=self.running,
            enabled=settings.scanner.enabled,
            last_started_at=self.last_started_at,
            last_finished_at=self.last_finished_at,
            last_error=self.last_error,
            next_run_at=(
                self.next_run_at.strftime("%Y-%m-%dT%H:%M:%SZ")
                if self.next_run_at and settings.scanner.enabled
                else None
            ),
            cards_scanned=self.outcome.cards_scanned,
            new_listings=self.outcome.new_listings,
            new_deals=self.outcome.new_deals,
        )

    def _loop(self) -> None:
        while not self._stop.is_set():
            with self._session_factory() as session:
                settings = load_settings(session)
            now = datetime.now(UTC)
            with self._lock:
                requested, self._requested = self._requested, False
            due = settings.scanner.enabled and (self.next_run_at is None or now >= self.next_run_at)
            if requested or due:
                self._run()
                self.next_run_at = datetime.now(UTC) + timedelta(
                    minutes=settings.scanner.interval_minutes
                )
            elif not settings.scanner.enabled:
                # Prices still matter for the watch list and the stock when scans are off.
                with self._session_factory() as session:
                    for game in Game:
                        cardmarket.refresh(session, self._client, game)
                    card_index.refresh(session, self._client)
            self._wake.wait(self.TICK_S)
            self._wake.clear()

    def _run(self) -> None:
        self.running = True
        self.last_started_at = utc_now()
        try:
            with self._session_factory() as session:
                self.outcome = scan_tracked_cards(
                    session,
                    self._client,
                    source_factory=self._source_factory,
                    should_stop=self._stop.is_set,
                )
            self.last_error = " · ".join(self.outcome.errors) or None
        # The worker thread must survive any failure, or scans would silently stop.
        except Exception as error:
            self.last_error = f"Erreur inattendue : {error}"
        finally:
            self.running = False
            self.last_finished_at = utc_now()
