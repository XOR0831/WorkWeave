"""Indexing of promoted Exit KT knowledge (ADR-053): the attempt bookkeeping on knowledge_promotions.

Written 2026-10-15. Promotion already marks a new KT document version "PENDING" for the index, but
nothing ever indexed it. The backend's KT indexer (app/services/kt_index.py) now claims pending
promotions, embeds the approved text and marks them READY, or FAILED after its retries. These columns
are its lease and retry state, like the outbox's:
- index_attempts: attempts so far;
- index_locked_at: when a worker claimed it (a worker that stopped is taken over after a while);
- index_next_attempt_at: when it's due again (growing waits after a failure);
- index_error: a short summary of the last failure (never document text), for operators only;
- indexed_at: when it became READY.

Existing PENDING promotions become due at once, so they're indexed after this deploy. No other data
changes; index_status keeps its values (PENDING, READY, FAILED, REVOKED).

Revision ID: 0019
Revises: 0018
"""

from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE workweave.knowledge_promotions
            ADD COLUMN index_attempts integer NOT NULL DEFAULT 0 CHECK (index_attempts >= 0),
            ADD COLUMN index_locked_at timestamptz,
            ADD COLUMN index_next_attempt_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            ADD COLUMN index_error text CHECK (index_error IS NULL OR length(index_error) <= 300),
            ADD COLUMN indexed_at timestamptz;
        CREATE INDEX ix_knowledge_promotions_index_due
            ON workweave.knowledge_promotions (index_next_attempt_at) WHERE index_status = 'PENDING';
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP INDEX workweave.ix_knowledge_promotions_index_due;
        ALTER TABLE workweave.knowledge_promotions
            DROP COLUMN index_attempts,
            DROP COLUMN index_locked_at,
            DROP COLUMN index_next_attempt_at,
            DROP COLUMN index_error,
            DROP COLUMN indexed_at;
        """
    )
