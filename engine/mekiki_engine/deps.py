"""FastAPI dependencies shared by the routes."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from mekiki_engine.auth import AuthError, user_for_token
from mekiki_engine.db import session_scope
from mekiki_engine.models import User
from mekiki_engine.schemas import AppSettings
from mekiki_engine.services.settings_service import load_settings


def get_session(request: Request) -> Iterator[Session]:
    yield from session_scope(request.app.state.session_factory)


SessionDep = Annotated[Session, Depends(get_session)]


def get_token(request: Request) -> str:
    scheme, _, token = request.headers.get("Authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="connexion requise",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token


TokenDep = Annotated[str, Depends(get_token)]


def get_current_user(session: SessionDep, token: TokenDep) -> User:
    try:
        return user_for_token(session, token)
    except AuthError as error:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail=str(error),
            headers={"WWW-Authenticate": "Bearer"},
        ) from error


UserDep = Annotated[User, Depends(get_current_user)]


def get_settings(session: SessionDep, user: UserDep) -> AppSettings:
    return load_settings(session, user.id)


SettingsDep = Annotated[AppSettings, Depends(get_settings)]
