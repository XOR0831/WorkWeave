"""Where a persistent handover item sits in the handover document (owner default 2026-10-09).

Written for review 2026-10-10 (not applied to the local dev database).

Published entries already record their section; the draft needs the item's current section too, so
the lead's document can show it and items added from a suggestion keep the section they were added
to. Existing items take the section of their latest published entry.

Downgrade drops the column (published entries keep their own section).

Revision ID: 0012
Revises: 0011
"""

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE workweave.handover_items ADD COLUMN section_id uuid;
        UPDATE workweave.handover_items i SET section_id = latest.section_id
        FROM (
            SELECT DISTINCT ON (e.handover_item_id) e.handover_item_id, e.section_id
            FROM workweave.handover_entries e
            JOIN workweave.handover_publications p ON p.organization_id = e.organization_id AND p.workspace_id = e.workspace_id
                 AND p.publication_id = e.publication_id
            ORDER BY e.handover_item_id, p.published_at DESC
        ) latest
        WHERE latest.handover_item_id = i.handover_item_id;
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE workweave.handover_items DROP COLUMN section_id;")
