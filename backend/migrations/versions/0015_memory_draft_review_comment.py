"""The reviewer's comment on a knowledge note (ADR-041).

Written for review 2026-10-10 (not applied to the local dev database).

Rejecting a submitted note needs a reason, and its author sees it with the note (the Companion's
notes list). Approval may carry an optional comment. Additive and nullable; downgrade drops it.

Revision ID: 0015
Revises: 0014
"""

from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE workweave.memory_drafts ADD COLUMN review_comment text CHECK (review_comment IS NULL OR length(review_comment) <= 2000);")


def downgrade() -> None:
    op.execute("ALTER TABLE workweave.memory_drafts DROP COLUMN review_comment;")
