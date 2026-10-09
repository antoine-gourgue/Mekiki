from __future__ import annotations

from fastapi import APIRouter, status

from mekiki_engine.deps import SessionDep, SettingsDep, UserDep
from mekiki_engine.schemas import (
    ImportReport,
    ItemOut,
    MatchPendingSale,
    PendingSaleOut,
    SalesReportUpload,
)
from mekiki_engine.services import sales_import

router = APIRouter(prefix="/sales", tags=["sales"])


@router.post("/import/ebay")
def import_ebay(
    payload: SalesReportUpload, session: SessionDep, user: UserDep, settings: SettingsDep
) -> ImportReport:
    """Reads eBay's orders report: sales recorded, brought up to date or left to match."""
    return sales_import.import_ebay_report(session, user.id, settings, payload.content)


@router.get("/pending")
def list_pending(session: SessionDep, user: UserDep) -> list[PendingSaleOut]:
    return sales_import.list_pending(session, user.id)


@router.post("/pending/{pending_id}/match")
def match_pending(
    pending_id: int,
    payload: MatchPendingSale,
    session: SessionDep,
    user: UserDep,
    settings: SettingsDep,
) -> ItemOut:
    return sales_import.match_pending(session, user.id, settings, pending_id, payload.item_id)


@router.delete("/pending/{pending_id}", status_code=status.HTTP_204_NO_CONTENT)
def ignore_pending(pending_id: int, session: SessionDep, user: UserDep) -> None:
    sales_import.ignore_pending(session, user.id, pending_id)
