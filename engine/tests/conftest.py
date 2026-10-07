from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mekiki_engine.app import create_app
from mekiki_engine.config import load_config


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    app = create_app(load_config(data_dir=str(tmp_path)))
    # The context manager runs the lifespan, which releases the SQLite file at the end.
    with TestClient(app, base_url="http://127.0.0.1:18421") as test_client:
        yield test_client
