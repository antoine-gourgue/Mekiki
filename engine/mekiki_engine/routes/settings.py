from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from mekiki_engine.deps import SessionDep, SettingsDep, UserDep
from mekiki_engine.resale.ebay import EbayBrowse
from mekiki_engine.resale.service import ebay_for
from mekiki_engine.scanner.sources.base import SourceError
from mekiki_engine.schemas import AppSettings, EbayKeys, EbayKeysUpdate, EbayStatus
from mekiki_engine.services.settings_service import load_ebay_keys, save_ebay_keys, save_settings

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("")
def read_settings(settings: SettingsDep) -> AppSettings:
    return settings


@router.put("")
def replace_settings(payload: AppSettings, session: SessionDep, user: UserDep) -> AppSettings:
    return save_settings(session, user.id, payload)


@router.get("/ebay")
def ebay_status(request: Request, session: SessionDep, user: UserDep) -> EbayStatus:
    """Which eBay keys the account's searches use; the secret is never sent back."""
    ebay, source = ebay_for(request.app.state, session, user.id)
    if ebay is None:
        return EbayStatus(configured=False)
    return EbayStatus(
        configured=True,
        source=source,  # type: ignore[arg-type]
        client_id=ebay.credentials[0] if source == "account" else None,
        marketplace=ebay.marketplace,
    )


@router.put("/ebay")
def save_ebay(
    payload: EbayKeysUpdate, request: Request, session: SessionDep, user: UserDep
) -> EbayStatus:
    """Saves the account's own eBay keys once eBay has accepted them."""
    current = load_ebay_keys(session, user.id)
    client_id = payload.client_id.strip()
    secret = (payload.client_secret or "").strip() or (
        current.client_secret if current and current.client_id == client_id else ""
    )
    if not secret:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "indiquez le Cert ID")
    keys = EbayKeys(client_id=client_id, client_secret=secret, marketplace=payload.marketplace)
    # Sandbox keys only reach eBay's test site, whose listings are made up.
    if "-SBX-" in keys.client_id.upper() or keys.client_secret.upper().startswith("SBX-"):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "ce sont des clés Sandbox, pour le site de test d'eBay : prenez celles de Production",
        )
    try:
        EbayBrowse(
            request.app.state.http, keys.client_id, keys.client_secret, keys.marketplace
        ).check()
    except SourceError as error:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"eBay refuse ces clés ({error}) : vérifiez l'App ID et le Cert ID de Production",
        ) from error
    save_ebay_keys(session, user.id, keys)
    return ebay_status(request, session, user)


@router.delete("/ebay")
def remove_ebay(request: Request, session: SessionDep, user: UserDep) -> EbayStatus:
    save_ebay_keys(session, user.id, None)
    return ebay_status(request, session, user)
