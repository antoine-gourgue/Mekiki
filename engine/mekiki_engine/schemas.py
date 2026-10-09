"""API contracts. Money is exchanged in minor units (cents, yen), rates as plain numbers."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated, ClassVar, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PlainSerializer,
    StringConstraints,
    field_validator,
    model_validator,
)

from mekiki_engine.domain import (
    Game,
    ItemStatus,
    ListingCondition,
    ListingTriage,
    LotStatus,
    SalePlatform,
    SourcePlatform,
)

# Decimals travel as JSON numbers: the UI needs numbers, and rates never need more precision
# than a float carries.
Rate = Annotated[Decimal, PlainSerializer(float, return_type=float, when_used="json")]
Percent = Annotated[Rate, Field(ge=0, le=100)]
Cents = Annotated[int, Field(ge=0)]
Yen = Annotated[int, Field(ge=0)]
ShortText = Annotated[str, Field(min_length=1, max_length=200)]


class PartialUpdate(BaseModel):
    """PATCH body: only the fields sent are applied, and ``null`` clears a field.

    Fields absent from ``NULLABLE`` map to NOT NULL columns, so ``null`` is refused for them.
    """

    NULLABLE: ClassVar[frozenset[str]] = frozenset()

    @model_validator(mode="after")
    def _reject_null_on_required_fields(self) -> Self:
        cleared = sorted(
            name for name in self.model_fields_set - self.NULLABLE if getattr(self, name) is None
        )
        if cleared:
            raise ValueError(f"cannot be null: {', '.join(cleared)}")
        return self


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


SCANNABLE_SOURCES = (
    SourcePlatform.MERCARI,
    SourcePlatform.RAKUMA,
    SourcePlatform.YAHOO_AUCTIONS,
    SourcePlatform.YAHOO_FLEAMARKET,
)
# Yahoo! JAPAN refuses visitors from Europe, so its two sites are opt-in.
DEFAULT_SOURCES = (SourcePlatform.MERCARI, SourcePlatform.RAKUMA)

# Noise in Japanese card listings: bulk lots, repacks, accessories, fakes, foreign printings.
DEFAULT_EXCLUDED_KEYWORDS = (
    "まとめ 枚セット 引退 オリパ 福袋 未開封 box スリーブ ローダー プレイマット デッキ "
    "フレーム ディスプレイ 観賞用 鑑賞用 acg 防犯 レプリカ カスタム ファンアート 自作 非公式 "
    "プロキシ コピー 英語 中国 韓国 簡体 繁体"
)


class ScannerSettings(BaseModel):
    """How the deal scanner searches and judges listings."""

    enabled: bool = False
    interval_minutes: Annotated[int, Field(ge=10, le=1440)] = 60
    sources: list[SourcePlatform] = Field(default_factory=lambda: list(DEFAULT_SOURCES))
    min_roi_percent: Annotated[Rate, Field(ge=0, le=1000)] = Decimal(30)
    # A listing is priced as one card of a typical parcel, like in the simulator.
    cards_per_lot: Annotated[int, Field(ge=1, le=500)] = 10
    lot_shipping_jpy: Yen = 4000
    resale_platform: SalePlatform = SalePlatform.CARDMARKET
    # Added when the buyer pays the Japanese shipping (frequent on Yahoo Auctions).
    domestic_shipping_jpy: Yen = 800
    excluded_keywords: Annotated[str, Field(max_length=2000)] = DEFAULT_EXCLUDED_KEYWORDS

    @field_validator("sources")
    @classmethod
    def _only_scannable(cls, value: list[SourcePlatform]) -> list[SourcePlatform]:
        unknown = [s for s in value if s not in SCANNABLE_SOURCES]
        if unknown:
            raise ValueError(f"not searchable: {', '.join(unknown)}")
        return list(dict.fromkeys(value))


class BusinessSettings(BaseModel):
    """The micro-enterprise behind the account, for its books and declarations."""

    name: Annotated[str, Field(max_length=120)] = ""
    siret: Annotated[str, Field(max_length=20)] = ""
    started_on: date | None = None
    # How often the turnover is declared to URSSAF.
    declaration: Literal["monthly", "quarterly"] = "quarterly"
    # Yearly limits of the micro-enterprise and of the VAT franchise for sales of goods. Set
    # by law and revised every few years: the user checks them on urssaf.fr.
    turnover_limit_cents: Cents = 18_870_000
    vat_franchise_limit_cents: Cents = 8_500_000


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
    scanner: ScannerSettings = Field(default_factory=ScannerSettings)
    business: BusinessSettings = Field(default_factory=BusinessSettings)

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


class LotUpdate(PartialUpdate):
    # ``import_vat_cents: null`` switches the lot back to an estimated VAT.
    NULLABLE = frozenset(
        {
            "import_vat_cents",
            "shipping_method",
            "tracking_number",
            "ordered_on",
            "shipped_on",
            "received_on",
            "notes",
        }
    )

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


class ItemUpdate(PartialUpdate):
    NULLABLE = frozenset(
        {
            "set_code",
            "card_number",
            "rarity",
            "condition",
            "grading",
            "source_url",
            "cardmarket_product_id",
            "listing_platform",
            "listing_price_cents",
            "notes",
        }
    )

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
    tracking_number: Annotated[str, Field(max_length=60)] | None = None
    # Left empty while the card is still to ship.
    shipped_on: date | None = None


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
    tracking_number: str | None = None
    shipped_on: date | None = None
    breakdown: SaleBreakdownOut


class ItemPhotoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    content_type: str
    position: int


class PhotoUpload(BaseModel):
    # JSON rather than multipart: the engine only accepts JSON bodies (see app.py).
    content_base64: Annotated[str, Field(min_length=4, max_length=12_000_000)]


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
    photos: list[ItemPhotoOut] = []


class LotOut(LotFields):
    id: int
    label: str
    fx_jpy_per_eur: Rate
    packing_fee_jpy: int
    handling_fee_cents: int
    item_count: int
    sold_count: int
    # Card prices plus Japanese domestic shipping: what the sellers were paid.
    goods_jpy: int
    landed_total_cents: int
    # The carrier's amount once entered, the estimate until then.
    applied_import_vat_cents: int
    vat_estimated: bool


class LotDetail(LotOut):
    items: list[ItemOut]


class PricePoint(BaseModel):
    """A card's resale price on Cardmarket, one day."""

    date: str
    cents: int


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
    # Unsold cards received more than ``DORMANT_DAYS`` ago, and what they cost.
    dormant_count: int = 0
    dormant_cost_cents: int = 0
    # Days from receiving a card to selling it, on average over the period's sales.
    average_days_to_sell: int | None = None
    # Sales whose parcel has not left yet, whatever their date.
    to_ship_count: int = 0


class BooksPeriod(BaseModel):
    """One month or quarter to declare to URSSAF."""

    label: str
    start: str
    end: str
    # Last day to declare it.
    due_on: str
    turnover_cents: int
    contributions_cents: int
    # The flat income tax paid with the contributions, when chosen.
    income_tax_cents: int
    # upcoming: not over yet. due: over, to declare by ``due_on``. past: its deadline passed.
    state: Literal["upcoming", "due", "past"]


class BooksSummary(BaseModel):
    year: int
    declaration: Literal["monthly", "quarterly"]
    periods: list[BooksPeriod]
    turnover_cents: int
    contributions_cents: int
    income_tax_cents: int
    turnover_limit_cents: int
    vat_franchise_limit_cents: int
    # The period over and not declared yet, if any.
    next_declaration: BooksPeriod | None


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


class TrackedCardFields(BaseModel):
    game: Game
    name: ShortText
    set_code: str | None = None
    card_number: str | None = None
    rarity: str | None = None
    grading: str | None = None
    cardmarket_product_id: int | None = None
    # Keywords sent to the marketplaces, in Japanese or as a card number ("205/187").
    search_query: ShortText
    # Space-separated words that a title must contain / must not contain.
    required_keywords: str | None = None
    excluded_keywords: str | None = None
    # Expected resale price; left empty, the Cardmarket price is used.
    target_price_cents: Cents | None = None
    min_price_jpy: Yen | None = None
    max_price_jpy: Yen | None = None
    active: bool = True
    notes: str | None = None


class TrackedCardCreate(TrackedCardFields):
    # Left empty, built from the card number (or the name when there is none).
    search_query: ShortText | None = None  # type: ignore[assignment]


class TrackedCardUpdate(PartialUpdate):
    NULLABLE = frozenset(
        {
            "set_code",
            "card_number",
            "rarity",
            "grading",
            "cardmarket_product_id",
            "required_keywords",
            "excluded_keywords",
            "target_price_cents",
            "min_price_jpy",
            "max_price_jpy",
            "notes",
        }
    )

    game: Game | None = None
    name: ShortText | None = None
    set_code: str | None = None
    card_number: str | None = None
    rarity: str | None = None
    grading: str | None = None
    cardmarket_product_id: int | None = None
    search_query: ShortText | None = None
    required_keywords: str | None = None
    excluded_keywords: str | None = None
    target_price_cents: Cents | None = None
    min_price_jpy: Yen | None = None
    max_price_jpy: Yen | None = None
    active: bool | None = None
    notes: str | None = None


class MarketPriceOut(BaseModel):
    """Cardmarket price guide values for one product, in cents."""

    id_product: int
    game: Game
    name: str | None
    expansion_name: str | None
    url: str
    avg_cents: int | None
    low_cents: int | None
    trend_cents: int | None
    avg1_cents: int | None
    avg7_cents: int | None
    avg30_cents: int | None
    prices_date: str | None
    # The value used as resale price: avg30, else avg7, avg, avg1, trend; never low.
    reference_cents: int | None
    reference_field: str | None
    # A Japanese printing, the one Japanese listings sell (the English one prices apart).
    japanese: bool = False


class TrackedCardOut(TrackedCardFields):
    id: int
    last_scanned_at: str | None
    market: MarketPriceOut | None
    expected_sale_cents: int | None
    # Highest price a listing may ask for and still reach the scanner's ROI target.
    max_buy_price_jpy: int | None
    listing_count: int
    best_roi: Rate | None


class DealOut(BaseModel):
    """A listing priced as one card of a typical parcel, resold at the expected price."""

    id: int
    tracked_card_id: int
    card_name: str
    game: Game
    cardmarket_product_id: int | None
    target_price_cents: int | None
    source: SourcePlatform
    external_id: str
    title: str
    price_jpy: int
    shipping_included: bool | None
    url: str
    neokyo_url: str | None
    thumbnail_url: str | None
    listed_at: str | None
    ends_at: str | None
    bids: int | None
    condition: ListingCondition | None = None
    triage: ListingTriage
    first_seen_at: str
    last_seen_at: str
    # False once the last scan of the card no longer found the listing (sold or removed).
    online: bool
    expected_sale_cents: int | None
    landed_cost: LandedCostOut
    sale: SaleBreakdownOut | None


class DealUpdate(BaseModel):
    triage: ListingTriage


class ScanStatus(BaseModel):
    running: bool
    enabled: bool
    last_started_at: str | None
    last_finished_at: str | None
    last_error: str | None
    next_run_at: str | None
    cards_scanned: int
    new_listings: int
    new_deals: int
    # Online listings not looked at yet that reach the ROI target (the sidebar badge).
    unseen_deals: int = 0


class CardmarketStatus(BaseModel):
    game: Game
    products: int
    priced_products: int
    prices_date: str | None
    fetched_at: str | None
    last_error: str | None
    # Japanese cards whose number leads to their Cardmarket product (Pokémon only).
    indexed_cards: int = 0
    index_error: str | None = None


class SearchRequest(BaseModel):
    """One-off search, not saved: prices every result against ``expected_sale_cents``."""

    query: ShortText
    game: Game = Game.POKEMON
    sources: list[SourcePlatform] | None = None
    card_number: str | None = None
    required_keywords: str | None = None
    excluded_keywords: str | None = None
    grading: str | None = None
    cardmarket_product_id: int | None = None
    expected_sale_cents: Cents | None = None


class SearchResultOut(BaseModel):
    source: SourcePlatform
    external_id: str
    title: str
    price_jpy: int
    shipping_included: bool | None
    url: str
    neokyo_url: str | None
    thumbnail_url: str | None
    listed_at: str | None
    ends_at: str | None
    bids: int | None
    condition: ListingCondition | None = None
    matched: bool
    reject_reason: str | None
    landed_cost: LandedCostOut
    sale: SaleBreakdownOut | None


class SearchResponse(BaseModel):
    # What was searched: the typed text with card names translated to Japanese.
    searched_query: str = ""
    expected_sale_cents: int | None
    results: list[SearchResultOut]
    # Sources that failed (blocked, timeout…) with the reason, so partial results are visible.
    errors: dict[str, str]
    # The same search on Neokyo's site, per marketplace (Yahoo stays reachable through it).
    neokyo_search_urls: dict[str, str] = Field(default_factory=dict)


class ListingAvailability(BaseModel):
    """A Japanese listing checked on its marketplace just now."""

    # None when the marketplace could not tell (blocked from Europe, unreachable…).
    available: bool | None
    # "en vente", "vendue", "supprimée"… or why it could not be checked.
    status: str
    condition: ListingCondition | None = None
    price_jpy: int | None = None
    checked_at: str
    seller_id: str | None = None
    # Why Neokyo would refuse this seller, when the listing gives it away.
    seller_warning: str | None = None


class DiscoveryRequest(BaseModel):
    """Compose a parcel: ``card_count`` listings whose total landed cost fits ``budget_cents``."""

    game: Game = Game.POKEMON
    # Everything included: cards, proxy fees, parcel shipping and estimated import taxes.
    budget_cents: Annotated[int, Field(gt=0, le=10_000_000)]
    card_count: Annotated[int, Field(ge=1, le=50)] = 10
    # Left empty, the scanner's ROI target from the settings.
    min_roi_percent: Annotated[Rate, Field(ge=0, le=1000)] | None = None
    sources: list[SourcePlatform] | None = None
    # quick: ~1 500 listings in 1-2 min; deep: ~5 000 in ~5 min; max: 10 000+ in ~15 min.
    depth: Literal["quick", "deep", "max"] = "quick"
    # Only listings in this condition or better; those that do not say are left out too.
    min_condition: ListingCondition | None = None


class DiscoveryPick(BaseModel):
    source: SourcePlatform
    external_id: str
    title: str
    price_jpy: int
    shipping_included: bool | None
    url: str
    neokyo_url: str | None
    thumbnail_url: str | None
    listed_at: str | None
    ends_at: str | None
    bids: int | None
    condition: ListingCondition | None = None
    # What the title was read as, e.g. "SV2a 201/165 · SAR" or "OP05-119 · parallèle".
    card_label: str
    product: MarketPriceOut
    # "high": one Cardmarket product fits; "medium": several versions share the number.
    confidence: Literal["high", "medium"]
    confidence_note: str | None
    # Set when the price is too far below the market to be the real card (copy, accessory,
    # wrong version): such listings never enter the parcel.
    warning: str | None = None
    landed_cost: LandedCostOut
    sale: SaleBreakdownOut


class DiscoveryTotals(BaseModel):
    card_count: int
    purchase_jpy: int
    landed_cents: int
    revenue_cents: int
    net_cents: int
    margin_cents: int
    roi: Rate | None
    # Cards without a resale price: their cost counts, their resale does not.
    unpriced_count: int = 0


class LogLine(BaseModel):
    """One step of a long task, shown in the app's logs."""

    at: str
    text: str


class DiscoveryRun(BaseModel):
    status: Literal["idle", "running", "done", "failed"]
    request: DiscoveryRequest | None = None
    started_at: str | None = None
    finished_at: str | None = None
    searches_done: int = 0
    searches_total: int = 0
    listings_seen: int = 0
    listings_identified: int = 0
    listings_priced: int = 0
    # Once the parcel is composed, its listings are checked on their marketplace: sold ones
    # are replaced by the next best candidates.
    verifying: bool = False
    listings_checked: int = 0
    listings_gone: int = 0
    # The parcel: priced together, shared costs split by price as in a real lot.
    picks: list[DiscoveryPick] = Field(default_factory=list)
    totals: DiscoveryTotals | None = None
    # Other listings reaching the ROI target, best first, to swap into the parcel.
    alternatives: list[DiscoveryPick] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    # Stopped by the user: the results cover the listings browsed until then.
    stopped: bool = False
    # Every step, oldest first: what the app shows while the discovery runs.
    log: list[LogLine] = Field(default_factory=list)


class FavoriteFields(BaseModel):
    game: Game
    source: SourcePlatform
    external_id: ShortText
    title: Annotated[str, Field(max_length=500)]
    price_jpy: Yen
    shipping_included: bool | None = None
    url: Annotated[str, Field(max_length=1000)]
    thumbnail_url: str | None = None
    listed_at: str | None = None
    ends_at: str | None = None
    bids: int | None = None
    condition: ListingCondition | None = None
    # What the listing was read as, e.g. "SV2a 201/165 · SAR".
    card_label: str | None = None
    cardmarket_product_id: int | None = None
    target_price_cents: Cents | None = None
    in_cart: bool = False
    notes: str | None = None


class FavoriteCreate(FavoriteFields):
    """Saving a listing that is already a favorite refreshes it instead of failing."""


class FavoriteUpdate(PartialUpdate):
    NULLABLE = frozenset({"target_price_cents", "notes"})

    in_cart: bool | None = None
    target_price_cents: Cents | None = None
    notes: str | None = None


class FavoriteOut(FavoriteFields):
    id: int
    created_at: str
    neokyo_url: str | None
    product: MarketPriceOut | None
    expected_sale_cents: int | None
    # In the cart: its share of the cart parcel. Otherwise: one card of a typical parcel.
    landed_cost: LandedCostOut
    sale: SaleBreakdownOut | None


class FavoritesOut(BaseModel):
    items: list[FavoriteOut]
    # The cart priced as one parcel; None when the cart is empty.
    cart: DiscoveryTotals | None


# Trimmed and lowercased before checking: one account per address, however it is typed.
Email = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        to_lower=True,
        min_length=3,
        max_length=254,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
    ),
]
Password = Annotated[str, Field(min_length=8, max_length=128)]


class RegisterRequest(BaseModel):
    email: Email
    password: Password
    display_name: Annotated[str, Field(min_length=1, max_length=80)]


class LoginRequest(BaseModel):
    email: Email
    password: Annotated[str, Field(min_length=1, max_length=128)]


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    display_name: str
    created_at: str


class AuthResponse(BaseModel):
    # Sent as "Authorization: Bearer <token>"; valid 30 days, revoked at sign-out.
    token: str
    user: UserOut


class AccountUpdate(BaseModel):
    display_name: Annotated[str, Field(min_length=1, max_length=80)] | None = None
    # Changing the password requires the current one, and signs out the other devices.
    current_password: str | None = None
    new_password: Password | None = None


class ResaleLinks(BaseModel):
    """Searches opened in the user's browser: the engine never fetches these pages."""

    ebay_listings: str
    ebay_sold: str
    ebay_research: str
    vinted: str


class EbayListingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    item_id: str
    title: str
    price_cents: int
    shipping_cents: int | None
    url: str
    image_url: str | None
    condition: str | None
    country: str | None


class EbayPrices(BaseModel):
    # False when the engine has no eBay application keys: only the links work then.
    configured: bool
    error: str | None = None
    total: int = 0
    min_cents: int | None = None
    median_cents: int | None = None
    max_cents: int | None = None
    listings: list[EbayListingOut] = []


class EbayKeys(BaseModel):
    """An account's eBay developer application (Production keyset), stored with its settings."""

    client_id: Annotated[str, Field(min_length=1, max_length=200)]
    client_secret: Annotated[str, Field(min_length=1, max_length=200)]
    marketplace: str = "EBAY_FR"


class EbayKeysUpdate(BaseModel):
    client_id: Annotated[str, Field(min_length=1, max_length=200)]
    # Left empty, the secret already saved is kept: the app never reads it back.
    client_secret: Annotated[str, Field(max_length=200)] | None = None
    marketplace: str = "EBAY_FR"


class EbayStatus(BaseModel):
    configured: bool
    # "account": the account's own keys; "server": the engine's .env, for every account.
    source: Literal["account", "server"] | None = None
    client_id: str | None = None
    marketplace: str | None = None


class ResalePrices(BaseModel):
    query: str
    links: ResaleLinks
    ebay: EbayPrices


class ListingDraftOut(BaseModel):
    platform: Literal["ebay", "vinted"]
    title: str
    description: str
    price_cents: int | None
    # "listing" for the price already set, else the Cardmarket field it comes from.
    price_source: str | None
    new_listing_url: str
    query: str
    links: ResaleLinks


class ResaleOutlet(BaseModel):
    """One way to resell a card: where, at what price, and what it would leave."""

    platform: SalePlatform
    sale_cents: int
    # Where the price comes from, in French: "Cote Cardmarket, moyenne des ventes sur 30 jours".
    basis: str
    net_cents: int
    # Highest price to pay in Japan, shipping included, to reach the target ROI.
    max_buy_jpy: int | None
    margin_cents: int | None
    roi: float | None


class VerdictSignal(BaseModel):
    tone: Literal["positive", "warning", "negative", "neutral"]
    text: str


class CardVerdict(BaseModel):
    """Is this card worth buying (or, once bought, where to sell it)?"""

    # good: reaches the target ROI; fair: profitable below it; bad: loses money;
    # suspicious: too cheap to be the real card; unknown: no resale price; limit: no
    # buying price given, only the most to pay.
    verdict: Literal["good", "fair", "bad", "suspicious", "unknown", "limit"]
    headline: str
    target_roi: float
    price_jpy: int | None
    landed_cents: int | None
    # Best first.
    outlets: list[ResaleOutlet]
    signals: list[VerdictSignal]
    prices: ResalePrices
    # The number listings must name to count: "201/165", "OP05-119".
    card_number: str | None = None
    # The card's name in French, English and Japanese, which listings must also name.
    card_names: list[str] = []
    # What to search on eBay's sold listings in Chrome, to complete the verdict.
    market_queries: dict[str, str] = {}


class TrackedCardTemplate(BaseModel):
    """Fields to track a Cardmarket product, as Japanese listings write the card."""

    model_config = ConfigDict(from_attributes=True)

    game: Game
    name: str
    set_code: str | None
    card_number: str | None
    rarity: str | None
    search_query: str
    # Which printing this is: "SV2A 201/165 · SAR", "OP05-119 · parallèle".
    label: str
    # False for an English printing: Japanese listings sell another card.
    japanese: bool


BrowserSite = Literal["vinted", "ebay"]


class BrowserStatus(BaseModel):
    chrome_installed: bool
    # The Mekiki Chrome window is open.
    running: bool


class SiteConnection(BaseModel):
    site: BrowserSite
    connected: bool


class BrowserPricesRequest(BaseModel):
    query: Annotated[str, Field(min_length=1, max_length=200)]
    # Listings must name it to count towards the median: "201/165", "OP05-119".
    card_number: Annotated[str, Field(max_length=40)] | None = None
    # The card's name in several languages; a listing must name one of them to count.
    names: Annotated[list[Annotated[str, Field(max_length=80)]], Field(max_length=6)] = []


class MarketListingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    site: BrowserSite
    external_id: str
    title: str
    price_cents: int
    url: str
    image_url: str | None
    # The sale date as eBay writes it: "Vendu le 6 oct. 2026".
    detail: str | None
    # eBay: the sale date read from ``detail``, "2026-10-06".
    sold_on: str | None = None
    shipping_cents: int | None
    # eBay: a lower offer was accepted; the real price is unknown.
    best_offer: bool
    # Names the card's number, ungraded and alone: counts towards the median.
    relevant: bool


class BrowserPricesOut(BaseModel):
    site: BrowserSite
    query: str
    listings: list[MarketListingOut]
    relevant_count: int
    median_cents: int | None
    min_cents: int | None
    max_cents: int | None
    # Sales of the card over the last 30 and 90 days.
    sales_30_days: int | None = None
    sales_90_days: int | None = None
    fetched_at: str
    error: str | None


class PublishRequest(BaseModel):
    """The listing as reviewed in the app; photos come from the card."""

    title: Annotated[str, Field(min_length=3, max_length=80)]
    description: Annotated[str, Field(min_length=1, max_length=5000)]
    price_cents: Annotated[int, Field(gt=0)]


class PublishJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    site: BrowserSite
    item_id: int
    started_at: str
    status: Literal["running", "done", "failed"]
    # The published listing, once done.
    url: str | None
    error: str | None


class BlockSellerRequest(BaseModel):
    """A listing whose seller Neokyo refused; its seller is looked up when not given."""

    source: SourcePlatform
    external_id: Annotated[str, Field(min_length=1, max_length=40)]
    seller_id: Annotated[str, Field(max_length=40)] | None = None
    reason: Annotated[str, Field(max_length=200)] = "bloqué par Neokyo"


class BlockedSellerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source: SourcePlatform
    seller_id: str
    reason: str
    blocked_at: str


class TaskOut(BaseModel):
    """Something the account has to do now, and the page where it is done."""

    id: str
    # Changes when something new comes in: the app notifies once per key.
    key: str
    title: str
    detail: str
    # The app's route: "/ventes", "/lots/12".
    to: str
    tone: Literal["primary", "warning", "info", "error"]
    count: int | None = None
    # Worth a Windows notification when its key is new.
    notify: bool = False


class BackupOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    # "mekiki-20261009-021500-000.sqlite3"
    name: str
    created_at: str
    size_bytes: int


class BackupsOut(BaseModel):
    """The daily copies of the database, newest first."""

    folder: str
    backups: list[BackupOut]
    # Only on the computer that keeps the database.
    restore_allowed: bool
    # Why the latest daily copy failed, if it did.
    last_error: str | None = None


class AuthStatus(BaseModel):
    """Whether this computer has accounts yet: the sign-in page then suggests creating one."""

    accounts_exist: bool


class BrowserActivity(BaseModel):
    """What Mekiki's Chrome window is doing, for the progress log in the app."""

    # "Vinted : « Dracaufeu 201/165 », page 2", or None when idle.
    activity: str | None
    running: bool
    # The window is on screen (sign-in, a form to finish, a bot check to pass).
    visible: bool
    # The latest steps and outcomes, oldest first.
    log: list[LogLine]
