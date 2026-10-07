"""Net proceeds and margin of a sale on a European marketplace."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from mekiki_engine.costing.money import to_cents


@dataclass(frozen=True, slots=True)
class PlatformFeeRule:
    rate: Decimal
    fixed_cents: int = 0
    applies_to_shipping: bool = False


@dataclass(frozen=True, slots=True)
class SaleBreakdown:
    revenue_cents: int
    platform_fee_cents: int
    shipping_cost_cents: int
    packaging_cents: int
    contributions_cents: int

    @property
    def net_cents(self) -> int:
        return (
            self.revenue_cents
            - self.platform_fee_cents
            - self.shipping_cost_cents
            - self.packaging_cents
            - self.contributions_cents
        )


def compute_platform_fee(
    rule: PlatformFeeRule, sale_price_cents: int, shipping_charged_cents: int
) -> int:
    base = sale_price_cents + (shipping_charged_cents if rule.applies_to_shipping else 0)
    return to_cents(Decimal(base) / 100 * rule.rate) + rule.fixed_cents


def compute_contributions(revenue_cents: int, contribution_rate: Decimal) -> int:
    """Micro-entrepreneur contributions are levied on turnover, shipping billed included.

    That is why they weigh so much more than the margin suggests: 12.3 % of the sale price
    can exceed half of a thin margin.
    """
    return to_cents(Decimal(revenue_cents) / 100 * contribution_rate)


def compute_sale(
    *,
    sale_price_cents: int,
    shipping_charged_cents: int,
    shipping_cost_cents: int,
    platform_fee_cents: int,
    packaging_cents: int,
    contribution_rate: Decimal,
) -> SaleBreakdown:
    revenue = sale_price_cents + shipping_charged_cents
    return SaleBreakdown(
        revenue_cents=revenue,
        platform_fee_cents=platform_fee_cents,
        shipping_cost_cents=shipping_cost_cents,
        packaging_cents=packaging_cents,
        contributions_cents=compute_contributions(revenue, contribution_rate),
    )


def roi(margin_cents: int, cost_cents: int) -> Decimal | None:
    if cost_cents <= 0:
        return None
    return (Decimal(margin_cents) / Decimal(cost_cents)).quantize(Decimal("0.0001"))
