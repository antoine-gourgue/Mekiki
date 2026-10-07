"""Favorite listings, and the cart: the favorites priced together as one parcel."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from mekiki_engine.domain import SourcePlatform
from mekiki_engine.models import CardmarketProduct, Favorite
from mekiki_engine.scanner import links
from mekiki_engine.scanner.pricing import (
    DealEstimate,
    expected_sale_cents,
    landed_cost_of_listing,
    landed_costs_of_parcel,
    parcel_totals,
)
from mekiki_engine.scanner.service import landed_cost_out, market_price_out, sale_breakdown_out
from mekiki_engine.schemas import (
    AppSettings,
    FavoriteCreate,
    FavoriteFields,
    FavoriteOut,
    FavoritesOut,
    FavoriteUpdate,
)
from mekiki_engine.services.portfolio import NotFoundError, project_sale


def list_favorites(session: Session, user_id: int, settings: AppSettings) -> FavoritesOut:
    favorites = session.scalars(
        select(Favorite).where(Favorite.user_id == user_id).order_by(Favorite.id.desc())
    ).all()
    products = _products(session, favorites)
    expected = {
        f.id: expected_sale_cents(f.target_price_cents, products.get(f.cardmarket_product_id))
        for f in favorites
    }
    sales = {
        f.id: project_sale(settings, settings.scanner.resale_platform, expected[f.id])
        if expected[f.id] is not None
        else None
        for f in favorites
    }

    cart = [f for f in favorites if f.in_cart]
    cart_landed = dict(
        zip(
            (f.id for f in cart),
            landed_costs_of_parcel(settings, [(f.price_jpy, f.shipping_included) for f in cart]),
            strict=True,
        )
    )
    items = []
    for favorite in favorites:
        landed = cart_landed.get(favorite.id) or landed_cost_of_listing(
            settings, favorite.price_jpy, favorite.shipping_included
        )
        estimate = DealEstimate(landed=landed, sale=sales[favorite.id])
        product = products.get(favorite.cardmarket_product_id)
        items.append(
            FavoriteOut(
                **{name: getattr(favorite, name) for name in FavoriteFields.model_fields},
                id=favorite.id,
                created_at=favorite.created_at,
                neokyo_url=links.neokyo_url(SourcePlatform(favorite.source), favorite.external_id),
                product=market_price_out(product) if product else None,
                expected_sale_cents=expected[favorite.id],
                landed_cost=landed_cost_out(estimate),
                sale=sale_breakdown_out(estimate),
            )
        )
    totals = (
        parcel_totals(
            [f.price_jpy for f in cart],
            [cart_landed[f.id] for f in cart],
            [sales[f.id] for f in cart],
        )
        if cart
        else None
    )
    return FavoritesOut(items=items, cart=totals)


def add_favorite(session: Session, user_id: int, payload: FavoriteCreate) -> None:
    """Saves a listing; saving it again refreshes its price, title and pictures."""
    favorite = session.scalars(
        select(Favorite).where(
            Favorite.user_id == user_id,
            Favorite.source == payload.source.value,
            Favorite.external_id == payload.external_id,
        )
    ).first()
    values = payload.model_dump()
    values["game"] = payload.game.value
    values["source"] = payload.source.value
    if favorite is None:
        session.add(Favorite(**values, user_id=user_id))
    else:
        # The user's own choices on an existing favorite win over a new save.
        for keep in ("in_cart", "notes", "target_price_cents"):
            values.pop(keep)
        for name, value in values.items():
            setattr(favorite, name, value)
    session.commit()


def update_favorite(
    session: Session, user_id: int, favorite_id: int, payload: FavoriteUpdate
) -> None:
    favorite = _get(session, user_id, favorite_id)
    for name, value in payload.model_dump(exclude_unset=True).items():
        setattr(favorite, name, value)
    session.commit()


def delete_favorite(session: Session, user_id: int, favorite_id: int) -> None:
    session.delete(_get(session, user_id, favorite_id))
    session.commit()


def empty_cart(session: Session, user_id: int) -> None:
    cart = select(Favorite).where(Favorite.user_id == user_id, Favorite.in_cart.is_(True))
    for favorite in session.scalars(cart):
        favorite.in_cart = False
    session.commit()


def _get(session: Session, user_id: int, favorite_id: int) -> Favorite:
    favorite = session.get(Favorite, favorite_id)
    if favorite is None or favorite.user_id != user_id:
        raise NotFoundError(f"favorite {favorite_id} not found")
    return favorite


def _products(session: Session, favorites: list[Favorite]) -> dict[int | None, CardmarketProduct]:
    ids = {f.cardmarket_product_id for f in favorites if f.cardmarket_product_id}
    if not ids:
        return {}
    rows = session.scalars(select(CardmarketProduct).where(CardmarketProduct.id_product.in_(ids)))
    return {product.id_product: product for product in rows}
