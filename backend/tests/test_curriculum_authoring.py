"""Creating curricula from uploaded Markdown (owner decisions 2026-10-10, ADR-040).

Her ingestion is replaced by a stand-in that writes what her code writes (document-bound topics
and subtopics, H3 sections and their links, embedded chunks), so no test calls Gemini.
"""

import json
import uuid

import pytest
from sqlalchemy import create_engine, text

from app.config import get_settings
from app.integrations import ingestion
from tests.test_companion_commands import count, fresh
from tests.test_demo_slice import code, pick

H = {"X-WorkWeave-Client": "web"}
DOC = """# Packaging Line Basics

## 1. Line start-up

### 1. Pre-start checks
Check guards and the emergency stop before every start.

### 2. Starting the line
Start at low speed, then ramp up.

## 2. Shutdown

### 1. Normal stop
Stop the feed first, then the conveyor.
"""


def k() -> str:
    return str(uuid.uuid4())


def fake_ingest(document_code: str, curriculum_id: str, workspace_id: str) -> None:
    """What her ingestion stores: per H2 a document-bound topic, per H3 a subtopic, a section, the
    section link and one embedded chunk."""
    e = create_engine(get_settings().url())
    with e.begin() as c:
        v = c.execute(text("""SELECT v.organization_id, v.document_version_id, v.source_id, v.content, cs.curriculum_source_id FROM workweave.knowledge_document_versions v
                              JOIN workweave.knowledge_documents d ON d.document_id=v.document_id AND d.current_version_id=v.document_version_id
                              JOIN workweave.curriculum_sources cs ON cs.document_version_id=v.document_version_id AND cs.curriculum_id=:c
                              WHERE d.workspace_id=:w AND d.document_code=:code AND v.approval_status='APPROVED'"""),
                      {"w": workspace_id, "code": document_code, "c": curriculum_id}).one()
        p = {"o": v.organization_id, "w": workspace_id, "c": curriculum_id, "v": v.document_version_id}
        topic = sub = None
        heading = ""
        ti = si = n = 0
        for line in v.content.splitlines():
            if line.startswith("## "):
                ti, si, heading = ti + 1, 0, line[3:].split(" ", 1)[1]
                topic = c.execute(text("""INSERT INTO workweave.curriculum_topics (organization_id, workspace_id, curriculum_id, document_version_id, name, order_index)
                                          VALUES (:o, :w, :c, :v, :n, :i) RETURNING topic_id"""), {**p, "n": heading, "i": ti}).scalar_one()
            elif line.startswith("### "):
                si += 1
                line = "### " + line[4:].split(" ", 1)[1]
                sub = c.execute(text("INSERT INTO workweave.curriculum_subtopics (organization_id, workspace_id, topic_id, name, order_index) VALUES (:o, :w, :t, :n, :i) RETURNING subtopic_id"),
                                {**p, "t": topic, "n": line[4:], "i": si}).scalar_one()
                sec = c.execute(text("""INSERT INTO workweave.knowledge_sections (organization_id, workspace_id, document_version_id, section_key, topic_heading, subtopic_heading, topic_order_index, subtopic_order_index)
                                        VALUES (:o, :w, :v, :key, :h, :n, :ti, :si) RETURNING section_id"""), {**p, "key": f"h2:{ti}/h3:{si}", "h": heading, "n": line[4:], "ti": ti, "si": si}).scalar_one()
                c.execute(text("""INSERT INTO workweave.curriculum_source_sections (organization_id, workspace_id, curriculum_source_id, curriculum_id, document_version_id, section_id, topic_id, subtopic_id, relationship_type)
                                  VALUES (:o, :w, :cs, :c, :v, :sec, :t, :s, 'TEACHES')"""), {**p, "cs": v.curriculum_source_id, "sec": sec, "t": topic, "s": sub})
                c.execute(text("""INSERT INTO workweave.knowledge_chunks (organization_id, workspace_id, document_version_id, source_id, source_section_id, section_path, heading, content, chunk_index, embedding, embedding_model, embedding_dimension)
                                  VALUES (:o, :w, :v, :src, :sec, CAST(:path AS jsonb), :n, :n, :i, CAST(:emb AS public.vector), 'test-embed', 3)"""),
                          {**p, "src": v.source_id, "sec": sec, "path": json.dumps([heading]), "n": line[4:], "i": n, "emb": json.dumps([0.1, 0.2, 0.3])})
                n += 1
    e.dispose()


@pytest.fixture()
def ingest(monkeypatch):
    calls = []
    monkeypatch.setattr(ingestion, "available", lambda: True)

    def run(*args):
        calls.append(args)
        fake_ingest(*args)

    monkeypatch.setattr(ingestion, "run", run)
    return calls


def detail(client, cid: str) -> dict:
    r = client.get(f"/api/curricula/{cid}")
    assert r.status_code == 200, r.text
    return r.json()["data"]


def create(client) -> dict:
    r = client.post("/api/curricula", json={"idempotency_key": k(), "name": "Packaging Line Basics", "version": "1.0"}, headers=H)
    assert r.status_code == 200, r.text
    return detail(client, r.json()["data"]["curriculum_id"])


def upload(client, c: dict, **over):
    body = {"idempotency_key": k(), "expected_revision": c["revision"], "document_code": "PKG-001", "title": "Packaging line basics", "version": "1.0",
            "filename": "packaging.md", "content": DOC, **over}
    return client.post(f"/api/curricula/{c['curriculum_id']}/sources", json=body, headers=H)


def review(client, c: dict, decision="APPROVED", **over):
    s = c["linked_sources"][0]
    body = {"idempotency_key": k(), "expected_revision": c["revision"], "decision": decision, **over}
    return client.post(f"/api/curricula/{c['curriculum_id']}/sources/{s['curriculum_source_id']}/review", json=body, headers=H)


def test_the_manager_creates_uploads_approves_ingests_and_publishes(client, engine, ingest):
    ws = fresh(client, "Morgan")
    c = create(client)
    assert c["status"] == "DRAFT" and c["can_manage"] and c["topics"] == []
    assert upload(client, c).status_code == 200
    c = detail(client, c["curriculum_id"])
    src = c["linked_sources"][0]
    assert src["approval_status"] == "PENDING_REVIEW" and src["ingestion"] is None
    assert code(review(client, c)) == "MALFORMED_INPUT"  # must confirm the exact version was reviewed
    assert review(client, c, reviewed_exact_version=True).status_code == 200
    assert len(ingest) == 1 and ingest[0][0] == "PKG-001"
    c = detail(client, c["curriculum_id"])
    assert c["linked_sources"][0]["approval_status"] == "APPROVED" and c["linked_sources"][0]["ingestion"]["status"] == "SUCCEEDED"
    assert [t["name"] for t in c["topics"]] == ["Line start-up", "Shutdown"] and sum(len(t["subtopics"]) for t in c["topics"]) == 3
    assert count(engine, ws, "SELECT count(*) FROM workweave.audit_events WHERE workspace_id=:w AND action='knowledge_document_version.approved_by_uploader'") == 1
    early = client.post(f"/api/curricula/{c['curriculum_id']}/publish", json={"idempotency_key": k(), "expected_revision": c["revision"]}, headers=H)
    assert early.status_code == 409 and "objective" in early.json()["error"]["message"]
    for t in c["topics"]:
        for s in t["subtopics"]:
            c = detail(client, c["curriculum_id"])
            r = client.put(f"/api/curricula/{c['curriculum_id']}/subtopics/{s['subtopic_id']}/objective",
                           json={"idempotency_key": k(), "expected_revision": c["revision"], "description": f"Explain {s['name']}.", "assessment_criteria": "States the steps in order."}, headers=H)
            assert r.status_code == 200, r.text
    c = detail(client, c["curriculum_id"])
    assert all(x["passed"] for x in c["readiness"])
    done = client.post(f"/api/curricula/{c['curriculum_id']}/publish", json={"idempotency_key": k(), "expected_revision": c["revision"]}, headers=H)
    assert done.status_code == 200, done.text
    c = detail(client, c["curriculum_id"])
    assert c["status"] == "PUBLISHED" and "readiness" not in c
    pick(client, "Sam")
    sop = next(d for d in client.get("/api/knowledge/documents").json()["data"] if d["document_code"] == "PKG-001")
    assert sop["temporal_status"] == "CURRENT" and sop["index_status"] == "READY"  # now in Knowledge for everyone


def test_failed_ingestion_can_be_retried(client, monkeypatch):
    fresh(client, "Morgan")
    monkeypatch.setattr(ingestion, "available", lambda: True)

    def broken(*args):
        raise ingestion.IngestionFailed("ValueError: No section key for x / y")

    monkeypatch.setattr(ingestion, "run", broken)
    c = create(client)
    upload(client, c)
    c = detail(client, c["curriculum_id"])
    review(client, c, reviewed_exact_version=True)
    c = detail(client, c["curriculum_id"])
    job = c["linked_sources"][0]["ingestion"]
    assert job["status"] == "FAILED" and job["attempts"] == 1
    assert "error was encountered" in job["error_summary"] and "ValueError" not in job["error_summary"]  # no technical detail for people
    with create_engine(get_settings().url()).connect() as conn:  # operators keep the detail
        assert conn.execute(text("SELECT error_summary FROM workweave.knowledge_ingestion_jobs WHERE job_id=:j"), {"j": job["job_id"]}).scalar_one().startswith("ValueError")
    monkeypatch.setattr(ingestion, "run", fake_ingest)
    r = client.post(f"/api/curricula/{c['curriculum_id']}/ingestion-jobs/{job['job_id']}/retry", json={"idempotency_key": k()}, headers=H)
    assert r.status_code == 200, r.text
    job = detail(client, c["curriculum_id"])["linked_sources"][0]["ingestion"]
    assert job["status"] == "SUCCEEDED" and job["attempts"] == 2


def test_uploads_are_checked_and_rejection_unlinks(client, ingest):
    fresh(client, "Morgan")
    c = create(client)
    assert code(upload(client, c, filename="notes.pdf")) == "MALFORMED_INPUT"
    assert "### subtopic" in upload(client, c, content="Just text").json()["error"]["message"]
    unnumbered = upload(client, c, content="## Start-up\n### Checks\nText")
    assert code(unnumbered) == "MALFORMED_INPUT" and "Number every" in unnumbered.json()["error"]["message"]
    assert "already exists" in upload(client, c, document_code="SOP-001", version="3.4").json()["error"]["message"]
    upload(client, c)
    c = detail(client, c["curriculum_id"])
    assert code(review(client, c, decision="REJECTED")) == "MALFORMED_INPUT"
    assert review(client, c, decision="REJECTED", reason="Wrong line.").status_code == 200
    assert detail(client, c["curriculum_id"])["linked_sources"] == [] and ingest == []


def test_only_managers_author(client):
    fresh(client, "Alex")
    r = client.post("/api/curricula", json={"idempotency_key": k(), "name": "X", "version": "1"}, headers=H)
    assert r.status_code == 403
    pick(client, "Morgan")
    pub = next(c for c in client.get("/api/curricula").json()["data"]["curricula"] if c["status"] == "PUBLISHED")
    r = client.post(f"/api/curricula/{pub['curriculum_id']}/sources", json={"idempotency_key": k(), "document_code": "A", "title": "A", "version": "1", "filename": "a.md", "content": DOC}, headers=H)
    assert r.status_code == 409  # published curricula are frozen


def test_without_ingestion_configured_approval_still_works(client, monkeypatch):
    fresh(client, "Morgan")
    monkeypatch.setattr(ingestion, "available", lambda: False)
    c = create(client)
    upload(client, c)
    c = detail(client, c["curriculum_id"])
    review(client, c, reviewed_exact_version=True)
    c = detail(client, c["curriculum_id"])
    assert c["linked_sources"][0]["approval_status"] == "APPROVED" and c["linked_sources"][0]["ingestion"] is None and not c["ingestion_available"]
