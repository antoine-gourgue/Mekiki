# Official Pokémon names in several languages (PokéAPI), to search Japanese marketplaces
# with a name typed in French or English. Reference data, shared by every account.
SQL = """
CREATE TABLE pokemon_species (
    id INTEGER PRIMARY KEY,
    ja TEXT,
    en TEXT,
    fr TEXT,
    de TEXT,
    es TEXT,
    it TEXT
)
"""
