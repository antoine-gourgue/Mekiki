# mekiki-engine

Local engine behind Mekiki: a FastAPI + SQLite service listening on `127.0.0.1:18421` that
tracks stock, landed costs and margins of TCG cards imported from Japan.

```bash
uv sync
uv run python -m mekiki_engine                 # http://127.0.0.1:18421, data in ./.data
uv run python -m mekiki_engine --dev           # also lets the Nuxt dev server (port 3000) in
uv run python -m mekiki_engine --port 18500 --data-dir /tmp/mekiki
```

`uv run mekiki-engine` does the same through the console script; on Windows with Smart App
Control enabled, that freshly generated `.exe` launcher may be blocked, `python -m` is not.

Checks run before every push:

```bash
uv run ruff check
uv run ruff format --check
uv run pytest
```

Release sidecar for the desktop app (PyInstaller, one file, copied to
`desktop/src-tauri/binaries/mekiki-engine-<target-triple>`):

```bash
uv sync --group bundle
uv run python scripts/build_sidecar.py
```

Money is stored in minor units only: euro cents (`*_cents`) and yen (`*_jpy`).
