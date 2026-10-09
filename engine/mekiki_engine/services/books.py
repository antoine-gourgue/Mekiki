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

from mekiki_engine.costing.landed_cost import ItemLandedCost
from mekiki_engine.costing.money import percent_to_fraction
from mekiki_engine.domain import SalePlatform
from mekiki_engine.models import Item, Sale
from mekiki_engine.schemas import AppSettings, BooksPeriod, BooksSummary
from mekiki_engine.services import portfolio, sales_import

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
    # The import VAT in the amount is Mekiki's estimate until the carrier invoice is entered,
    # and the amount will change with it.
    vat_estimated: bool = False


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
    """The register of purchases of ``year``, each cost on the day it was paid.

    A card (its price, Japanese shipping and proxy fees) is paid the day its parcel was
    ordered; the parcel's international shipping when it left Japan, its import taxes when it
    arrived. Until those days are known, the order day stands for them. Together the lines
    add up to the cards' full landed costs.
    """
    by_lot: dict[int, list[tuple[Item, ItemLandedCost]]] = {}
    for item, landed in portfolio.costed_items(session, user_id, settings):
        by_lot.setdefault(item.lot_id, []).append((item, landed))
    found = []
    for rows in by_lot.values():
        lot = rows[0][0].lot
        reference = f"Lot {lot.label}"
        ordered = date.fromisoformat(lot.ordered_on or lot.created_at[:10])
        received = date.fromisoformat(lot.received_on) if lot.received_on else ordered
        shipped = date.fromisoformat(lot.shipped_on) if lot.shipped_on else received
        for item, landed in rows:
            source = SOURCE_NAMES.get(item.source_platform, item.source_platform.capitalize())
            found.append(
                Purchase(
                    on=ordered,
                    reference=reference,
                    supplier=f"Neokyo ({source})",
                    description=_card(item),
                    amount_cents=landed.purchase_cents + landed.proxy_fees_cents,
                    payment="Paiement Neokyo",
                )
            )
        cards = "1 carte" if len(rows) == 1 else f"{len(rows)} cartes"
        found.append(
            Purchase(
                on=shipped,
                reference=reference,
                supplier="Neokyo",
                description=f"Envoi international ({cards})",
                amount_cents=sum(landed.shipping_cents for _item, landed in rows),
                payment="Paiement Neokyo",
            )
        )
        carrier = f"Transporteur ({lot.shipping_method})" if lot.shipping_method else "Transporteur"
        found.append(
            Purchase(
                on=received,
                reference=reference,
                supplier=carrier,
                description=f"TVA et frais d'import ({cards})",
                amount_cents=sum(landed.import_taxes_cents for _item, landed in rows),
                payment="Paiement au transporteur",
                vat_estimated=lot.import_vat_cents is None,
            )
        )
    found = [p for p in found if p.on.year == year and p.amount_cents]
    return sorted(found, key=lambda purchase: (purchase.on, purchase.reference))


def summary(
    session: Session, user_id: int, settings: AppSettings, year: int, *, today: date
) -> BooksSummary:
    """Turnover and contributions of each period of ``year``, and the yearly thresholds.

    Each sale counts at the rates frozen when it was recorded, as its margin does: the
    settings of today would rewrite contributions already declared. Sales read from a report
    and still waiting for their card are counted apart: they must be matched before the
    period is declared.

    Nothing is to declare before the business started: the periods begin with the one it
    started in, which also counts the sales dated earlier, and a year before has none.
    """
    business = settings.business
    count = 12 if business.declaration == "monthly" else 4
    first = 0
    started = business.started_on
    if started is not None and started.year >= year:
        first = count if started.year > year else _period_index(started, business.declaration)

    def index_of(day: date) -> int:
        return max(_period_index(day, business.declaration), first)

    # Turnover of each period, by (contribution, income tax) rates.
    by_rates: dict[int, dict[tuple[Decimal, Decimal], int]] = {}
    for item, _landed in portfolio.costed_items(session, user_id, settings):
        sale = item.sale
        if sale is None or date.fromisoformat(sale.sold_on).year != year:
            continue
        rates = frozen_rates(sale, settings)
        period = by_rates.setdefault(index_of(date.fromisoformat(sale.sold_on)), {})
        period[rates] = period.get(rates, 0) + sale.sale_price_cents + sale.shipping_charged_cents
    waiting: dict[int, list[int]] = {}
    for line in sales_import.unmatched(session, user_id):
        if line.sold_on.year == year:
            waiting.setdefault(index_of(line.sold_on), []).append(line.cents)

    periods = []
    for index in range(first, count):
        start, end = _period_bounds(year, index, business.declaration)
        if started is not None and start < started:
            start = started
        due = _due_date(end)
        groups = by_rates.get(index, {})
        turnover = sum(groups.values())
        periods.append(
            BooksPeriod(
                label=_period_label(year, index, business.declaration),
                start=start.isoformat(),
                end=end.isoformat(),
                due_on=due.isoformat(),
                turnover_cents=turnover,
                contributions_cents=sum(_share(cents, rate) for (rate, _), cents in groups.items()),
                income_tax_cents=sum(_share(cents, rate) for (_, rate), cents in groups.items()),
                state="upcoming" if today <= end else ("due" if today <= due else "past"),
                unmatched_count=len(waiting.get(index, [])),
                unmatched_cents=sum(waiting.get(index, [])),
            )
        )
    # Over every sale of the year, a year before the business started included: its sales
    # are not to declare, but they do not vanish from the books.
    groups = [(rates, cents) for period in by_rates.values() for rates, cents in period.items()]
    return BooksSummary(
        year=year,
        declaration=business.declaration,
        periods=periods,
        turnover_cents=sum(cents for _rates, cents in groups),
        contributions_cents=sum(_share(cents, rate) for (rate, _), cents in groups),
        income_tax_cents=sum(_share(cents, rate) for (_, rate), cents in groups),
        turnover_limit_cents=business.turnover_limit_cents,
        vat_franchise_limit_cents=business.vat_franchise_limit_cents,
        next_declaration=next((p for p in periods if p.state == "due"), None),
        unmatched_count=sum(len(cents) for cents in waiting.values()),
        unmatched_cents=sum(sum(cents) for cents in waiting.values()),
    )


def frozen_rates(sale: Sale, settings: AppSettings) -> tuple[Decimal, Decimal]:
    """(URSSAF contributions, flat income tax) rates frozen on the sale."""
    total = Decimal(sale.contribution_rate)
    if sale.income_tax_rate is not None:
        income_tax = Decimal(sale.income_tax_rate)
        return total - income_tax, income_tax
    # Recorded before the two were kept apart: split the frozen total as the settings do.
    contribution = percent_to_fraction(settings.contribution_rate_percent)
    income_tax = percent_to_fraction(settings.income_tax_rate_percent)
    if not contribution + income_tax:
        return total, Decimal(0)
    income_part = total * income_tax / (contribution + income_tax)
    return total - income_part, income_part


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
        (
            "Date",
            "Pièce",
            "Fournisseur",
            "Nature",
            "Montant (€)",
            "Mode de règlement",
            "TVA estimée",
        ),
        [
            (
                p.on,
                p.reference,
                p.supplier,
                p.description,
                _euros(p.amount_cents),
                p.payment,
                "oui" if p.vat_estimated else "",
            )
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
