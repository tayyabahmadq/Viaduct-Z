"""Test bootstrap.

Environment must be set *before* `app` is imported, because the engine and the
cached Settings are built at import time.
"""

from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path

_DB_PATH = Path(tempfile.gettempdir()) / f"viaduct_test_{uuid.uuid4().hex}.db"

os.environ["DATABASE_URL"] = f"sqlite:///{_DB_PATH.as_posix()}"
os.environ["SEED_ON_START"] = "0"
os.environ["START_BALANCE_CENTS"] = "250000"
os.environ["CREDIT_CEILING_CENTS"] = "500000"
os.environ["RATE_LIMIT_PER_MINUTE"] = "20"
os.environ["PEER_ONLINE_SECONDS"] = "180"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def _register(client: TestClient, name: str) -> dict:
    response = client.post("/api/v1/devices/register", json={"name": name})
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture
def register(client):
    def _factory(name: str = "Alice") -> dict:
        return _register(client, name)

    return _factory


@pytest.fixture
def auth():
    def _header(account: dict) -> dict:
        return {"Authorization": f"Bearer {account['token']}"}

    return _header


@pytest.fixture(scope="session", autouse=True)
def _cleanup_database_file():
    yield
    for suffix in ("", "-wal", "-shm"):
        candidate = Path(str(_DB_PATH) + suffix)
        if candidate.exists():
            try:
                candidate.unlink()
            except OSError:
                pass
