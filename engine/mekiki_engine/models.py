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
    # Owner; NULL only for data created before accounts existed, claimed by the first user.
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
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
    photos: Mapped[list[ItemPhoto]] = relationship(
        back_populates="item",
        cascade="all, delete-orphan",
        order_by="ItemPhoto.position",
        lazy="selectin",
    )


class ItemPhoto(Base):
    __tablename__ = "item_photos"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"))
    file_name: Mapped[str]
    content_type: Mapped[str]
    position: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[str] = mapped_column(server_default=FetchedValue())

    item: Mapped[Item] = relationship(back_populates="photos")


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
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
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


class Favorite(Base):
    """A listing kept for later; those ``in_cart`` are priced together as one parcel."""

    __tablename__ = "favorites"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    game: Mapped[str]
    source: Mapped[str]
    external_id: Mapped[str]
    title: Mapped[str]
    price_jpy: Mapped[int]
    shipping_included: Mapped[bool | None]
    url: Mapped[str]
    thumbnail_url: Mapped[str | None]
    listed_at: Mapped[str | None]
    ends_at: Mapped[str | None]
    bids: Mapped[int | None]
    card_label: Mapped[str | None]
    cardmarket_product_id: Mapped[int | None]
    # Resale price chosen by hand; left empty, the Cardmarket price of the product.
    target_price_cents: Mapped[int | None]
    in_cart: Mapped[bool] = mapped_column(default=False)
    notes: Mapped[str | None]
    created_at: Mapped[str] = mapped_column(server_default=FetchedValue())


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Stored lowercased: one account per address whatever the case typed.
    email: Mapped[str] = mapped_column(unique=True)
    password_hash: Mapped[str]
    display_name: Mapped[str]
    created_at: Mapped[str] = mapped_column(server_default=FetchedValue())


class AuthSession(Base):
    """A signed-in device. Only a hash of its token is stored, so a leaked database
    does not hand out working tokens."""

    __tablename__ = "auth_sessions"

    token_hash: Mapped[str] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[str] = mapped_column(server_default=FetchedValue())
    expires_at: Mapped[str]
