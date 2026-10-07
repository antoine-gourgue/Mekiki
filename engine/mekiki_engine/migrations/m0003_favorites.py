SQL = """
CREATE TABLE favorites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    game TEXT NOT NULL CHECK (game IN ('pokemon', 'one_piece')),
    source TEXT NOT NULL,
    external_id TEXT NOT NULL,
    title TEXT NOT NULL,
    price_jpy INTEGER NOT NULL CHECK (price_jpy >= 0),
    shipping_included INTEGER CHECK (shipping_included IN (0, 1)),
    url TEXT NOT NULL,
    thumbnail_url TEXT,
    listed_at TEXT,
    ends_at TEXT,
    bids INTEGER,
    card_label TEXT,
    cardmarket_product_id INTEGER,
    target_price_cents INTEGER CHECK (target_price_cents >= 0),
    in_cart INTEGER NOT NULL DEFAULT 0 CHECK (in_cart IN (0, 1)),
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE (source, external_id)
)
"""
