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


class ListingTriage(StrEnum):
    NEW = "new"
    SEEN = "seen"
    DISMISSED = "dismissed"
    BOUGHT = "bought"


class ListingCondition(StrEnum):
    """The six conditions every Japanese flea market offers, best first."""

    NEW = "new"  # 新品、未使用
    LIKE_NEW = "like_new"  # 未使用に近い
    GOOD = "good"  # 目立った傷や汚れなし
    FAIR = "fair"  # やや傷や汚れあり
    POOR = "poor"  # 傷や汚れあり
    BAD = "bad"  # 全体的に状態が悪い

    def at_least(self, minimum: ListingCondition) -> bool:
        order = list(ListingCondition)
        return order.index(self) <= order.index(minimum)
