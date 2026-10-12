"""Handover item sections, on a disposable database."""

import uuid

import pytest
from alembic import command
from sqlalchemy import create_engine, text

from tests import prepare_db


@pytest.fixture()
def scratch():
    name = f"workweave_scratch_{uuid.uuid4().hex[:8]}"
    url = prepare_db.build(name, revision="0011", catalog=False)
    engine = create_engine(url)
    try:
        yield url, engine
    finally:
        engine.dispose()
        prepare_db.drop(name)


def test_upgrade_takes_each_items_latest_published_section_and_downgrade_drops_it(scratch):
    url, engine = scratch
    command.upgrade(prepare_db.alembic_config(url), "0012")
    with engine.connect() as c:
        rows = c.execute(text("""SELECT i.section_id, e.section_id FROM workweave.handover_items i
                                 JOIN workweave.handover_entries e ON e.handover_item_id = i.handover_item_id""")).all()
    assert rows and all(item == entry for item, entry in rows)
    command.downgrade(prepare_db.alembic_config(url), "0011")
    with engine.connect() as c:
        assert not c.execute(text("SELECT 1 FROM information_schema.columns WHERE table_name='handover_items' AND column_name='section_id'")).first()
