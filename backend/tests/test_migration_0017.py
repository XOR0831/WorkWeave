"""Exit KT AI proposals (0017), on a disposable database."""

import uuid

import pytest
from alembic import command
from sqlalchemy import create_engine, text

from tests import prepare_db


@pytest.fixture()
def scratch():
    name = f"workweave_scratch_{uuid.uuid4().hex[:8]}"
    url = prepare_db.build(name, revision="0016", catalog=False)
    engine = create_engine(url)
    try:
        yield url, engine
    finally:
        engine.dispose()
        prepare_db.drop(name)


def cols(engine, table):
    with engine.connect() as c:
        return set(c.execute(text("SELECT column_name FROM information_schema.columns WHERE table_schema='workweave' AND table_name=:t"), {"t": table}).scalars())


def test_upgrade_keeps_existing_checklist_items_accepted_and_downgrade_reverts(scratch):
    url, engine = scratch
    command.upgrade(prepare_db.alembic_config(url), "0017")
    assert {"title", "method", "priority", "completion_criteria", "origin", "proposal_status"} <= cols(engine, "kt_checklist_items")
    with engine.connect() as c:
        assert set(c.execute(text("SELECT proposal_status || '/' || origin FROM workweave.kt_checklist_items")).scalars()) == {"ACCEPTED/SCENARIO"}
        assert c.execute(text("SELECT to_regclass('workweave.exit_kt_copilot_messages')")).scalar()
    command.downgrade(prepare_db.alembic_config(url), "0016")
    assert "proposal_status" not in cols(engine, "kt_checklist_items") and "risk_factors" not in cols(engine, "exit_kt_knowledge_items")
