"""Superseded report state, on a disposable database."""

import uuid

import pytest
from alembic import command
from sqlalchemy import create_engine, text

from tests import prepare_db


@pytest.fixture()
def scratch():
    name = f"workweave_scratch_{uuid.uuid4().hex[:8]}"
    url = prepare_db.build(name, revision="0007", catalog=False)
    engine = create_engine(url)
    try:
        yield url, engine
    finally:
        engine.dispose()
        prepare_db.drop(name)


def check(engine) -> str:
    with engine.connect() as c:
        return c.execute(text("""SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname='work_item_reported_updates_source_sync_status_check'""")).scalar_one()


def test_upgrade_allows_superseded_and_downgrade_restores_0007(scratch):
    url, engine = scratch
    assert "SUPERSEDED" not in check(engine)
    command.upgrade(prepare_db.alembic_config(url), "0008")
    assert "SUPERSEDED" in check(engine)
    command.downgrade(prepare_db.alembic_config(url), "0007")
    assert "SUPERSEDED" not in check(engine)
