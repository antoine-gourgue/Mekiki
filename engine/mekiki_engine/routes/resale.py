from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, Request, status

from mekiki_engine.deps import SessionDep, SettingsDep, UserDep
from mekiki_engine.domain import SalePlatform
from mekiki_engine.resale import service
from mekiki_engine.scanner import names
from mekiki_engine.schemas import CardVerdict, ListingDraftOut, ResalePrices

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
    ebay, _source = service.ebay_for(request.app.state, session, _user.id)
    return service.resale_prices(ebay, query)


@router.get("/resale/verdict")
def resale_verdict(
    request: Request,
    session: SessionDep,
    user: UserDep,
    settings: SettingsDep,
    item_id: int | None = None,
    product_id: int | None = None,
    label: Annotated[str | None, Query(max_length=200)] = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
    price_jpy: Annotated[int | None, Query(ge=0)] = None,
    shipping_included: bool | None = None,
) -> CardVerdict:
    """Whether a card is worth buying: a card in stock, a Japanese listing at ``price_jpy``
    or a catalog product, judged on every resale outlet."""
    # Vinted is searched with French names, which need the Pokémon name list.
    if not names.species_count(session):
        names.refresh(session, request.app.state.http)
    ebay, _source = service.ebay_for(request.app.state, session, user.id)
    result = service.verdict(
        session,
        settings,
        ebay,
        user.id,
        item_id=item_id,
        product_id=product_id,
        label=label,
        query=" ".join((q or "").replace("·", " ").split()),
        price_jpy=price_jpy,
        shipping_included=shipping_included,
        browsers=request.app.state.browsers,
    )
    if result is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="carte inconnue")
    return result


@router.get("/items/{item_id}/listing-draft")
def listing_draft(
    item_id: int,
    platform: Literal["ebay", "vinted"],
    session: SessionDep,
    user: UserDep,
) -> ListingDraftOut:
    return service.listing_draft(session, user.id, item_id, SalePlatform(platform))
