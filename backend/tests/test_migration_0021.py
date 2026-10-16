"""Fuller Acme and Harbor SOPs (0021): current v1.2, subtopics linked to sections, copied to a visitor's demo."""

import uuid

from alembic import command
from sqlalchemy import create_engine, text

from tests import prepare_db
from tests.test_demo_slice import open_company, pick

CURRENT = """SELECT d.document_code, v.version FROM workweave.knowledge_documents d JOIN workweave.knowledge_document_versions v
             ON v.document_version_id = d.current_version_id WHERE d.document_code IN ('OPS-SOP-001', 'BPO-SOP-001') AND d.workspace_id = ANY(CAST(:w AS uuid[]))"""
# The onboarding tutor's retrieval path (her retrieve_learning_knowledge), without the vector ranking.
TAUGHT = """SELECT s.name, count(c.chunk_id) FROM workweave.curriculum_subtopics s
            JOIN workweave.curriculum_topics t ON t.topic_id = s.topic_id
            LEFT JOIN workweave.curriculum_source_sections css ON css.subtopic_id = s.subtopic_id AND css.relationship_type = 'TEACHES'
            LEFT JOIN workweave.curriculum_sources cs ON cs.curriculum_source_id = css.curriculum_source_id AND cs.relationship_type = 'TEACHES'
            LEFT JOIN workweave.knowledge_document_versions v ON v.document_version_id = cs.document_version_id
                 AND v.approval_status = 'APPROVED' AND v.temporal_status = 'CURRENT'
            LEFT JOIN workweave.knowledge_chunks c ON c.source_section_id = css.section_id AND c.document_version_id = v.document_version_id
                 AND c.embedding IS NOT NULL
            WHERE t.workspace_id = ANY(CAST(:w AS uuid[])) AND t.document_version_id IS NULL GROUP BY s.name"""
BASELINES = ["00000003-0000-4000-8000-000000000002", "00000002-0000-4000-8000-000000000002"]
SUBTOPICS = {"Introduction", "Deployment Process", "Rollback", "Use the approved account guide",
             "Separate customer reports from verified facts", "Escalate without exposing private data"}


def test_upgrade_makes_v12_current_and_links_every_subtopic():
    name = f"workweave_scratch_{uuid.uuid4().hex[:8]}"
    url = prepare_db.build(name, revision="0020", catalog=False)
    eng = create_engine(url)
    try:
        cfg = prepare_db.alembic_config(url)
        with eng.connect() as c:
            assert dict(c.execute(text(CURRENT), {"w": BASELINES}).all()) == {"OPS-SOP-001": "1.1", "BPO-SOP-001": "1.1"}
            assert all(n == 0 for _, n in c.execute(text(TAUGHT), {"w": BASELINES}).all())
            objectives = c.execute(text("SELECT count(*) FROM workweave.learning_objectives")).scalar_one()
        for _ in range(2):  # idempotent, and a downgrade keeps the content
            command.upgrade(cfg, "0021")
            with eng.connect() as c:
                assert dict(c.execute(text(CURRENT), {"w": BASELINES}).all()) == {"OPS-SOP-001": "1.2", "BPO-SOP-001": "1.2"}
                taught = dict(c.execute(text(TAUGHT), {"w": BASELINES}).all())
                assert set(taught) == SUBTOPICS and all(n >= 1 for n in taught.values()), taught
                assert c.execute(text("""SELECT count(*) FROM workweave.knowledge_document_versions WHERE version = '1.1' AND temporal_status = 'SUPERSEDED'
                                         AND workspace_id = ANY(CAST(:w AS uuid[]))"""), {"w": BASELINES}).scalar_one() == 2
                sources = c.execute(text("""SELECT d.document_code || ' ' || v.version FROM workweave.curriculum_sources cs JOIN workweave.knowledge_document_versions v USING (document_version_id)
                                      JOIN workweave.knowledge_documents d ON d.document_id = v.document_id WHERE cs.workspace_id = ANY(CAST(:w AS uuid[]))"""), {"w": BASELINES}).scalars().all()
                assert sorted(sources) == ["BPO-PRC-004 1.0", "BPO-SOP-001 1.2", "OPS-RB-007 1.0", "OPS-SOP-001 1.2"]
                assert c.execute(text("SELECT count(*) FROM workweave.learning_objectives")).scalar_one() == objectives
            command.downgrade(cfg, "0020")
    finally:
        eng.dispose()
        prepare_db.drop(name)


def test_a_fresh_acme_demo_copies_the_taught_sections(client, engine):
    run = open_company(client, "acme", intent="FRESH")
    pick(client, "Sam")
    ov = client.get("/api/onboarding").json()["data"]
    assert [(s["document_code"], s["version"]) for s in ov["source_versions"] if s["document_code"] == "OPS-SOP-001"] == [("OPS-SOP-001", "1.2")]
    with engine.connect() as c:
        taught = dict(c.execute(text(TAUGHT), {"w": [run["workspace_id"]]}).all())
    assert set(taught) == {"Introduction", "Deployment Process", "Rollback"} and all(n >= 1 for n in taught.values()), taught
