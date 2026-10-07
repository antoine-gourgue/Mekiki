from __future__ import annotations

from fastapi import APIRouter, status

from mekiki_engine.deps import DataDirDep, SessionDep, SettingsDep, UserDep
from mekiki_engine.schemas import ItemCreate, ItemOut, LotCreate, LotDetail, LotOut, LotUpdate
from mekiki_engine.services import photos, portfolio

router = APIRouter(prefix="/lots", tags=["lots"])


@router.get("")
def list_lots(session: SessionDep, user: UserDep, settings: SettingsDep) -> list[LotOut]:
    return portfolio.list_lots(session, user.id, settings)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_lot(
    payload: LotCreate, session: SessionDep, user: UserDep, settings: SettingsDep
) -> LotDetail:
    return portfolio.create_lot(session, user.id, settings, payload)


@router.get("/{lot_id}")
def read_lot(lot_id: int, session: SessionDep, user: UserDep, settings: SettingsDep) -> LotDetail:
    return portfolio.lot_detail(session, user.id, settings, lot_id)


@router.patch("/{lot_id}")
def update_lot(
    lot_id: int, payload: LotUpdate, session: SessionDep, user: UserDep, settings: SettingsDep
) -> LotDetail:
    return portfolio.update_lot(session, user.id, settings, lot_id, payload)


@router.delete("/{lot_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_lot(lot_id: int, session: SessionDep, user: UserDep, data_dir: DataDirDep) -> None:
    item_ids = portfolio.lot_item_ids(session, user.id, lot_id)
    portfolio.delete_lot(session, user.id, lot_id)
    photos.remove_item_files(data_dir, item_ids)


@router.post("/{lot_id}/items", status_code=status.HTTP_201_CREATED)
def add_item(
    lot_id: int, payload: ItemCreate, session: SessionDep, user: UserDep, settings: SettingsDep
) -> ItemOut:
    return portfolio.add_item(session, user.id, settings, lot_id, payload)
