"""Automatic competency-based assignment, and why each assignment was made (ADR-035).

Written for review 2026-10-10 (not applied to the local dev database).

- assignment_source gains AUTOMATIC: WorkWeave assigned the ticket at the start of the shift by the
  competency rule; assigned_by_employee_id stays NULL (no person chose it). A shift lead can override
  it, which cancels it and creates a MANUAL assignment.
- match_data keeps why this person got the ticket, as it was when assigned: the ticket's competency
  requirements against the person's validated evidence, availability, current workload, the rule
  version, and how many teammates were compared. It holds no raw learning data (blueprint 04).

Downgrade turns AUTOMATIC rows into MANUAL ones (keeping them) and drops match_data.

Revision ID: 0010
Revises: 0009
"""

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE workweave.work_item_assignments DROP CONSTRAINT work_item_assignments_assignment_source_check;
        ALTER TABLE workweave.work_item_assignments ADD CONSTRAINT work_item_assignments_assignment_source_check
            CHECK (assignment_source IN ('MANUAL', 'AI_RECOMMENDED', 'HANDOVER', 'EXTERNAL_SYSTEM', 'AUTOMATIC'));
        ALTER TABLE workweave.work_item_assignments
            ADD COLUMN match_data jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(match_data) = 'object');
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE workweave.work_item_assignments SET assignment_source = 'MANUAL' WHERE assignment_source = 'AUTOMATIC';
        ALTER TABLE workweave.work_item_assignments DROP CONSTRAINT work_item_assignments_assignment_source_check;
        ALTER TABLE workweave.work_item_assignments ADD CONSTRAINT work_item_assignments_assignment_source_check
            CHECK (assignment_source IN ('MANUAL', 'AI_RECOMMENDED', 'HANDOVER', 'EXTERNAL_SYSTEM'));
        ALTER TABLE workweave.work_item_assignments DROP COLUMN match_data;
        """
    )
