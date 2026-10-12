"""Work Companion commands: delegation → member report → lead validation, and knowledge notes."""

import uuid

from sqlalchemy import text

from tests.test_demo_slice import code, open_company, pick

H = {"X-WorkWeave-Client": "web"}


def k() -> str:
    return str(uuid.uuid4())


# Baseline script 17 (since 2026-10-13): six pre-assigned sample tickets for the Companion's guidance.
SAMPLE_TICKETS = ("Ticket #934", "Ticket #941", "Ticket #947", "Ticket #952", "Ticket #958", "Ticket #963")


def drop_sample_tickets(ws: str) -> None:
    """Removes the sample tickets from a visitor run, so the original work story (#829, #910 and the
    past tickets) is all that's there."""
    from app.db import transaction

    with transaction() as c:
        ids = "(SELECT work_item_id FROM workweave.work_items WHERE workspace_id=:w AND external_id = ANY(:ext))"
        for t in ("work_item_assignments", "work_item_competency_requirements", "work_events", "handover_items", "delegation_proposal_items"):
            c.execute(text(f"DELETE FROM workweave.{t} WHERE workspace_id=:w AND work_item_id IN {ids}"), {"w": ws, "ext": list(SAMPLE_TICKETS)})
        c.execute(text(f"DELETE FROM workweave.work_items WHERE workspace_id=:w AND work_item_id IN {ids}"), {"w": ws, "ext": list(SAMPLE_TICKETS)})


def fresh(client, who: str, keep_829: bool = False, keep_samples: bool = False) -> str:
    """A new Northstar run as `who`. Since 2026-10-11 the baseline keeps Ticket #829 assigned to Alex
    (seed 20). Most work tests were written for #829 starting unassigned (the seeded delegation
    proposal assigns it), so they get that by default; `keep_829=True` keeps the baseline as shipped.
    The sample tickets (seed 17) are left out unless `keep_samples=True`."""
    ws = open_company(client, "northstar", intent="FRESH")["workspace_id"]
    if not keep_samples:
        drop_sample_tickets(ws)
    if not keep_829:
        from app.db import transaction

        with transaction() as c:
            c.execute(text("""UPDATE workweave.work_item_assignments a SET status='CANCELLED' FROM workweave.work_items i
                              WHERE a.workspace_id=:w AND i.workspace_id=a.workspace_id AND i.work_item_id=a.work_item_id
                                AND i.external_id='Ticket #829' AND a.status='ASSIGNED'"""), {"w": ws})
    pick(client, who)
    return ws


def item(client, ext: str) -> dict:
    return next(i for i in client.get("/api/assignments").json()["data"] if i["external_id"] == ext)


def proposal(client) -> dict:
    return client.get("/api/delegation-proposals").json()["data"][0]


def emp(engine, ws: str, first: str) -> str:
    with engine.connect() as c:
        return str(c.execute(text("SELECT employee_id FROM workweave.employees WHERE workspace_id=:w AND first_name=:f"), {"w": ws, "f": first}).scalar_one())


def count(engine, ws: str, sql: str) -> int:
    with engine.connect() as c:
        return c.execute(text(sql), {"w": ws}).scalar_one()


def confirm(client) -> dict:
    p = proposal(client)
    return client.post(f"/api/delegation-proposals/{p['delegation_proposal_id']}/confirm", json={"idempotency_key": k(), "expected_revision": p["revision"]}, headers=H)


# ---------------------------------------------------------------- delegation
def test_the_lead_sees_the_proposal_with_evidence_and_nothing_is_assigned_yet(client, engine):
    ws = fresh(client, "Alex")
    p = proposal(client)
    assert p["status"] == "PROPOSED" and p["origin"] == "SYNTHETIC_SEED" and len(p["items"]) == 2
    jamie_item = next(i for i in p["items"] if i["recommended_employee_id"] == emp(engine, ws, "Jamie"))
    assert "Declared available now" in jamie_item["evidence"]  # availability moved to "today" with the demo
    assert jamie_item["uncertainty"] and "no validated evidence for" in jamie_item["uncertainty"]  # gaps shown, not hidden
    assert count(engine, ws, "SELECT count(*) FROM workweave.work_item_assignments WHERE workspace_id=:w AND status <> 'CANCELLED' AND coalesce((SELECT metadata->>'historical_only' FROM workweave.work_items wi WHERE wi.work_item_id=work_item_assignments.work_item_id), 'false') <> 'true'") == 0  # past tickets keep their old assignments


def test_only_the_lead_can_see_or_act_on_proposals(client):
    fresh(client, "Sam")
    assert client.get("/api/delegation-proposals").status_code == 403


def test_edit_keeps_the_recommendation_and_confirm_assigns_once(client, engine):
    ws = fresh(client, "Alex")
    p = proposal(client)
    it = p["items"][0]
    sam = emp(engine, ws, "Sam")
    r = client.patch(f"/api/delegation-proposals/{p['delegation_proposal_id']}", json={"idempotency_key": k(), "expected_revision": p["revision"], "work_item_id": it["work_item_id"], "final_employee_id": sam}, headers=H)
    edited = r.json()["data"]
    e_it = next(i for i in edited["items"] if i["work_item_id"] == it["work_item_id"])
    assert edited["status"] == "EDITED" and e_it["final_employee_id"] == sam and e_it["recommended_employee_id"] == it["recommended_employee_id"]
    stale = client.post(f"/api/delegation-proposals/{p['delegation_proposal_id']}/confirm", json={"idempotency_key": k(), "expected_revision": p["revision"]}, headers=H)
    assert stale.status_code == 409 and code(stale) == "REVISION_CONFLICT"  # edited since review
    key = k()
    body = {"idempotency_key": key, "expected_revision": edited["revision"]}
    done = client.post(f"/api/delegation-proposals/{p['delegation_proposal_id']}/confirm", json=body, headers=H)
    assert done.json()["data"]["status"] == "CONFIRMED"
    again = client.post(f"/api/delegation-proposals/{p['delegation_proposal_id']}/confirm", json=body, headers=H)  # retried send
    assert again.status_code == 200 and again.json()["data"]["status"] == "CONFIRMED"
    assert count(engine, ws, "SELECT count(*) FROM workweave.work_item_assignments WHERE workspace_id=:w AND status='ASSIGNED'") == 2
    assert count(engine, ws, "SELECT count(*) FROM workweave.outbox_events WHERE workspace_id=:w AND event_type='work.assigned'") == 2
    assert count(engine, ws, "SELECT count(*) FROM workweave.audit_events WHERE workspace_id=:w AND action='delegation_proposal.confirmed'") == 1
    assert next(x for x in client.get("/api/assignments").json()["data"] if x["work_item_id"] == it["work_item_id"])["assignee_id"] == sam
    late = client.post(f"/api/delegation-proposals/{p['delegation_proposal_id']}/confirm", json={"idempotency_key": k(), "expected_revision": done.json()["data"]["revision"]}, headers=H)
    assert late.status_code == 409 and code(late) == "GUARD_FAILED"  # a confirmed proposal can't run again


def test_confirm_rechecks_work_assigned_meanwhile(client, engine):
    ws = fresh(client, "Alex")
    with engine.begin() as c:  # someone else assigned #829 after the proposal was made
        c.execute(
            text("""INSERT INTO workweave.work_item_assignments (organization_id, workspace_id, work_item_id, employee_id, assignment_source, status, assigned_at)
                    SELECT organization_id, workspace_id, work_item_id, (SELECT employee_id FROM workweave.employees WHERE workspace_id=:w AND first_name='Sam'), 'MANUAL', 'ASSIGNED', now()
                    FROM workweave.work_items WHERE workspace_id=:w AND external_id='Ticket #829'"""),
            {"w": ws},
        )
    r = confirm(client)
    assert r.status_code == 409 and "was assigned since" in r.json()["error"]["message"]
    assert count(engine, ws, "SELECT count(*) FROM workweave.work_item_assignments WHERE workspace_id=:w AND proposal_item_id IS NOT NULL") == 0  # all or nothing


def test_reject_needs_a_reason(client):
    fresh(client, "Alex")
    p = proposal(client)
    url = f"/api/delegation-proposals/{p['delegation_proposal_id']}/reject"
    assert client.post(url, json={"idempotency_key": k(), "expected_revision": p["revision"], "reason": " "}, headers=H).status_code == 422
    assert client.post(url, json={"idempotency_key": k(), "expected_revision": p["revision"], "reason": "Waiting for tooling"}, headers=H).json()["data"]["status"] == "REJECTED"


# ---------------------------------------------------------------- reports vs the ticket system (ADR-033)
def _assigned_story(client, engine) -> str:
    """Alex confirms the seeded proposal (Jamie gets #829, Alex #910); returns the workspace."""
    ws = fresh(client, "Alex")
    assert confirm(client).status_code == 200
    pick(client, "Jamie")
    return ws


def say(client, t: dict, status: str, text_: str = "Note."):
    return client.post(f"/api/work-items/{t['work_item_id']}/reports", json={"idempotency_key": k(), "expected_revision": t["revision"], "reported_status": status, "description": text_}, headers=H)


def tool(client, t: dict, status: str, note: str = ""):
    return client.post(f"/api/ticket-system/items/{t['work_item_id']}/status", json={"idempotency_key": k(), "expected_revision": t["revision"], "status": status, "note": note}, headers=H)


def test_saying_done_never_closes_the_ticket(client, engine):
    ws = _assigned_story(client, engine)
    t = item(client, "Ticket #829")
    rep = say(client, t, "DONE", "Inspection finished.").json()["data"]
    assert rep["sync_status"] == "AWAITING_SOURCE" and rep["reported_status"] == "DONE"
    after = item(client, "Ticket #829")
    assert after["status"] == t["status"] and after["revision"] == t["revision"]  # the real status is untouched
    assert after["report"]["reported_status"] == "DONE" and after["report"]["sync_status"] == "AWAITING_SOURCE"
    d = client.get("/api/work-state").json()["data"]
    assert d["awaiting_sync_count"] == 1 and d["active_count"] == 1  # still open, still reminded (Jamie sees only her own)
    assert d["priorities"][-1] == "Ticket #829 · Machine #14 inspection · reported done, waiting for the ticket system"  # lower priority
    ev = client.get("/api/work-events").json()["data"][0]
    assert ev["source"] == "COMPANION" and ev["evidence_type"] == "REPORTED" and ev["sync_status"] == "AWAITING_SOURCE"
    assert count(engine, ws, "SELECT count(*) FROM workweave.outbox_events WHERE workspace_id=:w AND event_type='work.reported_done'") == 1  # the lead monitors
    assert not any(i["external_id"] == "Ticket #910" for i in client.get("/api/assignments").json()["data"])  # Alex's: not in Jamie's view
    with engine.connect() as c:
        other = str(c.execute(text("SELECT work_item_id FROM workweave.work_items WHERE workspace_id=:w AND external_id='Ticket #910'"), {"w": ws}).scalar_one())
    assert say(client, {"work_item_id": other, "revision": 1}, "DONE").status_code == 404


def test_the_ticket_system_closes_it_and_the_report_matches(client, engine):
    ws = _assigned_story(client, engine)
    t = item(client, "Ticket #829")
    say(client, t, "IN_PROGRESS", "Started.")
    rep = say(client, t, "DONE", "Done.").json()["data"]
    with engine.connect() as c:
        states = c.execute(text("SELECT reported_status, source_sync_status FROM workweave.work_item_reported_updates WHERE workspace_id=:w ORDER BY reported_at"), {"w": ws}).all()
    assert [tuple(x) for x in states] == [("IN_PROGRESS", "MATCHED"), ("DONE", "AWAITING_SOURCE")]  # already in progress: matched at once
    r = tool(client, t, "COMPLETED", "Resolved after inspection.")
    assert r.status_code == 200 and r.json()["data"]["status"] == "COMPLETED"
    assert item(client, "Ticket #829")["report"]["sync_status"] == "MATCHED"
    d = client.get("/api/work-state").json()["data"]
    assert d["active_count"] == 0 and d["awaiting_sync_count"] == 0 and not any("#829" in p for p in d["priorities"])  # closed and gone
    sys_ = client.get("/api/ticket-system").json()["data"]
    t829 = next(i for i in sys_["items"] if i["external_id"] == "Ticket #829")
    assert t829["history"][0]["to_status"] == "COMPLETED" and t829["history"][0]["note"] == "Resolved after inspection."
    assert count(engine, ws, "SELECT count(*) FROM workweave.work_item_assignments WHERE workspace_id=:w AND status='COMPLETED' AND coalesce((SELECT metadata->>'historical_only' FROM workweave.work_items wi WHERE wi.work_item_id=work_item_assignments.work_item_id), 'false') <> 'true'") == 1
    assert rep["reported_update_id"]


def test_a_newer_report_supersedes_and_a_different_close_needs_review(client, engine):
    ws = _assigned_story(client, engine)
    t = item(client, "Ticket #829")
    say(client, t, "DONE", "Done.")
    say(client, t, "BLOCKED", "Actually waiting for a part.")
    assert tool(client, t, "CANCELLED", "Duplicate of another ticket.").status_code == 200
    with engine.connect() as c:
        states = c.execute(text("SELECT reported_status, source_sync_status FROM workweave.work_item_reported_updates WHERE workspace_id=:w ORDER BY reported_at"), {"w": ws}).all()
    assert [tuple(x) for x in states] == [("DONE", "SUPERSEDED"), ("BLOCKED", "NEEDS_REVIEW")]
    assert count(engine, ws, "SELECT count(*) FROM workweave.outbox_events WHERE workspace_id=:w AND event_type='work.report_needs_review'") == 2  # Jamie and the lead on shift
    closed = item(client, "Ticket #829")
    assert say(client, closed, "DONE").status_code == 409  # already closed in the ticket system
    assert tool(client, closed, "COMPLETED").status_code == 409  # reopen first
    assert tool(client, closed, "IN_PROGRESS", "Reopened").json()["data"]["status"] == "IN_PROGRESS"


def test_only_the_assignee_changes_a_ticket_in_the_tool(client, engine):
    _assigned_story(client, engine)
    pick(client, "Alex")  # the lead monitors; #829 is Jamie's
    t = item(client, "Ticket #829")
    assert tool(client, t, "COMPLETED").status_code == 403
    view = client.get("/api/ticket-system").json()["data"]
    assert view["system_name"] == "Northstar Manufacturing ticket system"
    flags = {i["external_id"]: i["can_update"] for i in view["items"]}
    assert flags == {"Ticket #829": False, "Ticket #910": True, "Ticket #492": False, "Ticket #431": False, "Ticket #458": False, "Ticket #476": False, "Ticket #487": False}
    # Past records are read-only, even for the employee who held them (docs/32).
    past = next(i for i in view["items"] if i["external_id"] == "Ticket #431")
    r = client.post(f"/api/ticket-system/items/{past['work_item_id']}/status", json={"idempotency_key": k(), "status": "IN_PROGRESS"}, headers=H)
    assert r.status_code == 409 and "historical record" in r.json()["error"]["message"]
    stale = client.post(f"/api/ticket-system/items/{item(client, 'Ticket #910')['work_item_id']}/status", json={"idempotency_key": k(), "expected_revision": 99, "status": "BLOCKED"}, headers=H)
    assert stale.status_code == 409 and code(stale) == "REVISION_CONFLICT"


def test_unassigned_tickets_cant_be_changed_until_delegated(client, engine):
    ws = fresh(client, "Jamie")
    assert client.get("/api/assignments").json()["data"] == []  # unassigned tickets are the lead's to see
    with engine.connect() as c:
        t = {"work_item_id": str(c.execute(text("SELECT work_item_id FROM workweave.work_items WHERE workspace_id=:w AND external_id='Ticket #829'"), {"w": ws}).scalar_one()), "revision": 1}
    assert tool(client, t, "COMPLETED").status_code == 404
    assert say(client, t, "DONE").status_code == 404


def test_every_company_has_its_ticket_system(client):
    for company, lead, name in (("harbor", "Leo", "case system"), ("acme", "Alex", "incident system")):
        open_company(client, company, intent="FRESH")
        pick(client, lead)
        view = client.get("/api/ticket-system").json()["data"]
        assert view["system_name"].endswith(name) and view["items"]
        p = proposal(client)
        assert client.post(f"/api/delegation-proposals/{p['delegation_proposal_id']}/confirm", json={"idempotency_key": k(), "expected_revision": p["revision"]}, headers=H).status_code == 200
        mine = [i for i in client.get("/api/ticket-system").json()["data"]["items"] if i["can_update"]]
        if mine:  # the lead was given one of the items
            t = mine[0]
            assert say(client, t, "DONE").json()["data"]["sync_status"] == "AWAITING_SOURCE"
            assert tool(client, t, "COMPLETED").status_code == 200
            assert next(i for i in client.get("/api/assignments").json()["data"] if i["work_item_id"] == t["work_item_id"])["report"]["sync_status"] == "MATCHED"


# ---------------------------------------------------------------- knowledge notes
def test_notes_are_private_drafts_until_submitted(client, other_client, engine):
    ws = fresh(client, "Jamie")
    d = client.post("/api/memory-drafts", json={"idempotency_key": k(), "content": "Check the mounting bolts first.", "requested_audience": "PRIVATE"}, headers=H).json()["data"]
    assert d["status"] == "DRAFT" and d["evidence_type"] == "REPORTED" and d["requested_audience"] == "PRIVATE"
    sub = client.post(f"/api/memory-drafts/{d['draft_id']}/review", json={"idempotency_key": k(), "expected_revision": d["revision"]}, headers=H)
    assert sub.status_code == 409 and "private note" in sub.json()["error"]["message"]
    t = client.post("/api/memory-drafts", json={"idempotency_key": k(), "content": "Torque values are on the card.", "requested_audience": "TEAM"}, headers=H).json()["data"]
    s = client.post(f"/api/memory-drafts/{t['draft_id']}/review", json={"idempotency_key": k(), "expected_revision": t["revision"]}, headers=H).json()["data"]
    assert s["status"] == "PENDING_REVIEW"
    assert count(engine, ws, "SELECT count(*) FROM workweave.outbox_events WHERE workspace_id=:w AND event_type='knowledge.note_awaiting_review' AND payload = '{}'::jsonb") == 1  # no content in the notice
    assert client.delete(f"/api/memory-drafts/{t['draft_id']}", params={"idempotency_key": k()}, headers=H).status_code == 409
    assert client.delete(f"/api/memory-drafts/{d['draft_id']}", params={"idempotency_key": k()}, headers=H).json()["data"] == {"deleted": True}
    assert [x["draft_id"] for x in client.get("/api/memory-drafts").json()["data"]] == [t["draft_id"]]
    pick(client, "Sam")  # another persona never sees them
    assert client.get("/api/memory-drafts").json()["data"] == []


# ---------------------------------------------------------------- only the lead of the shift in progress
def _move_shifts(engine, ws: str, hours: float) -> None:
    """Pretend `hours` have passed in this run's schedule (shifts only)."""
    with engine.begin() as c:
        c.execute(
            text("UPDATE workweave.shift_instances SET scheduled_start_at = scheduled_start_at - make_interval(secs => :s), scheduled_end_at = scheduled_end_at - make_interval(secs => :s) WHERE workspace_id=:w"),
            {"w": ws, "s": hours * 3600},
        )


def test_another_shifts_lead_cant_act_during_this_shift(client, engine):
    ws = fresh(client, "Alex")
    assert client.get("/api/work-state").json()["data"]["can_delegate"] is True
    p = proposal(client)
    pick(client, "Dana")  # leads the Evening shift, which hasn't started
    d = client.get("/api/work-state").json()["data"]
    assert d["can_delegate"] is False
    r = client.post(f"/api/delegation-proposals/{p['delegation_proposal_id']}/confirm", json={"idempotency_key": k(), "expected_revision": p["revision"]}, headers=H)
    assert r.status_code == 403 and "Alex Rivera, who leads the Afternoon shift in progress" in r.json()["error"]["message"]
    assert count(engine, ws, "SELECT count(*) FROM workweave.work_item_assignments WHERE workspace_id=:w AND proposal_item_id IS NOT NULL") == 0


def test_the_lead_changes_with_the_clock(client, engine):
    ws = fresh(client, "Alex")
    _move_shifts(engine, ws, 5)  # the Afternoon shift has ended; Evening is running
    assert client.get("/api/delegation-proposals").status_code == 403
    pick(client, "Dana")
    assert client.get("/api/work-state").json()["data"]["can_delegate"] is True
    assert confirm(client).status_code == 200


def test_nobody_leads_when_no_shift_is_in_progress(client, engine):
    ws = fresh(client, "Alex")
    _move_shifts(engine, ws, -48)  # every shift is in the future
    r = client.get("/api/delegation-proposals")
    assert r.status_code == 409 and "No shift is in progress" in r.json()["error"]["message"]


def test_the_report_notifies_only_the_lead_of_the_shift_in_progress(client, engine):
    ws = _assigned_story(client, engine)
    say(client, item(client, "Ticket #829"), "DONE", "Done.")
    with engine.connect() as c:
        to = c.execute(text("""SELECT e.first_name FROM workweave.outbox_events o JOIN workweave.employees e ON e.employee_id=o.recipient_employee_id
                               WHERE o.workspace_id=:w AND o.event_type='work.reported_done'"""), {"w": ws}).scalars().all()
    assert to == ["Alex"]  # not Priya or Dana


def test_the_ticket_system_shows_what_was_reported(client, engine):
    _assigned_story(client, engine)
    t = item(client, "Ticket #829")
    say(client, t, "DONE", "Done.")
    view = next(i for i in client.get("/api/ticket-system").json()["data"]["items"] if i["external_id"] == "Ticket #829")
    assert view["report"]["reported_status"] == "DONE" and view["report"]["sync_status"] == "AWAITING_SOURCE"
    assert tool(client, t, "COMPLETED").json()["data"]["report"]["sync_status"] == "MATCHED"
