"""Sales read from eBay's orders report, recorded on the cards they sold.

A line is matched to the card whose listing Mekiki published (its eBay item number); a sale
already imported is only brought up to date (shipped, tracking); the other lines wait as
pending sales for the user to name their card, with the likeliest cards first.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from mekiki_engine.domain import SalePlatform
from mekiki_engine.models import Item, Lot, PendingSale, Sale
from mekiki_engine.schemas import (
    AppSettings,
    ImportReport,
    ItemOut,
    PendingSaleOut,
    SaleUpsert,
    SuggestedItem,
)
from mekiki_engine.services import ebay_report, portfolio

# The eBay item number in a listing's address: ".../itm/123456789012", "...?itemId=1234…".
_ITEM_NUMBER = re.compile(r"(?:/itm/(?:[^/?#]+/)?|[?&](?:itemId|ItemID|item)=)(\d{9,15})")
MAX_SUGGESTIONS = 5


def listing_ref(url: str | None) -> str | None:
    match = _ITEM_NUMBER.search(url or "")
    return match[1] if match else None


def import_ebay_report(
    session: Session, user_id: int, settings: AppSettings, text: str
) -> ImportReport:
    report = ebay_report.read_report(text)
    result = ImportReport(
        lines=len(report.lines),
        errors=report.errors,
        headers=report.headers,
        missing_columns=report.missing,
    )
    items = _user_items(session, user_id)
    by_ref = {item.listing_ref: item for item in items if item.listing_ref}
    sales = {
        item.sale.external_ref: item.sale
        for item in items
        if item.sale is not None and item.sale.external_ref
    }
    pending = {
        row.external_ref: row
        for row in session.scalars(select(PendingSale).where(PendingSale.user_id == user_id))
    }
    for line in report.lines:
        sale = sales.get(line.reference)
        if sale is not None:
            if _bring_up_to_date(sale, line):
                result.updated += 1
            continue
        waiting = pending.get(line.reference)
        if waiting is not None:
            waiting.shipped_on = _iso(line.shipped_on) or waiting.shipped_on
            waiting.tracking_number = line.tracking_number or waiting.tracking_number
            continue
        item = by_ref.get(line.item)
        if item is not None and item.sale is None and line.quantity == 1:
            _record(session, user_id, settings, item.id, line)
            # The same line may come twice (overlapping reports joined): booked once.
            assert item.sale is not None
            sales[line.reference] = item.sale
            result.imported += 1
            continue
        row = PendingSale(
            user_id=user_id,
            platform=SalePlatform.EBAY.value,
            external_ref=line.reference,
            listing_ref=line.item,
            title=line.title,
            buyer=line.buyer,
            quantity=line.quantity,
            sold_on=line.sold_on.isoformat(),
            price_cents=line.price_cents,
            shipping_cents=line.shipping_cents,
            shipped_on=_iso(line.shipped_on),
            tracking_number=line.tracking_number,
            created_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
        session.add(row)
        pending[line.reference] = row
        result.pending += 1
    session.commit()
    return result


def list_pending(session: Session, user_id: int) -> list[PendingSaleOut]:
    rows = session.scalars(
        select(PendingSale)
        .where(PendingSale.user_id == user_id, PendingSale.ignored.is_(False))
        .order_by(PendingSale.sold_on.desc())
    )
    unsold = [item for item in _user_items(session, user_id) if item.sale is None]
    return [
        PendingSaleOut(
            id=row.id,
            platform=SalePlatform(row.platform),
            title=row.title,
            buyer=row.buyer,
            quantity=row.quantity,
            sold_on=row.sold_on,
            price_cents=row.price_cents,
            shipping_cents=row.shipping_cents,
            shipped_on=row.shipped_on,
            suggestions=_suggestions(row.title, unsold),
        )
        for row in rows
    ]


def match_pending(
    session: Session, user_id: int, settings: AppSettings, pending_id: int, item_id: int
) -> ItemOut:
    row = _pending(session, user_id, pending_id)
    item = portfolio.get_item(session, user_id, item_id)
    if item.sale is not None:
        raise portfolio.NotFoundError(f"item {item_id} is already sold")
    line = ebay_report.ReportLine(
        order=row.external_ref,
        item=row.listing_ref or "",
        title=row.title,
        buyer=row.buyer,
        quantity=row.quantity,
        price_cents=row.price_cents,
        shipping_cents=row.shipping_cents,
        sold_on=datetime.fromisoformat(row.sold_on).date(),
        shipped_on=datetime.fromisoformat(row.shipped_on).date() if row.shipped_on else None,
        tracking_number=row.tracking_number,
    )
    out = _record(session, user_id, settings, item_id, line, reference=row.external_ref)
    session.delete(row)
    session.commit()
    return out


def ignore_pending(session: Session, user_id: int, pending_id: int) -> None:
    """Kept, marked ignored: importing the same report again must not bring it back."""
    _pending(session, user_id, pending_id).ignored = True
    session.commit()


def count_pending(session: Session, user_id: int) -> tuple[int, str]:
    """How many lines wait, and when the newest came in: ids are reused once a line is matched,
    a moment is not, so a new line always makes a new notification."""
    rows = session.execute(
        select(func.count(), func.max(PendingSale.created_at)).where(
            PendingSale.user_id == user_id, PendingSale.ignored.is_(False)
        )
    ).one()
    return rows[0], rows[1] or ""


def _record(
    session: Session,
    user_id: int,
    settings: AppSettings,
    item_id: int,
    line: ebay_report.ReportLine,
    *,
    reference: str | None = None,
) -> ItemOut:
    note = " · ".join(filter(None, [f"Commande eBay {line.order}", line.buyer]))
    out = portfolio.record_sale(
        session,
        user_id,
        settings,
        item_id,
        SaleUpsert(
            platform=SalePlatform.EBAY,
            sold_on=line.sold_on,
            sale_price_cents=line.price_cents,
            shipping_charged_cents=line.shipping_cents,
            shipped_on=line.shipped_on,
            tracking_number=line.tracking_number,
            notes=note if reference is None else None,
        ),
    )
    item = portfolio.get_item(session, user_id, item_id)
    assert item.sale is not None
    item.sale.external_ref = reference or line.reference
    session.commit()
    return out


def _bring_up_to_date(sale: Sale, line: ebay_report.ReportLine) -> bool:
    changed = False
    if sale.shipped_on is None and line.shipped_on is not None:
        sale.shipped_on = line.shipped_on.isoformat()
        changed = True
    if not sale.tracking_number and line.tracking_number:
        sale.tracking_number = line.tracking_number
        changed = True
    return changed


def _suggestions(title: str, unsold: list[Item]) -> list[SuggestedItem]:
    """The cards the line most likely sold: its number in the title, listed on eBay, its name."""
    plain = title.lower()
    scored = []
    for item in unsold:
        score = 0
        if item.card_number and item.card_number.lower() in plain:
            score += 3
        if item.listing_platform == SalePlatform.EBAY.value:
            score += 2
        score += sum(1 for word in item.name.lower().split() if len(word) >= 3 and word in plain)
        if score:
            scored.append((score, item))
    scored.sort(key=lambda pair: (-pair[0], pair[1].id))
    return [
        SuggestedItem(
            item_id=item.id,
            label=" · ".join(filter(None, [item.name, item.card_number, item.lot.label])),
        )
        for _score, item in scored[:MAX_SUGGESTIONS]
    ]


def _user_items(session: Session, user_id: int) -> list[Item]:
    return list(session.scalars(select(Item).join(Item.lot).where(Lot.user_id == user_id)))


def _pending(session: Session, user_id: int, pending_id: int) -> PendingSale:
    row = session.get(PendingSale, pending_id)
    if row is None or row.user_id != user_id:
        raise portfolio.NotFoundError(f"pending sale {pending_id} not found")
    return row


def _iso(day: object) -> str | None:
    return day.isoformat() if day is not None else None  # type: ignore[attr-defined]
