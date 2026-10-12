"""Ingestion jobs (0014) and note review comments (0015), on a disposable database."""

import uuid

import pytest
from alembic import command
from sqlalchemy import create_engine, text

from tests import prepare_db


@pytest.fixture()
def scratch():
    name = f"workweave_scratch_{uuid.uuid4().hex[:8]}"
    url = prepare_db.build(name, revision="0013", catalog=False)
    engine = create_engine(url)
    try:
        yield url, engine
    finally:
        engine.dispose()
        prepare_db.drop(name)


def test_upgrade_and_downgrade(scratch):
    url, engine = scratch
    command.upgrade(prepare_db.alembic_config(url), "0015")
    with engine.connect() as c:
        assert c.execute(text("SELECT to_regclass('workweave.knowledge_ingestion_jobs')")).scalar()
        assert c.execute(text("SELECT 1 FROM information_schema.columns WHERE table_name='memory_drafts' AND column_name='review_comment'")).first()
    command.downgrade(prepare_db.alembic_config(url), "0013")
    with engine.connect() as c:
        assert not c.execute(text("SELECT to_regclass('workweave.knowledge_ingestion_jobs')")).scalar()
        assert not c.execute(text("SELECT 1 FROM information_schema.columns WHERE table_name='memory_drafts' AND column_name='review_comment'")).first()
