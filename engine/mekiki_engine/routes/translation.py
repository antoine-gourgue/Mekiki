from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from mekiki_engine.deps import SessionDep, UserDep
from mekiki_engine.scanner.sources.base import PoliteClient, SourceError
from mekiki_engine.schemas import (
    DeeplKeyUpdate,
    TranslationOut,
    TranslationRequest,
    TranslationStatus,
)
from mekiki_engine.services import translation
from mekiki_engine.services.settings_service import load_deepl_key, save_deepl_key

router = APIRouter(tags=["translation"])


def _client(request: Request) -> PoliteClient:
    return request.app.state.http  # type: ignore[no-any-return]


@router.post("/translate")
def translate(
    payload: TranslationRequest, request: Request, session: SessionDep, user: UserDep
) -> TranslationOut:
    """A listing's description in French, with the account's DeepL key when it has one."""
    try:
        result = translation.translate(
            _client(request), payload.text, deepl_key=load_deepl_key(session, user.id)
        )
    except SourceError as error:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, f"Traduction impossible : {error}"
        ) from error
    return TranslationOut(text=result.text, provider=result.provider)


@router.get("/settings/translation")
def translation_status(session: SessionDep, user: UserDep) -> TranslationStatus:
    configured = load_deepl_key(session, user.id) is not None
    return TranslationStatus(
        provider="deepl" if configured else "mymemory", deepl_configured=configured
    )


@router.put("/settings/translation")
def save_key(
    payload: DeeplKeyUpdate, request: Request, session: SessionDep, user: UserDep
) -> TranslationStatus:
    """Keeps the account's DeepL key once DeepL has accepted it; it is never sent back."""
    key = payload.key.strip()
    try:
        translation.check_deepl_key(_client(request), key)
    except SourceError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error
    save_deepl_key(session, user.id, key)
    return translation_status(session, user)


@router.delete("/settings/translation")
def remove_key(session: SessionDep, user: UserDep) -> TranslationStatus:
    save_deepl_key(session, user.id, None)
    return translation_status(session, user)
