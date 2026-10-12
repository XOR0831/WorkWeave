"""Migration 0004: durable visitor-run proof, enforced by PostgreSQL on every purge deletion path.

All on disposable databases: the session-wide workweave_test (at head) and per-test
workweave_scratch_* databases built at 0003 for the upgrade/downgrade and backfill checks.
"""

import hashlib
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from alembic import command
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from app.repositories import demo as repo
from app.workers import cleanup
from tests import prepare_db
from tests.test_cleanup import rows_in, run_with_history, sessionless_visitor_workspace
from tests.test_demo_slice import open_company

BASELINE_ORG = "00000001-0000-4000-8000-000000000001"
BASELINE_WS = "00000001-0000-4000-8000-000000000002"
FUNCTION = "SELECT pg_get_functiondef('workweave.reject_history_mutation()'::regprocedure)"


def scalar(eng, sql: str, **p):
    with eng.connect() as c:
        return c.execute(text(sql), p).scalar_one()


def flagged(c, ws) -> None:
    c.execute(text("SELECT set_config('workweave.retention_purge', 'demo-visitor', true)"))
    c.execute(text("SELECT set_config('workweave.retention_purge_workspace', :w, true)"), {"w": str(ws)})


def rejected(engine, sql: str, match: str, flag_ws=None, **p) -> None:
    with pytest.raises(DBAPIError, match=match):
        with engine.begin() as c:
            if flag_ws:
                flagged(c, flag_ws)
            c.execute(text(sql), p)


# ---------------------------------------------------------------- upgrade, backfill, downgrade
def new_run(eng, company: str, session_status: str | None, sessions: int = 1, scenario_override=None):
    """A visitor run as materialization creates it, with sessions inserted the way the service does."""
    with eng.begin() as c:
        scenario = next(s for s in repo.ready_catalog(c) if s["company_key"] == company)
        org, ws, _ = repo.materialize_identity(c, scenario, datetime.now(UTC) + timedelta(hours=8))
        sc = scenario_override or scenario
        for _ in range(sessions if session_status else 0):
            c.execute(
                text(
                    """INSERT INTO workweave.demo_visitor_sessions (organization_id, workspace_id, scenario_id, pack_version, token_hash, status, expires_at, updated_at)
                       VALUES (:o, :w, :s, :pv, :t, :st, now() + interval '8 hours', now() - interval '3 hours')"""
                ),
                {"o": org, "w": ws, "s": sc["scenario_id"], "pv": sc["pack_version"], "t": hashlib.sha256(uuid.uuid4().bytes).hexdigest(), "st": session_status},
            )
    return org, ws


@pytest.fixture()
def scratch_0003():
    name = f"workweave_scratch_{uuid.uuid4().hex[:8]}"
    url = prepare_db.build(name, revision="0003", catalog=True)
    eng = create_engine(url)
    yield url, eng
    eng.dispose()
    prepare_db.drop(name)


def test_backfill_comes_only_from_sessions_and_downgrade_restores_0003(scratch_0003):
    url, eng = scratch_0003
    cfg = prepare_db.alembic_config(url)
    _, active = new_run(eng, "northstar", "ACTIVE")
    _, revoked = new_run(eng, "northstar", "REVOKED", sessions=2)  # two sessions, one proof row
    _, sessionless = new_run(eng, "acme", None)  # DEMO, visitor org, aged below: still no proof
    with eng.begin() as c:
        c.execute(text("UPDATE workweave.workspaces SET created_at = now() - interval '30 days' WHERE workspace_id = :w"), {"w": sessionless})
        function_0003 = c.execute(text(FUNCTION)).scalar_one()
        # Before 0004 the worker falls back to session evidence and still works.
        assert [x.workspace_id for x in cleanup.candidates(c, 60, 10)] == [revoked]

    command.upgrade(cfg, "0004")
    with eng.connect() as c:
        proof = {r.workspace_id: r.proof_source for r in c.execute(text("SELECT workspace_id, proof_source FROM workweave.demo_visitor_runs"))}
        sessions_ws = {r[0] for r in c.execute(text("SELECT DISTINCT workspace_id FROM workweave.demo_visitor_sessions"))}
        assert proof == {active: "BACKFILL_FROM_SESSION", revoked: "BACKFILL_FROM_SESSION"}
        assert set(proof) == sessions_ws  # exactly the workspaces with sessions; nothing inferred
        assert sessionless not in proof
        assert [x.workspace_id for x in cleanup.candidates(c, 60, 10)] == [revoked]
        assert {r["workspace_id"]: r["reason"] for r in cleanup.needs_review(c)} == {sessionless: "NO_PROOF_NO_SESSION"}

    command.downgrade(cfg, "0003")
    with eng.connect() as c:
        assert c.execute(text(FUNCTION)).scalar_one() == function_0003
        assert c.execute(text("SELECT to_regclass('workweave.demo_visitor_runs') IS NULL")).scalar_one()
        assert c.execute(text("SELECT count(*) FROM pg_proc WHERE proname IN ('visitor_run_purge_allowed', 'guard_demo_visitor_run', 'guard_demo_visitor_session_delete', 'guard_workspace_delete')")).scalar_one() == 0
        assert c.execute(text("SELECT count(*) FROM pg_trigger WHERE tgname IN ('guard_workspace_delete', 'guard_demo_visitor_session_delete')")).scalar_one() == 0
        assert c.execute(text("SELECT to_regclass('workweave.demo_workspace_purges') IS NOT NULL")).scalar_one()  # 0003's log stays
    command.upgrade(cfg, "0004")
    assert scalar(eng, "SELECT count(*) FROM workweave.demo_visitor_runs") == 2


def test_backfill_refuses_sessions_from_two_packs(scratch_0003):
    url, eng = scratch_0003
    with eng.connect() as c:
        harbor = next(s for s in repo.ready_catalog(c) if s["company_key"] == "harbor")
    org, ws = new_run(eng, "northstar", "REVOKED")
    new_run(eng, "northstar", None)
    with eng.begin() as c:
        c.execute(
            text("INSERT INTO workweave.demo_visitor_sessions (organization_id, workspace_id, scenario_id, pack_version, token_hash, status, expires_at) VALUES (:o, :w, :s, :pv, :t, 'REVOKED', now())"),
            {"o": org, "w": ws, "s": harbor["scenario_id"], "pv": harbor["pack_version"], "t": uuid.uuid4().hex},
        )
    with pytest.raises(DBAPIError, match="more than one scenario"):
        command.upgrade(prepare_db.alembic_config(url), "0004")
    assert scalar(eng, "SELECT to_regclass('workweave.demo_visitor_runs') IS NULL")  # rolled back
    assert scalar(eng, "SELECT version_num FROM workweave.alembic_version") == "0003"


# ---------------------------------------------------------------- PostgreSQL-enforced deletion paths
def test_new_runs_get_exactly_one_materialization_proof(client, engine):
    ws = open_company(client, "northstar", intent="FRESH")["workspace_id"]
    with engine.connect() as c:
        rows = c.execute(text("SELECT proof_source FROM workweave.demo_visitor_runs WHERE workspace_id=:w"), {"w": ws}).scalars().all()
    assert rows == ["MATERIALIZATION"]


def test_unauthorized_deletes_are_rejected_by_postgresql(client, engine):
    ws = run_with_history(client)  # live session, proof row, audit rows and a receipt

    # Sessions: never without the purge flag, never while ACTIVE and unexpired.
    rejected(engine, "DELETE FROM workweave.demo_visitor_sessions WHERE workspace_id=:w", "active, unexpired", w=ws)
    rejected(engine, "DELETE FROM workweave.demo_visitor_sessions WHERE workspace_id=:w", "active, unexpired", flag_ws=ws, w=ws)
    with engine.begin() as c:
        c.execute(text("UPDATE workweave.demo_visitor_sessions SET status='REVOKED' WHERE workspace_id=:w"), {"w": ws})
    rejected(engine, "DELETE FROM workweave.demo_visitor_sessions WHERE workspace_id=:w", "only allowed in the purge", w=ws)
    # Workspaces: never without the flag (append-only rows aside, the guard fires first on the row itself).
    rejected(engine, "DELETE FROM workweave.workspaces WHERE workspace_id=:w", "can only be deleted by the purge", w=ws)
    # Proof rows: immutable; removable only by the purge, after the workspace is gone.
    rejected(engine, "UPDATE workweave.demo_visitor_runs SET pack_version='x' WHERE workspace_id=:w", "immutable", w=ws)
    rejected(engine, "DELETE FROM workweave.demo_visitor_runs WHERE workspace_id=:w", "can only be removed by the purge", w=ws)
    rejected(engine, "DELETE FROM workweave.demo_visitor_runs WHERE workspace_id=:w", "can only be removed by the purge", flag_ws=ws, w=ws)
    # Append-only rows: a flag naming another workspace isn't enough.
    rejected(engine, "DELETE FROM workweave.audit_events WHERE workspace_id=:w", "append-only", flag_ws=uuid.uuid4(), w=ws)


def test_a_purge_without_valid_proof_is_rejected(engine):
    """Flags set correctly, DEMO workspace, visitor organization, but no proof row."""
    ws = sessionless_visitor_workspace(engine)
    with engine.connect() as c:
        org = c.execute(text("SELECT organization_id FROM workweave.workspaces WHERE workspace_id=:w"), {"w": ws}).scalar_one()
    with engine.begin() as c:
        c.execute(text("INSERT INTO workweave.audit_events (organization_id, workspace_id, action, resource_type, result, request_id) VALUES (:o, :w, 'test', 'test', 'COMMITTED', gen_random_uuid())"), {"o": org, "w": ws})
    rejected(engine, "DELETE FROM workweave.audit_events WHERE workspace_id=:w", "append-only", flag_ws=ws, w=ws)
    rejected(engine, "DELETE FROM workweave.workspaces WHERE workspace_id=:w", "purge of a proven", flag_ws=ws, w=ws)
    assert rows_in(engine, ws) == 2


def test_proof_cannot_be_forged_for_pack_originals_or_operational_workspaces(engine):
    with engine.connect() as c:
        northstar = c.execute(text("SELECT scenario_id, pack_version FROM workweave.scenario_catalog WHERE company_key='northstar'")).one()
    p = {"s": northstar.scenario_id, "pv": northstar.pack_version}
    insert = "INSERT INTO workweave.demo_visitor_runs (organization_id, workspace_id, scenario_id, pack_version, proof_source) VALUES (:o, :w, :s, :pv, 'MATERIALIZATION')"
    rejected(engine, insert, "not in a visitor organization", o=BASELINE_ORG, w=BASELINE_WS, **p)  # pack original (company_key set)
    org, op_ws = uuid.uuid4(), uuid.uuid4()
    with engine.begin() as c:
        c.execute(text("INSERT INTO workweave.organizations (organization_id, name) VALUES (:o, 'Operational org')"), {"o": org})
        c.execute(text("INSERT INTO workweave.workspaces (workspace_id, organization_id, kind) VALUES (:w, :o, 'OPERATIONAL')"), {"w": op_ws, "o": org})
    rejected(engine, insert, "foreign key", o=org, w=op_ws, **p)  # kind must be DEMO
    # Neither can be deleted under a purge flag either.
    rejected(engine, "DELETE FROM workweave.workspaces WHERE workspace_id=:w", "can only be deleted by the purge", flag_ws=op_ws, w=op_ws)
    rejected(engine, "DELETE FROM workweave.workspaces WHERE workspace_id=:w", "can only be deleted by the purge", flag_ws=BASELINE_WS, w=BASELINE_WS)


# ---------------------------------------------------------------- sessionless runs
def test_a_proven_run_without_sessions_stays_in_review_whatever_its_age(client, engine):
    ws = run_with_history(client)
    with engine.begin() as c:  # the run's sessions disappear (deleted legitimately under the purge flag)
        c.execute(text("UPDATE workweave.demo_visitor_sessions SET status='REVOKED', updated_at = now() - interval '2 days' WHERE workspace_id=:w"), {"w": ws})
    with engine.begin() as c:
        flagged(c, ws)
        c.execute(text("DELETE FROM workweave.demo_visitor_sessions WHERE workspace_id=:w"), {"w": ws})
    with engine.begin() as c:  # very old: age alone must never qualify it
        c.execute(text("UPDATE workweave.workspaces SET created_at = now() - interval '90 days' WHERE workspace_id=:w"), {"w": ws})
    before = rows_in(engine, ws)
    with engine.connect() as c:
        assert cleanup.candidates(c, 0, 10, uuid.UUID(ws)) == []
        assert {str(r["workspace_id"]): r["reason"] for r in cleanup.needs_review(c)}[ws] == "PROOF_WITHOUT_SESSION"
    done = cleanup.run(engine, confirm=True, grace_minutes=0, limit=500)
    assert [r["action"] for r in done if r["workspace_id"] == ws] == ["needs review"]
    assert rows_in(engine, ws) == before
    assert scalar(engine, "SELECT count(*) FROM workweave.demo_visitor_runs WHERE workspace_id=:w", w=ws) == 1


def test_a_full_purge_removes_the_proof_row_last(client, engine):
    ws = run_with_history(client)
    with engine.begin() as c:
        c.execute(text("UPDATE workweave.demo_visitor_sessions SET status='REVOKED', updated_at = now() - interval '2 hours' WHERE workspace_id=:w"), {"w": ws})
    with engine.connect() as c:
        (cand,) = cleanup.candidates(c, 0, 10, uuid.UUID(ws))
    purged = cleanup.purge_one(engine, cand, 0)
    assert purged and purged["demo_visitor_runs"] == 1
    assert scalar(engine, "SELECT count(*) FROM workweave.demo_visitor_runs WHERE workspace_id=:w", w=ws) == 0
    assert scalar(engine, "SELECT count(*) FROM workweave.workspaces WHERE workspace_id=:w", w=ws) == 0
