# mekiki-engine

Local engine behind Mekiki: a FastAPI + SQLite service listening on `127.0.0.1:18421` that
tracks stock, landed costs and margins of TCG cards imported from Japan.

```bash
uv sync
uv run mekiki-engine                 # http://127.0.0.1:18421, data in ./.data
uv run mekiki-engine --port 18500 --data-dir /tmp/mekiki
```

Checks run before every push:

```bash
uv run ruff check
uv run ruff format --check
uv run pytest
```

Money is stored in minor units only: euro cents (`*_cents`) and yen (`*_jpy`).
