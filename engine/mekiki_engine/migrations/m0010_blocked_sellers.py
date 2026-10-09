# Sellers Neokyo refuses to buy from, shared by every account; and the seller of each listing
# found for a tracked card, to leave theirs out.
SQL = """
CREATE TABLE blocked_sellers (
    source TEXT NOT NULL,
    seller_id TEXT NOT NULL,
    reason TEXT NOT NULL,
    blocked_at TEXT NOT NULL,
    PRIMARY KEY (source, seller_id)
);
ALTER TABLE listings ADD COLUMN seller_id TEXT
"""
