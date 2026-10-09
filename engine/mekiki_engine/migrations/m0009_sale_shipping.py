# The parcel of each sale: its tracking number, and the day it left (null: still to ship).
SQL = """
ALTER TABLE sales ADD COLUMN tracking_number TEXT;
ALTER TABLE sales ADD COLUMN shipped_on TEXT
"""
