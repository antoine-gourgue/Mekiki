# Each sale keeps its two rates apart: the URSSAF contributions and the optional flat income
# tax (versement libératoire). The books then use the rates in force when the card sold, even
# after the settings change (end of ACRE, a new law).
SQL = """
ALTER TABLE sales ADD COLUMN income_tax_rate TEXT
"""
