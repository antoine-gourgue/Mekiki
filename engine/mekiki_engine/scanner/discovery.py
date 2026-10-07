"""Discovery: browse the newest listings, recognise the cards, compose the best parcel.

Unlike the scan, nothing has to be tracked beforehand: broad searches in the card category,
inside a price window derived from the budget, return a few hundred listings; each title
is read (set code and number, or One Piece code), matched to its Cardmarket product and
priced as one card of the parcel being composed.
"""

from __future__ import annotations

import threading
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from sqlalchemy.orm import Session, sessionmaker

from mekiki_engine.costing.landed_cost import (
    ItemCostInput,
    ItemLandedCost,
    LotCostInput,
    allocate_lot,
)
from mekiki_engine.costing.money import percent_to_fraction
from mekiki_engine.costing.sale import SaleBreakdown, roi
from mekiki_engine.domain import Game
from mekiki_engine.scanner import card_index, links
from mekiki_engine.scanner.identify import CardIdentity, identify
from mekiki_engine.scanner.matching import MatchRule, match_title, split_keywords
from mekiki_engine.scanner.pricing import DealEstimate, domestic_shipping_jpy, reference_price
from mekiki_engine.scanner.resolver import CatalogResolver, Resolution
from mekiki_engine.scanner.runner import SOURCE_LABELS, SourceFactory
from mekiki_engine.scanner.service import (
    landed_cost_out,
    market_price_out,
    sale_breakdown_out,
    utc_now,
)
from mekiki_engine.scanner.sources.base import (
    FoundListing,
    PoliteClient,
    SourceError,
    search_safely,
)
from mekiki_engine.scanner.sources.registry import build_source
from mekiki_engine.schemas import (
    AppSettings,
    DiscoveryPick,
    DiscoveryRequest,
    DiscoveryRun,
    DiscoveryTotals,
)
from mekiki_engine.services.portfolio import parcel_landed_cost, project_sale, vat_rate
from mekiki_engine.services.settings_service import load_settings

# Broad searches: the whole category, then the rarities worth importing.
DISCOVERY_QUERIES = {
    Game.POKEMON: ("", "SAR", "SR", "AR", "UR", "MUR", "SSR", "CHR", "CSR", "HR"),
    Game.ONE_PIECE: ("", "パラレル", "コミパラ", "SEC", "SR", "SP", "リーダー パラレル"),
}
RESULTS_PER_QUERY = 120
# Listings considered, relative to the average budget per card.
PRICE_WINDOW = (0.15, 1.6)
MAX_SAME_PRODUCT = 2
MAX_ALTERNATIVES = 30
# Below this share of the market price, a listing is almost always a reproduction, an
# accessory or another version of the card, not a bargain.
SUSPICIOUS_PRICE_SHARE = 0.2
SUSPICIOUS_WARNING = (
    "Prix à moins de 20 % de la cote : sans doute une reproduction, un accessoire ou une "
    "autre version. Vérifiez l'annonce avant d'acheter."
)


@dataclass(slots=True)
class Candidate:
    listing: FoundListing
    identity: CardIdentity
    resolution: Resolution
    expected_cents: int
    estimate: DealEstimate
    warning: str | None = None

    @property
    def landed_cents(self) -> int:
        return self.estimate.landed.total_cents

    @property
    def margin_cents(self) -> int:
        assert self.estimate.margin_cents is not None
        return self.estimate.margin_cents

    @property
    def roi(self) -> float:
        return self.margin_cents / self.landed_cents if self.landed_cents else 0.0


def price_window_jpy(settings: AppSettings, request: DiscoveryRequest) -> tuple[int, int]:
    per_card_eur = request.budget_cents / request.card_count / 100
    fx = float(settings.fx_jpy_per_eur)
    low, high = PRICE_WINDOW
    return int(per_card_eur * low * fx), int(per_card_eur * high * fx)


def discover(
    session: Session,
    client: PoliteClient,
    request: DiscoveryRequest,
    *,
    source_factory: SourceFactory = build_source,
    on_progress: Callable[[DiscoveryRun], None] = lambda _run: None,
) -> DiscoveryRun:
    settings = load_settings(session)
    platforms = request.sources or settings.scanner.sources
    queries = DISCOVERY_QUERIES[request.game]
    run = DiscoveryRun(
        status="running",
        request=request,
        started_at=utc_now(),
        searches_total=len(platforms) * len(queries),
    )
    on_progress(run)

    needs_index = request.game is Game.POKEMON and not card_index.indexed_count(session)
    if needs_index and (error := card_index.refresh(session, client)):
        run.errors.append(error)

    price_min, price_max = price_window_jpy(settings, request)
    found: dict[tuple[str, str], FoundListing] = {}
    for platform in platforms:
        source = source_factory(platform, client, request.game)
        for query in queries:
            try:
                for item in search_safely(
                    source,
                    query,
                    limit=RESULTS_PER_QUERY,
                    price_min_jpy=price_min,
                    price_max_jpy=price_max,
                ):
                    found.setdefault((item.source.value, item.external_id), item)
            except SourceError as error:
                run.errors.append(f"{SOURCE_LABELS[platform]} : {error}")
                break
            finally:
                run.searches_done += 1
                run.listings_seen = len(found)
                on_progress(run)

    candidates = evaluate(session, settings, request, found.values(), run)
    picked = compose_parcel(candidates, request.budget_cents, request.card_count)
    run.picks, run.totals = price_parcel(settings, picked)
    # Picked cards were priced as if the parcel held ``card_count`` cards; with fewer, each
    # one carries more of the parcel's fixed costs, so drop the weakest until it fits.
    while run.totals is not None and run.totals.landed_cents > request.budget_cents:
        picked.pop()
        run.picks, run.totals = price_parcel(settings, picked)
    if candidates and not picked:
        run.errors.append(
            "Budget trop serré : les frais fixes du colis (envoi, emballage, frais de "
            f"dossier) coûtent déjà environ {fixed_parcel_costs_eur(settings):.0f} €. "
            "Augmentez le budget ou réduisez le nombre de cartes."
        )
    chosen = {id(candidate) for candidate in picked}
    run.alternatives = [
        _pick(candidate, candidate.estimate.landed, candidate.estimate.sale)
        for candidate in candidates
        if id(candidate) not in chosen
    ][:MAX_ALTERNATIVES]
    run.status = "done"
    run.finished_at = utc_now()
    return run


def evaluate(
    session: Session,
    settings: AppSettings,
    request: DiscoveryRequest,
    listings: Iterable[FoundListing],
    run: DiscoveryRun,
) -> list[Candidate]:
    """Listings recognised, priced and reaching the ROI target, best return first."""
    resolver = CatalogResolver(session)
    noise = MatchRule(global_excluded=split_keywords(settings.scanner.excluded_keywords))
    target = percent_to_fraction(
        request.min_roi_percent
        if request.min_roi_percent is not None
        else settings.scanner.min_roi_percent
    )
    candidates: list[Candidate] = []
    for listing in listings:
        identity = identify(listing.title, request.game)
        # Graded copies and lots are other products; the noise rule rejects both.
        if identity.graded or not match_title(listing.title, noise).matched:
            continue
        resolution = resolver.resolve(identity)
        if resolution is None:
            continue
        run.listings_identified += 1
        reference = reference_price(resolution.product)
        if reference is None:
            continue
        run.listings_priced += 1
        landed = parcel_landed_cost(
            settings,
            price_jpy=listing.price_jpy,
            domestic_shipping_jpy=domestic_shipping_jpy(settings, listing.shipping_included),
            cards_in_lot=request.card_count,
            lot_shipping_jpy=settings.scanner.lot_shipping_jpy,
            fx_jpy_per_eur=settings.fx_jpy_per_eur,
        )
        sale = project_sale(settings, settings.scanner.resale_platform, reference[0])
        estimate = DealEstimate(landed=landed, sale=sale)
        margin = estimate.margin_cents
        if margin is None or landed.total_cents <= 0 or margin < target * landed.total_cents:
            continue
        price_cents = listing.price_jpy / settings.fx_jpy_per_eur * 100
        warning = (
            SUSPICIOUS_WARNING if price_cents < SUSPICIOUS_PRICE_SHARE * reference[0] else None
        )
        candidates.append(Candidate(listing, identity, resolution, reference[0], estimate, warning))
    # Confident identifications first, then the best return per euro spent.
    return sorted(
        candidates,
        key=lambda c: (
            c.warning is not None,
            c.resolution.confidence != "high",
            -c.roi,
            -c.margin_cents,
        ),
    )


def compose_parcel(candidates: list[Candidate], budget_cents: int, count: int) -> list[Candidate]:
    """Greedy pick by return within the budget.

    A first pass keeps enough budget to fill every slot with the cheapest candidate, so one
    expensive card cannot eat the whole budget; when the budget cannot hold ``count`` cards
    anyway, a second pass fills what it can.
    """
    if not candidates:
        return []
    cheapest = min(c.landed_cents for c in candidates)
    picked: list[Candidate] = []
    per_product: Counter[int] = Counter()

    def fill(reserve: bool) -> None:
        spent = sum(c.landed_cents for c in picked)
        for candidate in candidates:
            slots_left = count - len(picked)
            if slots_left == 0:
                return
            product_id = candidate.resolution.product.id_product
            if candidate.warning or candidate in picked:
                continue
            if per_product[product_id] >= MAX_SAME_PRODUCT:
                continue
            kept_back = cheapest * (slots_left - 1) if reserve else 0
            if spent + candidate.landed_cents + kept_back > budget_cents:
                continue
            picked.append(candidate)
            spent += candidate.landed_cents
            per_product[product_id] += 1

    fill(reserve=True)
    if len(picked) < count:
        fill(reserve=False)
    return picked


def fixed_parcel_costs_eur(settings: AppSettings) -> float:
    """What a parcel costs before any card: international shipping, packing, handling."""
    fx = float(settings.fx_jpy_per_eur)
    shipping_and_packing = settings.scanner.lot_shipping_jpy + settings.neokyo_packing_fee_jpy
    return shipping_and_packing / fx + settings.default_handling_fee_cents / 100


def price_parcel(
    settings: AppSettings, picked: list[Candidate]
) -> tuple[list[DiscoveryPick], DiscoveryTotals | None]:
    """Prices the picks as one real lot: shared costs split by price, not evenly."""
    if not picked:
        return [], None
    lot = LotCostInput(
        fx_jpy_per_eur=settings.fx_jpy_per_eur,
        packing_fee_jpy=settings.neokyo_packing_fee_jpy,
        international_shipping_jpy=settings.scanner.lot_shipping_jpy,
        handling_fee_cents=settings.default_handling_fee_cents,
    )
    items = [
        ItemCostInput(
            price_jpy=c.listing.price_jpy,
            domestic_shipping_jpy=domestic_shipping_jpy(settings, c.listing.shipping_included),
            service_fee_jpy=settings.neokyo_service_fee_jpy,
        )
        for c in picked
    ]
    landed_costs = allocate_lot(lot, items, vat_rate(settings))
    picks = [
        _pick(candidate, landed, candidate.estimate.sale)
        for candidate, landed in zip(picked, landed_costs, strict=True)
    ]
    landed_total = sum(cost.total_cents for cost in landed_costs)
    net_total = sum(c.estimate.sale.net_cents for c in picked if c.estimate.sale)
    margin = net_total - landed_total
    totals = DiscoveryTotals(
        card_count=len(picks),
        purchase_jpy=sum(c.listing.price_jpy for c in picked),
        landed_cents=landed_total,
        revenue_cents=sum(c.estimate.sale.revenue_cents for c in picked if c.estimate.sale),
        net_cents=net_total,
        margin_cents=margin,
        roi=roi(margin, landed_total),
    )
    return picks, totals


def _pick(
    candidate: Candidate, landed: ItemLandedCost, sale: SaleBreakdown | None
) -> DiscoveryPick:
    listing = candidate.listing
    estimate = DealEstimate(landed=landed, sale=sale)
    breakdown = sale_breakdown_out(estimate)
    assert breakdown is not None
    return DiscoveryPick(
        source=listing.source,
        external_id=listing.external_id,
        title=listing.title,
        price_jpy=listing.price_jpy,
        shipping_included=listing.shipping_included,
        url=listing.url,
        neokyo_url=links.neokyo_url(listing.source, listing.external_id),
        thumbnail_url=listing.thumbnail_url,
        listed_at=listing.listed_at,
        ends_at=listing.ends_at,
        bids=listing.bids,
        card_label=candidate.resolution.label,
        product=market_price_out(candidate.resolution.product),
        confidence=candidate.resolution.confidence,
        confidence_note=candidate.resolution.note,
        warning=candidate.warning,
        landed_cost=landed_cost_out(estimate),
        sale=breakdown,
    )


class DiscoveryJob:
    """Runs one discovery at a time in a background thread; the UI polls its progress."""

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
        self._lock = threading.Lock()
        self.run = DiscoveryRun(status="idle")

    @property
    def running(self) -> bool:
        return self.run.status == "running"

    def start(self, request: DiscoveryRequest, *, background: bool = True) -> DiscoveryRun:
        with self._lock:
            if self.running:
                return self.run
            self.run = DiscoveryRun(status="running", request=request, started_at=utc_now())
        if background:
            threading.Thread(
                target=self._execute, args=(request,), name="mekiki-discovery", daemon=True
            ).start()
        else:
            self._execute(request)
        return self.run

    def _execute(self, request: DiscoveryRequest) -> None:
        def publish(run: DiscoveryRun) -> None:
            self.run = run.model_copy()

        try:
            with self._session_factory() as session:
                self.run = discover(
                    session,
                    self._client,
                    request,
                    source_factory=self._source_factory,
                    on_progress=publish,
                )
        # A crash must still end the run, or the UI would wait forever.
        except Exception as error:
            failed = self.run.model_copy()
            failed.status = "failed"
            failed.finished_at = utc_now()
            failed.errors = [*failed.errors, f"Erreur inattendue : {error}"]
            self.run = failed
