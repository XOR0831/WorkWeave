"""Automatic assignment source and match_data, on a disposable database."""

import uuid

import pytest
from alembic import command
from sqlalchemy import create_engine, text

from tests import prepare_db


@pytest.fixture()
def scratch():
    name = f"workweave_scratch_{uuid.uuid4().hex[:8]}"
    url = prepare_db.build(name, revision="0009", catalog=False)
    engine = create_engine(url)
    try:
        yield url, engine
    finally:
        engine.dispose()
        prepare_db.drop(name)


def shape(engine) -> tuple[bool, bool]:
    with engine.connect() as c:
        source = c.execute(text("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname='work_item_assignments_assignment_source_check'")).scalar_one()
        column = c.execute(text("""SELECT count(*) FROM information_schema.columns WHERE table_schema='workweave'
                                   AND table_name='work_item_assignments' AND column_name='match_data'""")).scalar_one() == 1
    return "AUTOMATIC" in source, column


def test_upgrade_adds_automatic_and_match_data_and_downgrade_restores_0009(scratch):
    url, engine = scratch
    assert shape(engine) == (False, False)
    command.upgrade(prepare_db.alembic_config(url), "0010")
    assert shape(engine) == (True, True)
    command.downgrade(prepare_db.alembic_config(url), "0009")
    assert shape(engine) == (False, False)
