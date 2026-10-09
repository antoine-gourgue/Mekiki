# Sales imported from a platform's report: each keeps the report's reference so a second import
# changes nothing; lines no card could be found for wait in pending_sales. A card listed by
# Mekiki keeps its listing's address and number, which its sale's report line names.
SQL = """
ALTER TABLE sales ADD COLUMN external_ref TEXT;
ALTER TABLE items ADD COLUMN listing_url TEXT;
ALTER TABLE items ADD COLUMN listing_ref TEXT;
CREATE TABLE pending_sales (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    platform TEXT NOT NULL,
    external_ref TEXT NOT NULL,
    listing_ref TEXT,
    title TEXT NOT NULL,
    buyer TEXT,
    quantity INTEGER NOT NULL DEFAULT 1,
    sold_on TEXT NOT NULL,
    price_cents INTEGER NOT NULL,
    shipping_cents INTEGER NOT NULL DEFAULT 0,
    shipped_on TEXT,
    tracking_number TEXT,
    ignored INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    UNIQUE (user_id, external_ref)
)
"""
