"""What the account has to do now, gathered from the scans, the stock, the sales and the books.

Each task leads to the page where it is done. Those worth a Windows notification say so, with
a ``key`` that changes when something new comes in (another sale to ship, a new deal), so the
app notifies once per novelty rather than on every check.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from mekiki_engine.domain import ItemStatus, ListingTriage
from mekiki_engine.scanner import service as scanner
from mekiki_engine.schemas import AppSettings, TaskOut
from mekiki_engine.services import books, portfolio, sales_import

# A declaration this close to its deadline is worth a notification.
DECLARATION_WARNING_DAYS = 7


def list_tasks(
    session: Session,
    user_id: int,
    settings: AppSettings,
    *,
    today: date,
    backup_error: str | None = None,
) -> list[TaskOut]:
    tasks: list[TaskOut] = []
    if backup_error:
        tasks.append(
            TaskOut(
                id="backup",
                key=f"backup:{today.isoformat()}",
                title="La sauvegarde du jour a échoué",
                detail=backup_error,
                to="/parametres#sauvegardes",
                tone="error",
                notify=True,
            )
        )

    deals = scanner.list_deals(
        session,
        user_id,
        settings,
        triage=ListingTriage.NEW,
        min_roi_percent=settings.scanner.min_roi_percent,
    )
    if deals:
        best = max(deals, key=lambda deal: deal.sale.roi if deal.sale and deal.sale.roi else 0)
        tasks.append(
            TaskOut(
                id="deals",
                key=f"deals:{max(deal.id for deal in deals)}",
                title=_count(len(deals), "bonne affaire à voir", "bonnes affaires à voir"),
                detail=f"La meilleure : {best.card_name}",
                to="/affaires",
                tone="primary",
                count=len(deals),
                notify=True,
            )
        )

    pending, newest = sales_import.count_pending(session, user_id)
    if pending:
        tasks.append(
            TaskOut(
                id="pending-sales",
                key=f"pending-sales:{newest}",
                title=_count(pending, "vente eBay à rapprocher", "ventes eBay à rapprocher"),
                detail="Importées du rapport eBay : choisissez la carte vendue",
                to="/ventes",
                tone="warning",
                count=pending,
                notify=True,
            )
        )

    business = settings.business
    if business.siret or business.started_on:
        for year in (today.year - 1, today.year):
            summary = books.summary(session, user_id, settings, year, today=today)
            period = summary.next_declaration
            if period is None:
                continue
            days_left = (date.fromisoformat(period.due_on) - today).days
            tasks.append(
                TaskOut(
                    id=f"declaration:{period.start}",
                    key=f"declaration:{period.start}",
                    title=f"Déclarer le chiffre d'affaires : {period.label}",
                    detail=(
                        f"Avant le {_french_date(period.due_on)} · "
                        f"{books.euros(period.turnover_cents)} de chiffre d'affaires"
                    ),
                    to="/compta",
                    tone="warning" if days_left <= DECLARATION_WARNING_DAYS else "info",
                    notify=days_left <= DECLARATION_WARNING_DAYS,
                )
            )

    to_ship = []
    to_list = []
    dormant = 0
    for item, _landed in portfolio.costed_items(session, user_id, settings):
        if item.sale is not None:
            if item.sale.shipped_on is None:
                to_ship.append(item)
            continue
        status = portfolio.item_status(item)
        if status is ItemStatus.IN_STOCK:
            to_list.append(item)
        received = item.lot.received_on
        if (
            status is not ItemStatus.INCOMING
            and received
            and (today - date.fromisoformat(received)).days > portfolio.DORMANT_DAYS
        ):
            dormant += 1
    if to_ship:
        latest = max(to_ship, key=lambda item: item.sale.id)  # type: ignore[union-attr]
        tasks.append(
            TaskOut(
                id="ship",
                key=f"ship:{latest.sale.id}",  # type: ignore[union-attr]
                title=_count(len(to_ship), "vente à expédier", "ventes à expédier"),
                detail=", ".join(item.name for item in to_ship[:3])
                + ("…" if len(to_ship) > 3 else ""),
                to="/ventes",
                tone="warning",
                count=len(to_ship),
                notify=True,
            )
        )

    for lot in portfolio.lots_on_their_way(session, user_id):
        tasks.append(
            TaskOut(
                id=f"receive:{lot.id}",
                key=f"receive:{lot.id}",
                title=f"Réceptionner le lot « {lot.label} »",
                detail=(
                    f"Expédié le {_french_date(lot.shipped_on)}"
                    if lot.shipped_on
                    else "En route depuis le Japon"
                )
                + (f" · suivi {lot.tracking_number}" if lot.tracking_number else ""),
                to=f"/lots/{lot.id}",
                tone="info",
            )
        )

    if to_list:
        tasks.append(
            TaskOut(
                id="list",
                key=f"list:{len(to_list)}",
                title=_count(len(to_list), "carte à mettre en vente", "cartes à mettre en vente"),
                detail="En stock, sans annonce",
                to="/stock",
                tone="info",
                count=len(to_list),
            )
        )
    if dormant:
        tasks.append(
            TaskOut(
                id="dormant",
                key=f"dormant:{dormant}",
                title=_count(dormant, "carte dort en stock", "cartes dorment en stock"),
                detail=f"Depuis plus de {portfolio.DORMANT_DAYS} jours : baissez le prix ou "
                "changez de plateforme",
                to="/stock",
                tone="info",
                count=dormant,
            )
        )
    return tasks


def _count(count: int, one: str, many: str) -> str:
    return f"{count} {one if count == 1 else many}"


def _french_date(iso: str | None) -> str:
    if not iso:
        return ""
    day = date.fromisoformat(iso[:10])
    return day.strftime("%d/%m/%Y")
