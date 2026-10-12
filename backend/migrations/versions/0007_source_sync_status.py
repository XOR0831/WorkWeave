"""Use source-sync terminology for employee work-item reports.

The local dev table was already changed to this shape outside Alembic. This
migration upgrades databases built from 0006 and accepts that existing dev
shape without changing report data.

Revision ID: 0007
Revises: 0006
"""

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $migration$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'workweave'
                  AND table_name = 'work_item_reported_updates'
                  AND column_name = 'verification_status'
            ) THEN
                IF EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema = 'workweave'
                      AND table_name = 'work_item_reported_updates'
                      AND column_name = 'source_sync_status'
                ) THEN
                    RAISE EXCEPTION 'Both report status columns exist; resolve the schema before upgrading';
                END IF;

                ALTER TABLE workweave.work_item_reported_updates
                    DROP CONSTRAINT work_item_reported_updates_verification_status_check;
                ALTER TABLE workweave.work_item_reported_updates
                    RENAME COLUMN verification_status TO source_sync_status;
                UPDATE workweave.work_item_reported_updates
                SET source_sync_status = CASE source_sync_status
                    WHEN 'PENDING' THEN 'AWAITING_SOURCE'
                    WHEN 'VERIFIED' THEN 'MATCHED'
                    WHEN 'CONFLICTED' THEN 'NEEDS_REVIEW'
                END;
                ALTER TABLE workweave.work_item_reported_updates
                    ALTER COLUMN source_sync_status SET DEFAULT 'AWAITING_SOURCE';
                ALTER TABLE workweave.work_item_reported_updates
                    ADD CONSTRAINT work_item_reported_updates_source_sync_status_check
                    CHECK (source_sync_status IN ('AWAITING_SOURCE', 'MATCHED', 'NEEDS_REVIEW'));
                ALTER TABLE workweave.work_item_reported_updates
                    RENAME COLUMN verified_at TO source_reconciled_at;
            ELSIF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'workweave'
                  AND table_name = 'work_item_reported_updates'
                  AND column_name = 'source_sync_status'
            ) THEN
                RAISE EXCEPTION 'No report status column found; resolve the schema before upgrading';
            ELSIF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'workweave'
                  AND table_name = 'work_item_reported_updates'
                  AND column_name = 'source_reconciled_at'
            ) THEN
                RAISE EXCEPTION 'source_reconciled_at is missing; resolve the schema before upgrading';
            END IF;

            IF to_regclass('workweave.ix_work_item_reported_updates_item_verification_time') IS NOT NULL THEN
                ALTER INDEX workweave.ix_work_item_reported_updates_item_verification_time
                    RENAME TO ix_work_item_reported_updates_item_source_sync_time;
            END IF;
        END
        $migration$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE workweave.work_item_reported_updates
            DROP CONSTRAINT work_item_reported_updates_source_sync_status_check;
        UPDATE workweave.work_item_reported_updates
        SET source_sync_status = CASE source_sync_status
            WHEN 'AWAITING_SOURCE' THEN 'PENDING'
            WHEN 'MATCHED' THEN 'VERIFIED'
            WHEN 'NEEDS_REVIEW' THEN 'CONFLICTED'
        END;
        ALTER TABLE workweave.work_item_reported_updates
            ALTER COLUMN source_sync_status SET DEFAULT 'PENDING';
        ALTER TABLE workweave.work_item_reported_updates
            ADD CONSTRAINT work_item_reported_updates_verification_status_check
            CHECK (source_sync_status IN ('PENDING', 'VERIFIED', 'CONFLICTED'));
        ALTER TABLE workweave.work_item_reported_updates
            RENAME COLUMN source_sync_status TO verification_status;
        ALTER TABLE workweave.work_item_reported_updates
            RENAME COLUMN source_reconciled_at TO verified_at;
        ALTER INDEX workweave.ix_work_item_reported_updates_item_source_sync_time
            RENAME TO ix_work_item_reported_updates_item_verification_time;
        """
    )
