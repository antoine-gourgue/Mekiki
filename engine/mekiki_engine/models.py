"""ORM mappings of the tables created by the SQL migrations (the migrations own the schema)."""

from __future__ import annotations

from sqlalchemy import FetchedValue, ForeignKey, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class SettingRow(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str]


class Lot(Base):
    __tablename__ = "lots"

    id: Mapped[int] = mapped_column(primary_key=True)
    label: Mapped[str]
    proxy: Mapped[str] = mapped_column(default="neokyo")
    status: Mapped[str] = mapped_column(default="purchasing")
    # Kept as text: the rate actually paid has more decimals than a float shows faithfully.
    fx_jpy_per_eur: Mapped[str]
    packing_fee_jpy: Mapped[int] = mapped_column(default=0)
    international_shipping_jpy: Mapped[int] = mapped_column(default=0)
    insurance_jpy: Mapped[int] = mapped_column(default=0)
    other_fees_jpy: Mapped[int] = mapped_column(default=0)
    payment_fees_cents: Mapped[int] = mapped_column(default=0)
    import_vat_cents: Mapped[int | None]
    customs_duty_cents: Mapped[int] = mapped_column(default=0)
    handling_fee_cents: Mapped[int] = mapped_column(default=0)
    shipping_method: Mapped[str | None]
    tracking_number: Mapped[str | None]
    ordered_on: Mapped[str | None]
    shipped_on: Mapped[str | None]
    received_on: Mapped[str | None]
    notes: Mapped[str | None]
    created_at: Mapped[str] = mapped_column(server_default=FetchedValue())

    items: Mapped[list[Item]] = relationship(
        back_populates="lot", cascade="all, delete-orphan", order_by="Item.id"
    )


class Item(Base):
    __tablename__ = "items"

    id: Mapped[int] = mapped_column(primary_key=True)
    lot_id: Mapped[int] = mapped_column(ForeignKey("lots.id", ondelete="CASCADE"))
    game: Mapped[str]
    name: Mapped[str]
    set_code: Mapped[str | None]
    card_number: Mapped[str | None]
    rarity: Mapped[str | None]
    language: Mapped[str] = mapped_column(default="ja")
    condition: Mapped[str | None]
    grading: Mapped[str | None]
    source_platform: Mapped[str] = mapped_column(default="mercari")
    source_url: Mapped[str | None]
    price_jpy: Mapped[int]
    domestic_shipping_jpy: Mapped[int] = mapped_column(default=0)
    service_fee_jpy: Mapped[int] = mapped_column(default=0)
    cardmarket_product_id: Mapped[int | None]
    listing_platform: Mapped[str | None]
    listing_price_cents: Mapped[int | None]
    notes: Mapped[str | None]
    created_at: Mapped[str] = mapped_column(server_default=FetchedValue())

    lot: Mapped[Lot] = relationship(back_populates="items")
    sale: Mapped[Sale | None] = relationship(
        back_populates="item", cascade="all, delete-orphan", uselist=False
    )


class Sale(Base):
    __tablename__ = "sales"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), unique=True)
    platform: Mapped[str]
    sold_on: Mapped[str]
    sale_price_cents: Mapped[int]
    shipping_charged_cents: Mapped[int] = mapped_column(default=0)
    shipping_cost_cents: Mapped[int] = mapped_column(default=0)
    # Fees, packaging and contribution rate are frozen at sale time so that later settings
    # changes never rewrite the margin of past sales.
    platform_fee_cents: Mapped[int]
    packaging_cents: Mapped[int]
    contribution_rate: Mapped[str]
    notes: Mapped[str | None]
    created_at: Mapped[str] = mapped_column(server_default=FetchedValue())

    item: Mapped[Item] = relationship(back_populates="sale")


class CardmarketProduct(Base):
    """Cardmarket catalog entry with its latest price guide values (cents, EUR)."""

    __tablename__ = "cardmarket_products"

    id_product: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    game: Mapped[str]
    name: Mapped[str | None]
    id_category: Mapped[int | None]
    id_expansion: Mapped[int | None]
    # Not in the public files: borrowed from the sealed products of the same expansion.
    expansion_name: Mapped[str | None]
    id_metacard: Mapped[int | None]
    date_added: Mapped[str | None]
    avg_cents: Mapped[int | None]
    low_cents: Mapped[int | None]
    trend_cents: Mapped[int | None]
    avg1_cents: Mapped[int | None]
    avg7_cents: Mapped[int | None]
    avg30_cents: Mapped[int | None]
    prices_date: Mapped[str | None]


class CardmarketPriceHistory(Base):
    __tablename__ = "cardmarket_price_history"

    id_product: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    price_date: Mapped[str] = mapped_column(primary_key=True)
    avg_cents: Mapped[int | None]
    trend_cents: Mapped[int | None]
    avg1_cents: Mapped[int | None]
    avg7_cents: Mapped[int | None]
    avg30_cents: Mapped[int | None]


class TrackedCard(Base):
    __tablename__ = "tracked_cards"

    id: Mapped[int] = mapped_column(primary_key=True)
    game: Mapped[str]
    name: Mapped[str]
    set_code: Mapped[str | None]
    card_number: Mapped[str | None]
    rarity: Mapped[str | None]
    grading: Mapped[str | None]
    cardmarket_product_id: Mapped[int | None]
    search_query: Mapped[str]
    required_keywords: Mapped[str | None]
    excluded_keywords: Mapped[str | None]
    # Overrides the Cardmarket price, e.g. when the Japanese printing sells for less.
    target_price_cents: Mapped[int | None]
    min_price_jpy: Mapped[int | None]
    max_price_jpy: Mapped[int | None]
    active: Mapped[bool] = mapped_column(default=True)
    last_scanned_at: Mapped[str | None]
    notes: Mapped[str | None]
    created_at: Mapped[str] = mapped_column(server_default=FetchedValue())

    listings: Mapped[list[Listing]] = relationship(
        back_populates="tracked_card", cascade="all, delete-orphan", passive_deletes=True
    )


class Listing(Base):
    """A marketplace listing that matched a tracked card."""

    __tablename__ = "listings"

    id: Mapped[int] = mapped_column(primary_key=True)
    tracked_card_id: Mapped[int] = mapped_column(ForeignKey("tracked_cards.id", ondelete="CASCADE"))
    source: Mapped[str]
    external_id: Mapped[str]
    title: Mapped[str]
    price_jpy: Mapped[int]
    # None when the search results do not say who pays the Japanese shipping.
    shipping_included: Mapped[bool | None]
    url: Mapped[str]
    thumbnail_url: Mapped[str | None]
    listed_at: Mapped[str | None]
    ends_at: Mapped[str | None]
    bids: Mapped[int | None]
    triage: Mapped[str] = mapped_column(default="new")
    first_seen_at: Mapped[str]
    last_seen_at: Mapped[str]

    tracked_card: Mapped[TrackedCard] = relationship(back_populates="listings")


class CardIndexEntry(Base):
    """Japanese card identity (set code, collector number) → Cardmarket product."""

    __tablename__ = "card_index"

    game: Mapped[str] = mapped_column(primary_key=True)
    set_code: Mapped[str] = mapped_column(primary_key=True)
    number: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    id_product: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    set_total: Mapped[int | None]
    rarity: Mapped[str | None]
    name: Mapped[str | None]
    # "normal", "holo", "reverse-masterball"…: mirror versions are separate products.
    variant: Mapped[str] = mapped_column(default="normal")
