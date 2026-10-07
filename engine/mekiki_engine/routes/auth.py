from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from mekiki_engine import auth
from mekiki_engine.deps import SessionDep, TokenDep, UserDep
from mekiki_engine.models import User
from mekiki_engine.schemas import (
    AccountUpdate,
    AuthResponse,
    LoginRequest,
    RegisterRequest,
    UserOut,
)

router = APIRouter(prefix="/auth", tags=["auth"])

INVALID_CREDENTIALS = "adresse e-mail ou mot de passe incorrect"


def _throttle(request: Request) -> auth.SignInThrottle:
    return request.app.state.sign_in_throttle


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, session: SessionDep) -> AuthResponse:
    email = auth.normalize_email(payload.email)
    first_account = auth.no_account_yet(session)
    user = User(
        email=email,
        password_hash=auth.hash_password(payload.password),
        display_name=payload.display_name.strip(),
    )
    session.add(user)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="un compte existe déjà avec cette adresse"
        ) from error
    if first_account:
        auth.claim_unowned_data(session, user.id)
    token = auth.create_session(session, user)
    return AuthResponse(token=token, user=UserOut.model_validate(user))


@router.post("/login")
def login(payload: LoginRequest, request: Request, session: SessionDep) -> AuthResponse:
    email = auth.normalize_email(payload.email)
    throttle = _throttle(request)
    try:
        throttle.check(email)
    except auth.TooManyAttempts as error:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail="trop de tentatives, réessayez dans quelques minutes",
        ) from error
    user = session.scalars(select(User).where(User.email == email)).first()
    if user is None or not auth.verify_password(payload.password, user.password_hash):
        throttle.failed(email)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=INVALID_CREDENTIALS)
    throttle.succeeded(email)
    token = auth.create_session(session, user)
    return AuthResponse(token=token, user=UserOut.model_validate(user))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(session: SessionDep, token: TokenDep, _user: UserDep) -> None:
    auth.revoke_session(session, token)


@router.get("/me")
def me(user: UserDep) -> UserOut:
    return UserOut.model_validate(user)


@router.patch("/me")
def update_me(
    payload: AccountUpdate, session: SessionDep, token: TokenDep, user: UserDep
) -> UserOut:
    if payload.display_name is not None:
        user.display_name = payload.display_name.strip()
    if payload.new_password is not None:
        current = payload.current_password or ""
        if not auth.verify_password(current, user.password_hash):
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="mot de passe actuel incorrect")
        user.password_hash = auth.hash_password(payload.new_password)
        # A changed password must lock out whoever else was signed in.
        auth.revoke_other_sessions(session, user.id, token)
    session.commit()
    return UserOut.model_validate(user)
