from __future__ import annotations

from datetime import date

from fastapi import APIRouter

from mekiki_engine.deps import SessionDep, SettingsDep
from mekiki_engine.domain import Game, ItemStatus
from mekiki_engine.schemas import Dashboard, ItemOut, SimulationRequest, SimulationResult
from mekiki_engine.services import portfolio

router = APIRouter(tags=["reports"])


@router.get("/inventory")
def inventory(
    session: SessionDep,
    settings: SettingsDep,
    status: ItemStatus | None = None,
    game: Game | None = None,
) -> list[ItemOut]:
    return portfolio.inventory(session, settings, status=status, game=game)


@router.get("/dashboard")
def dashboard(
    session: SessionDep,
    settings: SettingsDep,
    since: date | None = None,
    until: date | None = None,
) -> Dashboard:
    return portfolio.dashboard(session, settings, since=since, until=until)


@router.post("/simulate")
def simulate(payload: SimulationRequest, settings: SettingsDep) -> SimulationResult:
    return portfolio.simulate(settings, payload)
