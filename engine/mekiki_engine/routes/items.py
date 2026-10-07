from __future__ import annotations

from fastapi import APIRouter, status

from mekiki_engine.deps import SessionDep, SettingsDep, UserDep
from mekiki_engine.schemas import ItemOut, ItemUpdate, SaleUpsert
from mekiki_engine.services import portfolio

router = APIRouter(prefix="/items", tags=["items"])


@router.patch("/{item_id}")
def update_item(
    item_id: int, payload: ItemUpdate, session: SessionDep, user: UserDep, settings: SettingsDep
) -> ItemOut:
    return portfolio.update_item(session, user.id, settings, item_id, payload)


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_item(item_id: int, session: SessionDep, user: UserDep) -> None:
    portfolio.delete_item(session, user.id, item_id)


@router.put("/{item_id}/sale")
def record_sale(
    item_id: int, payload: SaleUpsert, session: SessionDep, user: UserDep, settings: SettingsDep
) -> ItemOut:
    return portfolio.record_sale(session, user.id, settings, item_id, payload)


@router.delete("/{item_id}/sale")
def cancel_sale(item_id: int, session: SessionDep, user: UserDep, settings: SettingsDep) -> ItemOut:
    return portfolio.cancel_sale(session, user.id, settings, item_id)
