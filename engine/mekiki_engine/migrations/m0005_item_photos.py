# Photos of a card in stock, for its eBay and Vinted listings. The files live in the data
# folder (photos/<item id>/); the table keeps their order and type.
SQL = """
CREATE TABLE item_photos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    file_name TEXT NOT NULL,
    content_type TEXT NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE INDEX item_photos_by_item ON item_photos (item_id, position)
"""
