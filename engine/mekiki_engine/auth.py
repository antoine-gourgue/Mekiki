"""Accounts: password hashing, session tokens and sign-in throttling.

Passwords are hashed with scrypt (standard library, no compiled dependency). A session is an
opaque random token given to the client; only its SHA-256 is stored, and it can be revoked
by deleting the row, unlike a self-contained JWT.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import threading
import time
from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from mekiki_engine.models import AuthSession, Favorite, Lot, SettingRow, TrackedCard, User

SESSION_LIFETIME = timedelta(days=30)
# (N, r, p), OWASP's recommendation: 128 MiB and a fraction of a second per hash, so that
# passwords are slow to guess from a stolen database. Each hash carries its own parameters:
# older ones still verify, and are replaced at the next sign-in.
SCRYPT_PARAMS = (2**17, 8, 1)
# hashlib refuses scrypt above 32 MiB unless told otherwise; N=2^17 with r=8 needs 128 MiB.
_SCRYPT_MAXMEM = 256 * 1024 * 1024
_TIMESTAMP = "%Y-%m-%dT%H:%M:%SZ"


class AuthError(Exception):
    """Wrong credentials, unknown or expired token: the API answers 401."""


class TooManyAttempts(Exception):
    """Too many failed sign-ins for one address: the API answers 429."""


def hash_password(password: str) -> str:
    n, r, p = SCRYPT_PARAMS
    salt = secrets.token_bytes(16)
    digest = _scrypt(password, salt, n, r, p, 32)
    encoded = (base64.b64encode(part).decode() for part in (salt, digest))
    return "scrypt${}${}${}${}${}".format(n, r, p, *encoded)


def verify_password(password: str, stored: str) -> bool:
    try:
        _scheme, n, r, p, salt, digest = stored.split("$")
        expected = base64.b64decode(digest)
        actual = _scrypt(password, base64.b64decode(salt), int(n), int(r), int(p), len(expected))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


def needs_rehash(stored: str) -> bool:
    """Whether the hash was made with other parameters than today's."""
    try:
        _scheme, n, r, p, _salt, _digest = stored.split("$")
        return (int(n), int(r), int(p)) != SCRYPT_PARAMS
    except ValueError:
        return True


def _scrypt(password: str, salt: bytes, n: int, r: int, p: int, length: int) -> bytes:
    return hashlib.scrypt(
        password.encode(), salt=salt, n=n, r=r, p=p, dklen=length, maxmem=_SCRYPT_MAXMEM
    )


def normalize_email(email: str) -> str:
    return email.strip().lower()


def create_session(session: Session, user: User) -> str:
    token = secrets.token_urlsafe(32)
    expires = datetime.now(UTC) + SESSION_LIFETIME
    session.add(
        AuthSession(
            token_hash=_token_hash(token),
            user_id=user.id,
            expires_at=expires.strftime(_TIMESTAMP),
        )
    )
    session.commit()
    return token


def user_for_token(session: Session, token: str) -> User:
    row = session.get(AuthSession, _token_hash(token))
    if row is None or row.expires_at < datetime.now(UTC).strftime(_TIMESTAMP):
        raise AuthError("session expirée ou inconnue")
    user = session.get(User, row.user_id)
    if user is None:
        raise AuthError("compte supprimé")
    return user


def revoke_session(session: Session, token: str) -> None:
    session.execute(delete(AuthSession).where(AuthSession.token_hash == _token_hash(token)))
    session.commit()


def revoke_other_sessions(session: Session, user_id: int, keep_token: str) -> None:
    session.execute(
        delete(AuthSession).where(
            AuthSession.user_id == user_id,
            AuthSession.token_hash != _token_hash(keep_token),
        )
    )
    session.commit()


def claim_unowned_data(session: Session, user_id: int) -> None:
    """Gives data created before accounts existed to the first account."""
    for model in (Lot, TrackedCard, Favorite):
        session.execute(update(model).where(model.user_id.is_(None)).values(user_id=user_id))
    for key in ("app", "discovery:last"):
        row = session.get(SettingRow, key)
        if row is not None and session.get(SettingRow, f"{key}:{user_id}") is None:
            session.add(SettingRow(key=f"{key}:{user_id}", value=row.value))
            session.delete(row)
    session.commit()


def no_account_yet(session: Session) -> bool:
    return session.scalars(select(User.id).limit(2)).all() == []


class SignInThrottle:
    """At most ``limit`` failed sign-ins per address within ``window_s`` seconds."""

    def __init__(self, limit: int = 5, window_s: float = 15 * 60) -> None:
        self.limit = limit
        self.window_s = window_s
        self._failures: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, email: str) -> None:
        with self._lock:
            failures = self._recent(email)
            if len(failures) >= self.limit:
                raise TooManyAttempts

    def failed(self, email: str) -> None:
        with self._lock:
            self._recent(email).append(time.monotonic())

    def succeeded(self, email: str) -> None:
        with self._lock:
            self._failures.pop(email, None)

    def _recent(self, email: str) -> deque[float]:
        failures = self._failures[email]
        while failures and failures[0] < time.monotonic() - self.window_s:
            failures.popleft()
        return failures


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
