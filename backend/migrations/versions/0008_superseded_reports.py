"""Let a newer employee report supersede an older one that is still awaiting the ticket system.

Written for review 2026-10-08 (not applied to the local dev database).

An employee can say "in progress", then "blocked", then "done" before the ticket system catches up.
Only the latest report per assignment is matched against the ticket system (ADR-033); older ones
still awaiting it become SUPERSEDED instead of waiting forever or being deleted.

Downgrade maps SUPERSEDED back to AWAITING_SOURCE (the 0007 states).

Revision ID: 0008
Revises: 0007
"""

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE workweave.work_item_reported_updates
            DROP CONSTRAINT work_item_reported_updates_source_sync_status_check;
        ALTER TABLE workweave.work_item_reported_updates
            ADD CONSTRAINT work_item_reported_updates_source_sync_status_check
            CHECK (source_sync_status IN ('AWAITING_SOURCE', 'MATCHED', 'NEEDS_REVIEW', 'SUPERSEDED'));
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE workweave.work_item_reported_updates
            DROP CONSTRAINT work_item_reported_updates_source_sync_status_check;
        UPDATE workweave.work_item_reported_updates
            SET source_sync_status = 'AWAITING_SOURCE' WHERE source_sync_status = 'SUPERSEDED';
        ALTER TABLE workweave.work_item_reported_updates
            ADD CONSTRAINT work_item_reported_updates_source_sync_status_check
            CHECK (source_sync_status IN ('AWAITING_SOURCE', 'MATCHED', 'NEEDS_REVIEW'));
        """
    )
