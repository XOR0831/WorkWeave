"""Shift Handover copilot messages (0016), on a disposable database."""

import uuid

import pytest
from alembic import command
from sqlalchemy import create_engine, text

from tests import prepare_db


@pytest.fixture()
def scratch():
    name = f"workweave_scratch_{uuid.uuid4().hex[:8]}"
    url = prepare_db.build(name, revision="0015", catalog=False)
    engine = create_engine(url)
    try:
        yield url, engine
    finally:
        engine.dispose()
        prepare_db.drop(name)


def test_upgrade_and_downgrade(scratch):
    url, engine = scratch
    command.upgrade(prepare_db.alembic_config(url), "0016")
    with engine.connect() as c:
        assert c.execute(text("SELECT to_regclass('workweave.handover_copilot_messages')")).scalar()
    command.downgrade(prepare_db.alembic_config(url), "0015")
    with engine.connect() as c:
        assert not c.execute(text("SELECT to_regclass('workweave.handover_copilot_messages')")).scalar()
