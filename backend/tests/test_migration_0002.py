"""Migration 0002 against disposable scratch databases (never the local dev database)."""

import uuid

import pytest
from alembic import command
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from tests import prepare_db

LEGACY = ("demo_sessions", "demo_persona_grants")

SIGNATURE = """
SELECT 'col' AS k, c.relname || '.' || a.attname || ' ' || format_type(a.atttypid, a.atttypmod)
       || CASE WHEN a.attnotnull THEN ' NOT NULL' ELSE '' END || COALESCE(' DEFAULT ' || pg_get_expr(d.adbin, d.adrelid), '') AS v
FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid JOIN pg_namespace n ON n.oid = c.relnamespace
LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum
WHERE n.nspname = 'workweave' AND c.relname = ANY(:t) AND a.attnum > 0 AND NOT a.attisdropped
UNION ALL
SELECT 'con', c.relname || ' ' || k.conname || ' ' || pg_get_constraintdef(k.oid) || ' ' || k.condeferrable || k.condeferred
FROM pg_constraint k JOIN pg_class c ON c.oid = k.conrelid
WHERE c.relnamespace = 'workweave'::regnamespace AND c.relname = ANY(:t)
UNION ALL
SELECT 'idx', indexdef FROM pg_indexes WHERE schemaname = 'workweave' AND tablename = ANY(:t)
UNION ALL
SELECT 'trg', pg_get_triggerdef(tg.oid) FROM pg_trigger tg JOIN pg_class c ON c.oid = tg.tgrelid
WHERE NOT tg.tgisinternal AND c.relname = ANY(:t) AND c.relnamespace = 'workweave'::regnamespace
ORDER BY 1, 2
"""


def signature(eng, tables) -> list[tuple[str, str]]:
    with eng.connect() as c:
        return [tuple(r) for r in c.execute(text(SIGNATURE), {"t": list(tables)})]


def table_exists(eng, name: str) -> bool:
    with eng.connect() as c:
        return c.execute(text("SELECT to_regclass(:n) IS NOT NULL"), {"n": f"workweave.{name}"}).scalar_one()


def current(eng) -> str:
    with eng.connect() as c:
        return c.execute(text("SELECT version_num FROM workweave.alembic_version")).scalar_one()


@pytest.fixture()
def scratch():
    name = f"workweave_scratch_{uuid.uuid4().hex[:8]}"
    url = prepare_db.build(name, revision="0001", catalog=False)
    eng = create_engine(url)
    yield url, eng
    eng.dispose()
    prepare_db.drop(name)


def test_fresh_baseline_then_0001_then_0002(scratch):
    url, eng = scratch
    assert all(table_exists(eng, t) for t in LEGACY)
    command.upgrade(prepare_db.alembic_config(url), "0002")
    assert current(eng) == "0002"
    assert not any(table_exists(eng, t) for t in LEGACY)
    con = {r[1] for r in signature(eng, ["demo_visitor_sessions"]) if r[0] == "con"}
    # pg_get_constraintdef omits the schema when it's on the search path, so match without it.
    assert any(
        "demo_visitor_sessions_demo_workspace_fkey FOREIGN KEY (organization_id, workspace_id, workspace_kind) REFERENCES " in c
        and "workspaces(organization_id, workspace_id, kind)" in c
        for c in con
    )
    assert any("demo_visitor_sessions_workspace_kind_check CHECK ((workspace_kind = 'DEMO'::text))" in c for c in con)
    assert not any("demo_visitor_sessions_organization_id_workspace_id_fkey" in c for c in con)


def test_upgrade_downgrade_upgrade_restores_the_exact_legacy_schema(scratch):
    url, eng = scratch
    cfg = prepare_db.alembic_config(url)
    legacy_before = signature(eng, LEGACY)
    visitor_before = signature(eng, ["demo_visitor_sessions", "workspaces"])
    kinds = {k for k, _ in legacy_before}
    assert kinds == {"col", "con", "idx", "trg"}  # every object type is actually being compared
    assert sum(1 for k, _ in legacy_before if k == "con") >= 11 and sum(1 for k, _ in legacy_before if k == "trg") == 2
    command.upgrade(cfg, "0002")
    command.downgrade(cfg, "0001")
    assert current(eng) == "0001"
    assert signature(eng, LEGACY) == legacy_before
    assert signature(eng, ["demo_visitor_sessions", "workspaces"]) == visitor_before
    command.upgrade(cfg, "0002")
    assert current(eng) == "0002" and not any(table_exists(eng, t) for t in LEGACY)


def test_refuses_a_nonempty_legacy_table_and_changes_nothing(scratch):
    url, eng = scratch
    with eng.begin() as c:
        c.execute(
            text(
                """INSERT INTO workweave.demo_sessions (organization_id, workspace_id, scenario_id, token_hash, expires_at)
                   SELECT organization_id, workspace_id, scenario_id, 'legacy-row', now() + interval '1 hour'
                   FROM workweave.scenario_catalog WHERE company_key = 'northstar'"""
            )
        )
    with pytest.raises(DBAPIError, match="demo_sessions has 1 row"):
        command.upgrade(prepare_db.alembic_config(url), "0002")
    assert current(eng) == "0001"
    assert all(table_exists(eng, t) for t in LEGACY)  # atomic: nothing dropped


def test_refuses_existing_session_on_a_non_demo_workspace_without_relabelling(scratch):
    url, eng = scratch
    with eng.begin() as c:
        org, ws = uuid.uuid4(), uuid.uuid4()
        c.execute(text("INSERT INTO workweave.organizations (organization_id, name) VALUES (:o, 'Operational test org')"), {"o": org})
        c.execute(text("INSERT INTO workweave.workspaces (workspace_id, organization_id, kind) VALUES (:w, :o, 'OPERATIONAL')"), {"w": ws, "o": org})
        sid = c.execute(text("SELECT scenario_id FROM workweave.scenario_catalog WHERE company_key = 'northstar'")).scalar_one()
        c.execute(
            text("INSERT INTO workweave.demo_visitor_sessions (organization_id, workspace_id, scenario_id, pack_version, token_hash, expires_at) VALUES (:o, :w, :s, 'v', 'bad', now() + interval '1 hour')"),
            {"o": org, "w": ws, "s": sid},
        )
    with pytest.raises(DBAPIError, match="point at non-DEMO workspaces"):
        command.upgrade(prepare_db.alembic_config(url), "0002")
    assert current(eng) == "0001"
    with eng.connect() as c:
        assert c.execute(text("SELECT kind FROM workweave.workspaces WHERE workspace_id = :w"), {"w": ws}).scalar_one() == "OPERATIONAL"


def test_database_rejects_a_session_on_an_operational_workspace(engine):
    """Runs on workweave_test (baseline → 0001 → 0002)."""
    with pytest.raises(IntegrityError):
        with engine.begin() as c:
            org, ws = uuid.uuid4(), uuid.uuid4()
            c.execute(text("INSERT INTO workweave.organizations (organization_id, name) VALUES (:o, 'Main app org')"), {"o": org})
            c.execute(text("INSERT INTO workweave.workspaces (workspace_id, organization_id, kind) VALUES (:w, :o, 'OPERATIONAL')"), {"w": ws, "o": org})
            sid = c.execute(text("SELECT scenario_id FROM workweave.scenario_catalog WHERE company_key = 'northstar'")).scalar_one()
            c.execute(
                text("INSERT INTO workweave.demo_visitor_sessions (organization_id, workspace_id, scenario_id, pack_version, token_hash, expires_at) VALUES (:o, :w, :s, 'v', :t, now() + interval '1 hour')"),
                {"o": org, "w": ws, "s": sid, "t": uuid.uuid4().hex},
            )
    with pytest.raises(IntegrityError):
        with engine.begin() as c:
            c.execute(text("UPDATE workweave.demo_visitor_sessions SET workspace_kind = 'OPERATIONAL'"))
