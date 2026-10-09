"""Forward-only SQL migrations, applied at startup.

Migrations live in Python modules rather than ``.sql`` files so the PyInstaller sidecar
bundles them without any data-file configuration.
"""

from __future__ import annotations

from sqlalchemy import Connection, text

from mekiki_engine.migrations import (
    m0001_initial,
    m0002_scanner,
    m0003_favorites,
    m0004_accounts,
    m0005_item_photos,
    m0006_pokemon_species,
    m0007_listing_condition,
    m0008_card_set_names,
    m0009_sale_shipping,
    m0010_blocked_sellers,
    m0011_sales_import,
    m0012_lenient_ratings,
    m0013_accepted_proxies,
    m0014_sale_income_tax_rate,
)

MIGRATIONS: tuple[tuple[int, str], ...] = (
    (1, m0001_initial.SQL),
    (2, m0002_scanner.SQL),
    (3, m0003_favorites.SQL),
    (4, m0004_accounts.SQL),
    (5, m0005_item_photos.SQL),
    (6, m0006_pokemon_species.SQL),
    (7, m0007_listing_condition.SQL),
    (8, m0008_card_set_names.SQL),
    (9, m0009_sale_shipping.SQL),
    (10, m0010_blocked_sellers.SQL),
    (11, m0011_sales_import.SQL),
    (12, m0012_lenient_ratings.SQL),
    (13, m0013_accepted_proxies.SQL),
    (14, m0014_sale_income_tax_rate.SQL),
)


def apply_migrations(connection: Connection) -> list[int]:
    """Apply pending migrations in order and return the versions that ran."""
    connection.exec_driver_sql(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        " version INTEGER PRIMARY KEY,"
        " applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))"
        ")"
    )
    applied = set(connection.execute(text("SELECT version FROM schema_migrations")).scalars())
    ran: list[int] = []
    for version, sql in MIGRATIONS:
        if version in applied:
            continue
        for statement in _split_statements(sql):
            connection.exec_driver_sql(statement)
        connection.execute(
            text("INSERT INTO schema_migrations (version) VALUES (:version)"),
            {"version": version},
        )
        ran.append(version)
    return ran


def _split_statements(sql: str) -> list[str]:
    # The migrations contain no semicolons inside literals or triggers, so a plain split
    # is enough and avoids pulling in an SQL parser.
    return [s.strip() for s in sql.split(";") if s.strip()]
