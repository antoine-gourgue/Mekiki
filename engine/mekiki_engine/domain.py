from __future__ import annotations

from enum import StrEnum


class Game(StrEnum):
    POKEMON = "pokemon"
    ONE_PIECE = "one_piece"


class SourcePlatform(StrEnum):
    MERCARI = "mercari"
    YAHOO_AUCTIONS = "yahoo_auctions"
    YAHOO_FLEAMARKET = "yahoo_fleamarket"
    RAKUMA = "rakuma"
    OTHER = "other"


class SalePlatform(StrEnum):
    CARDMARKET = "cardmarket"
    EBAY = "ebay"
    VINTED = "vinted"
    LEBONCOIN = "leboncoin"
    OTHER = "other"


class LotStatus(StrEnum):
    PURCHASING = "purchasing"
    SHIPPED = "shipped"
    RECEIVED = "received"


class ItemStatus(StrEnum):
    INCOMING = "incoming"
    IN_STOCK = "in_stock"
    LISTED = "listed"
    SOLD = "sold"
