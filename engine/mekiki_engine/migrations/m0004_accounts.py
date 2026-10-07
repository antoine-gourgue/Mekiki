SQL = """
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    display_name TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE auth_sessions (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    expires_at TEXT NOT NULL
);

CREATE INDEX auth_sessions_user ON auth_sessions (user_id);

ALTER TABLE lots ADD COLUMN user_id INTEGER REFERENCES users (id) ON DELETE CASCADE;
CREATE INDEX lots_user ON lots (user_id);

ALTER TABLE tracked_cards ADD COLUMN user_id INTEGER REFERENCES users (id) ON DELETE CASCADE;
CREATE INDEX tracked_cards_user ON tracked_cards (user_id);

CREATE TABLE favorites_by_user (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES users (id) ON DELETE CASCADE,
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
    UNIQUE (user_id, source, external_id)
);

INSERT INTO favorites_by_user (
    id, game, source, external_id, title, price_jpy, shipping_included, url, thumbnail_url,
    listed_at, ends_at, bids, card_label, cardmarket_product_id, target_price_cents, in_cart,
    notes, created_at
)
SELECT
    id, game, source, external_id, title, price_jpy, shipping_included, url, thumbnail_url,
    listed_at, ends_at, bids, card_label, cardmarket_product_id, target_price_cents, in_cart,
    notes, created_at
FROM favorites;

DROP TABLE favorites;

ALTER TABLE favorites_by_user RENAME TO favorites;

CREATE INDEX favorites_user ON favorites (user_id)
"""
