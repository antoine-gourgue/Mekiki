"""Lots, cards and sales: loads them, runs the costing maths and shapes the API outputs.

Landed costs are never stored. They are recomputed from the lot on every read, so a carrier
invoice entered after a sale still corrects the margin of that sale.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from mekiki_engine.costing.landed_cost import (
    ItemCostInput,
    ItemLandedCost,
    LotCostInput,
    allocate_lot,
    estimate_import_vat_cents,
)
from mekiki_engine.costing.money import percent_to_fraction
from mekiki_engine.costing.sale import (
    PlatformFeeRule,
    SaleBreakdown,
    compute_platform_fee,
    compute_sale,
    roi,
)
from mekiki_engine.domain import Game, ItemStatus, LotStatus, SalePlatform
from mekiki_engine.models import Item, Lot, Sale
from mekiki_engine.schemas import (
    AppSettings,
    Dashboard,
    ItemCreate,
    ItemFields,
    ItemOut,
    ItemUpdate,
    LandedCostOut,
    LotCreate,
    LotDetail,
    LotFields,
    LotOut,
    LotUpdate,
    MonthlySales,
    SaleBreakdownOut,
    SaleOut,
    SaleUpsert,
    SimulationRequest,
    SimulationResult,
)


class NotFoundError(LookupError):
    """The requested lot or card does not exist."""


def vat_rate(settings: AppSettings) -> Decimal:
    return percent_to_fraction(settings.vat_rate_percent)


def contribution_rate(settings: AppSettings) -> Decimal:
    """URSSAF contributions plus the optional flat income tax, both levied on turnover."""
    return percent_to_fraction(
        settings.contribution_rate_percent + settings.income_tax_rate_percent
    )


def fee_rule(settings: AppSettings, platform: SalePlatform) -> PlatformFeeRule:
    fees = settings.platform_fees[platform]
    return PlatformFeeRule(
        rate=percent_to_fraction(fees.percent),
        fixed_cents=fees.fixed_cents,
        applies_to_shipping=fees.applies_to_shipping,
    )


def item_status(item: Item) -> ItemStatus:
    if item.sale is not None:
        return ItemStatus.SOLD
    if item.lot.status != LotStatus.RECEIVED:
        return ItemStatus.INCOMING
    if item.listing_platform is not None and item.listing_price_cents is not None:
        return ItemStatus.LISTED
    return ItemStatus.IN_STOCK


def project_sale(
    settings: AppSettings,
    platform: SalePlatform,
    sale_price_cents: int,
    *,
    shipping_charged_cents: int = 0,
    shipping_cost_cents: int = 0,
) -> SaleBreakdown:
    """What a sale would leave under the current settings."""
    return compute_sale(
        sale_price_cents=sale_price_cents,
        shipping_charged_cents=shipping_charged_cents,
        shipping_cost_cents=shipping_cost_cents,
        platform_fee_cents=compute_platform_fee(
            fee_rule(settings, platform), sale_price_cents, shipping_charged_cents
        ),
        packaging_cents=settings.default_packaging_cents,
        contribution_rate=contribution_rate(settings),
    )


@dataclass(frozen=True, slots=True)
class LotCosting:
    applied_import_vat_cents: int
    by_item: dict[int, ItemLandedCost]


def cost_lot(lot: Lot, settings: AppSettings) -> LotCosting:
    lot_input = LotCostInput(
        fx_jpy_per_eur=Decimal(lot.fx_jpy_per_eur),
        packing_fee_jpy=lot.packing_fee_jpy,
        international_shipping_jpy=lot.international_shipping_jpy,
        insurance_jpy=lot.insurance_jpy,
        other_fees_jpy=lot.other_fees_jpy,
        payment_fees_cents=lot.payment_fees_cents,
        import_vat_cents=lot.import_vat_cents,
        customs_duty_cents=lot.customs_duty_cents,
        handling_fee_cents=lot.handling_fee_cents,
    )
    item_inputs = [
        ItemCostInput(
            price_jpy=item.price_jpy,
            domestic_shipping_jpy=item.domestic_shipping_jpy,
            service_fee_jpy=item.service_fee_jpy,
        )
        for item in lot.items
    ]
    rate = vat_rate(settings)
    landed = allocate_lot(lot_input, item_inputs, rate)
    vat = (
        lot.import_vat_cents
        if lot.import_vat_cents is not None
        else estimate_import_vat_cents(lot_input, item_inputs, rate)
    )
    return LotCosting(
        applied_import_vat_cents=vat,
        by_item={item.id: cost for item, cost in zip(lot.items, landed, strict=True)},
    )


def list_lots(session: Session, user_id: int, settings: AppSettings) -> list[LotOut]:
    return [
        LotOut(**_lot_fields(lot, cost_lot(lot, settings))) for lot in _load_lots(session, user_id)
    ]


def lot_detail(session: Session, user_id: int, settings: AppSettings, lot_id: int) -> LotDetail:
    lot = _get_lot(session, user_id, lot_id)
    costing = cost_lot(lot, settings)
    return LotDetail(
        **_lot_fields(lot, costing),
        items=[_item_out(item, costing.by_item[item.id], settings) for item in lot.items],
    )


def create_lot(
    session: Session, user_id: int, settings: AppSettings, payload: LotCreate
) -> LotDetail:
    defaults = {"fx_jpy_per_eur", "packing_fee_jpy", "handling_fee_cents"}
    lot = Lot(
        **_to_columns(payload.model_dump(exclude=defaults)),
        user_id=user_id,
        fx_jpy_per_eur=str(_or(payload.fx_jpy_per_eur, settings.fx_jpy_per_eur)),
        packing_fee_jpy=_or(payload.packing_fee_jpy, settings.neokyo_packing_fee_jpy),
        handling_fee_cents=_or(payload.handling_fee_cents, settings.default_handling_fee_cents),
    )
    session.add(lot)
    _commit(session)
    return lot_detail(session, user_id, settings, lot.id)


def update_lot(
    session: Session, user_id: int, settings: AppSettings, lot_id: int, payload: LotUpdate
) -> LotDetail:
    lot = _get_lot(session, user_id, lot_id)
    for name, value in _to_columns(payload.model_dump(exclude_unset=True)).items():
        setattr(lot, name, value)
    _commit(session)
    return lot_detail(session, user_id, settings, lot_id)


def delete_lot(session: Session, user_id: int, lot_id: int) -> None:
    session.delete(_get_lot(session, user_id, lot_id))
    _commit(session)


def item_detail(session: Session, user_id: int, settings: AppSettings, item_id: int) -> ItemOut:
    item = get_item(session, user_id, item_id)
    return _item_out(item, cost_lot(item.lot, settings).by_item[item.id], settings)


def add_item(
    session: Session, user_id: int, settings: AppSettings, lot_id: int, payload: ItemCreate
) -> ItemOut:
    lot = _get_lot(session, user_id, lot_id)
    item = Item(
        **_to_columns(payload.model_dump(exclude={"service_fee_jpy"})),
        service_fee_jpy=_or(payload.service_fee_jpy, settings.neokyo_service_fee_jpy),
    )
    lot.items.append(item)
    _commit(session)
    return item_detail(session, user_id, settings, item.id)


def update_item(
    session: Session, user_id: int, settings: AppSettings, item_id: int, payload: ItemUpdate
) -> ItemOut:
    item = get_item(session, user_id, item_id)
    values = _to_columns(payload.model_dump(exclude_unset=True))
    if "lot_id" in values:
        # Going through the relationship keeps both lots' item lists in sync.
        item.lot = _get_lot(session, user_id, values.pop("lot_id"))
    for name, value in values.items():
        setattr(item, name, value)
    _commit(session)
    return item_detail(session, user_id, settings, item_id)


def delete_item(session: Session, user_id: int, item_id: int) -> None:
    session.delete(get_item(session, user_id, item_id))
    _commit(session)


def record_sale(
    session: Session, user_id: int, settings: AppSettings, item_id: int, payload: SaleUpsert
) -> ItemOut:
    item = get_item(session, user_id, item_id)
    platform_fee = payload.platform_fee_cents
    if platform_fee is None:
        platform_fee = compute_platform_fee(
            fee_rule(settings, payload.platform),
            payload.sale_price_cents,
            payload.shipping_charged_cents,
        )
    values = _to_columns(
        {
            **payload.model_dump(exclude={"platform_fee_cents", "packaging_cents"}),
            "platform_fee_cents": platform_fee,
            "packaging_cents": _or(payload.packaging_cents, settings.default_packaging_cents),
        }
    )
    if item.sale is None:
        item.sale = Sale(**values, contribution_rate=str(contribution_rate(settings)))
    else:
        # Editing a sale keeps the contribution rate that was in force when it was recorded.
        for name, value in values.items():
            setattr(item.sale, name, value)
    _commit(session)
    return item_detail(session, user_id, settings, item_id)


def cancel_sale(session: Session, user_id: int, settings: AppSettings, item_id: int) -> ItemOut:
    item = get_item(session, user_id, item_id)
    if item.sale is not None:
        item.sale = None
        _commit(session)
    return item_detail(session, user_id, settings, item_id)


def inventory(
    session: Session,
    user_id: int,
    settings: AppSettings,
    *,
    status: ItemStatus | None = None,
    game: Game | None = None,
) -> list[ItemOut]:
    items = [
        _item_out(item, landed, settings)
        for item, landed in _costed_items(session, user_id, settings)
        if (game is None or item.game == game) and (status is None or item_status(item) is status)
    ]
    return sorted(items, key=lambda item: item.id, reverse=True)


def dashboard(
    session: Session,
    user_id: int,
    settings: AppSettings,
    *,
    since: date | None = None,
    until: date | None = None,
) -> Dashboard:
    """Current stock, plus the sales recorded between ``since`` and ``until`` (inclusive)."""
    counts = dict.fromkeys(ItemStatus, 0)
    stock_cost = listed_price = listed_margin = 0
    revenue = net = cost_of_sold = 0
    monthly: dict[str, MonthlySales] = {}

    for item, landed in _costed_items(session, user_id, settings):
        status = item_status(item)
        if item.sale is None:
            counts[status] += 1
            stock_cost += landed.total_cents
            if status is ItemStatus.LISTED and item.listing_price_cents is not None:
                projection = project_sale(
                    settings, SalePlatform(item.listing_platform), item.listing_price_cents
                )
                listed_price += item.listing_price_cents
                listed_margin += projection.net_cents - landed.total_cents
            continue

        sold_on = date.fromisoformat(item.sale.sold_on)
        if (since is not None and sold_on < since) or (until is not None and sold_on > until):
            continue
        sale = _recorded_sale(item.sale)
        counts[status] += 1
        revenue += sale.revenue_cents
        net += sale.net_cents
        cost_of_sold += landed.total_cents
        key = sold_on.strftime("%Y-%m")
        if key not in monthly:
            monthly[key] = MonthlySales(
                month=key, sold_count=0, revenue_cents=0, net_cents=0, margin_cents=0
            )
        month = monthly[key]
        month.sold_count += 1
        month.revenue_cents += sale.revenue_cents
        month.net_cents += sale.net_cents
        month.margin_cents += sale.net_cents - landed.total_cents

    return Dashboard(
        incoming_count=counts[ItemStatus.INCOMING],
        in_stock_count=counts[ItemStatus.IN_STOCK],
        listed_count=counts[ItemStatus.LISTED],
        stock_cost_cents=stock_cost,
        listed_price_cents=listed_price,
        listed_expected_margin_cents=listed_margin,
        sold_count=counts[ItemStatus.SOLD],
        revenue_cents=revenue,
        net_cents=net,
        cost_of_sold_cents=cost_of_sold,
        margin_cents=net - cost_of_sold,
        roi=roi(net - cost_of_sold, cost_of_sold),
        monthly=[monthly[key] for key in sorted(monthly)],
    )


def parcel_landed_cost(
    settings: AppSettings,
    *,
    price_jpy: int,
    domestic_shipping_jpy: int,
    cards_in_lot: int,
    lot_shipping_jpy: int,
    fx_jpy_per_eur: Decimal,
) -> ItemLandedCost:
    """Landed cost of one card bought in a parcel of ``cards_in_lot`` identical cards."""
    lot = LotCostInput(
        fx_jpy_per_eur=fx_jpy_per_eur,
        packing_fee_jpy=settings.neokyo_packing_fee_jpy,
        international_shipping_jpy=lot_shipping_jpy,
        handling_fee_cents=settings.default_handling_fee_cents,
    )
    card = ItemCostInput(
        price_jpy=price_jpy,
        domestic_shipping_jpy=domestic_shipping_jpy,
        service_fee_jpy=settings.neokyo_service_fee_jpy,
    )
    # The first card collects the rounding leftovers: it is the costliest of the parcel.
    return allocate_lot(lot, [card] * cards_in_lot, vat_rate(settings))[0]


def simulate(settings: AppSettings, request: SimulationRequest) -> SimulationResult:
    """Prices one card bought in a parcel of ``cards_in_lot`` identical cards."""
    fx = _or(request.fx_jpy_per_eur, settings.fx_jpy_per_eur)

    def landed_at(price_jpy: int) -> ItemLandedCost:
        return parcel_landed_cost(
            settings,
            price_jpy=price_jpy,
            domestic_shipping_jpy=request.domestic_shipping_jpy,
            cards_in_lot=request.cards_in_lot,
            lot_shipping_jpy=request.lot_shipping_jpy,
            fx_jpy_per_eur=fx,
        )

    sale = project_sale(
        settings,
        request.platform,
        request.sale_price_cents,
        shipping_charged_cents=request.shipping_charged_cents,
        shipping_cost_cents=request.shipping_cost_cents,
    )
    landed = landed_at(request.price_jpy)
    max_price = (
        None
        if request.target_roi_percent is None
        else max_price_jpy_for_roi(
            landed_at, sale.net_cents, percent_to_fraction(request.target_roi_percent), fx
        )
    )
    return SimulationResult(
        landed_cost=_landed_out(landed),
        sale=_breakdown_out(sale, landed.total_cents),
        fx_jpy_per_eur=fx,
        max_price_jpy=max_price,
    )


def max_price_jpy_for_roi(
    landed_at: Callable[[int], ItemLandedCost],
    net_cents: int,
    target_roi: Decimal,
    fx_jpy_per_eur: Decimal,
) -> int | None:
    """Highest card price whose ROI still reaches ``target_roi``.

    The landed cost grows with the price while the net of the sale stays put, so the ROI only
    falls as the price rises and a binary search finds the threshold.
    """

    def meets_target(price_jpy: int) -> bool:
        cost = landed_at(price_jpy).total_cents
        return cost > 0 and net_cents - cost >= target_roi * cost

    if not meets_target(0):
        return None
    # From this price on, the card alone costs more than the sale brings in.
    high = int(Decimal(max(net_cents, 0)) / 100 * fx_jpy_per_eur) + 1
    if meets_target(high):
        return high
    low = 0
    while high - low > 1:
        middle = (low + high) // 2
        if meets_target(middle):
            low = middle
        else:
            high = middle
    return low


def _load_lots(session: Session, user_id: int) -> list[Lot]:
    statement = (
        select(Lot)
        .where(Lot.user_id == user_id)
        .options(selectinload(Lot.items).selectinload(Item.sale))
        .order_by(Lot.id.desc())
    )
    return list(session.scalars(statement))


def _costed_items(
    session: Session, user_id: int, settings: AppSettings
) -> list[tuple[Item, ItemLandedCost]]:
    rows: list[tuple[Item, ItemLandedCost]] = []
    for lot in _load_lots(session, user_id):
        costing = cost_lot(lot, settings)
        rows.extend((item, costing.by_item[item.id]) for item in lot.items)
    return rows


def _get_lot(session: Session, user_id: int, lot_id: int) -> Lot:
    lot = session.get(Lot, lot_id)
    # Another account's lot answers like a missing one: ids must not reveal anything.
    if lot is None or lot.user_id != user_id:
        raise NotFoundError(f"lot {lot_id} not found")
    return lot


def get_item(session: Session, user_id: int, item_id: int) -> Item:
    item = session.get(Item, item_id)
    if item is None or item.lot.user_id != user_id:
        raise NotFoundError(f"item {item_id} not found")
    return item


def _commit(session: Session) -> None:
    # Sessions keep objects alive after commit; expiring them makes the response reflect
    # what the database now holds, including cascades.
    session.commit()
    session.expire_all()


def _lot_fields(lot: Lot, costing: LotCosting) -> dict[str, Any]:
    return {
        **_attributes(lot, LotFields),
        "id": lot.id,
        "label": lot.label,
        "fx_jpy_per_eur": Decimal(lot.fx_jpy_per_eur),
        "packing_fee_jpy": lot.packing_fee_jpy,
        "handling_fee_cents": lot.handling_fee_cents,
        "item_count": len(lot.items),
        "sold_count": sum(1 for item in lot.items if item.sale is not None),
        "goods_jpy": sum(item.price_jpy + item.domestic_shipping_jpy for item in lot.items),
        "landed_total_cents": sum(cost.total_cents for cost in costing.by_item.values()),
        "applied_import_vat_cents": costing.applied_import_vat_cents,
        "vat_estimated": lot.import_vat_cents is None,
    }


def _item_out(item: Item, landed: ItemLandedCost, settings: AppSettings) -> ItemOut:
    projection = None
    if (
        item.sale is None
        and item.listing_platform is not None
        and item.listing_price_cents is not None
    ):
        projection = _breakdown_out(
            project_sale(settings, SalePlatform(item.listing_platform), item.listing_price_cents),
            landed.total_cents,
        )
    return ItemOut(
        **_attributes(item, ItemFields),
        id=item.id,
        lot_id=item.lot_id,
        lot_label=item.lot.label,
        lot_status=item.lot.status,
        service_fee_jpy=item.service_fee_jpy,
        status=item_status(item),
        landed_cost=_landed_out(landed),
        listing_projection=projection,
        sale=None if item.sale is None else _sale_out(item.sale, landed),
    )


def _sale_out(sale: Sale, landed: ItemLandedCost) -> SaleOut:
    return SaleOut(
        platform=sale.platform,
        sold_on=sale.sold_on,
        sale_price_cents=sale.sale_price_cents,
        shipping_charged_cents=sale.shipping_charged_cents,
        shipping_cost_cents=sale.shipping_cost_cents,
        platform_fee_cents=sale.platform_fee_cents,
        packaging_cents=sale.packaging_cents,
        contribution_rate_percent=Decimal(sale.contribution_rate) * 100,
        notes=sale.notes,
        breakdown=_breakdown_out(_recorded_sale(sale), landed.total_cents),
    )


def _recorded_sale(sale: Sale) -> SaleBreakdown:
    return compute_sale(
        sale_price_cents=sale.sale_price_cents,
        shipping_charged_cents=sale.shipping_charged_cents,
        shipping_cost_cents=sale.shipping_cost_cents,
        platform_fee_cents=sale.platform_fee_cents,
        packaging_cents=sale.packaging_cents,
        contribution_rate=Decimal(sale.contribution_rate),
    )


def _landed_out(cost: ItemLandedCost) -> LandedCostOut:
    return LandedCostOut(
        purchase_cents=cost.purchase_cents,
        proxy_fees_cents=cost.proxy_fees_cents,
        shipping_cents=cost.shipping_cents,
        import_taxes_cents=cost.import_taxes_cents,
        total_cents=cost.total_cents,
        vat_estimated=cost.vat_estimated,
    )


def _breakdown_out(sale: SaleBreakdown, cost_cents: int) -> SaleBreakdownOut:
    margin = sale.net_cents - cost_cents
    return SaleBreakdownOut(
        revenue_cents=sale.revenue_cents,
        platform_fee_cents=sale.platform_fee_cents,
        shipping_cost_cents=sale.shipping_cost_cents,
        packaging_cents=sale.packaging_cents,
        contributions_cents=sale.contributions_cents,
        net_cents=sale.net_cents,
        margin_cents=margin,
        roi=roi(margin, cost_cents),
    )


def _attributes(row: object, model: type[BaseModel]) -> dict[str, Any]:
    return {name: getattr(row, name) for name in model.model_fields}


def _to_columns(values: dict[str, Any]) -> dict[str, Any]:
    """API values in the shape the columns store them: ISO dates, decimal text, raw enums."""
    return {name: _to_column(value) for name, value in values.items()}


def _to_column(value: Any) -> Any:
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def _or[T](value: T | None, default: T) -> T:
    return default if value is None else value
