"""Demo shift clock (ADR-042)."""

import uuid

from sqlalchemy import text

from tests.test_companion_commands import count, fresh
from tests.test_demo_slice import code, pick
from tests.test_handover import open_handover

H = {"X-WorkWeave-Client": "web"}


def k() -> str:
    return str(uuid.uuid4())


def clock(client) -> dict:
    r = client.get("/api/demo-sessions/current/shift-clock")
    assert r.status_code == 200, r.text
    return r.json()["data"]


def advance(client, confirm=False):
    return client.post("/api/demo-sessions/current/shift-clock/advance", json={"idempotency_key": k(), "confirm_unpublished": confirm}, headers=H)


def test_any_persona_moves_the_run_to_the_next_shift_and_the_handover_follows(client, engine):
    ws = fresh(client, "Jamie")
    c = clock(client)
    assert c["current"]["name"] == "Afternoon" and c["next"]["name"] == "Evening" and c["handover_unpublished"]
    blocked = advance(client)
    assert blocked.status_code == 409 and "hasn't published its handover" in blocked.json()["error"]["message"]
    with engine.connect() as x:
        due_before = x.execute(text("SELECT min(due_at) FROM workweave.work_items WHERE workspace_id=:w AND due_at IS NOT NULL"), {"w": ws}).scalar()
        expires_before = x.execute(text("SELECT expires_at FROM workweave.demo_visitor_sessions WHERE workspace_id=:w"), {"w": ws}).scalar()
    r = advance(client, confirm=True)
    assert r.status_code == 200, r.text
    after = r.json()["data"]
    assert after["current"]["name"] == "Evening" and after["next"]["name"] == "Morning"
    with engine.connect() as x:
        assert x.execute(text("SELECT min(due_at) FROM workweave.work_items WHERE workspace_id=:w AND due_at IS NOT NULL"), {"w": ws}).scalar() < due_before  # time passed for work too
        assert x.execute(text("SELECT expires_at FROM workweave.demo_visitor_sessions WHERE workspace_id=:w"), {"w": ws}).scalar() == expires_before  # the session keeps real time
    assert count(engine, ws, "SELECT count(*) FROM workweave.audit_events WHERE workspace_id=:w AND action='demo.shift_clock_advanced'") == 1
    pick(client, "Dana")  # Evening lead now leads the shift in progress
    h = open_handover(client)
    assert h["source"]["name"] == "Evening" and h["can_configure_template"]


def test_a_published_handover_moves_without_confirmation_and_the_clock_keeps_going(client):
    fresh(client, "Alex")
    w = open_handover(client)
    pub = client.post(f"/api/handovers/{w['handover_id']}/publish", json={"idempotency_key": k(), "expected_revision": w["revision"]}, headers=H)
    assert pub.status_code == 200, pub.text
    assert not clock(client)["handover_unpublished"]
    assert advance(client).status_code == 200  # Evening
    assert advance(client, confirm=True).status_code == 200  # next Morning
    nxt = advance(client, confirm=True)  # past the scenario's last shift: tomorrow's Afternoon is added
    assert nxt.status_code == 200, nxt.text
    assert nxt.json()["data"]["current"]["name"] == "Afternoon"


def test_only_visitor_runs_and_history_keeps_its_time(client, engine):
    from app.errors import ApiError
    from app.services import demo_clock

    with engine.connect() as x:  # a pack baseline is never a visitor run
        try:
            demo_clock._visitor_run(x, "00000001-0000-4000-8000-000000000001", "00000001-0000-4000-8000-000000000002")
            raise AssertionError("baseline accepted")
        except ApiError as e:
            assert e.code == "FORBIDDEN"
    ws = fresh(client, "Sam")
    with engine.connect() as x:
        before = x.execute(text("SELECT min(observed_at) FROM workweave.work_events WHERE workspace_id=:w"), {"w": ws}).scalar()
    assert advance(client, confirm=True).status_code == 200
    with engine.connect() as x:
        assert x.execute(text("SELECT min(observed_at) FROM workweave.work_events WHERE workspace_id=:w"), {"w": ws}).scalar() == before  # append-only
