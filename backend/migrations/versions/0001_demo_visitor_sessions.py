"""Demo visitor sessions, pack persona metadata and catalog presentation (additive).

Why new tables instead of the existing demo_sessions/demo_persona_grants: those carry a
composite FK (organization_id, workspace_id, scenario_id) -> scenario_catalog, which pins a
session to the pack's baseline workspace. ADR-024 / blueprint 12 and 16 require each visitor's
session and personas to live in an isolated organization/workspace copy. The legacy tables are
left untouched (unused) rather than altered.

Revision ID: 0001
Revises:
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE workweave.scenario_catalog
            ADD COLUMN presentation jsonb NOT NULL DEFAULT '{}'::jsonb;

        -- A materialized persona remembers which pack baseline employee it was copied from.
        ALTER TABLE workweave.employees
            ADD COLUMN baseline_employee_id uuid REFERENCES workweave.employees (employee_id);

        CREATE TABLE workweave.scenario_personas (
            scenario_persona_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            scenario_id uuid NOT NULL REFERENCES workweave.scenario_catalog (scenario_id),
            baseline_employee_id uuid NOT NULL REFERENCES workweave.employees (employee_id),
            display_order integer NOT NULL CHECK (display_order > 0),
            scenario_note text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (scenario_id, baseline_employee_id),
            UNIQUE (scenario_id, display_order)
        );

        CREATE TABLE workweave.demo_visitor_sessions (
            demo_visitor_session_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            organization_id uuid NOT NULL,
            workspace_id uuid NOT NULL,
            scenario_id uuid NOT NULL REFERENCES workweave.scenario_catalog (scenario_id),
            pack_version text NOT NULL,
            -- SHA-256 of an opaque random token; the token itself lives only in an HttpOnly cookie.
            token_hash text NOT NULL UNIQUE,
            status text NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'EXPIRED', 'REVOKED')),
            active_employee_id uuid,
            expires_at timestamptz NOT NULL,
            created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
            UNIQUE (organization_id, workspace_id, demo_visitor_session_id),
            FOREIGN KEY (organization_id, workspace_id) REFERENCES workweave.workspaces (organization_id, workspace_id),
            FOREIGN KEY (organization_id, workspace_id, active_employee_id)
                REFERENCES workweave.employees (organization_id, workspace_id, employee_id)
        );
        CREATE INDEX ix_demo_visitor_sessions_scope ON workweave.demo_visitor_sessions (organization_id, workspace_id);
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TABLE workweave.demo_visitor_sessions;
        DROP TABLE workweave.scenario_personas;
        ALTER TABLE workweave.employees DROP COLUMN baseline_employee_id;
        ALTER TABLE workweave.scenario_catalog DROP COLUMN presentation;
        """
    )
