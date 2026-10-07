"""FastAPI dependencies shared by the routes."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from mekiki_engine.db import session_scope
from mekiki_engine.schemas import AppSettings
from mekiki_engine.services.settings_service import load_settings


def get_session(request: Request) -> Iterator[Session]:
    yield from session_scope(request.app.state.session_factory)


SessionDep = Annotated[Session, Depends(get_session)]


def get_settings(session: SessionDep) -> AppSettings:
    return load_settings(session)


SettingsDep = Annotated[AppSettings, Depends(get_settings)]
