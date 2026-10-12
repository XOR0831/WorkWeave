"""SOP-001 v3.4 section reconciliation and visitor materialization of sections, links and chunks.

Runs against copies of a read-only dump of the local dev database (see tests/ingestion_db.py).
"""

import uuid
from datetime import UTC, datetime, timedelta

import psycopg
import pytest
from sqlalchemy import create_engine, text

from app.repositories import demo as repo
from tests import ingestion_db, prepare_db

ORG = "00000001-0000-4000-8000-000000000001"
WS = "00000001-0000-4000-8000-000000000002"
EXPECTED = {"Find the current procedure": "h2:1/h3:1", "Separate history from evidence": "h2:1/h3:2", "Ask a clearer question": "h2:1/h3:3"}


@pytest.fixture(scope="session")
def template():
    try:
        ingestion_db.build_template()
    except Exception as e:  # pragma: no cover - environment without the dev stack
        pytest.skip(f"dev database dump unavailable: {e}")
    eng = create_engine(prepare_db._plain(prepare_db.get_settings().url(ingestion_db.TEMPLATE)).replace("postgresql://", "postgresql+psycopg://"))
    with eng.connect() as c:
        n = c.execute(text("SELECT count(*) FROM workweave.knowledge_sections WHERE workspace_id=:w"), {"w": WS}).scalar_one()
    eng.dispose()
    if n != 7:
        pytest.skip(f"dev database doesn't hold the expected SOP-001 v3.4 ingestion output (sections={n})")
    yield
    prepare_db.drop(ingestion_db.TEMPLATE)


@pytest.fixture()
def db(template):
    name, url = ingestion_db.copy_template()
    eng = create_engine(url)
    yield url, eng
    eng.dispose()
    prepare_db.drop(name)


def scalar(eng, sql: str, **p):
    with eng.connect() as c:
        return c.execute(text(sql), p).scalar_one()


def learner_state(eng) -> list:
    with eng.connect() as c:
        return [tuple(r) for r in c.execute(text(
            """SELECT s.name, s.order_index,
                      (SELECT string_agg(lo.description || '|' || lo.criteria_version, ';' ORDER BY lo.objective_id) FROM workweave.learning_objectives lo WHERE lo.subtopic_id = s.subtopic_id),
                      (SELECT string_agg(p.prerequisite_subtopic_id::text, ',' ORDER BY 1) FROM workweave.curriculum_prerequisites p WHERE p.subtopic_id = s.subtopic_id),
                      (SELECT string_agg(pr.status || '@' || pr.revision, ',' ORDER BY pr.progress_id) FROM workweave.employee_learning_progress pr WHERE pr.subtopic_id = s.subtopic_id),
                      s.revision
               FROM workweave.curriculum_subtopics s JOIN workweave.curriculum_topics t ON t.topic_id = s.topic_id
               WHERE t.workspace_id = :w AND t.document_version_id IS NULL ORDER BY s.order_index"""), {"w": WS})]


def legacy_links(eng, ws=WS) -> dict[str, str]:
    with eng.connect() as c:
        return {r.name: r.section_key for r in c.execute(text(
            """SELECT s.name, ks.section_key FROM workweave.curriculum_source_sections css
               JOIN workweave.curriculum_subtopics s ON s.subtopic_id = css.subtopic_id
               JOIN workweave.curriculum_topics t ON t.topic_id = css.topic_id
               JOIN workweave.knowledge_sections ks ON ks.section_id = css.section_id
               WHERE css.workspace_id = :w AND t.document_version_id IS NULL AND css.relationship_type = 'TEACHES'"""), {"w": ws})}


# ---------------------------------------------------------------- reconciliation
def test_reconciliation_links_the_three_learner_subtopics_and_changes_nothing_else(db):
    url, eng = db
    before_state = learner_state(eng)
    before_links = scalar(eng, "SELECT count(*) FROM workweave.curriculum_source_sections WHERE workspace_id=:w", w=WS)
    with eng.connect() as c:
        before_existing = {r[0]: r[1] for r in c.execute(text("SELECT curriculum_source_section_id, revision FROM workweave.curriculum_source_sections WHERE workspace_id=:w"), {"w": WS})}
    assert legacy_links(eng) == {}
    ingestion_db.reconcile(url)
    assert legacy_links(eng) == EXPECTED
    assert learner_state(eng) == before_state  # objectives, prerequisites, progress and revisions untouched
    ingestion_db.reconcile(url)  # idempotent
    after = scalar(eng, "SELECT count(*) FROM workweave.curriculum_source_sections WHERE workspace_id=:w", w=WS)
    assert after == before_links + 3
    with eng.connect() as c:
        existing_now = {r[0]: r[1] for r in c.execute(text("SELECT curriculum_source_section_id, revision FROM workweave.curriculum_source_sections WHERE curriculum_source_section_id = ANY(:ids)"), {"ids": list(before_existing)})}
    assert existing_now == before_existing  # the seven ingestion links still exist, unmodified
    # Reference aids stay source context: no learner subtopic links to them.
    assert scalar(eng, """SELECT count(*) FROM workweave.curriculum_source_sections css JOIN workweave.knowledge_sections ks ON ks.section_id = css.section_id
                          JOIN workweave.curriculum_topics t ON t.topic_id = css.topic_id
                          WHERE css.workspace_id = :w AND ks.topic_heading = 'Reference aids' AND t.document_version_id IS NULL""", w=WS) == 0


def run_reconcile_expecting(url: str, message: str):
    with pytest.raises(psycopg.Error, match=message):
        ingestion_db.reconcile(url)


def test_missing_section_fails_closed(db):
    url, eng = db
    with eng.begin() as c:
        sec = c.execute(text("SELECT section_id FROM workweave.knowledge_sections WHERE workspace_id=:w AND section_key='h2:1/h3:2'"), {"w": WS}).scalar_one()
        c.execute(text("DELETE FROM workweave.knowledge_chunks WHERE source_section_id=:s"), {"s": sec})
        c.execute(text("DELETE FROM workweave.curriculum_source_sections WHERE section_id=:s"), {"s": sec})
        c.execute(text("DELETE FROM workweave.knowledge_sections WHERE section_id=:s"), {"s": sec})
    run_reconcile_expecting(url, "expected 1 section h2:1/h3:2")
    assert legacy_links(eng) == {}  # atomic: the first section's link was rolled back too


def test_missing_embeddings_fail_closed(db):
    url, eng = db
    with eng.begin() as c:
        c.execute(text("""UPDATE workweave.knowledge_chunks SET embedding = NULL, embedding_model = NULL, embedding_dimension = NULL
                          WHERE source_section_id = (SELECT section_id FROM workweave.knowledge_sections WHERE workspace_id=:w AND section_key='h2:1/h3:3')"""), {"w": WS})
    run_reconcile_expecting(url, "section h2:1/h3:3 has no embedded chunk")


def test_ambiguous_learner_subtopic_fails_closed(db):
    url, eng = db
    with eng.begin() as c:
        topic = c.execute(text("SELECT topic_id FROM workweave.curriculum_topics WHERE workspace_id=:w AND name='Machine Fundamentals' AND document_version_id IS NULL"), {"w": WS}).scalar_one()
        dup = c.execute(text("INSERT INTO workweave.curriculum_subtopics (organization_id, workspace_id, topic_id, name, order_index) VALUES (:o, :w, :t, 'Find the current procedure', 9) RETURNING subtopic_id"), {"o": ORG, "w": WS, "t": topic}).scalar_one()
        c.execute(text("INSERT INTO workweave.learning_objectives (organization_id, workspace_id, subtopic_id, description, criteria_version) VALUES (:o, :w, :s, 'Duplicate', 'v1')"), {"o": ORG, "w": WS, "s": dup})
    run_reconcile_expecting(url, 'expected 1 learner subtopic "Find the current procedure" with an objective, found 2')


def test_revoked_source_fails_closed(db):
    url, eng = db
    with eng.begin() as c:
        c.execute(text("""UPDATE workweave.source_records SET revoked_at = now() WHERE source_id = (
                            SELECT v.source_id FROM workweave.knowledge_document_versions v JOIN workweave.knowledge_documents d USING (document_id)
                            WHERE v.workspace_id=:w AND d.document_code='SOP-001' AND v.version='3.4')"""), {"w": WS})
    run_reconcile_expecting(url, "expected 1 approved, current, unrevoked SOP-001 v3.4, found 0")


# ---------------------------------------------------------------- materialization
def materialize(eng) -> tuple[uuid.UUID, uuid.UUID]:
    with eng.begin() as c:
        scenario = next(s for s in repo.ready_catalog(c) if s["company_key"] == "northstar")
        org, ws, ids = repo.materialize_identity(c, scenario, datetime.now(UTC) + timedelta(hours=1))
        repo.materialize_learning(c, scenario, org, ws, ids)
        repo.materialize_knowledge(c, scenario, org, ws, ids)
    return org, ws


def counts(eng, ws) -> dict[str, int]:
    tables = ["curriculum_sources", "knowledge_sections", "curriculum_source_sections", "knowledge_chunks"]
    return {t: scalar(eng, f"SELECT count(*) FROM workweave.{t} WHERE workspace_id=:w", w=str(ws)) for t in tables}


def test_visitor_copy_gets_its_own_sections_links_and_embedded_chunks(db):
    url, eng = db
    ingestion_db.reconcile(url)
    baseline_before = counts(eng, WS)
    org, ws = materialize(eng)
    # The copy mirrors the baseline (since script 15 that includes Machine Fundamentals 1.1 too).
    # Chunks are the exception: only the 17 current v3.4 chunks are copied, never superseded ones.
    copied = counts(eng, ws)
    assert copied["knowledge_chunks"] == 17 and copied["knowledge_sections"] == 7
    assert {k: v for k, v in copied.items() if k != "knowledge_chunks"} == {k: v for k, v in baseline_before.items() if k != "knowledge_chunks"}
    assert counts(eng, WS) == baseline_before  # baseline untouched
    # New IDs everywhere; vectors identical to the baseline ones.
    assert scalar(eng, "SELECT count(*) FROM workweave.knowledge_chunks a JOIN workweave.knowledge_chunks b ON a.chunk_id = b.chunk_id WHERE a.workspace_id=:v AND b.workspace_id=:w", v=str(ws), w=WS) == 0
    assert scalar(eng, """SELECT count(*) FROM workweave.knowledge_chunks v JOIN workweave.knowledge_chunks b
                          ON b.workspace_id = :w AND b.content = v.content AND b.chunk_index = v.chunk_index AND b.embedding = v.embedding
                          AND b.embedding_model = v.embedding_model AND b.embedding_dimension = v.embedding_dimension
                          WHERE v.workspace_id = :v AND v.embedding IS NOT NULL""", v=str(ws), w=WS) == 17
    # The learner path stays the three reviewed subtopics, each linked to its v3.4 section.
    assert legacy_links(eng, str(ws)) == EXPECTED
    assert scalar(eng, "SELECT count(*) FROM workweave.curriculum_subtopics WHERE workspace_id=:v", v=str(ws)) == scalar(eng, "SELECT count(*) FROM workweave.curriculum_subtopics WHERE workspace_id=:w", w=WS)
    with eng.connect() as c:
        subs = [r[0] for r in c.execute(text("SELECT subtopic_id FROM workweave.curriculum_subtopics WHERE workspace_id=:v"), {"v": str(ws)})]
        versions = repo.typed_source_versions(c, org, ws, subs)
        assert [(v["document_code"], v["version"]) for v in versions] == [("SOP-001", "3.4")]  # typed path, no duplicates
        for sub in subs:
            chunks = repo.teaching_chunks(c, org, ws, sub)
            assert chunks and all(ch["embedding_dimension"] == 768 for ch in chunks)


def test_every_copied_reference_stays_inside_the_visitor_workspace(db):
    url, eng = db
    ingestion_db.reconcile(url)
    _, a = materialize(eng)
    _, b = materialize(eng)
    for ws in (a, b):
        crossing = scalar(eng, """
            SELECT
              (SELECT count(*) FROM workweave.knowledge_chunks c LEFT JOIN workweave.knowledge_sections s ON s.section_id = c.source_section_id
                 WHERE c.workspace_id = :w AND c.source_section_id IS NOT NULL AND s.workspace_id IS DISTINCT FROM c.workspace_id)
            + (SELECT count(*) FROM workweave.knowledge_chunks c LEFT JOIN workweave.source_records r ON r.source_id = c.source_id
                 WHERE c.workspace_id = :w AND r.workspace_id IS DISTINCT FROM c.workspace_id)
            + (SELECT count(*) FROM workweave.knowledge_chunks c LEFT JOIN workweave.knowledge_document_versions v ON v.document_version_id = c.document_version_id
                 WHERE c.workspace_id = :w AND v.workspace_id IS DISTINCT FROM c.workspace_id)
            + (SELECT count(*) FROM workweave.knowledge_chunks c LEFT JOIN workweave.knowledge_chunks p ON p.chunk_id = c.parent_chunk_id
                 WHERE c.workspace_id = :w AND c.parent_chunk_id IS NOT NULL AND p.workspace_id IS DISTINCT FROM c.workspace_id)
            + (SELECT count(*) FROM workweave.curriculum_source_sections x
                 LEFT JOIN workweave.knowledge_sections s ON s.section_id = x.section_id
                 LEFT JOIN workweave.curriculum_subtopics st ON st.subtopic_id = x.subtopic_id
                 LEFT JOIN workweave.curriculum_sources cs ON cs.curriculum_source_id = x.curriculum_source_id
                 WHERE x.workspace_id = :w AND (s.workspace_id IS DISTINCT FROM x.workspace_id OR st.workspace_id IS DISTINCT FROM x.workspace_id OR cs.workspace_id IS DISTINCT FROM x.workspace_id))""", w=str(ws))
        assert crossing == 0
    # Neither visitor can read the other's chunks through the scoped retrieval read.
    with eng.connect() as c:
        org_a = c.execute(text("SELECT organization_id FROM workweave.workspaces WHERE workspace_id=:w"), {"w": str(a)}).scalar_one()
        b_sub = c.execute(text("SELECT subtopic_id FROM workweave.curriculum_subtopics WHERE workspace_id=:w LIMIT 1"), {"w": str(b)}).scalar_one()
        assert repo.teaching_chunks(c, org_a, a, b_sub) == []
    with eng.connect() as c:
        ids_a = {r[0] for r in c.execute(text("SELECT chunk_id FROM workweave.knowledge_chunks WHERE workspace_id=:w"), {"w": str(a)})}
        ids_b = {r[0] for r in c.execute(text("SELECT chunk_id FROM workweave.knowledge_chunks WHERE workspace_id=:w"), {"w": str(b)})}
    assert ids_a.isdisjoint(ids_b) and len(ids_a) == len(ids_b) == 17


def test_superseded_v33_chunks_are_never_current_guidance(db):
    url, eng = db
    ingestion_db.reconcile(url)
    assert scalar(eng, """SELECT count(*) FROM workweave.knowledge_chunks c JOIN workweave.knowledge_document_versions v ON v.document_version_id = c.document_version_id
                          WHERE c.workspace_id=:w AND v.version='3.3'""", w=WS) > 0  # the baseline really has v3.3 chunks
    with eng.connect() as c:
        subs = [r[0] for r in c.execute(text("SELECT s.subtopic_id FROM workweave.curriculum_subtopics s JOIN workweave.curriculum_topics t ON t.topic_id=s.topic_id WHERE t.workspace_id=:w AND t.document_version_id IS NULL"), {"w": WS})]
        v34 = c.execute(text("SELECT v.document_version_id FROM workweave.knowledge_document_versions v JOIN workweave.knowledge_documents d USING (document_id) WHERE v.workspace_id=:w AND d.document_code='SOP-001' AND v.version='3.4'"), {"w": WS}).scalar_one()
        for sub in subs:
            got = repo.teaching_chunks(c, ORG, WS, sub)
            # Each learner subtopic resolves only to v3.4 chunks, although legacy mappings also link v3.3.
            assert got and {x["document_version_id"] for x in got} == {v34}
    _, ws = materialize(eng)
    assert scalar(eng, """SELECT count(*) FROM workweave.knowledge_chunks c JOIN workweave.knowledge_document_versions v ON v.document_version_id = c.document_version_id
                          WHERE c.workspace_id=:w AND v.version <> '3.4'""", w=str(ws)) == 0


def test_materialization_fails_closed_on_missing_embeddings(db):
    url, eng = db
    ingestion_db.reconcile(url)
    before = scalar(eng, "SELECT count(*) FROM workweave.workspaces")
    with eng.begin() as c:
        c.execute(text("""UPDATE workweave.knowledge_chunks SET embedding = NULL, embedding_model = NULL, embedding_dimension = NULL
                          WHERE chunk_id = (SELECT chunk_id FROM workweave.knowledge_chunks WHERE workspace_id=:w AND embedding IS NOT NULL LIMIT 1)"""), {"w": WS})
    with pytest.raises(RuntimeError, match="without embeddings"):
        materialize(eng)
    assert scalar(eng, "SELECT count(*) FROM workweave.workspaces") == before  # nothing partial committed


def test_revoked_source_is_not_copied_or_served(db):
    url, eng = db
    ingestion_db.reconcile(url)
    with eng.begin() as c:
        c.execute(text("""UPDATE workweave.source_records SET revoked_at = now() WHERE source_id = (
                            SELECT v.source_id FROM workweave.knowledge_document_versions v JOIN workweave.knowledge_documents d USING (document_id)
                            WHERE v.workspace_id=:w AND d.document_code='SOP-001' AND v.version='3.4')"""), {"w": WS})
    org, ws = materialize(eng)
    assert counts(eng, ws)["knowledge_chunks"] == 0 and counts(eng, ws)["knowledge_sections"] == 0
    with eng.connect() as c:
        subs = [r[0] for r in c.execute(text("SELECT subtopic_id FROM workweave.curriculum_subtopics WHERE workspace_id=:v"), {"v": str(ws)})]
        assert repo.legacy_source_versions(c, org, ws, subs) == []  # the revoked current version isn't offered
        for sub in subs:
            assert repo.teaching_chunks(c, ORG, WS, sub) == []  # nor served from the baseline
