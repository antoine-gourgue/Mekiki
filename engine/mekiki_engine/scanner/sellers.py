"""Sellers Neokyo refuses to buy from, and how to see them coming.

Neokyo blocks the sellers who refuse proxies, collect bad ratings, cancel too often or were
reported by its users: their listings cannot be bought, so Mekiki must not propose them.
Neokyo's own list sits behind a bot check that Mekiki never goes through. What a listing shows
on Mercari gives most of them away (a refusal in the description, the ratings); the user adds
the others in a click when Neokyo turns one down. The list is shared by every account.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from mekiki_engine.models import BlockedSeller

_REFUSED = r"(?:不可|お断り|禁止|ご遠慮|NG|できません)"
# Refusals of proxies in a description. "海外発送不可" (no shipping abroad) is no refusal:
# Neokyo buys and receives in Japan. Nor is "配送業者の指定はできません" (no choice of carrier).
PROXY_REFUSALS = (
    re.compile(rf"代行[^。\n]{{0,12}}?{_REFUSED}"),
    re.compile(rf"転送(?:業者|サービス)?[^。\n]{{0,10}}?{_REFUSED}"),
    re.compile(rf"業者(?:様|さん)?(?:の|は|から|も|ご)*(?:購入|入札)?(?:は|も)?{_REFUSED}"),
    re.compile(rf"海外(?:から|の方|在住)[^。\n]{{0,12}}?{_REFUSED}"),
)
# Below this many ratings, a single bad one says little.
MIN_RATINGS = 5
MAX_BAD_SHARE = 0.03


def seller_problem(item: dict[str, Any]) -> str | None:
    """Why Neokyo would refuse a Mercari listing, from its details; None when nothing shows."""
    seller = item.get("seller") or {}
    if seller.get("is_blocked") or seller.get("is_inactive"):
        return "compte du vendeur suspendu ou inactif"
    ratings = seller.get("ratings") or {}
    return refusal_in(str(item.get("description") or "")) or ratings_problem(
        int(ratings.get("bad") or 0), int(seller.get("num_ratings") or 0)
    )


def refusal_in(*texts: str) -> str | None:
    """A refusal of proxies in a description or a seller's profile."""
    for text in texts:
        plain = unicodedata.normalize("NFKC", text)
        for pattern in PROXY_REFUSALS:
            if match := pattern.search(plain):
                return f"refuse les achats par un intermédiaire (« {match[0]} »)"
    return None


def ratings_problem(bad: int, total: int) -> str | None:
    if total >= MIN_RATINGS and bad / total > MAX_BAD_SHARE:
        return f"trop d'évaluations négatives ({bad} sur {total})"
    return None


def blocked(session: Session) -> dict[tuple[str, str], str]:
    """Every seller to avoid, by (source, seller id), with why."""
    return {
        (row.source, row.seller_id): row.reason for row in session.scalars(select(BlockedSeller))
    }


def block(session: Session, source: str, seller_id: str, reason: str) -> BlockedSeller:
    row = session.get(BlockedSeller, (source, seller_id))
    if row is None:
        now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        row = BlockedSeller(source=source, seller_id=seller_id, reason=reason, blocked_at=now)
        session.add(row)
    else:
        row.reason = reason
    session.commit()
    return row


def unblock(session: Session, source: str, seller_id: str) -> None:
    session.execute(
        delete(BlockedSeller).where(
            BlockedSeller.source == source, BlockedSeller.seller_id == seller_id
        )
    )
    session.commit()
