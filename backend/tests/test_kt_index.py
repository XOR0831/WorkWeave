"""Indexing of promoted Exit KT knowledge (ADR-053): the backend's KT indexer with a stand-in embedder."""

import pytest
from sqlalchemy import text

from app.integrations import embeddings
from app.services import kt_index
from tests.test_companion_commands import count, fresh
from tests.test_demo_slice import code, pick
from tests.test_exit_kt import _approved_and_promoted, case, ok, post

DIM = 8


def vec(t: str) -> list[float]:
    """A deterministic stand-in vector: texts sharing words point the same way."""
    v = [0.0] * DIM
    for w in t.lower().split():
        v[sum(map(ord, w)) % DIM] += 1.0
    return v


@pytest.fixture()
def embedder():
    calls: list[list[str]] = []

    def fake(texts: list[str]) -> embeddings.Embedded:
        calls.append(texts)
        return embeddings.Embedded("test-embedding", DIM, [vec(t) for t in texts])

    embeddings.install_test_embedder(fake)
    yield calls
    embeddings.install_test_embedder(None)


def failing(texts):
    raise embeddings.EmbeddingFailed("quota")


def promo(engine, ws: str) -> dict:
    with engine.connect() as c:
        return dict(c.execute(text("SELECT * FROM workweave.knowledge_promotions WHERE workspace_id=:w"), {"w": ws}).mappings().one())


def due_now(engine, ws: str) -> None:
    with engine.begin() as c:
        c.execute(text("UPDATE workweave.knowledge_promotions SET index_next_attempt_at=now() WHERE workspace_id=:w"), {"w": ws})


def run_until_idle(ws: str) -> list[str]:
    out = []
    while (r := kt_index.index_once(ws)) is not None:
        out.append(r)
    return out


# The Work Companion graph's guidance search (ai_work_companion.py, search within a document), with
# the joins and filters that decide what it can return.
COMPANION_SEARCH = """
SELECT d.document_code, s.topic_heading AS topic, s.subtopic_heading AS subtopic, c.content
FROM workweave.knowledge_documents AS d
JOIN workweave.knowledge_document_versions AS v ON v.organization_id = d.organization_id AND v.workspace_id = d.workspace_id AND v.document_id = d.document_id
JOIN workweave.knowledge_chunks AS c ON c.organization_id = v.organization_id AND c.workspace_id = v.workspace_id AND c.document_version_id = v.document_version_id
LEFT JOIN workweave.knowledge_sections AS s ON s.organization_id = c.organization_id AND s.workspace_id = c.workspace_id
     AND s.document_version_id = c.document_version_id AND s.section_id = c.source_section_id
JOIN workweave.source_records AS r ON r.organization_id = c.organization_id AND r.workspace_id = c.workspace_id AND r.source_id = c.source_id AND r.source_id = v.source_id
WHERE d.organization_id = :o AND d.workspace_id = :w AND d.document_type = 'KT_ARTIFACT'
  AND d.current_version_id = v.document_version_id AND v.approval_status = 'APPROVED' AND v.temporal_status = 'CURRENT'
  AND r.revoked_at IS NULL AND c.embedding IS NOT NULL
ORDER BY c.embedding <=> CAST(:q AS vector)
"""


def companion_finds(engine, ws: str, question: str) -> list[dict]:
    with engine.connect() as c:
        org = c.execute(text("SELECT organization_id FROM workweave.workspaces WHERE workspace_id=:w"), {"w": ws}).scalar_one()
        return [dict(r) for r in c.execute(text(COMPANION_SEARCH), {"o": org, "w": ws, "q": str(vec(question))}).mappings()]


def test_chunks_keep_lines_whole_and_split_only_what_is_too_long():
    assert kt_index.chunks_of("1. Cite the source version.\n\n2. Keep the cause unknown.\n") == ["1. Cite the source version.\n2. Keep the cause unknown."]
    long_line = " ".join(f"w{i}" for i in range(320))
    pieces = kt_index.chunks_of(f"- short\n{long_line}\n- after")
    assert [len(p.split()) for p in pieces] == [2, 150, 150, 22]  # "- short" alone; the long line in 150-word parts; the rest together
    assert pieces[0] == "- short" and pieces[-1].endswith("- after")
    many = "\n".join(" ".join(["x"] * 100) for _ in range(60))
    assert len(kt_index.chunks_of(many)) == kt_index.MAX_CHUNKS
    assert kt_index.chunks_of(" \n\n ") == []


def test_promoted_knowledge_is_indexed_and_the_companion_search_finds_it(client, engine, embedder):
    ws = fresh(client, "Alex")
    m = _approved_and_promoted(client)
    p = promo(engine, ws)
    assert p["index_status"] == "PENDING"
    with engine.connect() as c:  # promotion gave the version its source record (the searches require one)
        src = c.execute(text("""SELECT r.* FROM workweave.knowledge_document_versions v JOIN workweave.source_records r ON r.source_id=v.source_id
                                WHERE v.document_version_id=:v"""), {"v": p["document_version_id"]}).mappings().one()
    assert (src["source_type"], src["evidence_type"], src["access_partition"], src["revoked_at"]) == ("APPROVED_EXCERPT", "REPORTED", "TEAM", None)
    assert companion_finds(engine, ws, "cite the source version") == []  # not searchable before it's indexed

    assert run_until_idle(ws) == ["ready"]
    p = promo(engine, ws)
    assert p["index_status"] == "READY" and p["indexed_at"] and p["index_error"] is None and p["index_locked_at"] is None
    assert embedder == [["Requesting evidence-based clarification\n\n1. Cite the source version.\n2. Keep the cause unknown."]]
    found = companion_finds(engine, ws, "cite the source version")
    assert found == [{"document_code": "KT-001", "topic": "Requesting evidence-based clarification", "subtopic": "Transferred knowledge",
                      "content": "1. Cite the source version.\n2. Keep the cause unknown."}]
    assert count(engine, ws, "SELECT count(*) FROM workweave.knowledge_chunks WHERE workspace_id=:w AND embedding_model='test-embedding' AND embedding_dimension=8") == 1
    assert ok(client.get("/api/exit-kt/case"))["artifacts"][0]["promotion"]["index_status"] == "READY"
    docs = ok(client.get("/api/knowledge/documents"))
    assert next(d for d in docs if d["document_code"] == "KT-001")["index_status"] == "READY"
    assert run_until_idle(ws) == []  # nothing else is due; READY isn't indexed again
    del m


def test_other_workspaces_never_see_it(client, engine, embedder):
    ws = fresh(client, "Alex")
    _approved_and_promoted(client)
    run_until_idle(ws)
    other = fresh(client, "Alex")  # a second visitor's run of the same company
    assert other != ws and companion_finds(engine, other, "cite the source version") == []
    assert count(engine, other, "SELECT count(*) FROM workweave.knowledge_chunks c JOIN workweave.knowledge_documents d ON d.workspace_id=c.workspace_id WHERE c.workspace_id=:w AND d.document_type='KT_ARTIFACT'") == 0


def test_failures_are_retried_then_failed_and_a_reviewer_can_retry(client, engine):
    ws = fresh(client, "Alex")
    _approved_and_promoted(client)
    embeddings.install_test_embedder(failing)
    try:
        results = []
        for _ in range(kt_index.MAX_ATTEMPTS):
            due_now(engine, ws)
            results += run_until_idle(ws)
        assert results == ["retry"] * (kt_index.MAX_ATTEMPTS - 1) + ["failed"]
    finally:
        embeddings.install_test_embedder(None)
    p = promo(engine, ws)
    assert p["index_status"] == "FAILED" and p["index_attempts"] == kt_index.MAX_ATTEMPTS and p["index_error"] == "Embedding failed: quota"
    m = case(client)  # Morgan, the reviewer
    art = m["artifacts"][0]
    assert art["promotion"]["index_status"] == "FAILED"
    assert "quota" not in str(m)  # the failure summary is for operators only

    pick(client, "Alex")
    a = case(client)
    denied = post(client, f"artifacts/{art['artifact_id']}/retry-indexing", a, artifact_revision_id=art["current_revision_id"])
    assert denied.status_code == 403
    pick(client, "Morgan")
    m = case(client)
    m = ok(post(client, f"artifacts/{art['artifact_id']}/retry-indexing", m, artifact_revision_id=art["current_revision_id"]))
    assert m["artifacts"][0]["promotion"]["index_status"] == "PENDING"
    again = post(client, f"artifacts/{art['artifact_id']}/retry-indexing", m, artifact_revision_id=art["current_revision_id"])
    assert again.status_code == 409 and code(again) == "GUARD_FAILED"  # only a failed index is retried
    embeddings.install_test_embedder(lambda texts: embeddings.Embedded("test-embedding", DIM, [vec(t) for t in texts]))
    try:
        assert run_until_idle(ws) == ["ready"]
    finally:
        embeddings.install_test_embedder(None)
    assert promo(engine, ws)["index_status"] == "READY"
    assert count(engine, ws, "SELECT count(*) FROM workweave.knowledge_promotions WHERE workspace_id=:w") == 1  # retrying never promotes again
    assert count(engine, ws, "SELECT count(*) FROM workweave.audit_events WHERE workspace_id=:w AND action='knowledge_promotion.index_retried'") == 1


def test_a_version_that_is_no_longer_current_is_not_indexed(client, engine, embedder):
    ws = fresh(client, "Alex")
    _approved_and_promoted(client)
    with engine.begin() as c:
        c.execute(text("""UPDATE workweave.knowledge_document_versions SET temporal_status='SUPERSEDED'
                          WHERE document_version_id=(SELECT document_version_id FROM workweave.knowledge_promotions WHERE workspace_id=:w)"""), {"w": ws})
    assert run_until_idle(ws) == ["failed"]
    assert embedder == []  # nothing was embedded
    p = promo(engine, ws)
    assert p["index_status"] == "FAILED" and "no longer the approved current version" in p["index_error"]
    assert count(engine, ws, "SELECT count(*) FROM workweave.knowledge_chunks c JOIN workweave.knowledge_promotions p ON p.document_version_id=c.document_version_id WHERE c.workspace_id=:w") == 0


def test_a_promotion_from_before_the_indexer_fails_with_its_reason(client, engine, embedder):
    """Promotions made before ADR-053 have no source record, and an approved version's source is immutable."""
    ws = fresh(client, "Alex")
    _approved_and_promoted(client)
    with engine.begin() as c:
        c.execute(text("ALTER TABLE workweave.knowledge_document_versions DISABLE TRIGGER approved_document_content"))
        c.execute(text("""UPDATE workweave.knowledge_document_versions SET source_id=NULL
                          WHERE document_version_id=(SELECT document_version_id FROM workweave.knowledge_promotions WHERE workspace_id=:w)"""), {"w": ws})
        c.execute(text("ALTER TABLE workweave.knowledge_document_versions ENABLE TRIGGER approved_document_content"))
    assert run_until_idle(ws) == ["failed"]
    assert embedder == [] and "no source record" in promo(engine, ws)["index_error"]


def test_a_stale_lease_is_taken_over(client, engine, embedder):
    ws = fresh(client, "Alex")
    _approved_and_promoted(client)
    with engine.begin() as c:  # a worker claimed it and stopped
        c.execute(text("UPDATE workweave.knowledge_promotions SET index_locked_at=now(), index_attempts=1 WHERE workspace_id=:w"), {"w": ws})
    assert run_until_idle(ws) == []  # still leased
    with engine.begin() as c:
        c.execute(text("UPDATE workweave.knowledge_promotions SET index_locked_at=now() - interval '10 minutes' WHERE workspace_id=:w"), {"w": ws})
    assert run_until_idle(ws) == ["ready"]
    assert promo(engine, ws)["index_attempts"] == 2
