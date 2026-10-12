"""Knowledge and history from the database (owner decision 2026-10-10, ADR-040)."""

from sqlalchemy import text

from tests.test_companion_commands import fresh
from tests.test_demo_slice import code, pick
from tests.test_exit_kt import _approved_and_promoted


def data(client, path: str):
    r = client.get(f"/api/knowledge/{path}")
    assert r.status_code == 200, r.text
    return r.json()["data"]


def test_everyone_reads_approved_versions_with_their_history(client):
    fresh(client, "Sam")
    docs = data(client, "documents")
    sop = {d["version"]: d for d in docs if d["document_code"] == "SOP-001"}
    assert sop["3.4"]["temporal_status"] == "CURRENT" and sop["3.3"]["effective_label"] == "Superseded by v3.4"
    assert all(d["approval_status"] == "APPROVED" for d in docs)
    tl = data(client, "timeline")
    assert {e["temporal"] for e in tl if "SOP-001" in e["label"]} >= {"HISTORICAL"}
    body = data(client, f"documents/{sop['3.4']['document_version_id']}")
    assert body["version"]["version"] == "3.4" and body["text"]


def test_unapproved_versions_never_appear(client, engine):
    ws = fresh(client, "Sam")
    with engine.begin() as c:
        doc = c.execute(text("SELECT organization_id, document_id FROM workweave.knowledge_documents WHERE workspace_id=:w AND document_code='SOP-001'"), {"w": ws}).one()
        vid = c.execute(text("""INSERT INTO workweave.knowledge_document_versions (organization_id, workspace_id, document_id, version, content, approval_status)
                                VALUES (:o, :w, :d, '3.5-draft', 'Draft text', 'PENDING_REVIEW') RETURNING document_version_id"""),
                        {"o": doc.organization_id, "w": ws, "d": doc.document_id}).scalar_one()
    assert all(d["version"] != "3.5-draft" for d in data(client, "documents"))
    r = client.get(f"/api/knowledge/documents/{vid}")
    assert r.status_code == 404 and code(r) == "NOT_FOUND"


def test_a_promoted_exit_kt_artifact_shows_as_waiting_for_indexing(client):
    fresh(client, "Alex")
    _approved_and_promoted(client)
    pick(client, "Sam")
    entry = next(e for e in data(client, "timeline") if e["label"] == "KT-001 v1 approved from Exit KT")
    assert entry["kind"] == "KT_PROMOTION" and entry["temporal"] == "PENDING" and "isn't in AI answers yet" in entry["detail"]
