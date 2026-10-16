"""Acme and Harbor procedures (0020): loaded into the baselines and copied into a visitor's demo."""

import uuid

from alembic import command
from sqlalchemy import create_engine, text

from tests import prepare_db
from tests.test_demo_slice import open_company

EMBEDDED = """SELECT d.document_code, count(c.chunk_id) FROM workweave.knowledge_documents d
              JOIN workweave.knowledge_chunks c ON c.workspace_id = d.workspace_id AND c.document_version_id = d.current_version_id
              WHERE d.workspace_id = ANY(CAST(:w AS uuid[])) AND c.embedding IS NOT NULL GROUP BY 1"""
BASELINES = ["00000003-0000-4000-8000-000000000002", "00000002-0000-4000-8000-000000000002"]
EXPECTED = {"OPS-RB-007": 14, "OPS-SOP-001": 3, "BPO-PRC-004": 9, "BPO-SOP-001": 3}


def test_upgrade_loads_the_procedures_once_and_downgrade_keeps_them():
    name = f"workweave_scratch_{uuid.uuid4().hex[:8]}"
    url = prepare_db.build(name, revision="0019", catalog=False)
    eng = create_engine(url)
    try:
        cfg = prepare_db.alembic_config(url)
        with eng.connect() as c:
            assert dict(c.execute(text(EMBEDDED), {"w": BASELINES}).all()) == {}
        command.upgrade(cfg, "0020")
        with eng.connect() as c:
            assert dict(c.execute(text(EMBEDDED), {"w": BASELINES}).all()) == EXPECTED
            sections = dict(c.execute(text("""SELECT d.document_code, count(*) FROM workweave.knowledge_sections s JOIN workweave.knowledge_documents d
                                              ON d.current_version_id = s.document_version_id GROUP BY 1""")).all())
            assert sections["OPS-RB-007"] == 7 and sections["BPO-PRC-004"] == 5
            # Learning paths unchanged: no topic is bound to the new documents.
            assert c.execute(text("""SELECT count(*) FROM workweave.curriculum_source_sections WHERE document_version_id IN
                                     ('00000003-0000-4000-8000-000000000962', '00000002-0000-4000-8000-000000000962')""")).scalar_one() == 0
        command.downgrade(cfg, "0019")
        command.upgrade(cfg, "0020")
        with eng.connect() as c:
            assert dict(c.execute(text(EMBEDDED), {"w": BASELINES}).all()) == EXPECTED
    finally:
        eng.dispose()
        prepare_db.drop(name)


def test_a_fresh_harbor_demo_gets_its_own_searchable_copy(client, engine):
    run = open_company(client, "harbor", intent="FRESH")
    ws = run["workspace_id"]
    assert ws not in BASELINES
    with engine.connect() as c:
        copied = dict(c.execute(text(EMBEDDED), {"w": [ws]}).all())
    assert copied == {"BPO-PRC-004": 9, "BPO-SOP-001": 14}  # BPO-SOP-001 is v1.2 from 0021
