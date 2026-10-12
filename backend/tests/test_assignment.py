"""Automatic competency-based assignment, the shift lead's override, and why (ADR-035)."""

import uuid

import pytest
from sqlalchemy import text

from tests.test_companion_commands import count, emp, fresh, item, proposal
from tests.test_demo_slice import code, pick

H = {"X-WorkWeave-Client": "web"}


@pytest.fixture()
def auto(monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "auto_assign_work", True)


def open_companion(client):
    r = client.post("/api/work-sessions", headers=H)
    assert r.status_code == 200, r.text


def assignments(engine, ws: str) -> dict[str, tuple[str, str]]:
    with engine.connect() as c:
        rows = c.execute(text("""SELECT wi.external_id, e.first_name, a.assignment_source FROM workweave.work_item_assignments a
                                 JOIN workweave.work_items wi ON wi.work_item_id=a.work_item_id JOIN workweave.employees e ON e.employee_id=a.employee_id
                                 WHERE a.workspace_id=:w AND a.status <> 'CANCELLED'
                                   AND coalesce(wi.metadata->>'historical_only', 'false') <> 'true'"""), {"w": ws}).all()  # past tickets keep their old assignments
    return {r[0]: (r[1], r[2]) for r in rows}


def test_open_tickets_go_to_members_on_the_shift_by_competency_once(client, engine, auto):
    ws = fresh(client, "Alex")  # Afternoon lead; Jamie and Sam are on the shift
    open_companion(client)
    got = assignments(engine, ws)
    assert set(got) == {"Ticket #829", "Ticket #910"} and {s for _, s in got.values()} == {"AUTOMATIC"}
    assert {who for who, _ in got.values()} == {"Jamie", "Sam"}  # spread by workload; never the lead
    with engine.connect() as c:
        match = c.execute(text("SELECT match_data FROM workweave.work_item_assignments WHERE workspace_id=:w AND assignment_source='AUTOMATIC' LIMIT 1"), {"w": ws}).scalar_one()
    assert match["rule"] == "competency-v1" and len(match["compared"]) == 2 and match["requirements"][0]["required_level"] == 1
    assert count(engine, ws, "SELECT count(*) FROM workweave.audit_events WHERE workspace_id=:w AND action='work_item_assignment.automatic'") == 2
    assert count(engine, ws, "SELECT count(*) FROM workweave.outbox_events WHERE workspace_id=:w AND event_type='work.assigned'") == 2
    assert proposal(client)["overtaken"] is True  # the seeded proposal's tickets already have someone
    open_companion(client)
    assert count(engine, ws, "SELECT count(*) FROM workweave.work_item_assignments WHERE workspace_id=:w AND assignment_source='AUTOMATIC'") == 2  # nothing assigned twice
    assert item(client, "Ticket #829")["assignment_source"] == "AUTOMATIC"


def test_a_validated_competency_wins_over_workload(client, engine, auto):
    ws = fresh(client, "Alex")
    jamie, sam = emp(engine, ws, "Jamie"), emp(engine, ws, "Sam")
    with engine.begin() as c:  # Sam has validated evidence for #910's requirement (evidence reporting)
        c.execute(text("""INSERT INTO workweave.employee_competency_evidence (organization_id, workspace_id, employee_id, competency_id, evidence_type, source_type, validation_status, validated_by, observed_at)
                          SELECT organization_id, workspace_id, CAST(:e AS uuid), competency_id, 'SUPERVISOR_VALIDATION', 'MANUAL', 'VALIDATED', CAST(:by AS uuid), now()
                          FROM workweave.competencies WHERE workspace_id=:w AND code='evidence_reporting'"""), {"e": sam, "w": ws, "by": emp(engine, ws, "Alex")})
    open_companion(client)
    assert assignments(engine, ws)["Ticket #910"][0] == "Sam"
    assert jamie


def test_why_is_shown_to_the_assignee_and_the_lead_only(client, engine, auto):
    ws = fresh(client, "Alex")
    open_companion(client)
    who = assignments(engine, ws)["Ticket #829"][0]
    other = "Sam" if who == "Jamie" else "Jamie"
    wid = item(client, "Ticket #829")["work_item_id"]
    lead_view = client.get(f"/api/work-items/{wid}/assignment").json()["data"]
    assert lead_view["source"] == "AUTOMATIC" and lead_view["assignee_name"].startswith(who) and len(lead_view["compared"]) == 2
    assert lead_view["summary"].startswith(f"Assigned automatically to {lead_view['assignee_name']} by the competency rule")
    pick(client, who)
    own = client.get(f"/api/work-items/{wid}/assignment").json()["data"]
    assert own["assignee_name"] == lead_view["assignee_name"] and "compared" not in own  # teammates' evidence stays private
    pick(client, other)
    assert client.get(f"/api/work-items/{wid}/assignment").status_code == 403


def test_the_lead_overrides_to_another_member_on_the_shift(client, engine, auto):
    ws = fresh(client, "Alex")
    open_companion(client)
    who = assignments(engine, ws)["Ticket #829"][0]
    other = "Sam" if who == "Jamie" else "Jamie"
    t = item(client, "Ticket #829")
    cands = client.get(f"/api/work-items/{t['work_item_id']}/assignment-candidates").json()["data"]
    assert {c["name"].split()[0] for c in cands} == {"Alex", "Jamie", "Sam"}  # the lead may take it
    body = lambda e, rev=t["revision"]: {"idempotency_key": str(uuid.uuid4()), "expected_revision": rev, "employee_id": e}  # noqa: E731
    off_shift = client.post(f"/api/work-items/{t['work_item_id']}/assignee", json=body(emp(engine, ws, "Priya")), headers=H)
    assert off_shift.status_code == 409 and code(off_shift) == "GUARD_FAILED"
    r = client.post(f"/api/work-items/{t['work_item_id']}/assignee", json=body(emp(engine, ws, other)), headers=H)
    assert r.status_code == 200, r.text
    why = r.json()["data"]
    assert why["source"] == "MANUAL" and why["rule"] == "lead-override" and why["assigned_by_name"].startswith("Alex")
    assert assignments(engine, ws)["Ticket #829"] == (other, "MANUAL")
    assert count(engine, ws, "SELECT count(*) FROM workweave.outbox_events WHERE workspace_id=:w AND event_type='work.unassigned'") == 1
    assert count(engine, ws, "SELECT count(*) FROM workweave.audit_events WHERE workspace_id=:w AND action='work_item_assignment.overridden'") == 1
    pick(client, other)  # a member can't override
    denied = client.post(f"/api/work-items/{t['work_item_id']}/assignee", json=body(emp(engine, ws, who)), headers=H)
    assert denied.status_code == 403


def test_nothing_is_assigned_automatically_when_switched_off(client, engine):
    ws = fresh(client, "Alex")
    open_companion(client)
    assert assignments(engine, ws) == {}
    assert client.get("/api/work-state").json()["data"]["unassigned_count"] == 2  # the lead sees what nobody holds
    pick(client, "Jamie")
    assert "unassigned_count" not in client.get("/api/work-state").json()["data"]


def test_a_confirmed_delegation_keeps_its_reasons_for_why(client, engine):
    from tests.test_companion_commands import _assigned_story

    ws = _assigned_story(client, engine)  # Alex confirmed the pack's proposal; Jamie got #829
    with engine.connect() as c:
        match = c.execute(text("""SELECT a.match_data FROM workweave.work_item_assignments a JOIN workweave.work_items wi ON wi.work_item_id=a.work_item_id
                                  WHERE a.workspace_id=:w AND wi.external_id='Ticket #829' AND a.status <> 'CANCELLED'"""), {"w": ws}).scalar_one()
    assert match["rule"] == "delegation-proposal" and match["recommendation_reason"] and match["requirements"][0]["name"]
    assert match["lead_changed_recommendation"] is False
    why = client.get(f"/api/work-items/{item(client, 'Ticket #829')['work_item_id']}/assignment").json()["data"]  # as Jamie, the assignee
    assert "confirmed a delegation proposal" in why["summary"] and "compared" not in why



def test_the_lead_can_take_a_ticket_but_isnt_chosen_automatically(client, engine, auto):
    ws = fresh(client, "Alex")
    open_companion(client)
    assert "Alex" not in {who for who, _ in assignments(engine, ws).values()}  # automatic: members only
    t = item(client, "Ticket #910")
    r = client.post(f"/api/work-items/{t['work_item_id']}/assignee", json={"idempotency_key": str(uuid.uuid4()), "expected_revision": t["revision"], "employee_id": emp(engine, ws, "Alex")}, headers=H)
    assert r.status_code == 200, r.text
    assert assignments(engine, ws)["Ticket #910"] == ("Alex", "MANUAL")


def test_the_baseline_keeps_829_with_alex_and_automatic_assignment_leaves_it(client, engine, auto):
    """Seed 20 (owner, 2026-10-11): the scenario's open ticket stays Alex's, so he can report on it and change it."""
    ws = fresh(client, "Alex", keep_829=True)
    open_companion(client)
    got = assignments(engine, ws)
    assert got["Ticket #829"] == ("Alex", "MANUAL") and got["Ticket #910"][1] == "AUTOMATIC"
    view = client.get("/api/ticket-system").json()["data"]
    assert next(i for i in view["items"] if i["external_id"] == "Ticket #829")["can_update"] is True
    pick(client, "Jamie")
    assert not any(i["can_update"] for i in client.get("/api/ticket-system").json()["data"]["items"] if i["external_id"] == "Ticket #829")


def test_the_lead_hands_over_his_own_829_by_confirming_the_seeded_proposal(client, engine):
    ws = fresh(client, "Alex", keep_829=True)  # automatic assignment off: the seeded proposal is still open
    p = proposal(client)
    r = client.post(f"/api/delegation-proposals/{p['delegation_proposal_id']}/confirm", json={"idempotency_key": str(uuid.uuid4()), "expected_revision": p["revision"]}, headers={"X-WorkWeave-Client": "web"})
    assert r.status_code == 200, r.text
    assert assignments(engine, ws)["Ticket #829"][0] != "Alex"  # moved to the teammate the proposal names
    assert count(engine, ws, "SELECT count(*) FROM workweave.audit_events WHERE workspace_id=:w AND action='work_item_assignment.handed_over'") == 1
