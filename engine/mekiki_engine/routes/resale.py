from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, Request, status

from mekiki_engine.deps import SessionDep, UserDep
from mekiki_engine.domain import SalePlatform
from mekiki_engine.resale import service
from mekiki_engine.schemas import ListingDraftOut, ResalePrices

router = APIRouter(tags=["resale"])


@router.get("/resale/prices")
def resale_prices(
    request: Request,
    session: SessionDep,
    _user: UserDep,
    q: Annotated[str | None, Query(max_length=200)] = None,
    product_id: int | None = None,
    label: Annotated[str | None, Query(max_length=200)] = None,
) -> ResalePrices:
    """eBay listings and price links for a search, or for a Cardmarket product."""
    # Card labels ("M6 110/076 · MUR") make fine searches once their separators are gone.
    query = " ".join((q or "").replace("·", " ").split())
    if not query and product_id is not None:
        query = service.product_query(session, product_id, label) or ""
    if not query:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="recherche vide")
    return service.resale_prices(request.app.state.ebay, query)


@router.get("/items/{item_id}/listing-draft")
def listing_draft(
    item_id: int,
    platform: Literal["ebay", "vinted"],
    session: SessionDep,
    user: UserDep,
) -> ListingDraftOut:
    return service.listing_draft(session, user.id, item_id, SalePlatform(platform))
