"""Builds a disposable `workweave_test` database from the reviewed local SQL scripts.

The development database is never touched: tests connect only to workweave_test, which is
dropped and recreated per test session in the same local PostgreSQL container.
"""

import os
import tempfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app import db
from app.config import get_settings
from tests import prepare_db

# Test process only: allows install_test_tutor(). Development and release never set this.
os.environ["WORKWEAVE_ENV"] = "test"
# Never the real tutor engine from src/local/.env: tests install fakes (tests/test_engine_turns.py).
os.environ["TUTOR_ENGINE"] = "none"
os.environ["COMPANION_ENGINE"] = "none"
os.environ["HANDOVER_ENGINE"] = "none"
os.environ["NOTIFICATIONS"] = "none"  # tests install an in-memory inbox where they need one
os.environ["DISPATCHER_IN_PROCESS"] = "false"
os.environ["EXIT_KT_ENGINE"] = "none"
# Tests that need tickets assigned automatically (ADR-035) switch it on themselves.
os.environ["AUTO_ASSIGN_WORK"] = "false"
os.environ["INGESTION_PYTHON"] = ""  # no test runs the real ingestion (Gemini); tests use a stand-in
os.environ["LOCAL_STORAGE_DIR"] = tempfile.mkdtemp(prefix="workweave-storage-")  # uploaded test originals never land in src/local
# Nor real Gemini keys: voice tests use fakes and mocked HTTP; no test may call Gemini.
os.environ["GEMINI_API_KEY"] = ""
os.environ["GEMINI_EVALUATOR_API_KEY"] = ""
get_settings.cache_clear()

@pytest.fixture(scope="session")
def test_url() -> str:
    return prepare_db.build()


@pytest.fixture(scope="session")
def engine(test_url: str):
    eng = create_engine(test_url)
    # Demo caps off for the suite (it opens many runs); test_usage_caps / test_access_codes set their own.
    with eng.begin() as c:
        c.execute(text("UPDATE workweave.demo_usage_limits SET daily_limit = 0"))
    db.get_engine.cache_clear()
    os.environ["DATABASE_URL"] = test_url
    get_settings.cache_clear()
    yield eng
    eng.dispose()


@pytest.fixture()
def client(engine) -> TestClient:
    from app.main import create_app

    return TestClient(create_app(), base_url="http://testserver", headers={"X-WorkWeave-Client": "web"})


@pytest.fixture()
def other_client(engine) -> TestClient:
    """A second, unrelated visitor (separate cookie jar)."""
    from app.main import create_app

    return TestClient(create_app(), base_url="http://testserver", headers={"X-WorkWeave-Client": "web"})
