"""eBay's orders report (Seller Hub, downloaded as a CSV file), read line by line.

eBay writes the report in the language of its site and reshuffles its columns now and then:
each column is found by several names, English and French, and whatever is not understood is
reported rather than guessed. The report has no fees: they come from the platform rule in the
settings, as for a sale entered by hand.
"""

from __future__ import annotations

import csv
import io
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date

# Each field and the headers eBay gives it, lowercase, without accents.
COLUMNS = {
    "order": ("order number", "numero de commande", "n° de commande"),
    "buyer": ("buyer username", "pseudo de l'acheteur", "pseudo acheteur", "acheteur"),
    "item": ("item number", "numero de l'objet", "numero d'objet", "n° de l'objet"),
    "title": ("item title", "intitule de l'objet", "titre de l'objet", "titre"),
    "quantity": ("quantity", "quantite"),
    "price": ("sold for", "vendu pour", "prix de vente", "prix unitaire"),
    "shipping": (
        "shipping and handling",
        "livraison et manutention",
        "frais de livraison",
        "frais de port",
    ),
    "sold_on": ("sale date", "date de vente", "date de la vente"),
    "shipped_on": ("shipped on date", "date d'expedition", "date d'envoi"),
    "tracking": ("tracking number", "numero de suivi"),
}
REQUIRED = ("order", "item", "title", "price", "sold_on")

MONTHS = {
    **dict.fromkeys(("jan", "janv", "janvier"), 1),
    **dict.fromkeys(("feb", "fev", "fevr", "fevrier"), 2),
    **dict.fromkeys(("mar", "mars"), 3),
    **dict.fromkeys(("apr", "avr", "avril"), 4),
    **dict.fromkeys(("may", "mai"), 5),
    **dict.fromkeys(("jun", "juin"), 6),
    **dict.fromkeys(("jul", "juil", "juillet"), 7),
    **dict.fromkeys(("aug", "aou", "aout"), 8),
    **dict.fromkeys(("sep", "sept", "septembre"), 9),
    **dict.fromkeys(("oct", "octobre"), 10),
    **dict.fromkeys(("nov", "novembre"), 11),
    **dict.fromkeys(("dec", "decembre"), 12),
}
_ISO = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})")
_NUMERIC = re.compile(r"^(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})\b")
# "Oct-05-26", "Oct 5, 2026"
_MONTH_FIRST = re.compile(r"^([a-z]+)\.?[\s-]+(\d{1,2}),?[\s-]+(\d{2,4})\b")
# "05-oct.-26", "5 oct. 2026"
_DAY_FIRST = re.compile(r"^(\d{1,2})[\s-]+([a-z]+)\.?[\s-]+(\d{2,4})\b")
_FOREIGN_CURRENCY = re.compile(r"\$|£|\b(?:usd|gbp|cad|aud|chf)\b", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class ReportLine:
    order: str
    item: str
    title: str
    buyer: str | None
    quantity: int
    price_cents: int
    shipping_cents: int
    sold_on: date
    shipped_on: date | None
    tracking_number: str | None

    @property
    def reference(self) -> str:
        return f"ebay:{self.order}:{self.item}"


@dataclass(slots=True)
class Report:
    lines: list[ReportLine] = field(default_factory=list)
    # Lines left out, and why, in French for the app.
    errors: list[str] = field(default_factory=list)
    # The headers read, when the required ones were not all found.
    headers: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)


def read_report(text: str) -> Report:
    report = Report()
    rows = list(csv.reader(io.StringIO(text.lstrip("﻿")), delimiter=_delimiter(text)))
    header_index, columns = _find_header(rows)
    if header_index is None:
        first = next((row for row in rows if any(cell.strip() for cell in row)), [])
        report.headers = [cell.strip() for cell in first]
        report.missing = [name for name in REQUIRED if name not in columns]
        return report
    for number, row in enumerate(rows[header_index + 1 :], start=header_index + 2):

        def cell(name: str, row: list[str] = row) -> str:
            index = columns.get(name)
            return row[index].strip() if index is not None and index < len(row) else ""

        order, item = cell("order"), cell("item")
        # Totals of a multi-item order and the closing summary carry no item number.
        if not order or not item or not item.isdigit():
            continue
        price_text = cell("price")
        if _FOREIGN_CURRENCY.search(price_text):
            report.errors.append(f"Ligne {number} : montant hors euros ({price_text}), ignorée.")
            continue
        price = money_cents(price_text)
        sold_on = parse_date(cell("sold_on"))
        if price is None or sold_on is None:
            report.errors.append(f"Ligne {number} : prix ou date de vente illisible, ignorée.")
            continue
        quantity = int(cell("quantity")) if cell("quantity").isdigit() else 1
        report.lines.append(
            ReportLine(
                order=order,
                item=item,
                title=cell("title"),
                buyer=cell("buyer") or None,
                quantity=quantity,
                price_cents=price,
                shipping_cents=money_cents(cell("shipping")) or 0,
                sold_on=sold_on,
                shipped_on=parse_date(cell("shipped_on")),
                tracking_number=cell("tracking") or None,
            )
        )
    return report


def money_cents(text: str) -> int | None:
    """ "EUR 1 234,50", "12,50 €", "12.50" → cents; None when no amount is written."""
    digits = re.sub(r"[^\d,.]", "", text)
    if not re.search(r"\d", digits):
        return None
    decimal_mark = max(digits.rfind(","), digits.rfind("."))
    if decimal_mark != -1 and len(digits) - decimal_mark - 1 in (1, 2):
        whole, cents = digits[:decimal_mark], digits[decimal_mark + 1 :].ljust(2, "0")
    else:
        whole, cents = digits, "00"
    whole = re.sub(r"[,.]", "", whole) or "0"
    return int(whole) * 100 + int(cents)


def parse_date(text: str) -> date | None:
    value = _plain(text)
    try:
        if match := _ISO.match(value):
            return date(int(match[1]), int(match[2]), int(match[3]))
        if match := _NUMERIC.match(value):
            return date(_year(match[3]), int(match[2]), int(match[1]))
        if (match := _MONTH_FIRST.match(value)) and match[1] in MONTHS:
            return date(_year(match[3]), MONTHS[match[1]], int(match[2]))
        if (match := _DAY_FIRST.match(value)) and match[2] in MONTHS:
            return date(_year(match[3]), MONTHS[match[2]], int(match[1]))
    except ValueError:
        return None
    return None


def _year(text: str) -> int:
    return int(text) + 2000 if len(text) == 2 else int(text)


def _plain(text: str) -> str:
    """Lowercase, without accents nor curly apostrophes, which eBay mixes in its headers."""
    decomposed = unicodedata.normalize("NFKD", text.replace(chr(0x2019), "'"))
    stripped = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(stripped.lower().split())


def _delimiter(text: str) -> str:
    sample = text[:4096]
    counts = {mark: sample.count(mark) for mark in (",", ";", "\t")}
    return max(counts, key=lambda mark: counts[mark])


def _find_header(rows: list[list[str]]) -> tuple[int | None, dict[str, int]]:
    """The header row (eBay starts the file with a blank line) and each field's column."""
    best: dict[str, int] = {}
    for index, row in enumerate(rows[:20]):
        found: dict[str, int] = {}
        for column, header in enumerate(row):
            plain = _plain(header)
            for name, labels in COLUMNS.items():
                if name not in found and plain in labels:
                    found[name] = column
        if all(name in found for name in REQUIRED):
            return index, found
        if len(found) > len(best):
            best = found
    return None, best
