# The Japanese name of each card's set ("ワイルドフォース"): titles without a number often
# name the set instead, which settles cards that share a name and a rarity.
SQL = """
ALTER TABLE card_index ADD COLUMN set_name TEXT
"""
