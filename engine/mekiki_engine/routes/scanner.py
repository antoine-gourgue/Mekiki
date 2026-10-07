from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Query, Request, status

from mekiki_engine.deps import SessionDep, SettingsDep, UserDep
from mekiki_engine.domain import Game, ListingTriage
from mekiki_engine.scanner import card_index, cardmarket, favorites, names, service
from mekiki_engine.scanner.discovery import DiscoveryJob, DiscoveryJobs
from mekiki_engine.scanner.runner import ScannerWorker, search_once
from mekiki_engine.scanner.sources.base import PoliteClient
from mekiki_engine.schemas import (
    AppSettings,
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


def _discovery(request: Request, user_id: int) -> DiscoveryJob:
    jobs: DiscoveryJobs = request.app.state.discovery
    return jobs.for_user(user_id)


@router.get("/tracked-cards")
def list_tracked_cards(
    session: SessionDep, user: UserDep, settings: SettingsDep
) -> list[TrackedCardOut]:
    return service.list_tracked_cards(session, user.id, settings)


@router.post("/tracked-cards", status_code=status.HTTP_201_CREATED)
def create_tracked_card(
    payload: TrackedCardCreate, session: SessionDep, user: UserDep, settings: SettingsDep
) -> TrackedCardOut:
    return service.create_tracked_card(session, user.id, settings, payload)


@router.patch("/tracked-cards/{card_id}")
def update_tracked_card(
    card_id: int,
    payload: TrackedCardUpdate,
    session: SessionDep,
    user: UserDep,
    settings: SettingsDep,
) -> TrackedCardOut:
    return service.update_tracked_card(session, user.id, settings, card_id, payload)


@router.delete("/tracked-cards/{card_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tracked_card(card_id: int, session: SessionDep, user: UserDep) -> None:
    service.delete_tracked_card(session, user.id, card_id)


@router.get("/cardmarket/products")
def search_products(
    request: Request,
    session: SessionDep,
    _user: UserDep,
    q: Annotated[str, Query(min_length=1, max_length=100)],
    game: Game = Game.POKEMON,
) -> list[MarketPriceOut]:
    # French names need the Pokémon name list, downloaded on first use.
    if game is Game.POKEMON and not names.species_count(session):
        names.refresh(session, _client(request))
    return service.search_products(session, game=game, query=q)


@router.get("/cardmarket/products/{id_product}")
def read_product(id_product: int, session: SessionDep, _user: UserDep) -> MarketPriceOut:
    return service.product_detail(session, id_product)


@router.get("/cardmarket/status")
def cardmarket_status(session: SessionDep, _user: UserDep) -> list[CardmarketStatus]:
    return cardmarket.status(session)


@router.post("/cardmarket/refresh")
def refresh_cardmarket(
    request: Request, session: SessionDep, _user: UserDep
) -> list[CardmarketStatus]:
    for game in Game:
        cardmarket.refresh(session, _client(request), game, force=True)
    card_index.refresh(session, _client(request))
    return cardmarket.status(session)


@router.get("/deals")
def list_deals(
    session: SessionDep,
    user: UserDep,
    settings: SettingsDep,
    triage: ListingTriage | None = None,
    tracked_card_id: int | None = None,
    min_roi_percent: Decimal | None = None,
    include_offline: bool = False,
) -> list[DealOut]:
    return service.list_deals(
        session,
        user.id,
        settings,
        triage=triage,
        tracked_card_id=tracked_card_id,
        min_roi_percent=min_roi_percent,
        include_offline=include_offline,
    )


@router.patch("/deals/{listing_id}")
def update_deal(
    listing_id: int,
    payload: DealUpdate,
    session: SessionDep,
    user: UserDep,
    settings: SettingsDep,
) -> DealOut:
    return service.update_deal(session, user.id, settings, listing_id, payload.triage)


@router.post("/deals/mark-seen")
def mark_deals_seen(session: SessionDep, user: UserDep) -> dict[str, int]:
    return {"updated": service.mark_new_deals_seen(session, user.id)}


@router.get("/scanner/status")
def scanner_status(
    request: Request, session: SessionDep, user: UserDep, settings: SettingsDep
) -> ScanStatus:
    return _status(request, session, user.id, settings)


@router.post("/scanner/run", status_code=status.HTTP_202_ACCEPTED)
def run_scanner(
    request: Request, session: SessionDep, user: UserDep, settings: SettingsDep
) -> ScanStatus:
    worker = _worker(request)
    if request.app.state.config.background_jobs:
        worker.request_scan(user.id)
    else:
        worker.run_now(user.id)
    return _status(request, session, user.id, settings)


def _status(
    request: Request, session: SessionDep, user_id: int, settings: AppSettings
) -> ScanStatus:
    scan_status = _worker(request).status(user_id, settings)
    scan_status.unseen_deals = service.count_unseen_deals(session, user_id, settings)
    return scan_status


@router.post("/search")
def search(
    payload: SearchRequest,
    request: Request,
    session: SessionDep,
    _user: UserDep,
    settings: SettingsDep,
) -> SearchResponse:
    return search_once(
        session,
        settings,
        _client(request),
        payload,
        source_factory=request.app.state.source_factory,
    )


@router.get("/discovery")
def discovery_status(request: Request, user: UserDep) -> DiscoveryRun:
    return _discovery(request, user.id).run


@router.post("/discovery", status_code=status.HTTP_202_ACCEPTED)
def start_discovery(payload: DiscoveryRequest, request: Request, user: UserDep) -> DiscoveryRun:
    background = request.app.state.config.background_jobs
    return _discovery(request, user.id).start(payload, background=background)


@router.post("/discovery/stop")
def stop_discovery(request: Request, user: UserDep) -> DiscoveryRun:
    return _discovery(request, user.id).stop()


@router.get("/favorites")
def list_favorites(session: SessionDep, user: UserDep, settings: SettingsDep) -> FavoritesOut:
    return favorites.list_favorites(session, user.id, settings)


@router.post("/favorites", status_code=status.HTTP_201_CREATED)
def add_favorite(
    payload: FavoriteCreate, session: SessionDep, user: UserDep, settings: SettingsDep
) -> FavoritesOut:
    favorites.add_favorite(session, user.id, payload)
    return favorites.list_favorites(session, user.id, settings)


@router.patch("/favorites/{favorite_id}")
def update_favorite(
    favorite_id: int,
    payload: FavoriteUpdate,
    session: SessionDep,
    user: UserDep,
    settings: SettingsDep,
) -> FavoritesOut:
    favorites.update_favorite(session, user.id, favorite_id, payload)
    return favorites.list_favorites(session, user.id, settings)


@router.delete("/favorites/{favorite_id}")
def delete_favorite(
    favorite_id: int, session: SessionDep, user: UserDep, settings: SettingsDep
) -> FavoritesOut:
    favorites.delete_favorite(session, user.id, favorite_id)
    return favorites.list_favorites(session, user.id, settings)


@router.post("/favorites/empty-cart")
def empty_cart(session: SessionDep, user: UserDep, settings: SettingsDep) -> FavoritesOut:
    favorites.empty_cart(session, user.id)
    return favorites.list_favorites(session, user.id, settings)
