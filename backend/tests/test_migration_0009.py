"""Companion transcript table and report update_type, on a disposable database."""

import uuid

import pytest
from alembic import command
from sqlalchemy import create_engine, text

from tests import prepare_db


@pytest.fixture()
def scratch():
    name = f"workweave_scratch_{uuid.uuid4().hex[:8]}"
    url = prepare_db.build(name, revision="0008", catalog=False)
    engine = create_engine(url)
    try:
        yield url, engine
    finally:
        engine.dispose()
        prepare_db.drop(name)


def shape(engine) -> tuple[bool, bool, bool]:
    with engine.connect() as c:
        table = c.execute(text("SELECT to_regclass('workweave.work_session_messages') IS NOT NULL")).scalar_one()
        column = c.execute(text("""SELECT count(*) FROM information_schema.columns WHERE table_schema='workweave'
                                   AND table_name='work_item_reported_updates' AND column_name='update_type'""")).scalar_one() == 1
        check = c.execute(text("SELECT count(*) FROM pg_constraint WHERE conname='work_item_reported_updates_update_type_check'")).scalar_one() == 1
    return table, column, check


def test_upgrade_adds_the_transcript_and_update_type_and_downgrade_keeps_the_column(scratch):
    url, engine = scratch
    with engine.begin() as c:  # the dev database already had the column before 0009
        c.execute(text("ALTER TABLE workweave.work_item_reported_updates ADD COLUMN update_type text"))
    command.upgrade(prepare_db.alembic_config(url), "0009")
    assert shape(engine) == (True, True, True)
    command.downgrade(prepare_db.alembic_config(url), "0008")
    assert shape(engine) == (False, True, False)
    command.upgrade(prepare_db.alembic_config(url), "0009")  # upgrading again over the kept column
    assert shape(engine) == (True, True, True)
