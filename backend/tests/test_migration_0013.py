"""Exit KT review fields, on a disposable database."""

import uuid

import pytest
from alembic import command
from sqlalchemy import create_engine, text

from tests import prepare_db

COLUMNS = {("exit_kt_artifact_revisions", "audience"), ("exit_kt_findings", "review_reason"), ("exit_kt_packages", "review_comment"), ("kt_checklist_items", "exception_reason")}


@pytest.fixture()
def scratch():
    name = f"workweave_scratch_{uuid.uuid4().hex[:8]}"
    url = prepare_db.build(name, revision="0012", catalog=False)
    engine = create_engine(url)
    try:
        yield url, engine
    finally:
        engine.dispose()
        prepare_db.drop(name)


def present(engine) -> set:
    with engine.connect() as c:
        return {(t, col) for t, col in c.execute(text("SELECT table_name, column_name FROM information_schema.columns WHERE table_schema='workweave'")).all() if (t, col) in COLUMNS}


def test_upgrade_adds_the_fields_and_existing_revisions_stay_private(scratch):
    url, engine = scratch
    command.upgrade(prepare_db.alembic_config(url), "0013")
    assert present(engine) == COLUMNS
    with engine.connect() as c:
        assert set(c.execute(text("SELECT audience FROM workweave.exit_kt_artifact_revisions")).scalars()) == {"PRIVATE"}
    command.downgrade(prepare_db.alembic_config(url), "0012")
    assert present(engine) == set()
