from __future__ import annotations

from mekiki_engine.domain import Game, SourcePlatform
from mekiki_engine.scanner.sources.base import PoliteClient, Source
from mekiki_engine.scanner.sources.mercari import MercariSource
from mekiki_engine.scanner.sources.rakuma import RakumaSource
from mekiki_engine.scanner.sources.yahoo_auctions import YahooAuctionsSource
from mekiki_engine.scanner.sources.yahoo_fleamarket import YahooFleamarketSource


def build_source(platform: SourcePlatform, client: PoliteClient, game: Game) -> Source:
    match platform:
        case SourcePlatform.MERCARI:
            return MercariSource(client, game)
        case SourcePlatform.YAHOO_AUCTIONS:
            return YahooAuctionsSource(client, game)
        case SourcePlatform.YAHOO_FLEAMARKET:
            return YahooFleamarketSource(client, game)
        case SourcePlatform.RAKUMA:
            return RakumaSource(client, game)
        case _:
            raise ValueError(f"{platform} cannot be searched")
