from decimal import Decimal

from mekiki_engine.costing.sale import (
    PlatformFeeRule,
    compute_contributions,
    compute_platform_fee,
    compute_sale,
    roi,
)

CARDMARKET = PlatformFeeRule(rate=Decimal("0.05"))
CONTRIBUTIONS = Decimal("0.123")


def test_reference_sale_on_cardmarket() -> None:
    fee = compute_platform_fee(CARDMARKET, 9000, 0)
    sale = compute_sale(
        sale_price_cents=9000,
        shipping_charged_cents=0,
        shipping_cost_cents=0,
        platform_fee_cents=fee,
        packaging_cents=50,
        contribution_rate=CONTRIBUTIONS,
    )

    assert fee == 450
    assert sale.revenue_cents == 9000
    assert sale.contributions_cents == 1107
    assert sale.net_cents == 7393

    margin = sale.net_cents - 6267
    assert margin == 1126
    assert roi(margin, 6267) == Decimal("0.1797")


def test_platform_fee_ignores_shipping_unless_the_rule_says_so() -> None:
    with_shipping = PlatformFeeRule(rate=Decimal("0.05"), applies_to_shipping=True)

    assert compute_platform_fee(CARDMARKET, 9000, 500) == 450
    assert compute_platform_fee(with_shipping, 9000, 500) == 475


def test_platform_fee_adds_the_fixed_part() -> None:
    rule = PlatformFeeRule(rate=Decimal("0.08"), fixed_cents=35)

    assert compute_platform_fee(rule, 1999, 0) == 160 + 35


def test_contributions_are_levied_on_turnover_shipping_included() -> None:
    sale = compute_sale(
        sale_price_cents=2000,
        shipping_charged_cents=400,
        shipping_cost_cents=380,
        platform_fee_cents=0,
        packaging_cents=50,
        contribution_rate=Decimal("0.133"),
    )

    assert sale.revenue_cents == 2400
    assert sale.contributions_cents == compute_contributions(2400, Decimal("0.133")) == 319
    assert sale.net_cents == 2400 - 380 - 50 - 319


def test_roi_is_undefined_without_a_cost() -> None:
    assert roi(100, 0) is None
    assert roi(-250, 1000) == Decimal("-0.25")
