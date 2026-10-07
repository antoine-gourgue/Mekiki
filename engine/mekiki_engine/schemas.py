"""API contracts. Money is exchanged in minor units (cents, yen), rates as plain numbers."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer, field_validator

from mekiki_engine.domain import Game, ItemStatus, LotStatus, SalePlatform, SourcePlatform

# Decimals travel as JSON numbers: the UI needs numbers, and rates never need more precision
# than a float carries.
Rate = Annotated[Decimal, PlainSerializer(float, return_type=float, when_used="json")]
Percent = Annotated[Rate, Field(ge=0, le=100)]
Cents = Annotated[int, Field(ge=0)]
Yen = Annotated[int, Field(ge=0)]
ShortText = Annotated[str, Field(min_length=1, max_length=200)]


class PlatformFeeSettings(BaseModel):
    percent: Percent = Decimal(0)
    fixed_cents: Cents = 0
    applies_to_shipping: bool = False


def default_platform_fees() -> dict[SalePlatform, PlatformFeeSettings]:
    return {
        SalePlatform.CARDMARKET: PlatformFeeSettings(percent=Decimal(5)),
        SalePlatform.EBAY: PlatformFeeSettings(),
        SalePlatform.VINTED: PlatformFeeSettings(),
        SalePlatform.LEBONCOIN: PlatformFeeSettings(),
        SalePlatform.OTHER: PlatformFeeSettings(),
    }


class AppSettings(BaseModel):
    fx_jpy_per_eur: Annotated[Rate, Field(gt=0)] = Decimal(170)
    vat_rate_percent: Percent = Decimal(20)
    default_handling_fee_cents: Cents = 1000
    neokyo_service_fee_jpy: Yen = 350
    neokyo_packing_fee_jpy: Yen = 500
    contribution_rate_percent: Percent = Decimal("12.3")
    income_tax_rate_percent: Percent = Decimal(0)
    default_packaging_cents: Cents = 50
    platform_fees: dict[SalePlatform, PlatformFeeSettings] = Field(
        default_factory=default_platform_fees
    )

    @field_validator("platform_fees")
    @classmethod
    def _fill_missing_platforms(
        cls, value: dict[SalePlatform, PlatformFeeSettings]
    ) -> dict[SalePlatform, PlatformFeeSettings]:
        # Settings saved before a platform existed must still yield a rule for it.
        return {**default_platform_fees(), **value}


class LotFields(BaseModel):
    proxy: ShortText = "neokyo"
    status: LotStatus = LotStatus.PURCHASING
    international_shipping_jpy: Yen = 0
    insurance_jpy: Yen = 0
    other_fees_jpy: Yen = 0
    payment_fees_cents: Cents = 0
    import_vat_cents: Cents | None = None
    customs_duty_cents: Cents = 0
    shipping_method: str | None = None
    tracking_number: str | None = None
    ordered_on: date | None = None
    shipped_on: date | None = None
    received_on: date | None = None
    notes: str | None = None


class LotCreate(LotFields):
    label: ShortText
    # Left empty, these three take the current defaults from the settings.
    fx_jpy_per_eur: Annotated[Rate, Field(gt=0)] | None = None
    packing_fee_jpy: Yen | None = None
    handling_fee_cents: Cents | None = None


class LotUpdate(BaseModel):
    label: ShortText | None = None
    proxy: ShortText | None = None
    status: LotStatus | None = None
    fx_jpy_per_eur: Annotated[Rate, Field(gt=0)] | None = None
    packing_fee_jpy: Yen | None = None
    international_shipping_jpy: Yen | None = None
    insurance_jpy: Yen | None = None
    other_fees_jpy: Yen | None = None
    payment_fees_cents: Cents | None = None
    import_vat_cents: Cents | None = None
    customs_duty_cents: Cents | None = None
    handling_fee_cents: Cents | None = None
    shipping_method: str | None = None
    tracking_number: str | None = None
    ordered_on: date | None = None
    shipped_on: date | None = None
    received_on: date | None = None
    notes: str | None = None


class ItemFields(BaseModel):
    game: Game
    name: ShortText
    set_code: str | None = None
    card_number: str | None = None
    rarity: str | None = None
    language: str = "ja"
    condition: str | None = None
    grading: str | None = None
    source_platform: SourcePlatform = SourcePlatform.MERCARI
    source_url: str | None = None
    price_jpy: Yen
    domestic_shipping_jpy: Yen = 0
    cardmarket_product_id: int | None = None
    listing_platform: SalePlatform | None = None
    listing_price_cents: Cents | None = None
    notes: str | None = None


class ItemCreate(ItemFields):
    # Left empty, takes the proxy service fee from the settings.
    service_fee_jpy: Yen | None = None


class ItemUpdate(BaseModel):
    lot_id: int | None = None
    game: Game | None = None
    name: ShortText | None = None
    set_code: str | None = None
    card_number: str | None = None
    rarity: str | None = None
    language: str | None = None
    condition: str | None = None
    grading: str | None = None
    source_platform: SourcePlatform | None = None
    source_url: str | None = None
    price_jpy: Yen | None = None
    domestic_shipping_jpy: Yen | None = None
    service_fee_jpy: Yen | None = None
    cardmarket_product_id: int | None = None
    listing_platform: SalePlatform | None = None
    listing_price_cents: Cents | None = None
    notes: str | None = None


class SaleUpsert(BaseModel):
    platform: SalePlatform
    sold_on: date
    sale_price_cents: Cents
    shipping_charged_cents: Cents = 0
    shipping_cost_cents: Cents = 0
    # Left empty, computed from the platform rule / packaging default in the settings.
    platform_fee_cents: Cents | None = None
    packaging_cents: Cents | None = None
    notes: str | None = None


class LandedCostOut(BaseModel):
    purchase_cents: int
    proxy_fees_cents: int
    shipping_cents: int
    import_taxes_cents: int
    total_cents: int
    vat_estimated: bool


class SaleBreakdownOut(BaseModel):
    revenue_cents: int
    platform_fee_cents: int
    shipping_cost_cents: int
    packaging_cents: int
    contributions_cents: int
    net_cents: int
    margin_cents: int
    roi: Rate | None


class SaleOut(BaseModel):
    platform: SalePlatform
    sold_on: date
    sale_price_cents: int
    shipping_charged_cents: int
    shipping_cost_cents: int
    platform_fee_cents: int
    packaging_cents: int
    contribution_rate_percent: Rate
    notes: str | None
    breakdown: SaleBreakdownOut


class ItemOut(ItemFields):
    model_config = ConfigDict(from_attributes=True)

    id: int
    lot_id: int
    lot_label: str
    lot_status: LotStatus
    service_fee_jpy: int
    status: ItemStatus
    landed_cost: LandedCostOut
    # What the current listing would leave once sold, shipping assumed neutral.
    listing_projection: SaleBreakdownOut | None
    sale: SaleOut | None


class LotOut(LotFields):
    id: int
    label: str
    fx_jpy_per_eur: Rate
    packing_fee_jpy: int
    handling_fee_cents: int
    item_count: int
    sold_count: int
    goods_jpy: int
    landed_total_cents: int
    vat_estimated: bool


class LotDetail(LotOut):
    items: list[ItemOut]


class MonthlySales(BaseModel):
    month: str
    sold_count: int
    revenue_cents: int
    net_cents: int
    margin_cents: int


class Dashboard(BaseModel):
    incoming_count: int
    in_stock_count: int
    listed_count: int
    stock_cost_cents: int
    listed_price_cents: int
    listed_expected_margin_cents: int
    sold_count: int
    revenue_cents: int
    net_cents: int
    cost_of_sold_cents: int
    margin_cents: int
    roi: Rate | None
    monthly: list[MonthlySales]


class SimulationRequest(BaseModel):
    price_jpy: Yen
    domestic_shipping_jpy: Yen = 0
    sale_price_cents: Cents
    platform: SalePlatform = SalePlatform.CARDMARKET
    shipping_charged_cents: Cents = 0
    shipping_cost_cents: Cents = 0
    cards_in_lot: Annotated[int, Field(ge=1, le=500)] = 10
    lot_shipping_jpy: Yen = 4000
    target_roi_percent: Annotated[Rate, Field(ge=0, le=1000)] | None = Decimal(30)
    fx_jpy_per_eur: Annotated[Rate, Field(gt=0)] | None = None


class SimulationResult(BaseModel):
    landed_cost: LandedCostOut
    sale: SaleBreakdownOut
    fx_jpy_per_eur: Rate
    # Highest price that still meets ``target_roi_percent``; ``None`` when no price does.
    max_price_jpy: int | None
