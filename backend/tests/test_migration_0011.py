"""Persona showcase columns, on a disposable database."""

import uuid

import pytest
from alembic import command
from sqlalchemy import create_engine, text

from tests import prepare_db


@pytest.fixture()
def scratch():
    name = f"workweave_scratch_{uuid.uuid4().hex[:8]}"
    url = prepare_db.build(name, revision="0010", catalog=False)
    engine = create_engine(url)
    try:
        yield url, engine
    finally:
        engine.dispose()
        prepare_db.drop(name)


def columns(engine) -> set[str]:
    with engine.connect() as c:
        return set(c.execute(text("SELECT column_name FROM information_schema.columns WHERE table_schema='workweave' AND table_name='scenario_personas'")).scalars())


def test_upgrade_adds_featured_and_showcase_and_downgrade_removes_them(scratch):
    url, engine = scratch
    assert not {"featured", "showcase"} & columns(engine)
    command.upgrade(prepare_db.alembic_config(url), "0011")
    assert {"featured", "showcase"} <= columns(engine)
    command.downgrade(prepare_db.alembic_config(url), "0010")
    assert not {"featured", "showcase"} & columns(engine)
