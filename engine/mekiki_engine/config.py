from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_PORT = 18421

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

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.data_dir / 'mekiki.sqlite3'}"


def load_config(
    *, data_dir: str | None = None, port: int | None = None, background_jobs: bool = True
) -> EngineConfig:
    """Explicit arguments win over ``MEKIKI_*`` environment variables, then defaults."""
    resolved_dir = Path(data_dir or os.environ.get("MEKIKI_DATA_DIR") or ".data").expanduser()
    resolved_port = port or int(os.environ.get("MEKIKI_ENGINE_PORT", DEFAULT_PORT))
    extra_origins = tuple(
        o.strip() for o in os.environ.get("MEKIKI_ALLOWED_ORIGINS", "").split(",") if o.strip()
    )
    return EngineConfig(
        data_dir=resolved_dir.resolve(),
        port=resolved_port,
        allowed_origins=DEFAULT_ALLOWED_ORIGINS + extra_origins,
        background_jobs=background_jobs,
    )
