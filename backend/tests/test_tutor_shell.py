"""Onboarding tutor shell: durable session state; every tutor reply is truthfully unavailable."""

import uuid

from sqlalchemy import text

from tests.test_demo_slice import code, open_company, pick


def start(c) -> dict:
    r = c.post("/api/onboarding/sessions")
    assert r.status_code == 200, r.text
    return r.json()["data"]


def current_name(view: dict) -> str:
    ov = view["overview"]
    return next(s["name"] for t in ov["topics"] for s in t["subtopics"] if s["subtopic_id"] == ov["current_subtopic_id"])


def as_jamie(c, fresh=True):
    open_company(c, "northstar", intent="FRESH" if fresh else "RESUME")
    pick(c, "Jamie")


def test_start_persists_an_active_session_at_the_deterministic_position(client, engine):
    as_jamie(client)
    v = start(client)
    assert v["status"] == "ACTIVE" and v["revision"] == 1
    assert current_name(v) == "Separate history from evidence"
    assert v["transcript"] == [] and v["script_prompts"] == []  # nothing invented
    assert v["tutor"]["status"] == "unavailable" and "isn't connected" in v["tutor"]["message"]
    assert v["overview"]["learning_session_id"] == v["learning_session_id"] and v["overview"]["session_status"] == "ACTIVE"
    with engine.connect() as c:
        row = c.execute(text("SELECT langgraph_thread_id, graph_version FROM workweave.learning_sessions WHERE learning_session_id=:s"), {"s": v["learning_session_id"]}).one()
    assert row.langgraph_thread_id == f"ww-{v['learning_session_id']}" and row.graph_version == "not-connected"


def test_starting_again_reuses_the_open_session(client, engine):
    as_jamie(client)
    a, b = start(client), start(client)
    assert a["learning_session_id"] == b["learning_session_id"]
    ws = client.get("/api/demo-sessions/current").json()["data"]["workspace_id"]
    with engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM workweave.learning_sessions WHERE workspace_id=:w"), {"w": ws}).scalar_one() == 1


def test_turns_are_unavailable_and_nothing_is_stored(client, engine):
    as_jamie(client)
    v = start(client)
    r = client.post(f"/api/onboarding/sessions/{v['learning_session_id']}/turns", json={"client_turn_id": str(uuid.uuid4()), "expected_revision": v["revision"], "text": "Is v3.3 still current?", "input_kind": "TEXT"})
    assert r.status_code == 501 and code(r) == "CAPABILITY_UNAVAILABLE" and "still in the box" in r.json()["error"]["message"]
    with engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM workweave.learning_turns WHERE learning_session_id=:s"), {"s": v["learning_session_id"]}).scalar_one() == 0
    stale = client.post(f"/api/onboarding/sessions/{v['learning_session_id']}/turns", json={"client_turn_id": str(uuid.uuid4()), "expected_revision": 99, "text": "x"})
    assert stale.status_code == 409 and code(stale) == "REVISION_CONFLICT"


def test_pause_is_atomic_idempotent_and_keeps_progress(client, engine):
    as_jamie(client)
    v = start(client)
    sid, key = v["learning_session_id"], f"pause-{uuid.uuid4()}"
    before = [(s["name"], s["status"]) for t in v["overview"]["topics"] for s in t["subtopics"]]
    r = client.post(f"/api/onboarding/sessions/{sid}/pause", json={"client_turn_id": key, "expected_revision": v["revision"]})
    assert r.status_code == 200, r.text
    p = r.json()["data"]
    assert p["status"] == "PAUSED" and p["revision"] == v["revision"] + 1
    assert [(s["name"], s["status"]) for t in p["overview"]["topics"] for s in t["subtopics"]] == before  # a break completes nothing
    # Replay with the same key: same result, no second change.
    again = client.post(f"/api/onboarding/sessions/{sid}/pause", json={"client_turn_id": key, "expected_revision": v["revision"]}).json()["data"]
    assert again["revision"] == p["revision"] and again["status"] == "PAUSED"
    # Same key, different request: rejected.
    assert client.post(f"/api/onboarding/sessions/{sid}/pause", json={"client_turn_id": key, "expected_revision": 7}).status_code == 422
    with engine.connect() as c:
        receipts = c.execute(text("SELECT count(*) FROM workweave.command_receipts WHERE command='onboarding.pause' AND idempotency_key=:k"), {"k": key}).scalar_one()
        audits = c.execute(text("SELECT count(*) FROM workweave.audit_events WHERE resource_id=:s AND action='learning_session.paused'"), {"s": sid}).scalar_one()
    assert receipts == 1 and audits == 1
    # Messages can't be sent to a paused conversation; resume reopens the same session.
    t = client.post(f"/api/onboarding/sessions/{sid}/turns", json={"client_turn_id": str(uuid.uuid4()), "expected_revision": p["revision"], "text": "hi"})
    assert t.status_code == 409 and code(t) == "GUARD_FAILED"
    resumed = start(client)
    assert resumed["learning_session_id"] == sid and resumed["status"] == "ACTIVE" and resumed["revision"] == p["revision"] + 1
    assert current_name(resumed) == "Separate history from evidence"


def test_stale_pause_is_rejected(client):
    as_jamie(client)
    v = start(client)
    r = client.post(f"/api/onboarding/sessions/{v['learning_session_id']}/pause", json={"client_turn_id": f"pause-{uuid.uuid4()}", "expected_revision": v["revision"] + 5})
    assert r.status_code == 409 and code(r) == "REVISION_CONFLICT"


def test_sessions_are_owner_only(client, other_client):
    as_jamie(client)
    v = start(client)
    path = f"/api/onboarding/sessions/{v['learning_session_id']}"
    assert client.get(path).status_code == 200
    pick(client, "Sam")  # another persona in the same workspace
    assert client.get(path).status_code == 404
    as_jamie(other_client)  # another visitor's Jamie
    assert other_client.get(path).status_code == 404
    assert other_client.post(f"{path}/pause", json={"client_turn_id": f"pause-{uuid.uuid4()}", "expected_revision": 1}).status_code == 404


def test_completed_curriculum_cannot_start_a_session(client, engine):
    as_jamie(client)
    ws = client.get("/api/demo-sessions/current").json()["data"]["workspace_id"]
    with engine.begin() as c:
        c.execute(text("UPDATE workweave.employee_learning_progress SET status='COMPLETED', started_at=coalesce(started_at, now()), completed_at=now() WHERE workspace_id=:w"), {"w": ws})
    r = client.post("/api/onboarding/sessions")
    assert r.status_code == 409 and code(r) == "GUARD_FAILED"


def test_persona_without_assignment_cannot_start(client):
    open_company(client, "northstar", intent="FRESH")
    pick(client, "Alex")
    r = client.post("/api/onboarding/sessions")
    assert r.status_code == 404 and code(r) == "NOT_FOUND"
