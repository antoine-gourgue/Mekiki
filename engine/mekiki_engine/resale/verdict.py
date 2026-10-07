"""Whether a card is worth buying: every resale outlet, what it leaves, and a verdict.

The Cardmarket price guide is the reference; the median of eBay's live listings joins it
when the engine has eBay keys. Vinted publishes no prices to software, so it only appears
as a link (see links.py).
"""

from __future__ import annotations

from typing import Literal

from mekiki_engine.costing.money import percent_to_fraction
from mekiki_engine.costing.sale import roi
from mekiki_engine.domain import SalePlatform
from mekiki_engine.models import CardmarketProduct
from mekiki_engine.scanner.pricing import (
    landed_cost_of_listing,
    max_buy_price_jpy,
    reference_price,
)
from mekiki_engine.schemas import (
    AppSettings,
    CardVerdict,
    ResaleOutlet,
    ResalePrices,
    VerdictSignal,
)
from mekiki_engine.services.portfolio import project_sale

Verdict = Literal["good", "fair", "bad", "suspicious", "unknown", "limit"]

REFERENCE_LABELS = {
    "avg30": "moyenne des ventes sur 30 jours",
    "avg7": "moyenne des ventes sur 7 jours",
    "avg": "prix moyen",
    "avg1": "ventes de la veille",
    "trend": "tendance",
}
PLATFORM_LABELS = {SalePlatform.CARDMARKET: "Cardmarket", SalePlatform.EBAY: "eBay"}
# Same rule as discovery: below this share of the price guide, it is not the real card.
SUSPICIOUS_PRICE_SHARE = 0.2
# A week's average this far from the month's shows a moving price.
TREND_THRESHOLD = 0.10
# Fewer eBay listings than this give a median too thin to trust alone.
FEW_EBAY_LISTINGS = 5


def card_verdict(
    settings: AppSettings,
    product: CardmarketProduct | None,
    prices: ResalePrices,
    *,
    price_jpy: int | None = None,
    shipping_included: bool | None = None,
    landed_cents: int | None = None,
    selling: bool = False,
) -> CardVerdict:
    """Judges a card bought at ``price_jpy`` (a Japanese listing), or at its real
    ``landed_cents`` (a card in stock), or without any price (a catalog product: only the
    most to pay in Japan). ``selling`` words the verdict for a card already bought."""
    if landed_cents is None and price_jpy is not None:
        landed_cents = landed_cost_of_listing(settings, price_jpy, shipping_included).total_cents

    outlets = [
        _outlet(settings, platform, sale_cents, basis, landed_cents)
        for platform, sale_cents, basis in _resale_prices(product, prices)
    ]
    outlets.sort(key=lambda o: (o.roi if o.roi is not None else -1e9, o.net_cents), reverse=True)

    reference = reference_price(product)
    verdict, headline = _judge(
        settings, outlets, price_jpy, landed_cents, reference[0] if reference else None
    )
    if selling:
        headline = _selling_headline(settings, verdict, outlets) or headline
    signals = _signals(product, prices)
    if verdict == "suspicious":
        signals.insert(
            0,
            VerdictSignal(
                tone="negative",
                text="Prix à moins de 20 % de la cote : sans doute une reproduction, un "
                "accessoire ou une autre version de la carte.",
            ),
        )
    return CardVerdict(
        verdict=verdict,
        headline=headline,
        target_roi=float(percent_to_fraction(settings.scanner.min_roi_percent)),
        price_jpy=price_jpy,
        landed_cents=landed_cents,
        outlets=outlets,
        signals=signals,
        prices=prices,
    )


def _resale_prices(
    product: CardmarketProduct | None, prices: ResalePrices
) -> list[tuple[SalePlatform, int, str]]:
    found = []
    reference = reference_price(product)
    if reference is not None:
        label = REFERENCE_LABELS.get(reference[1], reference[1])
        found.append((SalePlatform.CARDMARKET, reference[0], f"Cote Cardmarket, {label}"))
    ebay = prices.ebay
    if ebay.median_cents is not None:
        basis = f"Médiane de {len(ebay.listings)} annonces eBay en cours"
        found.append((SalePlatform.EBAY, ebay.median_cents, basis))
    return found


def _outlet(
    settings: AppSettings,
    platform: SalePlatform,
    sale_cents: int,
    basis: str,
    landed_cents: int | None,
) -> ResaleOutlet:
    sale = project_sale(settings, platform, sale_cents)
    margin = None if landed_cents is None else sale.net_cents - landed_cents
    ratio = None if margin is None or not landed_cents else roi(margin, landed_cents)
    return ResaleOutlet(
        platform=platform,
        sale_cents=sale_cents,
        basis=basis,
        net_cents=sale.net_cents,
        max_buy_jpy=max_buy_price_jpy(settings, sale_cents, platform),
        margin_cents=margin,
        roi=None if ratio is None else float(ratio),
    )


def _judge(
    settings: AppSettings,
    outlets: list[ResaleOutlet],
    price_jpy: int | None,
    landed_cents: int | None,
    reference_cents: int | None,
) -> tuple[Verdict, str]:
    target_percent = f"{settings.scanner.min_roi_percent:g} %"
    if not outlets:
        return "unknown", "Pas de prix de revente connu : impossible de juger cette carte."
    best = outlets[0]
    where = PLATFORM_LABELS.get(best.platform, best.platform.value)
    if landed_cents is None:
        if not best.max_buy_jpy or best.max_buy_jpy <= 0:
            return "bad", f"Même très bon marché, cette carte ne rapporterait pas {target_percent}."
        return (
            "limit",
            f"À acheter {_yen(best.max_buy_jpy)} au plus, port compris, pour viser "
            f"{target_percent} en revendant sur {where}.",
        )
    if (
        price_jpy is not None
        and reference_cents
        and price_jpy / float(settings.fx_jpy_per_eur) * 100
        < SUSPICIOUS_PRICE_SHARE * reference_cents
    ):
        return "suspicious", "Trop beau pour être vrai : vérifiez l'annonce avant d'acheter."
    margin = best.margin_cents or 0
    target = float(percent_to_fraction(settings.scanner.min_roi_percent))
    if best.roi is not None and best.roi >= target:
        return "good", f"Bonne affaire : {_euros(margin)} de marge en revendant sur {where}."
    if margin >= 0:
        return "fair", f"Rentable, mais sous votre objectif de {target_percent} ({where})."
    return "bad", f"À éviter : {_euros(-margin)} de perte, même sur {where}."


def _selling_headline(
    settings: AppSettings, verdict: Verdict, outlets: list[ResaleOutlet]
) -> str | None:
    if not outlets or outlets[0].margin_cents is None:
        return None
    best = outlets[0]
    where = PLATFORM_LABELS.get(best.platform, best.platform.value)
    margin = best.margin_cents or 0
    if verdict == "good":
        return f"À vendre sur {where} : {_euros(margin)} de marge à la cote actuelle."
    if verdict == "fair":
        target = f"{settings.scanner.min_roi_percent:g} %"
        return f"Marge faible : {_euros(margin)} sur {where}, sous votre objectif de {target}."
    if verdict == "bad":
        return f"Perte de {_euros(-margin)} même sur {where} : attendez une meilleure cote."
    return None


def _signals(product: CardmarketProduct | None, prices: ResalePrices) -> list[VerdictSignal]:
    signals: list[VerdictSignal] = []
    if product is not None and product.avg7_cents and product.avg30_cents:
        change = product.avg7_cents / product.avg30_cents - 1
        if change >= TREND_THRESHOLD:
            text = (
                f"Cote en hausse : la moyenne sur 7 jours dépasse de {change:.0%} celle sur "
                "30 jours."
            )
            signals.append(VerdictSignal(tone="positive", text=text))
        elif change <= -TREND_THRESHOLD:
            text = (
                f"Cote en baisse : la moyenne sur 7 jours est {-change:.0%} sous celle sur "
                "30 jours."
            )
            signals.append(VerdictSignal(tone="warning", text=text))
    if reference_price(product) is not None:
        text = (
            "La cote Cardmarket mélange langues et états : une carte japonaise se vend souvent "
            "un peu moins cher que l'anglaise."
        )
        signals.append(VerdictSignal(tone="neutral", text=text))
    ebay = prices.ebay
    if not ebay.configured:
        text = (
            "Prix eBay en direct indisponibles : ouvrez les ventes réussies eBay et les "
            "annonces Vinted pour compléter."
        )
        signals.append(VerdictSignal(tone="neutral", text=text))
    elif ebay.listings and len(ebay.listings) < FEW_EBAY_LISTINGS:
        text = f"Seulement {len(ebay.listings)} annonces eBay : la médiane est fragile."
        signals.append(VerdictSignal(tone="warning", text=text))
    elif ebay.listings:
        text = (
            f"{ebay.total} annonces en vente sur eBay : vérifiez les ventes réussies avant "
            "de fixer votre prix."
        )
        signals.append(VerdictSignal(tone="neutral", text=text))
    return signals


def _euros(cents: int) -> str:
    return f"{cents / 100:.2f} €".replace(".", ",")


def _yen(amount: int) -> str:
    return f"{amount:,} ¥".replace(",", " ")
