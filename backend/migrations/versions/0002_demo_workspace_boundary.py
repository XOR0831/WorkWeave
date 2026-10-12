"""Remove unused legacy demo tables; enforce that visitor sessions attach only to DEMO workspaces.

Approved 2026-10-03 for implementation and disposable-database testing.

- Aborts (no partial change) if either legacy table has rows, or if any existing visitor session
  points at a non-DEMO workspace. Invalid data is reported, never relabelled.
- Drops demo_persona_grants, then demo_sessions, without CASCADE: any unexpected dependent object
  makes PostgreSQL refuse the drop and the whole migration rolls back.
- Replaces the two-column workspace FK on demo_visitor_sessions with a three-column FK that
  includes workspaces.kind, so the database rejects a session linked to an OPERATIONAL workspace.

src/local/postgres/01_schema.sql stays the immutable historical baseline: fresh databases apply it,
then 0001, then this migration. Downgrade recreates the empty legacy tables exactly as defined there.

Revision ID: 0002
Revises: 0001
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

PREFLIGHT = r"""
DO $preflight$
DECLARE
    n bigint;
    deps text;
BEGIN
    SELECT count(*) INTO n FROM workweave.demo_persona_grants;
    IF n > 0 THEN
        RAISE EXCEPTION '0002 aborted: workweave.demo_persona_grants has % row(s). Migrate or remove them deliberately first.', n;
    END IF;
    SELECT count(*) INTO n FROM workweave.demo_sessions;
    IF n > 0 THEN
        RAISE EXCEPTION '0002 aborted: workweave.demo_sessions has % row(s). Migrate or remove them deliberately first.', n;
    END IF;
    SELECT count(*) INTO n
    FROM workweave.demo_visitor_sessions s
    JOIN workweave.workspaces w ON w.organization_id = s.organization_id AND w.workspace_id = s.workspace_id
    WHERE w.kind <> 'DEMO';
    IF n > 0 THEN
        RAISE EXCEPTION '0002 aborted: % demo_visitor_sessions row(s) point at non-DEMO workspaces. Investigate them; this migration does not relabel data.', n;
    END IF;
    -- Foreign keys from other tables would block the drops below; report them by name.
    SELECT string_agg(conrelid::regclass || '.' || conname, ', ') INTO deps
    FROM pg_constraint
    WHERE contype = 'f'
      AND confrelid IN ('workweave.demo_sessions'::regclass, 'workweave.demo_persona_grants'::regclass)
      AND conrelid NOT IN ('workweave.demo_sessions'::regclass, 'workweave.demo_persona_grants'::regclass);
    IF deps IS NOT NULL THEN
        RAISE EXCEPTION '0002 aborted: unexpected foreign keys reference the legacy demo tables: %', deps;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'workweave.demo_visitor_sessions'::regclass
          AND conname = 'demo_visitor_sessions_organization_id_workspace_id_fkey'
    ) THEN
        RAISE EXCEPTION '0002 aborted: expected FK demo_visitor_sessions_organization_id_workspace_id_fkey (from 0001) was not found.';
    END IF;
END
$preflight$;
"""

UPGRADE = """
DROP TABLE workweave.demo_persona_grants;
DROP TABLE workweave.demo_sessions;

ALTER TABLE workweave.workspaces
    ADD CONSTRAINT workspaces_scope_kind_key UNIQUE (organization_id, workspace_id, kind);

ALTER TABLE workweave.demo_visitor_sessions
    ADD COLUMN workspace_kind text NOT NULL DEFAULT 'DEMO'
        CONSTRAINT demo_visitor_sessions_workspace_kind_check CHECK (workspace_kind = 'DEMO');

ALTER TABLE workweave.demo_visitor_sessions
    DROP CONSTRAINT demo_visitor_sessions_organization_id_workspace_id_fkey;

ALTER TABLE workweave.demo_visitor_sessions
    ADD CONSTRAINT demo_visitor_sessions_demo_workspace_fkey
    FOREIGN KEY (organization_id, workspace_id, workspace_kind)
    REFERENCES workweave.workspaces (organization_id, workspace_id, kind);
"""

# Verbatim from src/local/postgres/01_schema.sql (tables, FKs, FK indexes, scope-time indexes, triggers).
LEGACY_DDL = """
CREATE TABLE workweave.demo_sessions (
    demo_session_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    scenario_id uuid NOT NULL,
    token_hash text NOT NULL,
    status text NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'EXPIRED', 'REVOKED')),
    expires_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    UNIQUE (organization_id, workspace_id, demo_session_id),
    FOREIGN KEY (organization_id, workspace_id) REFERENCES workweave.workspaces (organization_id, workspace_id),
    UNIQUE (organization_id, workspace_id, token_hash)
);

CREATE TABLE workweave.demo_persona_grants (
    demo_persona_grant_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    demo_session_id uuid NOT NULL,
    employee_id uuid NOT NULL,
    allowed_actions jsonb NOT NULL DEFAULT '[]'::jsonb,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    UNIQUE (organization_id, workspace_id, demo_persona_grant_id),
    FOREIGN KEY (organization_id, workspace_id) REFERENCES workweave.workspaces (organization_id, workspace_id),
    UNIQUE (organization_id, workspace_id, demo_session_id, employee_id)
);

ALTER TABLE workweave.demo_sessions ADD CONSTRAINT fk_demo_sessions_163
    FOREIGN KEY (organization_id, workspace_id, scenario_id)
    REFERENCES workweave.scenario_catalog (organization_id, workspace_id, scenario_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_demo_sessions_fk_163 ON workweave.demo_sessions (organization_id, workspace_id, scenario_id);
ALTER TABLE workweave.demo_persona_grants ADD CONSTRAINT fk_demo_persona_grants_164
    FOREIGN KEY (organization_id, workspace_id, demo_session_id)
    REFERENCES workweave.demo_sessions (organization_id, workspace_id, demo_session_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_demo_persona_grants_fk_164 ON workweave.demo_persona_grants (organization_id, workspace_id, demo_session_id);
ALTER TABLE workweave.demo_persona_grants ADD CONSTRAINT fk_demo_persona_grants_165
    FOREIGN KEY (organization_id, workspace_id, employee_id)
    REFERENCES workweave.employees (organization_id, workspace_id, employee_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_demo_persona_grants_fk_165 ON workweave.demo_persona_grants (organization_id, workspace_id, employee_id);
CREATE INDEX ix_demo_sessions_scope_time ON workweave.demo_sessions (organization_id, workspace_id, created_at);
CREATE INDEX ix_demo_persona_grants_scope_time ON workweave.demo_persona_grants (organization_id, workspace_id, created_at);
CREATE TRIGGER touch_demo_sessions BEFORE UPDATE ON workweave.demo_sessions FOR EACH ROW EXECUTE FUNCTION workweave.touch_revision();
CREATE TRIGGER touch_demo_persona_grants BEFORE UPDATE ON workweave.demo_persona_grants FOR EACH ROW EXECUTE FUNCTION workweave.touch_revision();
"""

DOWNGRADE = """
ALTER TABLE workweave.demo_visitor_sessions DROP CONSTRAINT demo_visitor_sessions_demo_workspace_fkey;
ALTER TABLE workweave.demo_visitor_sessions
    ADD CONSTRAINT demo_visitor_sessions_organization_id_workspace_id_fkey
    FOREIGN KEY (organization_id, workspace_id) REFERENCES workweave.workspaces (organization_id, workspace_id);
ALTER TABLE workweave.demo_visitor_sessions DROP COLUMN workspace_kind;
ALTER TABLE workweave.workspaces DROP CONSTRAINT workspaces_scope_kind_key;
"""


def upgrade() -> None:
    op.execute(PREFLIGHT)
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
    op.execute(LEGACY_DDL)
