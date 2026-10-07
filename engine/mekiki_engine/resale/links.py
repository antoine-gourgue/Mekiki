"""Pages the UI opens in the user's browser to check prices or publish a listing.

eBay's sold listings sit behind sign-in and Vinted's search behind a bot challenge, and
both forbid scraping: the engine never fetches them, the user's own browser does.
"""

from __future__ import annotations

from urllib.parse import urlencode

from mekiki_engine.domain import SalePlatform

# eBay "CCG Individual Cards" (Pokémon and One Piece singles alike).
EBAY_CARDS_CATEGORY = 183454
# Vinted "Cartes à collectionner > Cartes à l'unité".
VINTED_SINGLE_CARDS_CATALOG = 4875

NEW_LISTING_URLS = {
    SalePlatform.EBAY: "https://www.ebay.fr/sl/prelist/suggest",
    SalePlatform.VINTED: "https://www.vinted.fr/items/new",
}


def ebay_search_url(query: str, *, sold: bool = False) -> str:
    params: dict[str, str | int] = {"_nkw": query, "_sacat": EBAY_CARDS_CATEGORY}
    if sold:
        params |= {"LH_Sold": 1, "LH_Complete": 1}
    return f"https://www.ebay.fr/sch/i.html?{urlencode(params)}"


def ebay_research_url(query: str) -> str:
    """Terapeak, eBay's own research of sold prices (free for sellers, signed in)."""
    params = {"marketplace": "EBAY-FR", "keywords": query, "tabName": "SOLD", "dayRange": 90}
    return f"https://www.ebay.fr/sh/research?{urlencode(params)}"


def vinted_search_url(query: str) -> str:
    params = {"search_text": query, "catalog[]": VINTED_SINGLE_CARDS_CATALOG}
    return f"https://www.vinted.fr/catalog?{urlencode(params)}"
