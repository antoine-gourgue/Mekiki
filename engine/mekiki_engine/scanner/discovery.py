"""Discovery: browse the newest listings, recognise the cards, compose the best parcel.

Unlike the scan, nothing has to be tracked beforehand: broad searches in the card category,
inside a price window derived from the budget, return a few hundred listings; each title
is read (set code and number, or One Piece code), matched to its Cardmarket product and
priced as one card of the parcel being composed.
"""

from __future__ import annotations

import re
import threading
from collections import Counter
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from mekiki_engine.costing.landed_cost import (
    ItemLandedCost,
)
from mekiki_engine.costing.money import percent_to_fraction
from mekiki_engine.costing.sale import SaleBreakdown
from mekiki_engine.domain import Game, ListingCondition, SourcePlatform
from mekiki_engine.models import CardIndexEntry, CardmarketProduct, SettingRow
from mekiki_engine.scanner import availability, card_index, links, sellers
from mekiki_engine.scanner.identify import CardIdentity, identify
from mekiki_engine.scanner.matching import MatchRule, match_title, split_keywords
from mekiki_engine.scanner.pricing import (
    DealEstimate,
    domestic_shipping_jpy,
    landed_costs_of_parcel,
    parcel_totals,
    reference_price,
)
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
    SiteBlocked,
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
    LogLine,
)
from mekiki_engine.services.portfolio import parcel_landed_cost, project_sale
from mekiki_engine.services.settings_service import load_settings

# Broad searches: the whole category, then the rarities worth importing.
DISCOVERY_QUERIES = {
    Game.POKEMON: ("", "SAR", "SR", "AR", "UR", "MUR", "SSR", "CHR", "CSR", "HR"),
    Game.ONE_PIECE: ("", "パラレル", "コミパラ", "SEC", "SR", "SP", "リーダー パラレル"),
}
RESULTS_PER_QUERY = 120
# Per depth: pages of each broad search, number of set-code searches, pages of each.
DEPTHS = {"quick": (1, 0, 1), "deep": (2, 15, 1), "max": (3, 40, 2)}
# Sets whose cards are worth importing: the most products priced at 10 euros or more.
VALUABLE_CENTS = 1000
# Listings considered, relative to the average budget per card.
PRICE_WINDOW = (0.15, 1.6)
ONE_PIECE_SET = re.compile(r"\(\s*((?:OP|EB|PRB|ST)\d{2})-\d{3}\s*\)", re.IGNORECASE)
MAX_SAME_PRODUCT = 2
# A site failing this many searches in a row is down or has changed: stop browsing it.
MAX_FAILURES_IN_A_ROW = 3
MAX_ALTERNATIVES = 30
# The log keeps the latest lines only: a maximal discovery reads hundreds of pages.
MAX_LOG_LINES = 400
DEPTH_LABELS = {"quick": "rapide", "deep": "approfondie", "max": "maximale"}
GAME_NAMES = {Game.POKEMON: "Pokémon", Game.ONE_PIECE: "One Piece"}
# Listings checked on their marketplace per discovery: a few seconds each (see PoliteClient),
# so a parcel full of sold listings cannot hold the result back for long.
MAX_CHECKS = 30
# Sites whose search results leave the condition out: it is read on the listing's page,
# when the listing makes the parcel.
CONDITION_ON_PAGE = frozenset({SourcePlatform.RAKUMA})
CONDITION_NAMES = {
    ListingCondition.NEW: "neuve",
    ListingCondition.LIKE_NEW: "quasi neuve",
    ListingCondition.GOOD: "en bon état",
    ListingCondition.FAIR: "avec de légères traces",
    ListingCondition.POOR: "abîmée",
    ListingCondition.BAD: "en mauvais état",
}
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
    # Under the ROI target on its own: only used to fill a parcel left short of cards.
    below_target: bool = False

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


def note(run: DiscoveryRun, text: str) -> None:
    """Adds a step to the discovery's log, which the app shows as it runs."""
    run.log.append(LogLine(at=utc_now(), text=text))
    del run.log[:-MAX_LOG_LINES]


def euros(cents: int) -> str:
    """12345 → "123,45 €", French style."""
    return f"{cents / 100:,.2f}".replace(",", " ").replace(".", ",") + " €"


def percent(rate: Decimal) -> str:
    """0.3 → "30 %", 0.165 → "16,5 %"."""
    return f"{rate * 100:.1f}".rstrip("0").rstrip(".").replace(".", ",") + " %"


def yen(amount: int) -> str:
    return f"{amount:,}".replace(",", " ") + " ¥"


def counted(count: int, words: str) -> str:
    """counted(3, "annonce écartée") → "3 annonces écartées", with French spacing."""
    if count > 1:
        words = " ".join(word if word.endswith("s") else word + "s" for word in words.split())
    return f"{count:,}".replace(",", " ") + " " + words


def search_plan(session: Session, game: Game, depth: str) -> list[tuple[str, int]]:
    """(query, pages) to run on each site: broad searches, then the most valuable sets.

    Set-code searches find listings whose title carries the set code, the ones the card
    index recognises best.
    """
    broad_pages, set_count, set_pages = DEPTHS[depth]
    plan = [(query, broad_pages) for query in DISCOVERY_QUERIES[game]]
    if set_count:
        plan += [(code, set_pages) for code in valuable_sets(session, game, set_count)]
    return plan


def valuable_sets(session: Session, game: Game, limit: int) -> list[str]:
    """Set codes with the most cards priced at ``VALUABLE_CENTS`` or more."""
    price = func.coalesce(
        CardmarketProduct.avg30_cents,
        CardmarketProduct.avg7_cents,
        CardmarketProduct.avg_cents,
        CardmarketProduct.trend_cents,
    )
    if game is Game.POKEMON:
        rows = session.execute(
            select(CardIndexEntry.set_code, func.count())
            .join(CardmarketProduct, CardmarketProduct.id_product == CardIndexEntry.id_product)
            .where(CardIndexEntry.game == game.value, price >= VALUABLE_CENTS)
            .group_by(CardIndexEntry.set_code)
            .order_by(func.count().desc())
        ).all()
        return [code for code, _count in rows if _searchable_set_code(code)][:limit]
    codes: Counter[str] = Counter()
    names = session.scalars(
        select(CardmarketProduct.name).where(
            CardmarketProduct.game == game.value,
            price >= VALUABLE_CENTS,
            CardmarketProduct.expansion_name.is_not(None),
        )
    )
    for name in names:
        if match := ONE_PIECE_SET.search(name or ""):
            codes[match[1].upper()] += 1
    return [code for code, _count in codes.most_common(limit)]


def _searchable_set_code(code: str) -> bool:
    # Promo sets ("s-p", "sv-p") and two-letter codes ("mc") never appear as such in
    # listing titles: searching them only brings unrelated listings.
    return len(code) >= 3 and not code.endswith("-p")


def price_window_jpy(settings: AppSettings, request: DiscoveryRequest) -> tuple[int, int]:
    per_card_eur = request.budget_cents / request.card_count / 100
    fx = float(settings.fx_jpy_per_eur)
    low, high = PRICE_WINDOW
    return int(per_card_eur * low * fx), int(per_card_eur * high * fx)


def discover(
    session: Session,
    client: PoliteClient,
    user_id: int,
    request: DiscoveryRequest,
    *,
    source_factory: SourceFactory = build_source,
    on_progress: Callable[[DiscoveryRun], None] = lambda _run: None,
    should_stop: Callable[[], bool] = lambda: False,
) -> DiscoveryRun:
    settings = load_settings(session, user_id)
    platforms = request.sources or settings.scanner.sources
    run = DiscoveryRun(status="running", request=request, started_at=utc_now())
    sites = ", ".join(SOURCE_LABELS[platform] for platform in platforms)
    note(
        run,
        f"Recherche lancée : {GAME_NAMES[request.game]}, budget {euros(request.budget_cents)}, "
        f"{request.card_count} cartes, profondeur {DEPTH_LABELS[request.depth]}, "
        f"sur {sites}.",
    )
    on_progress(run)

    needs_index = request.game is Game.POKEMON and card_index.needs_rebuild(session)
    if needs_index:
        note(
            run,
            "Construction de l'index des cartes Pokémon japonaises (TCGdex et TCGplayer, "
            "environ deux minutes, une fois par semaine)…",
        )
        on_progress(run)
        if error := card_index.refresh(session, client):
            run.errors.append(error)
            note(run, error)
        else:
            note(run, f"Index prêt : {card_index.indexed_count(session)} cartes.")
    plan = search_plan(session, request.game, request.depth)
    run.searches_total = len(platforms) * sum(pages for _query, pages in plan)
    price_min, price_max = price_window_jpy(settings, request)
    note(
        run,
        f"{len(plan)} recherches prévues par site, {run.searches_total} pages au plus, "
        f"annonces entre {yen(price_min)} et {yen(price_max)}.",
    )
    on_progress(run)
    found: dict[tuple[str, str], FoundListing] = {}
    lock = threading.Lock()

    def report(platform: SourcePlatform, error: SourceError) -> None:
        message = f"{SOURCE_LABELS[platform]} : {error}"
        if message not in run.errors:
            run.errors.append(message)

    def browse(platform: SourcePlatform) -> None:
        source = source_factory(platform, client, request.game)
        remaining = sum(pages for _query, pages in plan)
        failures_in_a_row = 0
        for query, pages in plan:
            for page in range(pages):
                if should_stop():
                    return
                try:
                    items = search_safely(
                        source,
                        query,
                        limit=RESULTS_PER_QUERY,
                        price_min_jpy=price_min,
                        price_max_jpy=price_max,
                        page=page,
                    )
                    failures_in_a_row = 0
                except SourceError as error:
                    failures_in_a_row += 1
                    give_up = (
                        isinstance(error, SiteBlocked) or failures_in_a_row >= MAX_FAILURES_IN_A_ROW
                    )
                    # One failed page skips its search; a blocked or failing site is left.
                    skipped = remaining if give_up else pages - page
                    with lock:
                        report(platform, error)
                        run.searches_done += skipped
                        note(
                            run,
                            f"{SOURCE_LABELS[platform]} : {error}"
                            + (", site abandonné." if give_up else ", recherche suivante."),
                        )
                        on_progress(run)
                    if give_up:
                        return
                    remaining -= skipped
                    break
                skipped = 0 if items else pages - page - 1
                with lock:
                    before = len(found)
                    for item in items:
                        found.setdefault((item.source.value, item.external_id), item)
                    # An empty page ends this search: its next pages would be empty too.
                    run.searches_done += 1 + skipped
                    run.listings_seen = len(found)
                    note(
                        run,
                        f"{SOURCE_LABELS[platform]} : « {query or 'toutes les cartes'} », "
                        f"page {page + 1} : {counted(len(items), 'annonce')}, "
                        f"{counted(len(found) - before, 'nouvelle')}.",
                    )
                    on_progress(run)
                remaining -= 1 + skipped
                if skipped:
                    break

    # Each site keeps its own pace (see PoliteClient), so sites are browsed side by side.
    with ThreadPoolExecutor(max_workers=len(platforms) or 1) as pool:
        list(pool.map(browse, platforms))

    if should_stop():
        note(run, "Arrêt demandé : les annonces déjà lues sont évaluées.")
    note(
        run,
        f"{counted(run.listings_seen, 'annonce lue')} au total : lecture des titres et des cotes…",
    )
    on_progress(run)
    candidates = evaluate(session, settings, request, found.values(), run)
    on_progress(run)
    picked, gone = compose_available_parcel(
        session,
        client,
        run,
        settings,
        candidates,
        request,
        on_progress=on_progress,
        should_stop=should_stop,
    )
    run.picks, run.totals = price_parcel(settings, picked)
    # Picked cards were priced as if the parcel held ``card_count`` cards; with fewer, each
    # one carries more of the parcel's fixed costs, so drop the weakest until it fits.
    while run.totals is not None and run.totals.landed_cents > request.budget_cents:
        picked.pop()
        run.picks, run.totals = price_parcel(settings, picked)
    # The budget is to blame only when listings reaching the target, still for sale and in
    # the condition asked, could not fit it.
    fitting = [c for c in candidates if not (c.below_target or c.warning or id(c) in gone)]
    if fitting and not picked:
        run.errors.append(
            "Budget trop serré : les frais fixes du colis (envoi, emballage, frais de "
            f"dossier) coûtent déjà environ {fixed_parcel_costs_eur(settings):.0f} €. "
            "Augmentez le budget ou réduisez le nombre de cartes."
        )
        note(run, run.errors[-1])
    if run.totals is not None:
        fillers = sum(1 for candidate in picked if candidate.below_target)
        note(
            run,
            f"Colis proposé : {len(run.picks)} cartes"
            + (f" dont {fillers} pour le compléter" if fillers else "")
            + f", coût {euros(run.totals.landed_cents)}, marge {euros(run.totals.margin_cents)}, "
            f"ROI {percent(run.totals.roi) if run.totals.roi is not None else '?'}.",
        )
        target = target_roi(settings, request)
        if run.totals.roi is not None and run.totals.roi < target:
            run.errors.append(short_of_target(settings, request, platforms, candidates, picked))
            note(run, run.errors[-1])
    left_out = {id(candidate) for candidate in picked} | gone
    run.alternatives = [
        _pick(candidate, candidate.estimate.landed, candidate.estimate.sale)
        for candidate in candidates
        if id(candidate) not in left_out and not candidate.below_target
    ][:MAX_ALTERNATIVES]
    run.stopped = should_stop()
    note(
        run,
        f"Terminé : {counted(len(run.alternatives), 'autre annonce')} à voir à côté du colis."
        if run.picks
        else "Terminé : aucun colis ne remplit les conditions.",
    )
    run.status = "done"
    run.finished_at = utc_now()
    return run


def target_roi(settings: AppSettings, request: DiscoveryRequest) -> Decimal:
    return percent_to_fraction(
        request.min_roi_percent
        if request.min_roi_percent is not None
        else settings.scanner.min_roi_percent
    )


def evaluate(
    session: Session,
    settings: AppSettings,
    request: DiscoveryRequest,
    listings: Iterable[FoundListing],
    run: DiscoveryRun,
) -> list[Candidate]:
    """Listings recognised and priced at a profit, best return first.

    Those under the ROI target come last, flagged ``below_target``: they only fill a parcel
    that would otherwise stay short of cards.
    """
    resolver = CatalogResolver(session)
    noise = MatchRule(global_excluded=split_keywords(settings.scanner.excluded_keywords))
    target = target_roi(settings, request)
    avoided = sellers.blocked(session)
    # Why the other listings were left out, for the log: most never become a candidate.
    dropped: Counter[str] = Counter()
    candidates: list[Candidate] = []
    for listing in listings:
        minimum = request.min_condition
        # Without a condition in the results, the listing's page is checked if it makes the
        # parcel (see compose_available_parcel).
        unknown_until_checked = listing.condition is None and listing.source in CONDITION_ON_PAGE
        if (
            minimum
            and not unknown_until_checked
            and not (listing.condition and listing.condition.at_least(minimum))
        ):
            dropped["condition"] += 1
            continue
        if (listing.source.value, listing.seller_id) in avoided:
            dropped["seller"] += 1
            continue
        identity = identify(listing.title, request.game)
        # Graded copies and lots are other products; the noise rule rejects both.
        if identity.graded or not match_title(listing.title, noise).matched:
            dropped["noise"] += 1
            continue
        resolution = resolver.resolve(identity)
        if resolution is None:
            dropped["unknown"] += 1
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
        if margin is None or landed.total_cents <= 0 or margin <= 0:
            dropped["loss"] += 1
            continue
        price_cents = listing.price_jpy / settings.fx_jpy_per_eur * 100
        warning = (
            SUSPICIOUS_WARNING if price_cents < SUSPICIOUS_PRICE_SHARE * reference[0] else None
        )
        below = margin < target * landed.total_cents
        candidates.append(
            Candidate(listing, identity, resolution, reference[0], estimate, warning, below)
        )
    above = sum(1 for c in candidates if not c.below_target and not c.warning)
    below = sum(1 for c in candidates if c.below_target and not c.warning)
    suspicious = sum(1 for c in candidates if c.warning)
    note(
        run,
        "Écartées : "
        + (
            ", ".join(
                f"{counted(count, 'annonce')} {why}"
                for count, why in (
                    (dropped["condition"], "par l'état (insuffisant ou non précisé)"),
                    (dropped["seller"], "d'un vendeur bloqué par Neokyo"),
                    (dropped["noise"], "en lot, booster, gradée ou avec un mot exclu"),
                    (dropped["unknown"], "sans carte reconnue dans le titre"),
                )
                if count
            )
            or "aucune"
        )
        + ".",
    )
    note(
        run,
        f"{counted(run.listings_identified, 'carte reconnue')}, "
        f"{counted(run.listings_priced, 'cotée')} sur Cardmarket, "
        f"{dropped['loss']} à perte, "
        f"{counted(above, 'rentable')} à {percent(target)} ou plus, "
        f"{counted(below, 'autre')} rentable{'s' if below > 1 else ''} en dessous"
        + (
            f", {counted(suspicious, 'signalée')} (prix sous 20 % de la cote : reproduction ou "
            "autre version ?)"
            if suspicious
            else ""
        )
        + ".",
    )
    # Confident identifications first, then the best return per euro spent.
    return sorted(
        candidates,
        key=lambda c: (
            c.warning is not None,
            c.below_target,
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
    candidates = [c for c in candidates if not c.below_target and not c.warning]
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
            if candidate.warning or candidate.below_target or candidate in picked:
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


def fill_parcel(
    settings: AppSettings,
    picked: list[Candidate],
    candidates: list[Candidate],
    budget_cents: int,
    count: int,
) -> list[Candidate]:
    """Completes a parcel left short of ``count`` cards with listings under the ROI target.

    Shipping, packing and handling cost the same for 3 cards or 15: candidates were priced
    as one card of a full parcel, so a short one spreads those costs over too few cards and
    misses the target its cards reached alone. A filler only goes in when it raises the
    parcel's return, so it never makes the parcel worse.
    """
    if not picked:
        return picked
    picked = list(picked)
    per_product = Counter(c.resolution.product.id_product for c in picked)
    _picks, totals = price_parcel(settings, picked)
    for candidate in candidates:
        if len(picked) >= count:
            break
        product_id = candidate.resolution.product.id_product
        if not candidate.below_target or candidate.warning:
            continue
        if per_product[product_id] >= MAX_SAME_PRODUCT:
            continue
        _picks, trial = price_parcel(settings, [*picked, candidate])
        assert trial is not None and totals is not None
        if trial.landed_cents > budget_cents or (trial.roi or 0) <= (totals.roi or 0):
            continue
        picked.append(candidate)
        per_product[product_id] += 1
        totals = trial
    return picked


def short_of_target(
    settings: AppSettings,
    request: DiscoveryRequest,
    platforms: Iterable[SourcePlatform],
    candidates: list[Candidate],
    picked: list[Candidate],
) -> str:
    """Why the parcel misses the ROI target, and what to change to find more cards."""
    target = percent(target_roi(settings, request))
    above = sum(1 for c in candidates if not c.below_target and not c.warning)
    fillers = sum(1 for c in picked if c.below_target)
    fixed = fixed_parcel_costs_eur(settings)
    if above < request.card_count:
        reason = (
            f"seules {above} annonces les dépassent"
            if above > 1
            else "une seule annonce les dépasse"
        ) + f", chiffrées comme une carte d'un colis de {request.card_count}"
    else:
        reason = f"le budget ne laisse place qu'à {len(picked)} cartes"
    message = (
        f"Le colis n'atteint pas les {target} demandés : {reason}. Les frais fixes du colis "
        f"(envoi international, emballage, frais de dossier : environ {fixed:.0f} €, plus la "
        "TVA) pèsent alors sur moins de cartes."
    )
    if fillers:
        message += (
            f" {fillers} carte{'s' if fillers > 1 else ''} un peu moins rentable"
            f"{'s le complètent' if fillers > 1 else ' le complète'} pour mieux les partager."
        )
    ideas = []
    if request.depth != "max":
        ideas.append("une recherche plus profonde")
    if SourcePlatform.RAKUMA not in platforms:
        ideas.append("Rakuma")
    if request.min_condition is not None:
        ideas.append("un état minimum moins strict")
    ideas.append("un ROI minimum plus bas")
    return message + " Pour plus de choix : " + ", ".join(ideas) + "."


def compose_available_parcel(
    session: Session,
    client: PoliteClient,
    run: DiscoveryRun,
    settings: AppSettings,
    candidates: list[Candidate],
    request: DiscoveryRequest,
    *,
    on_progress: Callable[[DiscoveryRun], None],
    should_stop: Callable[[], bool],
) -> tuple[list[Candidate], set[int]]:
    """The best parcel among listings still for sale, and the ids of the candidates gone.

    Good deals sell within minutes: each picked listing is checked on its marketplace, one
    request at a time, and a sold one gives its place to the next candidate. A listing that
    could not be checked keeps its place, as do those past ``MAX_CHECKS``. Stopping the
    discovery skips what is left to check.

    With a minimum condition, a listing whose condition only shows on its page (Rakuma) keeps
    its place once that page shows a condition good enough, and gives it up otherwise.
    """
    minimum = request.min_condition
    gone: set[int] = set()
    checked: set[int] = set()
    while True:
        remaining = [c for c in candidates if id(c) not in gone]
        picked = compose_parcel(remaining, request.budget_cents, request.card_count)
        picked = fill_parcel(settings, picked, remaining, request.budget_cents, request.card_count)
        unchecked = [c for c in picked if id(c) not in checked]
        if not unchecked or should_stop() or len(checked) >= MAX_CHECKS:
            # Unchecked, a listing without a condition cannot be shown to meet the minimum.
            return [c for c in picked if not minimum or c.listing.condition], gone
        run.verifying = True
        note(run, f"Vérification des {len(unchecked)} annonces du colis : encore en vente ?")
        on_progress(run)
        for candidate in unchecked:
            if should_stop() or len(checked) >= MAX_CHECKS:
                break
            listing = candidate.listing
            result = availability.check_listing(client, listing.source, listing.external_id)
            checked.add(id(candidate))
            run.listings_checked += 1
            # Cardmarket names Pokémon cards after their attacks: "Umbreon V [Mean Look | …]".
            name = (candidate.resolution.product.name or listing.title[:40]).split(" [")[0]
            label = f"{name} · {candidate.resolution.label}"
            site = SOURCE_LABELS[listing.source]
            condition = listing.condition or result.condition
            if result.available is False:
                gone.add(id(candidate))
                run.listings_gone += 1
                note(run, f"{label} ({site}) : déjà vendue, remplacée par la suivante.")
            elif result.seller_warning and result.seller_id:
                # Neokyo would turn the purchase down: the seller is avoided from now on.
                gone.add(id(candidate))
                sellers.block(
                    session, listing.source.value, result.seller_id, result.seller_warning
                )
                note(run, f"{label} ({site}) : vendeur à éviter, {result.seller_warning}.")
            elif minimum and not (condition and condition.at_least(minimum)):
                gone.add(id(candidate))
                state = (
                    f"{CONDITION_NAMES[condition]}, sous l'état demandé"
                    if condition
                    else "état illisible sur l'annonce"
                )
                note(run, f"{label} ({site}) : {state}, remplacée par la suivante.")
            else:
                note(
                    run,
                    f"{label} ({site}) : "
                    + ("encore en vente." if result.available else "non vérifiable, gardée."),
                )
                if listing.condition is None and result.condition is not None:
                    # Rakuma only gives the condition on the listing's own page.
                    candidate.listing = replace(listing, condition=result.condition)
            on_progress(run)
        run.verifying = False


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
    landed_costs = landed_costs_of_parcel(
        settings, [(c.listing.price_jpy, c.listing.shipping_included) for c in picked]
    )
    picks = [
        _pick(candidate, landed, candidate.estimate.sale)
        for candidate, landed in zip(picked, landed_costs, strict=True)
    ]
    totals = parcel_totals(
        [c.listing.price_jpy for c in picked],
        landed_costs,
        [c.estimate.sale for c in picked],
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
        condition=listing.condition,
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
        user_id: int,
        *,
        source_factory: SourceFactory = build_source,
    ) -> None:
        self._session_factory = session_factory
        self._client = client
        self._user_id = user_id
        self._source_factory = source_factory
        self._lock = threading.Lock()
        self._stop = threading.Event()
        with session_factory() as session:
            self.run = load_last_run(session, user_id) or DiscoveryRun(status="idle")

    @property
    def running(self) -> bool:
        return self.run.status == "running"

    def start(self, request: DiscoveryRequest, *, background: bool = True) -> DiscoveryRun:
        with self._lock:
            if self.running:
                return self.run
            self.run = DiscoveryRun(status="running", request=request, started_at=utc_now())
            self._stop.clear()
        if background:
            threading.Thread(
                target=self._execute, args=(request,), name="mekiki-discovery", daemon=True
            ).start()
        else:
            self._execute(request)
        return self.run

    def stop(self) -> DiscoveryRun:
        """Stops browsing; the listings found so far are still evaluated."""
        if self.running:
            self._stop.set()
        return self.run

    def _execute(self, request: DiscoveryRequest) -> None:
        def publish(run: DiscoveryRun) -> None:
            # The lists keep growing in the worker thread while the API serialises the copy.
            self.run = run.model_copy(update={"log": list(run.log), "errors": list(run.errors)})

        try:
            with self._session_factory() as session:
                self.run = discover(
                    session,
                    self._client,
                    self._user_id,
                    request,
                    source_factory=self._source_factory,
                    on_progress=publish,
                    should_stop=self._stop.is_set,
                )
        # A crash must still end the run, or the UI would wait forever.
        except Exception as error:
            failed = self.run.model_copy()
            failed.status = "failed"
            failed.finished_at = utc_now()
            failed.errors = [*failed.errors, f"Erreur inattendue : {error}"]
            note(failed, failed.errors[-1])
            self.run = failed
        with self._session_factory() as session:
            save_last_run(session, self._user_id, self.run)


def last_run_key(user_id: int) -> str:
    return f"discovery:last:{user_id}"


def load_last_run(session: Session, user_id: int) -> DiscoveryRun | None:
    """The last finished discovery, kept so the page shows it again after a restart."""
    row = session.get(SettingRow, last_run_key(user_id))
    if row is None:
        return None
    try:
        run = DiscoveryRun.model_validate_json(row.value)
    except ValueError:
        return None
    # A run cut short by a restart cannot resume.
    return run if run.status != "running" else None


def save_last_run(session: Session, user_id: int, run: DiscoveryRun) -> None:
    row = session.get(SettingRow, last_run_key(user_id))
    if row is None:
        session.add(SettingRow(key=last_run_key(user_id), value=run.model_dump_json()))
    else:
        row.value = run.model_dump_json()
    session.commit()


class DiscoveryJobs:
    """One discovery job per account, created on first use."""

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
        self._jobs: dict[int, DiscoveryJob] = {}
        self._lock = threading.Lock()

    def for_user(self, user_id: int) -> DiscoveryJob:
        with self._lock:
            if user_id not in self._jobs:
                self._jobs[user_id] = DiscoveryJob(
                    self._session_factory,
                    self._client,
                    user_id,
                    source_factory=self._source_factory,
                )
            return self._jobs[user_id]
