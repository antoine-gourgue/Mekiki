"""The books of a micro-enterprise selling goods: receipts, purchases, URSSAF declarations.

A micro-entrepreneur selling goods must keep a chronological book of receipts and a register
of purchases, and declares their turnover each month or quarter. Mekiki keeps both from the
lots and the sales, counts the turnover of each period with the contributions it will cost,
and watches the yearly thresholds. It never declares anything itself.

The sale date stands for the day the money comes in: platforms pay within days.
"""

from __future__ import annotations

import calendar
import csv
import io
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.orm import Session

from mekiki_engine.costing.money import percent_to_fraction
from mekiki_engine.domain import SalePlatform
from mekiki_engine.schemas import AppSettings, BooksPeriod, BooksSummary
from mekiki_engine.services import portfolio

PLATFORM_NAMES = {
    SalePlatform.CARDMARKET: "Cardmarket",
    SalePlatform.EBAY: "eBay",
    SalePlatform.VINTED: "Vinted",
    SalePlatform.LEBONCOIN: "Leboncoin",
    SalePlatform.OTHER: "Vente directe",
}
SOURCE_NAMES = {
    "mercari": "Mercari",
    "rakuma": "Rakuma",
    "yahoo_auctions": "Yahoo Auctions",
    "yahoo_fleamarket": "Yahoo Fleamarket",
}
MONTHS = (
    "janvier",
    "février",
    "mars",
    "avril",
    "mai",
    "juin",
    "juillet",
    "août",
    "septembre",
    "octobre",
    "novembre",
    "décembre",
)


@dataclass(frozen=True, slots=True)
class Receipt:
    on: date
    reference: str
    customer: str
    description: str
    amount_cents: int
    payment: str


@dataclass(frozen=True, slots=True)
class Purchase:
    on: date
    reference: str
    supplier: str
    description: str
    amount_cents: int
    payment: str


def receipts(session: Session, user_id: int, settings: AppSettings, year: int) -> list[Receipt]:
    """The book of receipts of ``year``, oldest first."""
    found = []
    for item, _landed in portfolio.costed_items(session, user_id, settings):
        sale = item.sale
        if sale is None or date.fromisoformat(sale.sold_on).year != year:
            continue
        platform = PLATFORM_NAMES.get(SalePlatform(sale.platform), sale.platform)
        found.append(
            Receipt(
                on=date.fromisoformat(sale.sold_on),
                reference=f"V-{sale.id:05d}",
                customer=f"Client {platform}",
                description=_card(item),
                amount_cents=sale.sale_price_cents + sale.shipping_charged_cents,
                payment=f"Virement {platform}",
            )
        )
    return sorted(found, key=lambda receipt: (receipt.on, receipt.reference))


def purchases(session: Session, user_id: int, settings: AppSettings, year: int) -> list[Purchase]:
    """The register of purchases of ``year``: each card at its full cost (proxy, shipping,
    import taxes), dated the day its parcel was ordered."""
    found = []
    for item, landed in portfolio.costed_items(session, user_id, settings):
        lot = item.lot
        bought = date.fromisoformat(lot.ordered_on or lot.created_at[:10])
        if bought.year != year:
            continue
        source = SOURCE_NAMES.get(item.source_platform, item.source_platform.capitalize())
        found.append(
            Purchase(
                on=bought,
                reference=f"Lot {lot.label}",
                supplier=f"Neokyo ({source})",
                description=_card(item),
                amount_cents=landed.total_cents,
                payment="Paiement Neokyo",
            )
        )
    return sorted(found, key=lambda purchase: (purchase.on, purchase.reference))


def summary(
    session: Session, user_id: int, settings: AppSettings, year: int, *, today: date
) -> BooksSummary:
    """Turnover and contributions of each period of ``year``, and the yearly thresholds."""
    business = settings.business
    contribution = percent_to_fraction(settings.contribution_rate_percent)
    income_tax = percent_to_fraction(settings.income_tax_rate_percent)
    turnover_by_period: dict[int, int] = {}
    for receipt in receipts(session, user_id, settings, year):
        index = _period_index(receipt.on, business.declaration)
        turnover_by_period[index] = turnover_by_period.get(index, 0) + receipt.amount_cents

    periods = []
    count = 12 if business.declaration == "monthly" else 4
    for index in range(count):
        start, end = _period_bounds(year, index, business.declaration)
        due = _due_date(end)
        turnover = turnover_by_period.get(index, 0)
        periods.append(
            BooksPeriod(
                label=_period_label(year, index, business.declaration),
                start=start.isoformat(),
                end=end.isoformat(),
                due_on=due.isoformat(),
                turnover_cents=turnover,
                contributions_cents=_share(turnover, contribution),
                income_tax_cents=_share(turnover, income_tax),
                state="upcoming" if today <= end else ("due" if today <= due else "past"),
            )
        )
    turnover = sum(period.turnover_cents for period in periods)
    return BooksSummary(
        year=year,
        declaration=business.declaration,
        periods=periods,
        turnover_cents=turnover,
        contributions_cents=sum(period.contributions_cents for period in periods),
        income_tax_cents=sum(period.income_tax_cents for period in periods),
        turnover_limit_cents=business.turnover_limit_cents,
        vat_franchise_limit_cents=business.vat_franchise_limit_cents,
        next_declaration=next((p for p in periods if p.state == "due"), None),
    )


def receipts_csv(rows: list[Receipt]) -> str:
    return _csv(
        ("Date", "Pièce", "Client", "Nature", "Montant encaissé (€)", "Mode de règlement"),
        [
            (r.on, r.reference, r.customer, r.description, _euros(r.amount_cents), r.payment)
            for r in rows
        ],
    )


def purchases_csv(rows: list[Purchase]) -> str:
    return _csv(
        ("Date", "Pièce", "Fournisseur", "Nature", "Montant (€)", "Mode de règlement"),
        [
            (p.on, p.reference, p.supplier, p.description, _euros(p.amount_cents), p.payment)
            for p in rows
        ],
    )


def _card(item: object) -> str:
    name = getattr(item, "name", "")
    number = getattr(item, "card_number", None)
    return f"Carte {name}" + (f" {number}" if number else "")


def _period_index(day: date, declaration: str) -> int:
    return day.month - 1 if declaration == "monthly" else (day.month - 1) // 3


def _period_bounds(year: int, index: int, declaration: str) -> tuple[date, date]:
    first, last = (
        (index + 1, index + 1) if declaration == "monthly" else (3 * index + 1, 3 * index + 3)
    )
    return date(year, first, 1), date(year, last, calendar.monthrange(year, last)[1])


def _period_label(year: int, index: int, declaration: str) -> str:
    if declaration == "monthly":
        return f"{MONTHS[index].capitalize()} {year}"
    return f"{'1er' if index == 0 else f'{index + 1}e'} trimestre {year}"


def _due_date(end: date) -> date:
    """URSSAF wants a period declared by the last day of the month after it ends."""
    year, month = (end.year + 1, 1) if end.month == 12 else (end.year, end.month + 1)
    return date(year, month, calendar.monthrange(year, month)[1])


def _share(cents: int, rate: Decimal) -> int:
    return int((Decimal(cents) * rate).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def _euros(cents: int) -> str:
    """French decimal comma, as Excel in French reads numbers."""
    return f"{cents / 100:.2f}".replace(".", ",")


def euros(cents: int) -> str:
    """12345 → "123,45 €", for sentences."""
    return f"{cents / 100:,.2f}".replace(",", " ").replace(".", ",") + " €"


def _csv(header: tuple[str, ...], rows: list[tuple[object, ...]]) -> str:
    buffer = io.StringIO()
    # Semicolons: Excel in French splits columns on them, not on commas.
    writer = csv.writer(buffer, delimiter=";", lineterminator="\r\n")
    writer.writerow(header)
    for row in rows:
        writer.writerow(
            [value.strftime("%d/%m/%Y") if isinstance(value, date) else value for value in row]
        )
    # The byte order mark tells Excel the file is UTF-8, accents included.
    return "﻿" + buffer.getvalue()
