from __future__ import annotations

from fastapi import APIRouter, status

from mekiki_engine.deps import SessionDep, SettingsDep
from mekiki_engine.schemas import ItemOut, ItemUpdate, SaleUpsert
from mekiki_engine.services import portfolio

router = APIRouter(prefix="/items", tags=["items"])


@router.patch("/{item_id}")
def update_item(
    item_id: int, payload: ItemUpdate, session: SessionDep, settings: SettingsDep
) -> ItemOut:
    return portfolio.update_item(session, settings, item_id, payload)


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_item(item_id: int, session: SessionDep) -> None:
    portfolio.delete_item(session, item_id)


@router.put("/{item_id}/sale")
def record_sale(
    item_id: int, payload: SaleUpsert, session: SessionDep, settings: SettingsDep
) -> ItemOut:
    return portfolio.record_sale(session, settings, item_id, payload)


@router.delete("/{item_id}/sale")
def cancel_sale(item_id: int, session: SessionDep, settings: SettingsDep) -> ItemOut:
    return portfolio.cancel_sale(session, settings, item_id)
