SQL = """
CREATE TABLE settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE lots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    label TEXT NOT NULL,
    proxy TEXT NOT NULL DEFAULT 'neokyo',
    status TEXT NOT NULL DEFAULT 'purchasing'
        CHECK (status IN ('purchasing', 'shipped', 'received')),
    fx_jpy_per_eur TEXT NOT NULL,
    packing_fee_jpy INTEGER NOT NULL DEFAULT 0 CHECK (packing_fee_jpy >= 0),
    international_shipping_jpy INTEGER NOT NULL DEFAULT 0
        CHECK (international_shipping_jpy >= 0),
    insurance_jpy INTEGER NOT NULL DEFAULT 0 CHECK (insurance_jpy >= 0),
    other_fees_jpy INTEGER NOT NULL DEFAULT 0 CHECK (other_fees_jpy >= 0),
    payment_fees_cents INTEGER NOT NULL DEFAULT 0 CHECK (payment_fees_cents >= 0),
    import_vat_cents INTEGER CHECK (import_vat_cents >= 0),
    customs_duty_cents INTEGER NOT NULL DEFAULT 0 CHECK (customs_duty_cents >= 0),
    handling_fee_cents INTEGER NOT NULL DEFAULT 0 CHECK (handling_fee_cents >= 0),
    shipping_method TEXT,
    tracking_number TEXT,
    ordered_on TEXT,
    shipped_on TEXT,
    received_on TEXT,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lot_id INTEGER NOT NULL REFERENCES lots (id) ON DELETE CASCADE,
    game TEXT NOT NULL CHECK (game IN ('pokemon', 'one_piece')),
    name TEXT NOT NULL,
    set_code TEXT,
    card_number TEXT,
    rarity TEXT,
    language TEXT NOT NULL DEFAULT 'ja',
    condition TEXT,
    grading TEXT,
    source_platform TEXT NOT NULL DEFAULT 'mercari',
    source_url TEXT,
    price_jpy INTEGER NOT NULL CHECK (price_jpy >= 0),
    domestic_shipping_jpy INTEGER NOT NULL DEFAULT 0 CHECK (domestic_shipping_jpy >= 0),
    service_fee_jpy INTEGER NOT NULL DEFAULT 0 CHECK (service_fee_jpy >= 0),
    cardmarket_product_id INTEGER,
    listing_platform TEXT,
    listing_price_cents INTEGER CHECK (listing_price_cents >= 0),
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX items_lot_id ON items (lot_id);

CREATE TABLE sales (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER NOT NULL UNIQUE REFERENCES items (id) ON DELETE CASCADE,
    platform TEXT NOT NULL,
    sold_on TEXT NOT NULL,
    sale_price_cents INTEGER NOT NULL CHECK (sale_price_cents >= 0),
    shipping_charged_cents INTEGER NOT NULL DEFAULT 0 CHECK (shipping_charged_cents >= 0),
    shipping_cost_cents INTEGER NOT NULL DEFAULT 0 CHECK (shipping_cost_cents >= 0),
    platform_fee_cents INTEGER NOT NULL CHECK (platform_fee_cents >= 0),
    packaging_cents INTEGER NOT NULL CHECK (packaging_cents >= 0),
    contribution_rate TEXT NOT NULL,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX sales_sold_on ON sales (sold_on);
"""
