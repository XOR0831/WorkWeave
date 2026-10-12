"""Reviewed retention exception: purge expired demo visitor runs, nothing else.

Approved 2026-10-03 (product owner: "Retention migration").

The schema's append-only tables reject every UPDATE/DELETE through
workweave.reject_history_mutation() ("updates/deletes require a separately reviewed retention
migration"). This is that migration, scoped as narrowly as possible. A DELETE (never an UPDATE)
is allowed only when ALL of the following hold for the row's workspace:

1. the transaction set `workweave.retention_purge = 'demo-visitor'` (transaction-local), and
2. `workweave.retention_purge_workspace` names exactly this row's workspace, and
3. that workspace is kind DEMO, and
4. it is not a pack original (no scenario_catalog row lives in it).

Operational workspaces and pack originals therefore stay strictly append-only. Only the
cleanup worker (app/workers/cleanup.py) sets these flags, after checking that the run has no live
session. demo_workspace_purges keeps a content-free record of every purge.

Revision ID: 0003
Revises: 0002
"""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

ORIGINAL_FUNCTION = """
CREATE OR REPLACE FUNCTION workweave.reject_history_mutation() RETURNS trigger LANGUAGE plpgsql AS $body$
BEGIN
    RAISE EXCEPTION '% is append-only: updates/deletes require a separately reviewed retention migration', TG_TABLE_NAME;
END;
$body$;
"""

UPGRADE = """
CREATE TABLE workweave.demo_workspace_purges (
    demo_workspace_purge_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    workspace_id uuid NOT NULL UNIQUE,
    scenario_id uuid,
    reason text NOT NULL CHECK (reason IN ('EXPIRED', 'REVOKED', 'NO_LIVE_SESSION')),
    row_counts jsonb NOT NULL DEFAULT '{}'::jsonb,
    purged_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);
COMMENT ON TABLE workweave.demo_workspace_purges IS
    'Content-free log of purged demo visitor workspaces (no FK: the workspace no longer exists).';

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


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(ORIGINAL_FUNCTION)
    op.execute("DROP TABLE workweave.demo_workspace_purges;")
