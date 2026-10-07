from decimal import Decimal

from mekiki_engine.costing.landed_cost import (
    ItemCostInput,
    LotCostInput,
    allocate_lot,
    estimate_import_vat_cents,
)

VAT = Decimal("0.20")


def reference_lot(**overrides: object) -> LotCostInput:
    """Section 4 reference parcel: 10 cards, 500 JPY packing, 4000 JPY shipping, 10 EUR handling."""
    fields: dict[str, object] = {
        "fx_jpy_per_eur": Decimal(170),
        "packing_fee_jpy": 500,
        "international_shipping_jpy": 4000,
        "handling_fee_cents": 1000,
    }
    fields.update(overrides)
    return LotCostInput(**fields)  # type: ignore[arg-type]


REFERENCE_ITEMS = [ItemCostInput(price_jpy=8000, service_fee_jpy=350)] * 10


def test_reference_case_first_card() -> None:
    first = allocate_lot(reference_lot(), REFERENCE_ITEMS, VAT)[0]

    assert first.purchase_cents == 4706
    assert first.proxy_fees_cents == 236
    assert first.shipping_cents == 236
    assert first.import_taxes_cents == 1089
    assert first.total_cents == 6267
    assert first.vat_estimated is True


def test_reference_case_vat_estimate() -> None:
    # 20 % of (80 000 + 4 000) JPY at 170 JPY/EUR = 98.82 EUR; proxy fees stay out of the base.
    assert estimate_import_vat_cents(reference_lot(), REFERENCE_ITEMS, VAT) == 9882


def test_allocation_adds_up_to_what_the_parcel_cost() -> None:
    lot = reference_lot(payment_fees_cents=137, insurance_jpy=300, customs_duty_cents=321)
    items = [
        ItemCostInput(price_jpy=12000, domestic_shipping_jpy=230, service_fee_jpy=350),
        ItemCostInput(price_jpy=777, service_fee_jpy=350),
        ItemCostInput(price_jpy=3456, domestic_shipping_jpy=185, service_fee_jpy=350),
    ]
    costs = allocate_lot(lot, items, VAT)

    shared_proxy = round(Decimal(500) / 170 * 100) + 137
    shared_shipping = round(Decimal(4300) / 170 * 100)
    vat = estimate_import_vat_cents(lot, items, VAT)
    service_fees = 3 * round(Decimal(350) / 170 * 100)

    assert sum(c.proxy_fees_cents for c in costs) == shared_proxy + service_fees
    assert sum(c.shipping_cents for c in costs) == shared_shipping
    assert sum(c.import_taxes_cents for c in costs) == vat + 321 + 1000


def test_shared_costs_follow_the_card_price() -> None:
    items = [ItemCostInput(price_jpy=9000), ItemCostInput(price_jpy=1000)]
    expensive, cheap = allocate_lot(reference_lot(), items, VAT)

    assert expensive.shipping_cents > 8 * cheap.shipping_cents
    assert expensive.import_taxes_cents > 8 * cheap.import_taxes_cents


def test_actual_vat_replaces_the_estimate() -> None:
    estimated = allocate_lot(reference_lot(), REFERENCE_ITEMS, VAT)
    actual = allocate_lot(reference_lot(import_vat_cents=12000), REFERENCE_ITEMS, VAT)

    assert all(not c.vat_estimated for c in actual)
    assert sum(c.import_taxes_cents for c in actual) == 12000 + 1000
    assert sum(c.import_taxes_cents for c in estimated) == 9882 + 1000


def test_actual_vat_of_zero_is_not_an_estimate() -> None:
    costs = allocate_lot(
        reference_lot(import_vat_cents=0, handling_fee_cents=0), REFERENCE_ITEMS, VAT
    )

    assert all(c.import_taxes_cents == 0 and not c.vat_estimated for c in costs)


def test_empty_lot_has_no_costs() -> None:
    assert allocate_lot(reference_lot(), [], VAT) == []
