"""Work Companion: database-backed work context, the conversation shell and voice (no engine yet)."""

import re
import uuid

from sqlalchemy import text

from tests.test_demo_slice import code, open_company, pick
from tests.test_usage_caps import caps, used  # noqa: F401 (fixture)
from tests.test_voice import fake_voice  # noqa: F401 (fixture)

NORTHSTAR_WS = "00000001-0000-4000-8000-000000000002"


def as_(client, who: str, fresh: bool = True) -> str:
    ws = open_company(client, "northstar", intent="FRESH")["workspace_id"] if fresh else None
    pick(client, who)
    return ws


def test_a_fresh_demo_has_the_work_story_as_today(client):
    as_(client, "Alex")  # the lead of the shift in progress sees the team's work
    d = client.get("/api/work-state").json()["data"]
    assert d["active_count"] == 2 and d["blocked_count"] == 0 and d["overdue_count"] == 0 and d["work_state"] == "ON_TRACK"
    assert re.fullmatch(r"Afternoon shift · ends in (3 h( \d+ min)?|4 h)", d["shift_label"])  # in the active shift
    assert d["priorities"][0].startswith("Ticket #829 · Machine #14 inspection · Due in 1 h")  # HIGH first
    assert d["priorities"][1].startswith("Ticket #910 · Machine #22 document check · Due in 5 h")
    assert d["incoming_continuity"] is None and d["scope"] == "TEAM"


def test_a_member_sees_only_their_own_tickets(client):
    as_(client, "Sam")  # nothing is assigned to Sam in the pack
    d = client.get("/api/work-state").json()["data"]
    assert d["scope"] == "OWN" and d["active_count"] == 0 and d["priorities"] == []
    assert client.get("/api/assignments").json()["data"] == []
    assert client.get("/api/ticket-system").json()["data"]["items"] == []


def test_work_items_open_first_with_due_labels_history_last(client):
    as_(client, "Alex")
    items = client.get("/api/assignments").json()["data"]
    assert [i["external_id"] for i in items[:2]] == ["Ticket #829", "Ticket #910"]  # open work first
    assert items[0]["priority"] == "HIGH" and items[0]["due_label"].startswith("Due in 1 h") and not items[0]["historical"]
    past = items[2:]  # then history: #492 and Alex's past tickets (docs/32 synthetic history)
    assert {"Ticket #492", "Ticket #431"} <= {i["external_id"] for i in past}
    assert all(i["status"] == "CLOSED" and i["historical"] and i["due_label"] == "" for i in past)
    assert all(uuid.UUID(i["work_item_id"]) for i in items)


def test_updates_keep_reports_apart_from_recorded_transitions(client):
    as_(client, "Alex")
    ev = client.get("/api/work-events").json()["data"]
    kinds: dict = {}
    for e in ev:  # newest first: the latest update of each kind
        kinds.setdefault(e["event_type"], e)
    assert kinds["COMMENTED"]["evidence_type"] == "REPORTED" and kinds["COMMENTED"]["observed_label"].endswith("ago")
    assert kinds["COMPLETED"]["evidence_type"] == "OBSERVED" and re.fullmatch(r"\d\d \w{3} \d{4}", kinds["COMPLETED"]["observed_label"])  # months ago
    assert ev[0]["event_type"] == "COMMENTED"  # newest first


def test_work_is_scoped_to_the_visitor_run_and_its_work_read_grants(client, other_client, engine):
    ws = as_(client, "Alex")
    as_(other_client, "Alex")
    mine = {i["work_item_id"] for i in client.get("/api/assignments").json()["data"]}
    theirs = {i["work_item_id"] for i in other_client.get("/api/assignments").json()["data"]}
    assert mine and theirs and not (mine & theirs)  # each visitor sees only their own copy
    with engine.connect() as c:
        copied = c.execute(text("SELECT count(*) FROM workweave.work_items WHERE workspace_id=:w AND work_item_id = ANY(CAST(:ids AS uuid[]))"), {"w": ws, "ids": list(mine)}).scalar_one()
        baseline = c.execute(text("SELECT count(*) FROM workweave.work_items WHERE workspace_id=:w"), {"w": NORTHSTAR_WS}).scalar_one()
    assert copied == len(mine) and baseline == 7  # the pack original is untouched (3 + 4 synthetic past tickets)
    with engine.begin() as c:  # no work:read grant -> no Companion data
        c.execute(text("""DELETE FROM workweave.permission_grants WHERE workspace_id=:w AND action='work:read'
                          AND actor_id = (SELECT employee_id FROM workweave.employees WHERE workspace_id=:w AND first_name='Alex')"""), {"w": ws})
    r = client.get("/api/work-state")
    assert r.status_code == 403 and code(r) == "FORBIDDEN"


def test_copied_proposals_and_shifts_point_into_the_copy(client, engine):
    ws = as_(client, "Alex")
    with engine.connect() as c:
        bad = c.execute(
            text("""SELECT count(*) FROM workweave.delegation_proposals p WHERE p.workspace_id=:w
                    AND NOT EXISTS (SELECT 1 FROM workweave.teams t WHERE t.workspace_id=:w AND t.team_id=p.team_id)"""),
            {"w": ws},
        ).scalar_one()
        active = c.execute(text("SELECT count(*) FROM workweave.shift_instances WHERE workspace_id=:w AND status='ACTIVE' AND scheduled_start_at <= now() AND scheduled_end_at > now()"), {"w": ws}).scalar_one()
    assert bad == 0 and active == 1


def test_the_conversation_is_an_honest_shell_until_the_engine_exists(client, other_client, engine):
    as_(client, "Sam")
    s = client.post("/api/work-sessions").json()["data"]
    assert s["canvas"] == {"view": "BRIEFING"} and s["transcript"] == [] and s["assistant"]["status"] == "unavailable"
    assert client.post("/api/work-sessions").json()["data"]["work_session_id"] == s["work_session_id"]  # resumed, not duplicated
    r = client.post(f"/api/work-sessions/{s['work_session_id']}/messages", json={"client_turn_id": str(uuid.uuid4()), "expected_revision": 1, "text": "What should I focus on?"})
    assert r.status_code == 501 and code(r) == "CAPABILITY_UNAVAILABLE" and "still in the box" in r.json()["error"]["message"]
    assert client.get(f"/api/work-sessions/{s['work_session_id']}").json()["data"]["revision"] == s["revision"]  # nothing stored
    as_(other_client, "Sam")
    assert other_client.get(f"/api/work-sessions/{s['work_session_id']}").status_code == 404


def test_voice_input_works_for_the_companion_with_the_demo_caps(client, fake_voice, caps):  # noqa: F811
    caps(PUBLIC_RUN_VOICE_LISTEN=1)
    as_(client, "Sam")
    sid = client.post("/api/work-sessions").json()["data"]["work_session_id"]
    url = f"/api/work-sessions/{sid}/voice/listen"
    r = client.post(url, json={"mode": "HANDS_FREE"})
    assert r.status_code == 200 and r.json()["data"]["token"] == "fake-token" and fake_voice.modes == ["HANDS_FREE"]
    assert client.post(url, json={"mode": "TAP"}).status_code == 429  # same read-aloud/listen caps as onboarding
