from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_PORT = 18421
# Loopback by default: on a desktop the engine trusts whoever can reach it, so it never
# listens on the network unless deployed as a server on purpose.
DEFAULT_HOST = "127.0.0.1"
DEFAULT_ALLOWED_HOSTS = ("127.0.0.1", "localhost")
DEFAULT_EBAY_MARKETPLACE = "EBAY_FR"

# Tauri serves the bundled UI from ``tauri://localhost`` on macOS/Linux and from
# ``http://tauri.localhost`` on Windows; the Nuxt dev server runs on port 3000.
DEFAULT_ALLOWED_ORIGINS = (
    "tauri://localhost",
    "http://tauri.localhost",
    "https://tauri.localhost",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
)


@dataclass(frozen=True, slots=True)
class EngineConfig:
    data_dir: Path
    port: int
    allowed_origins: tuple[str, ...]
    # Cardmarket downloads and scheduled scans; tests turn them off to stay offline.
    background_jobs: bool = True
    host: str = DEFAULT_HOST
    # Host headers accepted (see app.py); a server adds its public domain name.
    allowed_hosts: tuple[str, ...] = DEFAULT_ALLOWED_HOSTS
    # Keys of an eBay developer application, for live eBay prices (see resale/ebay.py).
    ebay_client_id: str | None = None
    ebay_client_secret: str | None = None
    ebay_marketplace: str = DEFAULT_EBAY_MARKETPLACE

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.data_dir / 'mekiki.sqlite3'}"


def load_config(
    *,
    data_dir: str | None = None,
    port: int | None = None,
    host: str | None = None,
    background_jobs: bool = True,
) -> EngineConfig:
    """Explicit arguments win over ``MEKIKI_*`` environment variables, then defaults."""
    resolved_dir = Path(data_dir or os.environ.get("MEKIKI_DATA_DIR") or ".data").expanduser()
    resolved_port = port or int(os.environ.get("MEKIKI_ENGINE_PORT", DEFAULT_PORT))
    return EngineConfig(
        data_dir=resolved_dir.resolve(),
        port=resolved_port,
        allowed_origins=DEFAULT_ALLOWED_ORIGINS + _env_list("MEKIKI_ALLOWED_ORIGINS"),
        background_jobs=background_jobs,
        host=host or os.environ.get("MEKIKI_HOST") or DEFAULT_HOST,
        allowed_hosts=DEFAULT_ALLOWED_HOSTS + _env_list("MEKIKI_ALLOWED_HOSTS"),
        ebay_client_id=os.environ.get("MEKIKI_EBAY_CLIENT_ID") or None,
        ebay_client_secret=os.environ.get("MEKIKI_EBAY_CLIENT_SECRET") or None,
        ebay_marketplace=os.environ.get("MEKIKI_EBAY_MARKETPLACE") or DEFAULT_EBAY_MARKETPLACE,
    )


def _env_list(name: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in os.environ.get(name, "").split(",") if item.strip())
