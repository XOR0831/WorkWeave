"""Store employee work-item reports separately from authoritative source status.

Revision ID: 0006
Revises: 0005
"""

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE workweave.work_item_assignments
            ADD CONSTRAINT uq_work_item_assignments_report_owner
            UNIQUE (organization_id, workspace_id, assignment_id, work_item_id, employee_id);

        CREATE TABLE workweave.work_item_reported_updates (
            reported_update_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            organization_id uuid NOT NULL,
            workspace_id uuid NOT NULL,
            assignment_id uuid NOT NULL,
            work_item_id uuid NOT NULL,
            employee_id uuid NOT NULL,
            work_session_id uuid,
            reported_status text,
            blocker text,
            description text,
            verification_status text NOT NULL DEFAULT 'PENDING'
                CHECK (verification_status IN ('PENDING', 'VERIFIED', 'CONFLICTED')),
            source_status_at_report text,
            reported_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            verified_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
            CONSTRAINT fk_work_item_reported_updates_assignment
                FOREIGN KEY (organization_id, workspace_id, assignment_id, work_item_id, employee_id)
                REFERENCES workweave.work_item_assignments
                    (organization_id, workspace_id, assignment_id, work_item_id, employee_id)
                DEFERRABLE INITIALLY IMMEDIATE,
            CONSTRAINT fk_work_item_reported_updates_work_session
                FOREIGN KEY (organization_id, workspace_id, work_session_id)
                REFERENCES workweave.work_sessions
                    (organization_id, workspace_id, work_session_id)
                DEFERRABLE INITIALLY IMMEDIATE
        );

        CREATE INDEX ix_work_item_reported_updates_assignment_time
            ON workweave.work_item_reported_updates
            (organization_id, workspace_id, assignment_id, reported_at DESC);
        CREATE INDEX ix_work_item_reported_updates_item_verification_time
            ON workweave.work_item_reported_updates
            (organization_id, workspace_id, work_item_id, verification_status, reported_at DESC);

        CREATE TRIGGER touch_work_item_reported_updates
            BEFORE UPDATE ON workweave.work_item_reported_updates
            FOR EACH ROW EXECUTE FUNCTION workweave.touch_revision();
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TABLE workweave.work_item_reported_updates;
        ALTER TABLE workweave.work_item_assignments
            DROP CONSTRAINT uq_work_item_assignments_report_owner;
        """
    )
