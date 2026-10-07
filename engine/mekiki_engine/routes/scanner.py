from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Query, Request, status

from mekiki_engine.deps import SessionDep, SettingsDep
from mekiki_engine.domain import Game, ListingTriage
from mekiki_engine.scanner import card_index, cardmarket, favorites, service
from mekiki_engine.scanner.discovery import DiscoveryJob
from mekiki_engine.scanner.runner import ScannerWorker, search_once
from mekiki_engine.scanner.sources.base import PoliteClient
from mekiki_engine.schemas import (
    CardmarketStatus,
    DealOut,
    DealUpdate,
    DiscoveryRequest,
    DiscoveryRun,
    FavoriteCreate,
    FavoritesOut,
    FavoriteUpdate,
    MarketPriceOut,
    ScanStatus,
    SearchRequest,
    SearchResponse,
    TrackedCardCreate,
    TrackedCardOut,
    TrackedCardUpdate,
)

router = APIRouter(tags=["scanner"])


def _worker(request: Request) -> ScannerWorker:
    return request.app.state.scanner


def _client(request: Request) -> PoliteClient:
    return request.app.state.http


@router.get("/tracked-cards")
def list_tracked_cards(session: SessionDep, settings: SettingsDep) -> list[TrackedCardOut]:
    return service.list_tracked_cards(session, settings)


@router.post("/tracked-cards", status_code=status.HTTP_201_CREATED)
def create_tracked_card(
    payload: TrackedCardCreate, session: SessionDep, settings: SettingsDep
) -> TrackedCardOut:
    return service.create_tracked_card(session, settings, payload)


@router.patch("/tracked-cards/{card_id}")
def update_tracked_card(
    card_id: int, payload: TrackedCardUpdate, session: SessionDep, settings: SettingsDep
) -> TrackedCardOut:
    return service.update_tracked_card(session, settings, card_id, payload)


@router.delete("/tracked-cards/{card_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tracked_card(card_id: int, session: SessionDep) -> None:
    service.delete_tracked_card(session, card_id)


@router.get("/cardmarket/products")
def search_products(
    session: SessionDep,
    q: Annotated[str, Query(min_length=1, max_length=100)],
    game: Game = Game.POKEMON,
) -> list[MarketPriceOut]:
    return service.search_products(session, game=game, query=q)


@router.get("/cardmarket/status")
def cardmarket_status(session: SessionDep) -> list[CardmarketStatus]:
    return cardmarket.status(session)


@router.post("/cardmarket/refresh")
def refresh_cardmarket(request: Request, session: SessionDep) -> list[CardmarketStatus]:
    for game in Game:
        cardmarket.refresh(session, _client(request), game, force=True)
    card_index.refresh(session, _client(request))
    return cardmarket.status(session)


@router.get("/deals")
def list_deals(
    session: SessionDep,
    settings: SettingsDep,
    triage: ListingTriage | None = None,
    tracked_card_id: int | None = None,
    min_roi_percent: Decimal | None = None,
    include_offline: bool = False,
) -> list[DealOut]:
    return service.list_deals(
        session,
        settings,
        triage=triage,
        tracked_card_id=tracked_card_id,
        min_roi_percent=min_roi_percent,
        include_offline=include_offline,
    )


@router.patch("/deals/{listing_id}")
def update_deal(
    listing_id: int, payload: DealUpdate, session: SessionDep, settings: SettingsDep
) -> DealOut:
    return service.update_deal(session, settings, listing_id, payload.triage)


@router.post("/deals/mark-seen")
def mark_deals_seen(session: SessionDep) -> dict[str, int]:
    return {"updated": service.mark_new_deals_seen(session)}


@router.get("/scanner/status")
def scanner_status(request: Request, session: SessionDep, settings: SettingsDep) -> ScanStatus:
    return _status(request, session, settings)


@router.post("/scanner/run", status_code=status.HTTP_202_ACCEPTED)
def run_scanner(request: Request, session: SessionDep, settings: SettingsDep) -> ScanStatus:
    worker = _worker(request)
    if request.app.state.config.background_jobs:
        worker.request_scan()
    else:
        worker.run_now()
    return _status(request, session, settings)


def _status(request: Request, session: SessionDep, settings: SettingsDep) -> ScanStatus:
    scan_status = _worker(request).status(settings)
    scan_status.unseen_deals = service.count_unseen_deals(session, settings)
    return scan_status


@router.post("/search")
def search(
    payload: SearchRequest, request: Request, session: SessionDep, settings: SettingsDep
) -> SearchResponse:
    return search_once(
        session,
        settings,
        _client(request),
        payload,
        source_factory=request.app.state.source_factory,
    )


@router.get("/discovery")
def discovery_status(request: Request) -> DiscoveryRun:
    return _discovery(request).run


@router.post("/discovery", status_code=status.HTTP_202_ACCEPTED)
def start_discovery(payload: DiscoveryRequest, request: Request) -> DiscoveryRun:
    background = request.app.state.config.background_jobs
    return _discovery(request).start(payload, background=background)


@router.post("/discovery/stop")
def stop_discovery(request: Request) -> DiscoveryRun:
    return _discovery(request).stop()


def _discovery(request: Request) -> DiscoveryJob:
    return request.app.state.discovery


@router.get("/favorites")
def list_favorites(session: SessionDep, settings: SettingsDep) -> FavoritesOut:
    return favorites.list_favorites(session, settings)


@router.post("/favorites", status_code=status.HTTP_201_CREATED)
def add_favorite(
    payload: FavoriteCreate, session: SessionDep, settings: SettingsDep
) -> FavoritesOut:
    favorites.add_favorite(session, payload)
    return favorites.list_favorites(session, settings)


@router.patch("/favorites/{favorite_id}")
def update_favorite(
    favorite_id: int, payload: FavoriteUpdate, session: SessionDep, settings: SettingsDep
) -> FavoritesOut:
    favorites.update_favorite(session, favorite_id, payload)
    return favorites.list_favorites(session, settings)


@router.delete("/favorites/{favorite_id}")
def delete_favorite(favorite_id: int, session: SessionDep, settings: SettingsDep) -> FavoritesOut:
    favorites.delete_favorite(session, favorite_id)
    return favorites.list_favorites(session, settings)


@router.post("/favorites/empty-cart")
def empty_cart(session: SessionDep, settings: SettingsDep) -> FavoritesOut:
    favorites.empty_cart(session)
    return favorites.list_favorites(session, settings)
