SQL = """
CREATE TABLE cardmarket_products (
    id_product INTEGER PRIMARY KEY,
    game TEXT NOT NULL CHECK (game IN ('pokemon', 'one_piece')),
    name TEXT,
    id_category INTEGER,
    id_expansion INTEGER,
    expansion_name TEXT,
    id_metacard INTEGER,
    date_added TEXT,
    avg_cents INTEGER,
    low_cents INTEGER,
    trend_cents INTEGER,
    avg1_cents INTEGER,
    avg7_cents INTEGER,
    avg30_cents INTEGER,
    prices_date TEXT
);

CREATE INDEX cardmarket_products_game ON cardmarket_products (game, name);

CREATE TABLE cardmarket_price_history (
    id_product INTEGER NOT NULL,
    price_date TEXT NOT NULL,
    avg_cents INTEGER,
    trend_cents INTEGER,
    avg1_cents INTEGER,
    avg7_cents INTEGER,
    avg30_cents INTEGER,
    PRIMARY KEY (id_product, price_date)
);

CREATE TABLE tracked_cards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    game TEXT NOT NULL CHECK (game IN ('pokemon', 'one_piece')),
    name TEXT NOT NULL,
    set_code TEXT,
    card_number TEXT,
    rarity TEXT,
    grading TEXT,
    cardmarket_product_id INTEGER,
    search_query TEXT NOT NULL,
    required_keywords TEXT,
    excluded_keywords TEXT,
    target_price_cents INTEGER CHECK (target_price_cents >= 0),
    min_price_jpy INTEGER CHECK (min_price_jpy >= 0),
    max_price_jpy INTEGER CHECK (max_price_jpy >= 0),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    last_scanned_at TEXT,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE listings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tracked_card_id INTEGER NOT NULL REFERENCES tracked_cards (id) ON DELETE CASCADE,
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
    triage TEXT NOT NULL DEFAULT 'new'
        CHECK (triage IN ('new', 'seen', 'dismissed', 'bought')),
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    UNIQUE (tracked_card_id, source, external_id)
);

CREATE INDEX listings_triage ON listings (triage, last_seen_at);

CREATE TABLE card_index (
    game TEXT NOT NULL CHECK (game IN ('pokemon', 'one_piece')),
    set_code TEXT NOT NULL,
    number INTEGER NOT NULL,
    set_total INTEGER,
    rarity TEXT,
    name TEXT,
    variant TEXT NOT NULL DEFAULT 'normal',
    id_product INTEGER NOT NULL,
    PRIMARY KEY (game, set_code, number, id_product)
);

CREATE INDEX card_index_number ON card_index (game, number, set_total)
"""
