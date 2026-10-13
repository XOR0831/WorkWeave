"""The migration job on disposable databases: fresh -> baseline + Alembic + catalog; rerun is a no-op."""

import uuid

import psycopg
import pytest
from sqlalchemy import create_engine, text

from app.ops import migrate
from tests import prepare_db


@pytest.fixture()
def empty_db():
    name = f"workweave_scratch_{uuid.uuid4().hex[:8]}"
    url = prepare_db.recreate(name)
    with psycopg.connect(prepare_db._plain(url), autocommit=True) as c:
        c.execute("CREATE EXTENSION IF NOT EXISTS vector")  # Cloud SQL: allowed for the default user
    yield url
    prepare_db.drop(name)


def test_fresh_database_gets_baseline_head_and_ready_catalog_and_reruns_are_noops(empty_db):
    logs: list[str] = []
    assert migrate.run(empty_db, activate=True, log=logs.append) == "fresh"
    eng = create_engine(empty_db)
    with eng.connect() as c:
        assert c.execute(text("SELECT version_num FROM workweave.alembic_version")).scalar_one() == "0018"
        assert {r[0]: r[1] for r in c.execute(text("SELECT company_key, status FROM workweave.scenario_catalog"))} == {"northstar": "READY", "acme": "READY", "harbor": "READY"}
        assert c.execute(text("SELECT count(*) FROM workweave.knowledge_chunks WHERE embedding IS NOT NULL")).scalar_one() == 17
        before = c.execute(text("SELECT count(*) FROM workweave.employees")).scalar_one()
    assert any(line.startswith("baseline: 01_schema.sql") for line in logs)
    logs.clear()
    assert migrate.run(empty_db, activate=True, log=logs.append) == "managed"  # second run: no baseline
    assert not any(line.startswith("baseline:") for line in logs)
    with eng.connect() as c:
        assert c.execute(text("SELECT count(*) FROM workweave.employees")).scalar_one() == before
    eng.dispose()


def test_unknown_state_is_refused(empty_db):
    with psycopg.connect(prepare_db._plain(empty_db), autocommit=True) as c:
        c.execute("CREATE SCHEMA workweave")
    with pytest.raises(SystemExit, match="unknown state"):
        migrate.run(empty_db, activate=False)
