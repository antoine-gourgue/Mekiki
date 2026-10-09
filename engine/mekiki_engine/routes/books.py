from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query, Response

from mekiki_engine.deps import SessionDep, SettingsDep, UserDep
from mekiki_engine.schemas import BooksSummary
from mekiki_engine.services import books

router = APIRouter(prefix="/books", tags=["books"])

Year = Annotated[int | None, Query(ge=2000, le=2100)]


@router.get("/summary")
def summary(
    session: SessionDep, user: UserDep, settings: SettingsDep, year: Year = None
) -> BooksSummary:
    today = date.today()
    return books.summary(session, user.id, settings, year or today.year, today=today)


@router.get("/receipts.csv")
def receipts_csv(
    session: SessionDep, user: UserDep, settings: SettingsDep, year: Year = None
) -> Response:
    """The book of receipts, for Excel."""
    year = year or date.today().year
    rows = books.receipts(session, user.id, settings, year)
    return _download(books.receipts_csv(rows), f"livre-des-recettes-{year}.csv")


@router.get("/purchases.csv")
def purchases_csv(
    session: SessionDep, user: UserDep, settings: SettingsDep, year: Year = None
) -> Response:
    """The register of purchases, for Excel."""
    year = year or date.today().year
    rows = books.purchases(session, user.id, settings, year)
    return _download(books.purchases_csv(rows), f"registre-des-achats-{year}.csv")


def _download(content: str, file_name: str) -> Response:
    return Response(
        content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{file_name}"'},
    )
