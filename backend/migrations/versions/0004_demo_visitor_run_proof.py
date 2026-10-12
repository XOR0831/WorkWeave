"""Durable proof that a workspace is a demo visitor run; PostgreSQL rejects purges without it.

Approved for review 2026-10-03 (not applied to the local dev database).

Migration 0003 lets the cleanup delete append-only rows in a flagged DEMO workspace that is not a
pack original. Its only evidence of a visitor run lived in the cleanup worker (session rows), which
the purge itself deletes. This migration stores that evidence in PostgreSQL and makes every purge
deletion path require it:

- demo_visitor_runs: one immutable row per visitor run, written when the run is materialized.
  Existing runs are backfilled ONLY from existing demo_visitor_sessions rows: never inferred from
  DEMO kind, a NULL company_key or workspace age. Its insert trigger refuses pack originals,
  non-visitor organizations and (through a three-column FK) any non-DEMO workspace.
- workweave.visitor_run_purge_allowed(org, ws): true only inside the cleanup transaction (the 0003
  transaction-local flags naming this workspace) for a DEMO workspace with a proof row, in a
  visitor organization, that is not a pack original.
- Deletion guards using it: append-only tables (reject_history_mutation), demo_visitor_sessions
  (also never an ACTIVE unexpired session), workspaces, and demo_visitor_runs itself (only after
  its workspace and sessions are gone). Proof rows are never updated.

Downgrade restores the 0003 trigger function exactly and drops the new objects.

Revision ID: 0004
Revises: 0003
"""

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

# reject_history_mutation() exactly as migration 0003 created it (restored on downgrade).
FUNCTION_0003 = """
CREATE OR REPLACE FUNCTION workweave.reject_history_mutation() RETURNS trigger LANGUAGE plpgsql AS $body$
BEGIN
    IF TG_OP = 'DELETE'
       AND current_setting('workweave.retention_purge', true) = 'demo-visitor'
       AND current_setting('workweave.retention_purge_workspace', true) = OLD.workspace_id::text
       AND EXISTS (
            SELECT 1 FROM workweave.workspaces w
            WHERE w.organization_id = OLD.organization_id AND w.workspace_id = OLD.workspace_id AND w.kind = 'DEMO')
       AND NOT EXISTS (
            SELECT 1 FROM workweave.scenario_catalog c
            WHERE c.organization_id = OLD.organization_id AND c.workspace_id = OLD.workspace_id)
    THEN
        RETURN OLD;  -- reviewed exception: purge of one expired demo visitor run (migration 0003)
    END IF;
    RAISE EXCEPTION '% is append-only: updates/deletes require a separately reviewed retention migration', TG_TABLE_NAME;
END;
$body$;
"""

UPGRADE = """
CREATE TABLE workweave.demo_visitor_runs (
    organization_id uuid NOT NULL,
    workspace_id uuid PRIMARY KEY,
    workspace_kind text NOT NULL DEFAULT 'DEMO' CHECK (workspace_kind = 'DEMO'),
    scenario_id uuid NOT NULL REFERENCES workweave.scenario_catalog (scenario_id),
    pack_version text NOT NULL,
    proof_source text NOT NULL CHECK (proof_source IN ('MATERIALIZATION', 'BACKFILL_FROM_SESSION')),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (organization_id, workspace_id),
    -- Deferrable so the purge can delete the workspace while its proof row still exists.
    FOREIGN KEY (organization_id, workspace_id, workspace_kind)
        REFERENCES workweave.workspaces (organization_id, workspace_id, kind) DEFERRABLE INITIALLY IMMEDIATE
);
COMMENT ON TABLE workweave.demo_visitor_runs IS
    'Immutable proof that a DEMO workspace is a visitor run (migration 0004). Required by every purge deletion path.';

CREATE FUNCTION workweave.visitor_run_purge_allowed(p_org uuid, p_ws uuid) RETURNS boolean
LANGUAGE sql STABLE AS $body$
    SELECT current_setting('workweave.retention_purge', true) = 'demo-visitor'
       AND current_setting('workweave.retention_purge_workspace', true) = p_ws::text
       AND EXISTS (
            SELECT 1 FROM workweave.demo_visitor_runs r
            JOIN workweave.workspaces w
              ON w.organization_id = r.organization_id AND w.workspace_id = r.workspace_id AND w.kind = 'DEMO'
            JOIN workweave.organizations o ON o.organization_id = r.organization_id AND o.company_key IS NULL
            WHERE r.organization_id = p_org AND r.workspace_id = p_ws)
       AND NOT EXISTS (
            SELECT 1 FROM workweave.scenario_catalog c WHERE c.organization_id = p_org AND c.workspace_id = p_ws)
$body$;

CREATE FUNCTION workweave.guard_demo_visitor_run() RETURNS trigger LANGUAGE plpgsql AS $body$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NOT EXISTS (SELECT 1 FROM workweave.organizations o WHERE o.organization_id = NEW.organization_id AND o.company_key IS NULL) THEN
            RAISE EXCEPTION 'demo_visitor_runs: % is not in a visitor organization', NEW.workspace_id;
        END IF;
        IF EXISTS (SELECT 1 FROM workweave.scenario_catalog c WHERE c.organization_id = NEW.organization_id AND c.workspace_id = NEW.workspace_id) THEN
            RAISE EXCEPTION 'demo_visitor_runs: % is a pack original', NEW.workspace_id;
        END IF;
        RETURN NEW;
    ELSIF TG_OP = 'UPDATE' THEN
        RAISE EXCEPTION 'demo_visitor_runs is immutable';
    END IF;
    -- DELETE: only inside the purge of this workspace, after its workspace and sessions are gone.
    IF current_setting('workweave.retention_purge', true) = 'demo-visitor'
       AND current_setting('workweave.retention_purge_workspace', true) = OLD.workspace_id::text
       AND NOT EXISTS (SELECT 1 FROM workweave.workspaces w WHERE w.workspace_id = OLD.workspace_id)
       AND NOT EXISTS (SELECT 1 FROM workweave.demo_visitor_sessions s WHERE s.workspace_id = OLD.workspace_id)
    THEN
        RETURN OLD;
    END IF;
    RAISE EXCEPTION 'demo_visitor_runs: proof for % can only be removed by the purge of that run, after its workspace', OLD.workspace_id;
END;
$body$;
CREATE TRIGGER guard_demo_visitor_runs BEFORE INSERT OR UPDATE OR DELETE ON workweave.demo_visitor_runs
    FOR EACH ROW EXECUTE FUNCTION workweave.guard_demo_visitor_run();

CREATE FUNCTION workweave.guard_demo_visitor_session_delete() RETURNS trigger LANGUAGE plpgsql AS $body$
BEGIN
    IF OLD.status = 'ACTIVE' AND OLD.expires_at > now() THEN
        RAISE EXCEPTION 'demo_visitor_sessions: an active, unexpired session cannot be deleted';
    END IF;
    IF NOT workweave.visitor_run_purge_allowed(OLD.organization_id, OLD.workspace_id) THEN
        RAISE EXCEPTION 'demo_visitor_sessions: deletes are only allowed in the purge of a proven visitor run';
    END IF;
    RETURN OLD;
END;
$body$;
CREATE TRIGGER guard_demo_visitor_session_delete BEFORE DELETE ON workweave.demo_visitor_sessions
    FOR EACH ROW EXECUTE FUNCTION workweave.guard_demo_visitor_session_delete();

CREATE FUNCTION workweave.guard_workspace_delete() RETURNS trigger LANGUAGE plpgsql AS $body$
BEGIN
    IF NOT workweave.visitor_run_purge_allowed(OLD.organization_id, OLD.workspace_id) THEN
        RAISE EXCEPTION 'workspaces: % can only be deleted by the purge of a proven demo visitor run', OLD.workspace_id;
    END IF;
    RETURN OLD;
END;
$body$;
CREATE TRIGGER guard_workspace_delete BEFORE DELETE ON workweave.workspaces
    FOR EACH ROW EXECUTE FUNCTION workweave.guard_workspace_delete();

CREATE OR REPLACE FUNCTION workweave.reject_history_mutation() RETURNS trigger LANGUAGE plpgsql AS $body$
BEGIN
    IF TG_OP = 'DELETE' AND workweave.visitor_run_purge_allowed(OLD.organization_id, OLD.workspace_id) THEN
        RETURN OLD;  -- reviewed exception: purge of one proven, expired demo visitor run (0003, 0004)
    END IF;
    RAISE EXCEPTION '% is append-only: updates/deletes require a separately reviewed retention migration', TG_TABLE_NAME;
END;
$body$;
"""

# Proof comes only from existing visitor sessions: one row per workspace that has any session.
BACKFILL = """
DO $backfill$
DECLARE
    expected bigint;
    written bigint;
BEGIN
    IF EXISTS (
        SELECT 1 FROM workweave.demo_visitor_sessions
        GROUP BY organization_id, workspace_id
        HAVING count(DISTINCT (scenario_id, pack_version)) > 1
    ) THEN
        RAISE EXCEPTION '0004 backfill: a workspace has sessions from more than one scenario/pack version';
    END IF;

    INSERT INTO workweave.demo_visitor_runs (organization_id, workspace_id, scenario_id, pack_version, proof_source, created_at)
    SELECT DISTINCT ON (s.organization_id, s.workspace_id)
           s.organization_id, s.workspace_id, s.scenario_id, s.pack_version, 'BACKFILL_FROM_SESSION', s.created_at
    FROM workweave.demo_visitor_sessions s
    ORDER BY s.organization_id, s.workspace_id, s.created_at;
    GET DIAGNOSTICS written = ROW_COUNT;

    SELECT count(*) INTO expected FROM (SELECT DISTINCT organization_id, workspace_id FROM workweave.demo_visitor_sessions) x;
    IF written <> expected THEN
        RAISE EXCEPTION '0004 backfill: expected % proof rows, wrote %', expected, written;
    END IF;
    RAISE NOTICE '0004 backfill: % visitor run proof row(s) from existing sessions', written;
END
$backfill$;
"""

DOWNGRADE = """
DROP TRIGGER guard_workspace_delete ON workweave.workspaces;
DROP FUNCTION workweave.guard_workspace_delete();
DROP TRIGGER guard_demo_visitor_session_delete ON workweave.demo_visitor_sessions;
DROP FUNCTION workweave.guard_demo_visitor_session_delete();
DROP TABLE workweave.demo_visitor_runs;
DROP FUNCTION workweave.guard_demo_visitor_run();
"""


def upgrade() -> None:
    op.execute(UPGRADE)
    op.execute(BACKFILL)


def downgrade() -> None:
    op.execute(FUNCTION_0003)  # stops calling visitor_run_purge_allowed before it is dropped
    op.execute(DOWNGRADE)
    op.execute("DROP FUNCTION workweave.visitor_run_purge_allowed(uuid, uuid);")
