# Sellers blocked automatically for a few bad ratings ("1 sur 24") were often not refused by
# Neokyo: they are unblocked, and only a seller with a truly bad share is blocked again.
SQL = """
DELETE FROM blocked_sellers WHERE reason LIKE 'trop d''évaluations négatives (%'
"""
