"""Demo entry slice: catalog → isolated workspace → personas → persona → refresh."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from app import cli
from app.repositories import demo as repo


def scenarios(c) -> dict[str, dict]:
    r = c.get("/api/scenarios")
    assert r.status_code == 200
    return {s["key"]: s for s in r.json()["data"]}


def open_company(c, key: str, intent: str = "RESUME") -> dict:
    sid = scenarios(c)[key]["scenario_id"]
    r = c.post("/api/demo-sessions", json={"scenario_id": sid, "intent": intent})
    assert r.status_code == 200, r.text
    return r.json()["data"]


def personas(c) -> list[dict]:
    r = c.get("/api/personas")
    assert r.status_code == 200, r.text
    return r.json()["data"]


def pick(c, first_name: str) -> dict:
    p = next(x for x in personas(c) if x["first_name"] == first_name)
    r = c.post("/api/demo-sessions/current/persona", json={"employee_id": p["employee_id"]})
    assert r.status_code == 200, r.text
    return r.json()["data"]


def decode_session(c) -> dict:
    import base64
    import json

    raw = c.cookies.get("__session")
    return json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))


def encode_session(data: dict) -> str:
    import base64
    import json

    return base64.urlsafe_b64encode(json.dumps(data).encode()).decode().rstrip("=")


def code(r) -> str:
    return r.json()["error"]["code"]


# ---------------------------------------------------------------- catalog
def test_catalog_lists_only_ready_synthetic_packs(client, test_url):
    assert set(scenarios(client)) == {"northstar", "acme", "harbor"}
    card = scenarios(client)["northstar"]
    assert card["company_name"] == "Northstar Manufacturing"
    assert card["terminology"]["workItem"] == "ticket"
    cli.main(["deactivate", "harbor"], url=test_url)
    try:
        assert "harbor" not in scenarios(client)
    finally:
        cli.main(["activate", "harbor", "--confirm-reviewed"], url=test_url)


def test_draft_pack_cannot_be_opened_by_id(client, engine, test_url):
    sid = scenarios(client)["harbor"]["scenario_id"]
    cli.main(["deactivate", "harbor"], url=test_url)
    try:
        r = client.post("/api/demo-sessions", json={"scenario_id": sid, "intent": "RESUME"})
        assert r.status_code == 404 and code(r) == "NOT_FOUND"
    finally:
        cli.main(["activate", "harbor", "--confirm-reviewed"], url=test_url)


def test_activation_requires_explicit_review_confirmation(test_url):
    with pytest.raises(SystemExit):
        cli.main(["activate", "northstar"], url=test_url)


# ---------------------------------------------------------------- sessions and personas
def test_session_is_an_isolated_copy_with_pack_personas(client, engine):
    s = open_company(client, "northstar")
    assert s["persona_selected"] is False
    jar = decode_session(client)
    assert jar["c"] and set(jar["r"]) == {"northstar"} and jar["r"]["northstar"] == jar["c"]
    assert [k for k in client.cookies.keys() if k.startswith("ww_")] == []  # one __session cookie only
    roster = personas(client)
    assert [p["first_name"] for p in roster] == ["Sam", "Alex", "Jamie", "Morgan", "Priya", "Dana"]
    assert roster[1]["scenario_note"].startswith("Machine #14 owner")
    assert "handover.publish" in roster[1]["grants"]
    with engine.connect() as conn:
        # New organization/workspace; baseline employee IDs are never handed out.
        ws = conn.execute(text("SELECT workspace_id FROM workweave.employees WHERE employee_id=:e"), {"e": roster[0]["employee_id"]}).scalar_one()
        assert str(ws) == s["workspace_id"]
        assert str(ws) != "00000001-0000-4000-8000-000000000002"
        key = conn.execute(text("SELECT o.company_key FROM workweave.workspaces w JOIN workweave.organizations o USING (organization_id) WHERE w.workspace_id=:w"), {"w": ws}).scalar_one()
        assert key is None  # the public key never becomes tenant identity


@pytest.mark.parametrize(
    ("company", "expected_leads", "expected_members", "persona_count"),
    [
        ("northstar", {"Evening": "Dana Brooks", "Morning": "Priya Nair"}, {"Evening": "Jamie Chen", "Morning": "Sam Kim"}, 6),
        ("harbor", {"Evening": "Tessa Lim", "Morning": "Cora Mendoza"}, {"Evening": "Mia Reyes", "Morning": "Nora Santos"}, 6),
        ("acme", {"Evening": "Aisha Rahman", "Morning": "Neha Shah"}, {"Evening": "Maria Garcia", "Morning": "Sam Lim"}, 8),
    ],
)
def test_new_evening_and_morning_rosters_are_copied_to_demo(
    client, engine, company, expected_leads, expected_members, persona_count
):
    session = open_company(client, company)
    roster = personas(client)
    assert len(roster) == persona_count
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT s.name, si.shift_lead_employee_id, sim.membership_role,
                       e.first_name || ' ' || e.last_name AS employee_name,
                       si.scheduled_start_at, si.scheduled_end_at
                  FROM workweave.shift_instances si
                  JOIN workweave.shifts s ON s.shift_id = si.shift_id
                  JOIN workweave.shift_instance_memberships sim ON sim.shift_instance_id = si.shift_instance_id
                  JOIN workweave.employees e ON e.employee_id = sim.employee_id
                 WHERE si.workspace_id = :workspace_id AND si.status = 'SCHEDULED'
                   AND s.name IN ('Evening', 'Morning')
                 ORDER BY si.scheduled_start_at, sim.membership_role
            """),
            {"workspace_id": session["workspace_id"]},
        ).mappings().all()
    assert len(rows) == 4
    for shift_name in ("Evening", "Morning"):
        members = [r for r in rows if r["name"] == shift_name]
        assert len(members) == 2
        assert [r["employee_name"] for r in members if r["membership_role"] == "SHIFT_LEAD"] == [expected_leads[shift_name]]
        assert [r["employee_name"] for r in members if r["membership_role"] == "MEMBER"] == [expected_members[shift_name]]
    assert max(r["scheduled_end_at"] for r in rows if r["name"] == "Evening") == min(
        r["scheduled_start_at"] for r in rows if r["name"] == "Morning"
    )


def test_persona_selection_persists_across_refresh(client):
    open_company(client, "northstar")
    s = pick(client, "Alex")
    assert s["persona_selected"] and s["persona"]["first_name"] == "Alex"
    # "Refresh": a new request with the same cookie jar sees the committed state.
    r = client.get("/api/demo-sessions/current")
    assert r.json()["data"]["persona"]["first_name"] == "Alex"
    # Resume returns the same workspace, not a new one.
    again = open_company(client, "northstar")
    assert again["workspace_id"] == s["workspace_id"] and again["resumed"] is True


def test_unauthorized_persona_selection_is_rejected(client, engine):
    open_company(client, "northstar")
    with engine.connect() as conn:
        baseline_sam = "00000001-0000-4000-8000-000000000008"  # pack baseline, not this copy
        acme_any = conn.execute(text("SELECT employee_id FROM workweave.employees WHERE workspace_id='00000003-0000-4000-8000-000000000002' LIMIT 1")).scalar_one()
    for eid in (baseline_sam, str(acme_any), str(uuid.uuid4())):
        r = client.post("/api/demo-sessions/current/persona", json={"employee_id": eid})
        assert r.status_code == 403 and code(r) == "FORBIDDEN"
    r = client.post("/api/demo-sessions/current/persona", json={"employee_id": "not-a-uuid"})
    assert r.status_code == 422


def test_cross_company_and_cross_visitor_isolation(client, other_client):
    ns = open_company(client, "northstar")
    ns_people = {p["employee_id"] for p in personas(client)}
    ac = open_company(client, "acme")
    assert ac["workspace_id"] != ns["workspace_id"]
    ac_people = {p["employee_id"] for p in personas(client)}
    assert ns_people.isdisjoint(ac_people)
    # Current session is Acme now; a Northstar persona can't be selected in it.
    r = client.post("/api/demo-sessions/current/persona", json={"employee_id": next(iter(ns_people))})
    assert r.status_code == 403
    # Another visitor of the same company gets a different workspace and can't use the first one's personas.
    other = open_company(other_client, "northstar")
    assert other["workspace_id"] != ns["workspace_id"]
    r = other_client.post("/api/demo-sessions/current/persona", json={"employee_id": next(iter(ns_people))})
    assert r.status_code == 403
    # Switching back resumes the first company's own run.
    back = open_company(client, "northstar")
    assert back["workspace_id"] == ns["workspace_id"]


def test_company_key_in_cookie_name_grants_nothing(client, other_client):
    """Copying another company's run cookie name doesn't help: tokens are bound to their scenario."""
    open_company(client, "acme")
    acme_token = decode_session(client)["r"]["acme"]
    other_client.cookies.set("__session", encode_session({"c": None, "r": {"northstar": acme_token}}), path="/api")
    s = open_company(other_client, "northstar")
    assert s["resumed"] is False and s["scenario"]["key"] == "northstar"


def test_session_expiry(client, engine):
    s = open_company(client, "northstar")
    with engine.begin() as conn:
        conn.execute(text("UPDATE workweave.demo_visitor_sessions SET expires_at=:t WHERE demo_visitor_session_id=:id"), {"t": datetime.now(UTC) - timedelta(minutes=1), "id": s["session_id"]})
    r = client.get("/api/personas")
    assert r.status_code == 401 and code(r) == "SESSION_EXPIRED"
    assert client.post("/api/demo-sessions/current/persona", json={"employee_id": str(uuid.uuid4())}).status_code == 401
    assert client.get("/api/demo-sessions/current").status_code == 401
    # Opening the company again starts a new run instead of reviving the expired one.
    again = open_company(client, "northstar")
    assert again["workspace_id"] != s["workspace_id"] and again["resumed"] is False


def test_no_session_reads(client):
    assert client.get("/api/demo-sessions/current").json()["data"] is None
    r = client.get("/api/personas")
    assert r.status_code == 401 and code(r) == "SESSION_EXPIRED"


def test_state_changes_require_client_header(client):
    sid = scenarios(client)["northstar"]["scenario_id"]
    r = client.post("/api/demo-sessions", json={"scenario_id": sid}, headers={"X-WorkWeave-Client": ""})
    assert r.status_code == 403


# ---------------------------------------------------------------- start fresh
def counts(engine, ws: str) -> int:
    with engine.connect() as conn:
        return conn.execute(text("SELECT count(*) FROM workweave.employees WHERE workspace_id=:w"), {"w": ws}).scalar_one()


def test_fresh_start_is_isolated_to_this_visitor_and_company(client, other_client, engine):
    baseline_before = counts(engine, "00000001-0000-4000-8000-000000000002")
    old = open_company(client, "northstar")
    pick(client, "Alex")
    acme = open_company(client, "acme")
    other = open_company(other_client, "northstar")
    open_company(client, "northstar")
    fresh = open_company(client, "northstar", intent="FRESH")
    assert fresh["workspace_id"] != old["workspace_id"] and fresh["persona_selected"] is False
    # The old run is revoked; the baseline, the other visitor's run and this visitor's Acme run are untouched.
    with engine.connect() as conn:
        st = conn.execute(text("SELECT status FROM workweave.demo_visitor_sessions WHERE demo_visitor_session_id=:i"), {"i": old["session_id"]}).scalar_one()
    assert st == "REVOKED"
    assert counts(engine, "00000001-0000-4000-8000-000000000002") == baseline_before
    assert other_client.get("/api/demo-sessions/current").json()["data"]["workspace_id"] == other["workspace_id"]
    assert open_company(client, "acme")["workspace_id"] == acme["workspace_id"]


def test_failed_fresh_start_keeps_the_previous_run(client, engine, monkeypatch):
    old = open_company(client, "northstar")
    pick(client, "Jamie")
    with engine.connect() as conn:
        before = conn.execute(text("SELECT count(*) FROM workweave.workspaces")).scalar_one()
    real = repo.materialize_identity

    def broken(conn, scenario, expires_at):
        real(conn, scenario, expires_at)
        raise RuntimeError("simulated failure after partial copy")

    monkeypatch.setattr(repo, "materialize_identity", broken)
    sid = scenarios(client)["northstar"]["scenario_id"]
    from fastapi.testclient import TestClient

    from app.main import create_app

    # Same cookie jar, but surface the server's error response instead of re-raising.
    lenient = TestClient(create_app(), base_url="http://testserver", headers={"X-WorkWeave-Client": "web"}, raise_server_exceptions=False, cookies=client.cookies)
    r = lenient.post("/api/demo-sessions", json={"scenario_id": sid, "intent": "FRESH"})
    assert r.status_code == 500 and r.json()["error"]["retryable"] is True
    assert "__session" not in r.headers.get("set-cookie", "")  # no cookie for a failed start
    monkeypatch.undo()
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM workweave.workspaces")).scalar_one() == before  # no partial copy
    cur = client.get("/api/demo-sessions/current").json()["data"]
    assert cur["workspace_id"] == old["workspace_id"] and cur["persona"]["first_name"] == "Jamie"


def test_baseline_drift_blocks_new_runs_until_reverified(client, engine, test_url):
    with engine.begin() as conn:
        conn.execute(text("UPDATE workweave.employees SET last_name='Changed' WHERE employee_id='00000002-0000-4000-8000-000000000009'"))
    try:
        sid = scenarios(client)["harbor"]["scenario_id"]
        r = client.post("/api/demo-sessions", json={"scenario_id": sid, "intent": "FRESH"})
        assert r.status_code == 503 and code(r) == "DEPENDENCY_UNAVAILABLE"
    finally:
        with engine.begin() as conn:
            conn.execute(text("UPDATE workweave.employees SET last_name='Cruz' WHERE employee_id='00000002-0000-4000-8000-000000000009'"))


def test_runs_endpoint_reports_this_visitors_runs(client):
    open_company(client, "northstar")
    pick(client, "Morgan")
    open_company(client, "acme")
    runs = {r["key"]: r for r in client.get("/api/demo-sessions/runs").json()["data"]}
    assert set(runs) == {"northstar", "acme"}
    assert runs["northstar"]["persona"]["first_name"] == "Morgan" and runs["acme"]["is_active_session"]


def test_service_rejects_a_session_on_a_non_demo_workspace(client, monkeypatch):
    """Defence in depth with a mocked repository result (database constraints stay enabled)."""
    open_company(client, "northstar")
    real = repo.session_by_token_hash

    def operational(conn, token_hash):
        s = real(conn, token_hash)
        return {**s, "attached_workspace_kind": "OPERATIONAL"} if s else s

    monkeypatch.setattr(repo, "session_by_token_hash", operational)
    r = client.get("/api/personas")
    assert r.status_code == 403 and code(r) == "FORBIDDEN"
    assert client.post("/api/demo-sessions/current/persona", json={"employee_id": str(uuid.uuid4())}).status_code == 403
