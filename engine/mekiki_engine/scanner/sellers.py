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
# The words between a proxy and its refusal stay in one clause and never accept it:
# "代行OK、値下げ不可" accepts proxies and refuses discounts. Full-width commas and marks
# end a clause too.
_CLAUSE_ENDS = r"、,。.!?\s" + chr(0xFF0C) + chr(0xFF01) + chr(0xFF1F)
_GAP = rf"(?:(?!OK|ok|Ok|歓迎|大丈夫|可能|いただけ)[^{_CLAUSE_ENDS}]){{0,12}}?"
# Refusals of proxies in a description. "海外発送不可" (no shipping abroad) is no refusal:
# Neokyo buys and receives in Japan. Nor is "配送業者の指定はできません" (no choice of carrier).
PROXY_REFUSALS = (
    re.compile(rf"代行{_GAP}{_REFUSED}"),
    re.compile(rf"転送(?:業者|サービス)?{_GAP}{_REFUSED}"),
    re.compile(rf"業者(?:様|さん)?(?:の|は|から|も|ご)*(?:購入|入札)?(?:は|も)?{_REFUSED}"),
    re.compile(rf"海外(?:から|の方|在住){_GAP}{_REFUSED}"),
)
# Neokyo refuses sellers with "too many bad ratings" without saying how many. A bad rating
# out of 24 is no such seller (Neokyo bought from several): only a share this bad, on this
# many ratings, blocks one; fewer bad ratings are only shown.
MIN_RATINGS = 10
REFUSED_BAD_SHARE = 0.2


def seller_problem(item: dict[str, Any]) -> str | None:
    """Why Neokyo would refuse a Mercari listing, from its details; None when nothing shows."""
    seller = item.get("seller") or {}
    if seller.get("is_blocked") or seller.get("is_inactive"):
        return "compte du vendeur suspendu ou inactif"
    bad, total = mercari_ratings(item)
    return refusal_in(str(item.get("description") or "")) or ratings_problem(bad, total)


def mercari_ratings(item: dict[str, Any]) -> tuple[int, int]:
    """(bad, total) ratings of a Mercari item's seller."""
    seller = item.get("seller") or {}
    ratings = seller.get("ratings") or {}
    return int(ratings.get("bad") or 0), int(seller.get("num_ratings") or 0)


def refusal_in(*texts: str) -> str | None:
    """A refusal of proxies in a description or a seller's profile."""
    for text in texts:
        plain = unicodedata.normalize("NFKC", text)
        for pattern in PROXY_REFUSALS:
            if match := pattern.search(plain):
                return f"refuse les achats par un intermédiaire (« {match[0]} »)"
    return None


def ratings_problem(bad: int, total: int) -> str | None:
    if total >= MIN_RATINGS and bad / total >= REFUSED_BAD_SHARE:
        return f"trop d'évaluations négatives ({bad} sur {total})"
    return None


def ratings_note(bad: int, total: int) -> str | None:
    """The seller's bad ratings, to show, when there are some but not enough to block them."""
    if not bad or ratings_problem(bad, total):
        return None
    plural = "s" if bad > 1 else ""
    return f"{bad} évaluation{plural} négative{plural} sur {total}"


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
