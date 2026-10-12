"""Shift Handover copilot conversations (docs/31, ADR-043).

Written for review 2026-10-10 (not applied to the local dev database).

One conversation per handover and shift lead: the lead's messages, the graph's answers (with the
records they cite, what the records don't say, and any edit it proposes; a proposal is never applied
by itself) and its clarification questions from a gap check. Private to that lead: never in
notifications or other leads' views, and never copied into a demo run.

Append-only like other conversation records; downgrade drops the table.

Revision ID: 0016
Revises: 0015
"""

from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE workweave.handover_copilot_messages (
            message_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            organization_id uuid NOT NULL,
            workspace_id uuid NOT NULL,
            handover_id uuid NOT NULL,
            employee_id uuid NOT NULL,
            sender text NOT NULL CHECK (sender IN ('LEAD', 'AI', 'SYSTEM')),
            kind text NOT NULL DEFAULT 'MESSAGE' CHECK (kind IN ('MESSAGE', 'QUESTION', 'BRIEF')),
            content text NOT NULL CHECK (length(content) BETWEEN 1 AND 8000),
            citations jsonb NOT NULL DEFAULT '[]'::jsonb,
            unknowns jsonb NOT NULL DEFAULT '[]'::jsonb,
            proposed_edit jsonb,
            model text,
            created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (organization_id, workspace_id, message_id),
            FOREIGN KEY (organization_id, workspace_id) REFERENCES workweave.workspaces (organization_id, workspace_id),
            FOREIGN KEY (organization_id, workspace_id, handover_id) REFERENCES workweave.shift_handovers (organization_id, workspace_id, handover_id),
            FOREIGN KEY (organization_id, workspace_id, employee_id) REFERENCES workweave.employees (organization_id, workspace_id, employee_id)
        );
        CREATE INDEX handover_copilot_messages_thread ON workweave.handover_copilot_messages (organization_id, workspace_id, handover_id, employee_id, created_at);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE workweave.handover_copilot_messages;")
