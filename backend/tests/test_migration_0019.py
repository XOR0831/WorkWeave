"""KT promotion indexing columns (0019), on a disposable database."""

import uuid

from alembic import command
from sqlalchemy import create_engine, text

from tests import prepare_db

COLUMNS = """SELECT count(*) FROM information_schema.columns WHERE table_schema='workweave' AND table_name='knowledge_promotions'
             AND column_name IN ('index_attempts', 'index_locked_at', 'index_next_attempt_at', 'index_error', 'indexed_at')"""


def test_upgrade_adds_the_indexing_columns_and_downgrade_removes_them():
    name = f"workweave_scratch_{uuid.uuid4().hex[:8]}"
    url = prepare_db.build(name, revision="0018", catalog=False)
    eng = create_engine(url)
    try:
        cfg = prepare_db.alembic_config(url)
        with eng.connect() as c:
            assert c.execute(text(COLUMNS)).scalar_one() == 0
        command.upgrade(cfg, "0019")
        with eng.connect() as c:
            assert c.execute(text(COLUMNS)).scalar_one() == 5
        command.downgrade(cfg, "0018")
        with eng.connect() as c:
            assert c.execute(text(COLUMNS)).scalar_one() == 0
        command.upgrade(cfg, "0019")
    finally:
        eng.dispose()
        prepare_db.drop(name)
