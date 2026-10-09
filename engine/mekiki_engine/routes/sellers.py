from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from mekiki_engine.deps import SessionDep, UserDep
from mekiki_engine.domain import SourcePlatform
from mekiki_engine.models import BlockedSeller
from mekiki_engine.scanner import availability, sellers
from mekiki_engine.schemas import BlockedSellerOut, BlockSellerRequest

router = APIRouter(prefix="/sellers", tags=["sellers"])


@router.get("/blocked")
def list_blocked(session: SessionDep, _user: UserDep) -> list[BlockedSellerOut]:
    rows = session.query(BlockedSeller).order_by(BlockedSeller.blocked_at.desc()).all()
    return [BlockedSellerOut.model_validate(row) for row in rows]


@router.post("/blocked", status_code=status.HTTP_201_CREATED)
def block_seller(
    payload: BlockSellerRequest, request: Request, session: SessionDep, _user: UserDep
) -> BlockedSellerOut:
    """Never propose this listing's seller again: Neokyo refused them."""
    seller_id = payload.seller_id
    if seller_id is None:
        # The listing's page names its seller; one request, as when opening its panel.
        checked = availability.check_listing(
            request.app.state.http, payload.source, payload.external_id
        )
        seller_id = checked.seller_id
    if seller_id is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "vendeur introuvable : seules les annonces Mercari le donnent",
        )
    row = sellers.block(session, payload.source.value, seller_id, payload.reason)
    return BlockedSellerOut.model_validate(row)


@router.delete("/blocked/{source}/{seller_id}", status_code=status.HTTP_204_NO_CONTENT)
def unblock_seller(
    source: SourcePlatform, seller_id: str, session: SessionDep, _user: UserDep
) -> None:
    sellers.unblock(session, source.value, seller_id)
