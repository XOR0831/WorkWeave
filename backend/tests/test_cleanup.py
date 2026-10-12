"""Demo visitor cleanup (migration 0003 + app/workers/cleanup.py) on disposable databases."""

import uuid

import pytest
from alembic import command
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from app.workers import cleanup
from tests import prepare_db
from tests.test_demo_slice import open_company, pick

BASELINE_WS = "00000001-0000-4000-8000-000000000002"


def run_with_history(client) -> str:
    """A Northstar run with audit rows and a command receipt (append-only tables)."""
    s = open_company(client, "northstar", intent="FRESH")
    pick(client, "Jamie")
    v = client.post("/api/onboarding/sessions").json()["data"]
    r = client.post(f"/api/onboarding/sessions/{v['learning_session_id']}/pause", json={"client_turn_id": f"pause-{uuid.uuid4()}", "expected_revision": v["revision"]})
    assert r.status_code == 200
    return s["workspace_id"]


def revoke(engine, ws: str) -> None:
    with engine.begin() as c:
        c.execute(text("UPDATE workweave.demo_visitor_sessions SET status='REVOKED', updated_at = now() - interval '2 hours' WHERE workspace_id=:w"), {"w": ws})


def rows_in(engine, ws: str) -> int:
    with engine.connect() as c:
        return sum(cleanup.counts(c, cleanup.scoped_tables(c), uuid.UUID(ws)).values())


def candidate(engine, ws: str, grace=0):
    with engine.connect() as c:
        found = cleanup.candidates(c, grace, 10, uuid.UUID(ws))
    return found[0] if found else None


def test_purges_a_revoked_run_completely_including_its_append_only_rows(client, other_client, engine):
    ws = run_with_history(client)
    keep = open_company(other_client, "northstar", intent="FRESH")["workspace_id"]
    with engine.connect() as c:
        audits = c.execute(text("SELECT count(*) FROM workweave.audit_events WHERE workspace_id=:w"), {"w": ws}).scalar_one()
        receipts = c.execute(text("SELECT count(*) FROM workweave.command_receipts WHERE workspace_id=:w"), {"w": ws}).scalar_one()
    assert audits >= 3 and receipts == 1
    baseline_before, keep_before = rows_in(engine, BASELINE_WS), rows_in(engine, keep)
    revoke(engine, ws)
    cand = candidate(engine, ws)
    assert cand and cand.reason == "REVOKED"
    purged = cleanup.purge_one(engine, cand, 0)
    assert purged and purged["audit_events"] == audits and purged["knowledge_document_versions"] >= 1
    assert rows_in(engine, ws) == 0
    with engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM workweave.workspaces WHERE workspace_id=:w"), {"w": ws}).scalar_one() == 0
        org_left = c.execute(text("SELECT count(*) FROM workweave.organizations WHERE organization_id=:o"), {"o": cand.organization_id}).scalar_one()
        log = c.execute(text("SELECT reason, row_counts FROM workweave.demo_workspace_purges WHERE workspace_id=:w"), {"w": ws}).one()
    assert org_left == 0 and log.reason == "REVOKED" and log.row_counts["audit_events"] == audits
    assert rows_in(engine, BASELINE_WS) == baseline_before  # pack original untouched
    assert rows_in(engine, keep) == keep_before  # another visitor's run untouched


def test_live_runs_pack_originals_and_recent_runs_are_never_candidates(client, engine):
    ws = open_company(client, "northstar", intent="FRESH")["workspace_id"]
    assert candidate(engine, ws) is None  # active and unexpired
    assert candidate(engine, BASELINE_WS) is None  # pack original (kind DEMO, no sessions)
    with engine.begin() as c:
        c.execute(text("UPDATE workweave.demo_visitor_sessions SET status='REVOKED', updated_at = now() WHERE workspace_id=:w"), {"w": ws})
    assert candidate(engine, ws, grace=60) is None  # just revoked: inside the grace period
    assert candidate(engine, ws, grace=0) is not None


def test_expired_runs_become_candidates(client, engine):
    ws = open_company(client, "northstar", intent="FRESH")["workspace_id"]
    with engine.begin() as c:
        c.execute(text("UPDATE workweave.demo_visitor_sessions SET expires_at = now() - interval '3 hours', updated_at = now() - interval '4 hours' WHERE workspace_id=:w"), {"w": ws})
    cand = candidate(engine, ws, grace=60)
    assert cand and cand.reason == "EXPIRED"


def test_dry_run_deletes_nothing(client, engine):
    ws = run_with_history(client)
    revoke(engine, ws)
    before = rows_in(engine, ws)
    plan = cleanup.run(engine, confirm=False, grace_minutes=0, limit=500)
    assert any(p["workspace_id"] == ws and p["action"] == "would purge" for p in plan)
    assert rows_in(engine, ws) == before


def test_a_run_that_becomes_active_again_is_skipped(client, engine):
    ws = run_with_history(client)
    revoke(engine, ws)
    cand = candidate(engine, ws)
    with engine.begin() as c:  # the visitor resumes before the purge transaction starts
        c.execute(text("UPDATE workweave.demo_visitor_sessions SET status='ACTIVE', expires_at = now() + interval '1 hour', updated_at = now() WHERE workspace_id=:w"), {"w": ws})
    assert cleanup.purge_one(engine, cand, 0) is None
    assert rows_in(engine, ws) > 0


def test_append_only_still_holds_outside_the_scoped_purge(client, engine):
    ws = run_with_history(client)

    def attempt(sql: str, flag_ws: str | None, **p):
        with pytest.raises(DBAPIError, match="append-only"):
            with engine.begin() as c:
                if flag_ws:
                    c.execute(text("SELECT set_config('workweave.retention_purge', 'demo-visitor', true)"))
                    c.execute(text("SELECT set_config('workweave.retention_purge_workspace', :w, true)"), {"w": flag_ws})
                c.execute(text(sql), p)

    attempt("DELETE FROM workweave.audit_events WHERE workspace_id=:w", None, w=ws)  # no flag
    attempt("DELETE FROM workweave.audit_events WHERE workspace_id=:w", str(uuid.uuid4()), w=ws)  # flag names another workspace
    attempt("UPDATE workweave.audit_events SET result='X' WHERE workspace_id=:w", ws, w=ws)  # updates never allowed
    with engine.begin() as c:  # pack originals are never purgeable, even when flagged
        c.execute(text("""INSERT INTO workweave.audit_events (organization_id, workspace_id, action, resource_type, result, request_id)
                          VALUES ('00000001-0000-4000-8000-000000000001', :w, 'test', 'test', 'COMMITTED', gen_random_uuid())"""), {"w": BASELINE_WS})
    attempt("DELETE FROM workweave.audit_events WHERE workspace_id=:w AND action='test'", BASELINE_WS, w=BASELINE_WS)
    with engine.begin() as c:  # operational workspaces are never purgeable
        org, op_ws = uuid.uuid4(), uuid.uuid4()
        c.execute(text("INSERT INTO workweave.organizations (organization_id, name) VALUES (:o, 'Operational org')"), {"o": org})
        c.execute(text("INSERT INTO workweave.workspaces (workspace_id, organization_id, kind) VALUES (:w, :o, 'OPERATIONAL')"), {"w": op_ws, "o": org})
        c.execute(text("INSERT INTO workweave.audit_events (organization_id, workspace_id, action, resource_type, result, request_id) VALUES (:o, :w, 'test', 'test', 'COMMITTED', gen_random_uuid())"), {"o": org, "w": op_ws})
    attempt("DELETE FROM workweave.audit_events WHERE workspace_id=:w", str(op_ws), w=str(op_ws))


def test_migration_0003_up_down_up_restores_the_original_trigger_function():
    name = f"workweave_scratch_{uuid.uuid4().hex[:8]}"
    url = prepare_db.build(name, revision="0002", catalog=False)
    eng = create_engine(url)
    try:
        definition = "SELECT pg_get_functiondef('workweave.reject_history_mutation()'::regprocedure)"
        with eng.connect() as c:
            original = c.execute(text(definition)).scalar_one()
        cfg = prepare_db.alembic_config(url)
        command.upgrade(cfg, "0003")
        with eng.connect() as c:
            assert "retention_purge" in c.execute(text(definition)).scalar_one()
        command.downgrade(cfg, "0002")
        with eng.connect() as c:
            assert c.execute(text(definition)).scalar_one() == original
            assert c.execute(text("SELECT to_regclass('workweave.demo_workspace_purges') IS NULL")).scalar_one()
        command.upgrade(cfg, "0003")
    finally:
        eng.dispose()
        prepare_db.drop(name)



def test_a_session_reactivated_while_the_purge_waits_keeps_the_run(client, engine):
    """Eligibility is re-checked only after every lock is held.

    A concurrent transaction reactivates the run's session and holds that row. The purge passes
    its first check (the change isn't committed yet), locks the workspace, then must wait on the
    session lock. Once the reactivation commits, the purge's re-check sees it and skips.
    """
    import threading
    import time

    ws = run_with_history(client)
    revoke(engine, ws)
    cand = candidate(engine, ws)
    assert cand is not None
    before = rows_in(engine, ws)

    # A dedicated engine for the purge, with a lock_timeout so a regression fails instead of hanging.
    purge_engine = create_engine(engine.url, connect_args={"options": "-c lock_timeout=20000"})
    result: dict[str, object] = {}
    pid: dict[str, int] = {}

    def purge() -> None:
        from sqlalchemy import event

        @event.listens_for(purge_engine, "connect")
        def _remember(dbapi_conn, _):
            with dbapi_conn.cursor() as cur:
                cur.execute("SELECT pg_backend_pid()")
                pid["purge"] = cur.fetchone()[0]

        try:
            result["purged"] = cleanup.purge_one(purge_engine, cand, 0)
        except Exception as e:  # surfaced by the assertions below
            result["error"] = e

    blocker = engine.connect()
    tx = blocker.begin()
    worker = threading.Thread(target=purge, daemon=True)
    try:
        blocker.execute(
            text("UPDATE workweave.demo_visitor_sessions SET status='ACTIVE', expires_at = now() + interval '1 hour', updated_at = now() WHERE workspace_id=:w"),
            {"w": ws},
        )
        worker.start()
        waiting = None
        with engine.connect() as watch:  # wait until the purge is blocked on the session row lock
            for _ in range(200):
                if "purge" in pid:
                    waiting = watch.execute(
                        text("SELECT query FROM pg_stat_activity WHERE pid = :p AND wait_event_type = 'Lock'"), {"p": pid["purge"]}
                    ).scalar()
                    if waiting:
                        break
                time.sleep(0.05)
        assert waiting and "demo_visitor_sessions" in waiting, f"the purge never waited on the session lock: {waiting!r} {result}"
        tx.commit()
    finally:
        if tx.is_active:
            tx.rollback()
        blocker.close()
        worker.join(timeout=30)
        purge_engine.dispose()
    assert not worker.is_alive()
    assert "error" not in result, result.get("error")
    assert result["purged"] is None  # skipped: the run became active again
    assert rows_in(engine, ws) == before
    with engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM workweave.demo_workspace_purges WHERE workspace_id=:w"), {"w": ws}).scalar_one() == 0


def sessionless_visitor_workspace(engine) -> str:
    """A DEMO workspace in a visitor-style organization, with content but no session ever issued."""
    org, ws = uuid.uuid4(), uuid.uuid4()
    with engine.begin() as c:
        c.execute(text("INSERT INTO workweave.organizations (organization_id, name) VALUES (:o, 'Sessionless org')"), {"o": org})
        c.execute(text("INSERT INTO workweave.workspaces (workspace_id, organization_id, kind, created_at) VALUES (:w, :o, 'DEMO', now() - interval '3 days')"), {"w": ws, "o": org})
        c.execute(text("INSERT INTO workweave.departments (organization_id, workspace_id, name) VALUES (:o, :w, 'Kept')"), {"o": org, "w": ws})
    return str(ws)


def test_a_sessionless_demo_workspace_is_never_an_automatic_candidate(engine):
    ws = sessionless_visitor_workspace(engine)
    before = rows_in(engine, ws)
    assert before > 0
    assert candidate(engine, ws, grace=0) is None
    with engine.connect() as c:
        assert ws in {str(r["workspace_id"]) for r in cleanup.needs_review(c)}
    dry = cleanup.run(engine, confirm=False, grace_minutes=0, limit=500)
    assert [r["action"] for r in dry if r["workspace_id"] == ws] == ["needs review"]
    done = cleanup.run(engine, confirm=True, grace_minutes=0, limit=500)
    assert [r["action"] for r in done if r["workspace_id"] == ws] == ["needs review"]
    assert rows_in(engine, ws) == before
    with engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM workweave.workspaces WHERE workspace_id=:w"), {"w": ws}).scalar_one() == 1
