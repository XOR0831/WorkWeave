"""The reviewer workspace (ADR-041)."""

import uuid

from tests.test_companion_commands import count, fresh
from tests.test_demo_slice import code, pick

H = {"X-WorkWeave-Client": "web"}


def k() -> str:
    return str(uuid.uuid4())


def submitted_note(client, text: str = "Torque the guard bolts to 12 Nm before restarting #14.", audience: str = "TEAM") -> str:
    d = client.post("/api/memory-drafts", json={"idempotency_key": k(), "content": text, "requested_audience": audience}, headers=H).json()["data"]
    r = client.post(f"/api/memory-drafts/{d['draft_id']}/review", json={"idempotency_key": k(), "expected_revision": d["revision"]}, headers=H)
    assert r.status_code == 200, r.text
    return d["draft_id"]


def queue(client) -> list:
    r = client.get("/api/reviews")
    assert r.status_code == 200, r.text
    return r.json()["data"]


def decide(client, draft_id: str, decision: str, comment: str = ""):
    return client.post(f"/api/memory-drafts/{draft_id}/decision", json={"idempotency_key": k(), "decision": decision, "comment": comment}, headers=H)


def test_a_reviewer_approves_a_note_and_it_becomes_shared_knowledge(client, engine):
    ws = fresh(client, "Jamie")
    did = submitted_note(client)
    assert code(client.get("/api/reviews")) == "FORBIDDEN"  # not a reviewer
    pick(client, "Morgan")
    item = next(x for x in queue(client) if x["kind"] == "MEMORY_DRAFT")
    assert item["submitted_by"] == "Jamie Chen" and item["audience"] == "TEAM" and "12 Nm" in item["content"]
    assert decide(client, did, "APPROVE").status_code == 200
    assert not [x for x in queue(client) if x["kind"] == "MEMORY_DRAFT"]
    assert count(engine, ws, "SELECT count(*) FROM workweave.memory_records WHERE workspace_id=:w AND evidence_type='REPORTED'") == 1
    assert count(engine, ws, "SELECT count(*) FROM workweave.outbox_events WHERE workspace_id=:w AND event_type='knowledge.note_decided'") == 1
    pick(client, "Sam")  # same team: sees the approved team note in Knowledge
    tl = client.get("/api/knowledge/timeline").json()["data"]
    assert any(e["kind"] == "MEMORY_RECORD" and "12 Nm" in e["detail"] for e in tl)
    again = decide(client, did, "REJECT", "late")
    assert again.status_code == 403  # Sam isn't a reviewer


def test_rejecting_needs_a_reason_which_the_author_sees(client):
    fresh(client, "Jamie")
    did = submitted_note(client)
    pick(client, "Morgan")
    assert code(decide(client, did, "REJECT")) == "MALFORMED_INPUT"
    assert decide(client, did, "REJECT", "Cite the SOP section for the torque value.").status_code == 200
    pick(client, "Jamie")
    mine = next(d for d in client.get("/api/memory-drafts").json()["data"] if d["draft_id"] == did)
    assert mine["status"] == "REJECTED" and mine["review_comment"] == "Cite the SOP section for the torque value."


def test_nobody_reviews_their_own_note_and_exit_kt_items_link_to_exit_kt(client):
    fresh(client, "Morgan")
    did = submitted_note(client, "Calibration logs live in the shared QA folder.")
    assert not [x for x in queue(client) if x["review_id"] == did]
    assert decide(client, did, "APPROVE").status_code == 403
    pick(client, "Alex")
    c = client.get("/api/exit-kt/case").json()["data"]
    art = c["artifacts"][0]
    r = client.post(f"/api/exit-kt/artifacts/{art['artifact_id']}/submit", json={"idempotency_key": k(), "expected_revision": c["revision"], "artifact_revision_id": art["current_revision_id"], "audience": "TEAM"}, headers=H)
    assert r.status_code == 200
    pick(client, "Morgan")
    kt = next(x for x in queue(client) if x["kind"] == "KT_ARTIFACT")
    assert kt["submitted_by"] == "Alex Rivera" and kt["href"].startswith("/exit-kt/")
