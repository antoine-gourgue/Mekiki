"""Landed cost of cards bought through a Japanese proxy and imported into the EU.

A lot is one international parcel: every card in it pays its own price, Japanese domestic
shipping and proxy service fee, then shares the parcel-level costs (packing, international
shipping, payment fees, import VAT, customs duty, carrier handling fee) pro rata to its
price, the same basis customs uses to compute VAT.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from mekiki_engine.costing.money import jpy_to_cents, jpy_to_eur, split_cents, to_cents


@dataclass(frozen=True, slots=True)
class ItemCostInput:
    price_jpy: int
    domestic_shipping_jpy: int = 0
    service_fee_jpy: int = 0


@dataclass(frozen=True, slots=True)
class LotCostInput:
    fx_jpy_per_eur: Decimal
    packing_fee_jpy: int = 0
    international_shipping_jpy: int = 0
    insurance_jpy: int = 0
    other_fees_jpy: int = 0
    payment_fees_cents: int = 0
    # ``None`` until the carrier invoice arrives: the VAT is then estimated.
    import_vat_cents: int | None = None
    customs_duty_cents: int = 0
    handling_fee_cents: int = 0


@dataclass(frozen=True, slots=True)
class ItemLandedCost:
    purchase_cents: int
    proxy_fees_cents: int
    shipping_cents: int
    import_taxes_cents: int
    vat_estimated: bool

    @property
    def total_cents(self) -> int:
        return (
            self.purchase_cents
            + self.proxy_fees_cents
            + self.shipping_cents
            + self.import_taxes_cents
        )


def estimate_import_vat_cents(
    lot: LotCostInput, items: Sequence[ItemCostInput], vat_rate: Decimal
) -> int:
    """Import VAT on the customs value: goods plus transport up to the EU border.

    Proxy service fees are buying commissions, which EU customs rules leave out of the
    customs value.
    """
    goods_jpy = sum(i.price_jpy + i.domestic_shipping_jpy for i in items)
    transport_jpy = lot.international_shipping_jpy + lot.insurance_jpy
    customs_value = jpy_to_eur(goods_jpy + transport_jpy, lot.fx_jpy_per_eur)
    return to_cents(customs_value * vat_rate)


def allocate_lot(
    lot: LotCostInput, items: Sequence[ItemCostInput], vat_rate: Decimal
) -> list[ItemLandedCost]:
    """Landed cost of each item of ``lot``, in the same order as ``items``.

    ``vat_rate`` is a fraction (0.20 for 20 %) and is only used when the lot has no actual
    import VAT amount yet.
    """
    if not items:
        return []

    fx = lot.fx_jpy_per_eur
    weights = [i.price_jpy for i in items]

    shared_proxy = jpy_to_cents(lot.packing_fee_jpy + lot.other_fees_jpy, fx)
    shared_proxy += lot.payment_fees_cents
    shared_shipping = jpy_to_cents(lot.international_shipping_jpy + lot.insurance_jpy, fx)

    vat_estimated = lot.import_vat_cents is None
    vat_cents = (
        estimate_import_vat_cents(lot, items, vat_rate)
        if lot.import_vat_cents is None
        else lot.import_vat_cents
    )
    shared_taxes = vat_cents + lot.customs_duty_cents + lot.handling_fee_cents

    proxy_parts = split_cents(shared_proxy, weights)
    shipping_parts = split_cents(shared_shipping, weights)
    tax_parts = split_cents(shared_taxes, weights)

    return [
        ItemLandedCost(
            purchase_cents=jpy_to_cents(item.price_jpy + item.domestic_shipping_jpy, fx),
            proxy_fees_cents=jpy_to_cents(item.service_fee_jpy, fx) + proxy_parts[idx],
            shipping_cents=shipping_parts[idx],
            import_taxes_cents=tax_parts[idx],
            vat_estimated=vat_estimated,
        )
        for idx, item in enumerate(items)
    ]
