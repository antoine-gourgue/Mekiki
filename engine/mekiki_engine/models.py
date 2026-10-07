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
