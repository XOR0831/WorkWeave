"""Featured personas and their showcase on the demo page (owner decision 2026-10-10).

Written for review 2026-10-10 (not applied to the local dev database).

The demo page shows each pack's featured personas (up to four) with what each one lets a visitor
try ("Use Sam to test AI Onboarding", then a short feature list). Every persona stays reachable from
the persona switcher inside WorkWeave. Both values come from the reviewed pack (catalog.json, loaded
by `sync-catalog`) and are part of the pack's content hash, like scenario_note.

Downgrade drops both columns.

Revision ID: 0011
Revises: 0010
"""

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE workweave.scenario_personas
            ADD COLUMN featured boolean NOT NULL DEFAULT false,
            ADD COLUMN showcase jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(showcase) = 'object');
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE workweave.scenario_personas DROP COLUMN showcase, DROP COLUMN featured;")
