from __future__ import annotations

import os
import tempfile
from collections.abc import Generator
from pathlib import Path

# Test environment must be configured before app modules import settings.
_tmp_uploads = tempfile.mkdtemp(prefix="jobpilot-test-uploads-")
os.environ.setdefault("JOBPILOT_ENV", "test")
os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("REDIS_URL", "redis://localhost:1/9")  # intentionally unreachable
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("UPLOAD_DIR", _tmp_uploads)
os.environ.setdefault("LLM_DRY_RUN", "1")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from app.db import set_engine
from app.models import Base

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture()
def engine():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    set_engine(engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def client(engine) -> Generator[TestClient, None, None]:
    from app.main import app

    with TestClient(app) as c:
        yield c


def register_and_login(client: TestClient, email: str, password: str = "correct horse 9!") -> dict:
    """Create an account, log in, and return auth headers incl. CSRF."""
    r = client.post("/api/auth/register", json={"email": email, "password": password})
    assert r.status_code == 201, r.text
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    csrf = r.json()["csrf_token"]
    return {"x-csrf-token": csrf}
