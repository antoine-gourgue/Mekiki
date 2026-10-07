"""What a listing would earn: expected resale price, landed cost and margin."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from mekiki_engine.costing.landed_cost import (
    ItemCostInput,
    ItemLandedCost,
    LotCostInput,
    allocate_lot,
)
from mekiki_engine.costing.money import percent_to_fraction
from mekiki_engine.costing.sale import SaleBreakdown, roi
from mekiki_engine.domain import SalePlatform
from mekiki_engine.models import CardmarketProduct
from mekiki_engine.schemas import AppSettings, DiscoveryTotals
from mekiki_engine.services.portfolio import (
    max_price_jpy_for_roi,
    parcel_landed_cost,
    project_sale,
    vat_rate,
)

# Cardmarket's price guide ignores language and condition; averages of actual sales are the
# least misleading figure, and "low" (the cheapest offer, often damaged) is never used.
REFERENCE_FIELDS = ("avg30", "avg7", "avg", "avg1", "trend")


def reference_price(product: CardmarketProduct | None) -> tuple[int, str] | None:
    """The price guide value used as resale price, with the field it came from."""
    if product is None:
        return None
    for field in REFERENCE_FIELDS:
        value = getattr(product, f"{field}_cents")
        if value:
            return value, field
    return None


def expected_sale_cents(
    target_price_cents: int | None, product: CardmarketProduct | None
) -> int | None:
    if target_price_cents is not None:
        return target_price_cents
    reference = reference_price(product)
    return reference[0] if reference else None


@dataclass(frozen=True, slots=True)
class DealEstimate:
    landed: ItemLandedCost
    sale: SaleBreakdown | None

    @property
    def margin_cents(self) -> int | None:
        return None if self.sale is None else self.sale.net_cents - self.landed.total_cents


def domestic_shipping_jpy(settings: AppSettings, shipping_included: bool | None) -> int:
    # Unknown counts as not included: better to underestimate a deal than to chase a loss.
    return 0 if shipping_included else settings.scanner.domestic_shipping_jpy


def landed_cost_of_listing(
    settings: AppSettings, price_jpy: int, shipping_included: bool | None
) -> ItemLandedCost:
    return parcel_landed_cost(
        settings,
        price_jpy=price_jpy,
        domestic_shipping_jpy=domestic_shipping_jpy(settings, shipping_included),
        cards_in_lot=settings.scanner.cards_per_lot,
        lot_shipping_jpy=settings.scanner.lot_shipping_jpy,
        fx_jpy_per_eur=settings.fx_jpy_per_eur,
    )


def estimate_listing(
    settings: AppSettings,
    *,
    price_jpy: int,
    shipping_included: bool | None,
    expected_sale_cents: int | None,
) -> DealEstimate:
    landed = landed_cost_of_listing(settings, price_jpy, shipping_included)
    sale = (
        None
        if expected_sale_cents is None
        else project_sale(settings, settings.scanner.resale_platform, expected_sale_cents)
    )
    return DealEstimate(landed=landed, sale=sale)


def max_buy_price_jpy(
    settings: AppSettings,
    expected_sale_cents: int | None,
    platform: SalePlatform | None = None,
) -> int | None:
    """Highest asking price (shipping included) that still reaches the scanner's ROI target.

    The resale goes through ``platform``, by default the one set for the scanner.
    """
    if expected_sale_cents is None:
        return None
    sale = project_sale(settings, platform or settings.scanner.resale_platform, expected_sale_cents)
    return max_price_jpy_for_roi(
        lambda price: landed_cost_of_listing(settings, price, True),
        sale.net_cents,
        percent_to_fraction(settings.scanner.min_roi_percent),
        settings.fx_jpy_per_eur,
    )


def meets_target(settings: AppSettings, estimate: DealEstimate) -> bool:
    margin = estimate.margin_cents
    if margin is None or estimate.landed.total_cents <= 0:
        return False
    target = percent_to_fraction(settings.scanner.min_roi_percent)
    return margin >= target * estimate.landed.total_cents


def landed_costs_of_parcel(
    settings: AppSettings, listings: Sequence[tuple[int, bool | None]]
) -> list[ItemLandedCost]:
    """Listings bought together, as (price, shipping included): shared costs split by price."""
    if not listings:
        return []
    lot = LotCostInput(
        fx_jpy_per_eur=settings.fx_jpy_per_eur,
        packing_fee_jpy=settings.neokyo_packing_fee_jpy,
        international_shipping_jpy=settings.scanner.lot_shipping_jpy,
        handling_fee_cents=settings.default_handling_fee_cents,
    )
    items = [
        ItemCostInput(
            price_jpy=price,
            domestic_shipping_jpy=domestic_shipping_jpy(settings, shipping_included),
            service_fee_jpy=settings.neokyo_service_fee_jpy,
        )
        for price, shipping_included in listings
    ]
    return allocate_lot(lot, items, vat_rate(settings))


def parcel_totals(
    prices_jpy: Sequence[int],
    landed: Sequence[ItemLandedCost],
    sales: Sequence[SaleBreakdown | None],
) -> DiscoveryTotals:
    landed_total = sum(cost.total_cents for cost in landed)
    net_total = sum(sale.net_cents for sale in sales if sale)
    margin = net_total - landed_total
    return DiscoveryTotals(
        card_count=len(landed),
        purchase_jpy=sum(prices_jpy),
        landed_cents=landed_total,
        revenue_cents=sum(sale.revenue_cents for sale in sales if sale),
        net_cents=net_total,
        margin_cents=margin,
        roi=roi(margin, landed_total),
        unpriced_count=sum(1 for sale in sales if sale is None),
    )
