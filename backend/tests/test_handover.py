"""Shift Handover from the database (owner decisions 2026-10-10)."""

import uuid

from sqlalchemy import text

from tests.test_companion_commands import _assigned_story, count, fresh, item, tool
from tests.test_demo_slice import code, pick

H = {"X-WorkWeave-Client": "web"}


def k() -> str:
    return str(uuid.uuid4())


def open_handover(client) -> dict:
    r = client.post("/api/handovers/active", headers=H)
    assert r.status_code == 200, r.text
    return r.json()["data"]


def section(w: dict, name: str) -> dict:
    return next(s for s in w["sections"] if s["name"] == name)


def test_the_lead_sees_the_draft_and_suggestions_other_leads_see_published_handovers_members_nothing(client):
    fresh(client, "Alex")  # Afternoon lead
    w = open_handover(client)
    assert w["status"] == "DRAFT" and w["source"]["name"] == "Afternoon" and w["target"]["name"] == "Evening"
    assert len(w["sections"]) == 6 and w["can_configure_template"] and w["draft_sections"]
    assert {s["suggestion_type"] for s in w["suggestions"]} == {"MISSING_ITEM", "STALE_INFORMATION"}
    assert {i["display_id"] for i in w["items"]} == {"Ticket #829", "Ticket #910"} and all(i["section_id"] for i in w["items"])
    assert [p["publication_number"] for p in w["publications"]] == [1] and w["publications"][0]["entries"]
    assert w["copilot"][0]["text"].startswith("The handover companion isn't connected") and not w["can_check"]  # HANDOVER_ENGINE=none in tests
    pick(client, "Dana")  # leads the Evening shift: reads, doesn't edit the Afternoon draft
    m = open_handover(client)
    assert m["draft_sections"] == [] and m["suggestions"] == [] and not m["can_configure_template"]
    for who in ("Jamie", "Morgan"):  # a member; a manager who leads no shift
        pick(client, who)
        r = client.post("/api/handovers/active", headers=H)
        assert r.status_code == 403 and code(r) == "FORBIDDEN" and "shift leads" in r.json()["error"]["message"]


def test_the_receiving_shift_lead_confirms_receipt_once(client, engine):
    ws = fresh(client, "Alex")  # led the Morning shift and leads the Afternoon shift that received #1
    w = open_handover(client)
    pub = w["publications"][0]["publication_id"]
    body = {"idempotency_key": k()}
    first = client.post(f"/api/handover-publications/{pub}/receipt", json=body, headers=H)
    assert first.status_code == 200
    assert client.post(f"/api/handover-publications/{pub}/receipt", json={"idempotency_key": k()}, headers=H).status_code == 200
    assert count(engine, ws, "SELECT count(*) FROM workweave.handover_receipts WHERE workspace_id=:w") == 1
    assert len(first.json()["data"]["publications"][0]["receipts"]) == 1
    pick(client, "Dana")  # another lead, not the receiving one
    assert client.post(f"/api/handover-publications/{pub}/receipt", json={"idempotency_key": k()}, headers=H).status_code == 403


def test_the_lead_edits_accepts_and_publishes_members_cant(client, engine):
    ws = fresh(client, "Alex")
    w = open_handover(client)
    hid = w["handover_id"]
    summary = section(w, "Shift Summary")["section_id"]
    r = client.patch(f"/api/handovers/{hid}/sections/{summary}", json={"idempotency_key": k(), "expected_revision": w["revision"], "content": "Machine #14 still under inspection."}, headers=H)
    assert r.status_code == 200, r.text
    w2 = r.json()["data"]
    assert next(d for d in w2["draft_sections"] if d["section_id"] == summary)["content"] == "Machine #14 still under inspection." and w2["last_change_section_id"] == summary
    stale = client.patch(f"/api/handovers/{hid}/sections/{summary}", json={"idempotency_key": k(), "expected_revision": w["revision"], "content": "x"}, headers=H)
    assert stale.status_code == 409 and code(stale) == "REVISION_CONFLICT"
    missing = next(s for s in w2["suggestions"] if s["suggestion_type"] == "MISSING_ITEM")
    w3 = client.post(f"/api/handover-suggestions/{missing['suggestion_id']}/accept", json={"idempotency_key": k(), "expected_revision": w2["revision"], "handover_id": hid}, headers=H).json()["data"]
    added = next(i for i in w3["items"] if i["title"] == "Upcoming team briefing")
    assert added["section_id"] == section(w3, "Scheduled Activities")["section_id"] and added["evidence_type"] == "REPORTED"
    stale_info = next(s for s in w3["suggestions"] if s["suggestion_type"] == "STALE_INFORMATION")
    bad = client.post(f"/api/handover-suggestions/{stale_info['suggestion_id']}/accept", json={"idempotency_key": k(), "expected_revision": w3["revision"], "handover_id": hid, "mode": "VALIDATE_COMPLETION"}, headers=H)
    assert bad.status_code == 409  # completion comes from the ticket system
    w4 = client.post(f"/api/handover-suggestions/{stale_info['suggestion_id']}/ignore", json={"idempotency_key": k(), "expected_revision": w3["revision"], "handover_id": hid}, headers=H).json()["data"]
    assert all(s["status"] != "PENDING" for s in w4["suggestions"])
    published = client.post(f"/api/handovers/{hid}/publish", json={"idempotency_key": k(), "expected_revision": w4["revision"]}, headers=H)
    assert published.status_code == 200, published.text
    w5 = published.json()["data"]
    assert w5["status"] == "PUBLISHED" and [p["publication_number"] for p in w5["publications"] if p["source_shift_instance_id"] == w5["source"]["shift_instance_id"]] == [1]
    with engine.connect() as c:
        owners = c.execute(text("""SELECT DISTINCT si.shift_instance_id FROM workweave.handover_items i JOIN workweave.shift_instances si ON si.shift_instance_id = i.current_owner_shift_instance_id
                                   WHERE i.workspace_id=:w"""), {"w": ws}).scalars().all()
    assert [str(x) for x in owners] == [w5["target"]["shift_instance_id"]]  # the Evening shift carries the items now
    assert count(engine, ws, "SELECT count(*) FROM workweave.outbox_events WHERE workspace_id=:w AND event_type='handover.published'") >= 1
    again = client.post(f"/api/handovers/{hid}/publish", json={"idempotency_key": k(), "expected_revision": w5["revision"]}, headers=H)
    assert again.status_code == 409  # already published; edit to publish a new version
    pick(client, "Dana")  # leads the receiving shift, not the shift in progress
    denied = client.patch(f"/api/handovers/{hid}/sections/{summary}", json={"idempotency_key": k(), "expected_revision": w5["revision"], "content": "x"}, headers=H)
    assert denied.status_code == 403


def test_a_new_template_version_keeps_the_draft(client):
    fresh(client, "Alex")
    w = open_handover(client)
    rows = [{"section_id": s["section_id"], "name": s["name"], "is_required": s["is_required"]} for s in w["sections"]] + [{"name": "Safety notes", "is_required": False}]
    r = client.post(f"/api/handovers/{w['handover_id']}/template-versions", json={"idempotency_key": k(), "expected_revision": w["revision"], "sections": rows}, headers=H)
    assert r.status_code == 200, r.text
    w2 = r.json()["data"]
    assert w2["template_version"] == "2" and w2["sections"][-1]["name"] == "Safety notes"
    assert len([d for d in w2["draft_sections"] if d["content"]]) == len([d for d in w["draft_sections"] if d["content"]])  # moved to the new sections
    removed = client.post(f"/api/handovers/{w['handover_id']}/template-versions", json={"idempotency_key": k(), "expected_revision": w2["revision"], "sections": rows[1:3]}, headers=H)
    assert removed.status_code == 409


def test_a_ticket_resolved_in_the_ticket_system_asks_the_originating_shift_to_acknowledge(client, engine):
    ws = _assigned_story(client, engine)  # Jamie holds #829 (its handover item came from the Morning shift)
    t = item(client, "Ticket #829")
    assert tool(client, t, "COMPLETED", "Resolved.").status_code == 200
    pick(client, "Alex")  # led the Morning shift too
    w = open_handover(client)
    hi = next(i for i in w["items"] if i["display_id"] == "Ticket #829")
    assert hi["work_status"] == "COMPLETED" and hi["acknowledgement_status"] == "PENDING"
    cyc = next(c for c in w["cycles"] if c["handover_item_id"] == hi["handover_item_id"])
    assert count(engine, ws, "SELECT count(*) FROM workweave.outbox_events WHERE workspace_id=:w AND event_type='handover.ack_requested'") == 1
    empty = client.post(f"/api/handover-acknowledgements/{cyc['completion_cycle_id']}/dispute", json={"idempotency_key": k(), "comment": ""}, headers=H)
    assert empty.status_code == 422 and code(empty) == "MALFORMED_INPUT"
    disputed = client.post(f"/api/handover-acknowledgements/{cyc['completion_cycle_id']}/dispute", json={"idempotency_key": k(), "comment": "Bolt torque wasn't recorded."}, headers=H).json()["data"]
    hi2 = next(i for i in disputed["items"] if i["handover_item_id"] == hi["handover_item_id"])
    assert hi2["acknowledgement_status"] == "DISPUTED" and hi2["work_status"] == "COMPLETED"  # flagged; the ticket system still decides the status
    assert count(engine, ws, "SELECT count(*) FROM workweave.outbox_events WHERE workspace_id=:w AND event_type='handover.completion_disputed'") == 1
    late = client.post(f"/api/handover-acknowledgements/{cyc['completion_cycle_id']}/acknowledge", json={"idempotency_key": k()}, headers=H)
    assert late.status_code == 409  # already answered
    pick(client, "Jamie")
    reopened = tool(client, item(client, "Ticket #829"), "IN_PROGRESS", "Reopened to record the torque.")
    assert reopened.status_code == 200
    resolved = tool(client, item(client, "Ticket #829"), "COMPLETED", "Torque recorded.")
    assert resolved.status_code == 200
    pick(client, "Alex")
    w3 = open_handover(client)
    new_cycle = next(c for c in reversed(w3["cycles"]) if c["handover_item_id"] == hi["handover_item_id"])
    assert new_cycle["completion_cycle_id"] != cyc["completion_cycle_id"] and new_cycle["status"] == "PENDING"
    ok = client.post(f"/api/handover-acknowledgements/{new_cycle['completion_cycle_id']}/acknowledge", json={"idempotency_key": k()}, headers=H).json()["data"]
    assert next(i for i in ok["items"] if i["handover_item_id"] == hi["handover_item_id"])["work_status"] == "CLOSED"


def test_the_copilot_says_it_isnt_connected(client):
    fresh(client, "Alex")
    w = open_handover(client)
    r = client.post(f"/api/handovers/{w['handover_id']}/copilot", json={"idempotency_key": k(), "text": "What's blocked?"}, headers=H)
    assert code(r) == "CAPABILITY_UNAVAILABLE"
