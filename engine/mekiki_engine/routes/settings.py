from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from mekiki_engine.deps import SessionDep, SettingsDep, UserDep
from mekiki_engine.resale.ebay import EbayBrowse, EbayKeysRefused
from mekiki_engine.resale.service import ebay_for
from mekiki_engine.scanner.sources.base import SourceError
from mekiki_engine.schemas import AppSettings, EbayKeys, EbayKeysUpdate, EbayStatus
from mekiki_engine.services.settings_service import load_ebay_keys, save_ebay_keys, save_settings

router = APIRouter(prefix="/settings", tags=["settings"])

# eBay's OAuth errors, explained. "invalid_client" also answers keys that are right but
# belong to a Production keyset eBay keeps disabled until its developer has dealt with the
# account deletion notifications every application must handle.
REFUSED_KEYS = {
    "invalid_client": (
        "eBay ne reconnaît pas ce couple de clés de Production. Vérifiez que le Cert ID est bien "
        "le Client Secret (et non le Dev ID), copié en entier. Si les clés sont justes, le jeu "
        "Production est sans doute encore désactivé : sur developer.ebay.com, eBay demande "
        "d'abord de régler les notifications de suppression de compte (« Marketplace Account "
        "Deletion »). Mekiki ne garde aucune donnée d'utilisateur eBay : l'exemption convient."
    ),
    "invalid_scope": (
        "Ces clés n'ont pas accès à la recherche d'annonces d'eBay (API Browse) : vérifiez que "
        "le jeu de clés Production est actif sur developer.ebay.com."
    ),
}


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
    try:
        sold_api: bool | None = ebay.sold_allowed()
    except SourceError:
        sold_api = None
    return EbayStatus(
        configured=True,
        source=source,  # type: ignore[arg-type]
        client_id=ebay.credentials[0] if source == "account" else None,
        marketplace=ebay.marketplace,
        sold_api=sold_api,
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
    except EbayKeysRefused as error:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            REFUSED_KEYS.get(
                error.code,
                f"eBay refuse ces clés ({error}) : vérifiez l'App ID et le Cert ID de Production",
            ),
        ) from error
    except SourceError as error:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"Clés non vérifiées : eBay ne répond pas ({error}). Réessayez dans un moment.",
        ) from error
    save_ebay_keys(session, user.id, keys)
    return ebay_status(request, session, user)


@router.delete("/ebay")
def remove_ebay(request: Request, session: SessionDep, user: UserDep) -> EbayStatus:
    save_ebay_keys(session, user.id, None)
    return ebay_status(request, session, user)
