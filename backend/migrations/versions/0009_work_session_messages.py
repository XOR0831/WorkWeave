"""Save the Work Companion conversation, and record the report type the AI engine writes.

Written for review 2026-10-09 (not applied to the local dev database).

- work_session_messages: the employee's messages and the companion's replies, in order. The AI
  engineer's graph keeps only its latest message, so the backend saves each exchange after a turn
  (ADR-034). A reply keeps the validated ui_action and the source chunks it used; excerpts are
  resolved when read, so a revoked or superseded source is never shown as current guidance.
  Private to the session's employee: not used by manager analytics, shared search or previews.
- work_item_reported_updates.update_type: STATUS_CHANGE, BLOCKER, BLOCKER_RESOLVED or
  PROGRESS_UPDATE, written by the engine (NULL for reports made with the Companion's report form).
  The local dev table already has this column (added outside Alembic); this adds it where missing.

Downgrade drops the messages table and the update_type check, and keeps the column, which the
engine needs and which the dev database had before this migration.

Revision ID: 0009
Revises: 0008
"""

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE workweave.work_item_reported_updates ADD COLUMN IF NOT EXISTS update_type text;
        ALTER TABLE workweave.work_item_reported_updates
            ADD CONSTRAINT work_item_reported_updates_update_type_check
            CHECK (update_type IS NULL OR update_type IN ('STATUS_CHANGE', 'BLOCKER', 'BLOCKER_RESOLVED', 'PROGRESS_UPDATE'));

        CREATE TABLE workweave.work_session_messages (
            message_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            organization_id uuid NOT NULL,
            workspace_id uuid NOT NULL,
            work_session_id uuid NOT NULL,
            seq bigint GENERATED ALWAYS AS IDENTITY,
            sender text NOT NULL CHECK (sender IN ('EMPLOYEE', 'AI', 'SYSTEM')),
            -- The employee message a reply answers (NULL for the opening brief).
            client_turn_id uuid,
            input_kind text CHECK (input_kind IS NULL OR input_kind IN ('TEXT', 'VOICE_TRANSCRIPT')),
            text text NOT NULL CHECK (length(text) BETWEEN 1 AND 20000),
            provenance text NOT NULL CHECK (provenance IN ('EMPLOYEE_INPUT', 'WORK_ENGINE', 'BACKEND_RECORD')),
            ui_action text CHECK (ui_action IS NULL OR ui_action IN (
                'SHOW_BRIEFING', 'SHOW_WORK_ITEMS', 'SHOW_WORK_UPDATES', 'SHOW_FOCUS_PLAN',
                'SHOW_GUIDANCE', 'SHOW_DELEGATION_PROPOSAL', 'NO_VIEW_CHANGE', 'REQUEST_CLARIFICATION')),
            resource_refs jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(resource_refs) = 'array'),
            -- Source chunk references ({chunk_id}); excerpts are looked up when read.
            citations jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(citations) = 'array'),
            created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_work_session_messages_session
                FOREIGN KEY (organization_id, workspace_id, work_session_id)
                REFERENCES workweave.work_sessions (organization_id, workspace_id, work_session_id)
                ON DELETE CASCADE,
            CONSTRAINT uq_work_session_messages_turn UNIQUE (organization_id, workspace_id, work_session_id, client_turn_id, sender)
        );
        CREATE INDEX ix_work_session_messages_session_seq
            ON workweave.work_session_messages (organization_id, workspace_id, work_session_id, seq);
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TABLE workweave.work_session_messages;
        ALTER TABLE workweave.work_item_reported_updates DROP CONSTRAINT work_item_reported_updates_update_type_check;
        """
    )
