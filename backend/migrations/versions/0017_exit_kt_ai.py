"""Exit KT AI proposals (docs/32, ADR-044).

Written for review 2026-10-11 (not applied to the local dev database).

- kt_checklist_items gains the plan fields: title, method, priority, completion criteria, origin and a
  proposal status. The AI proposes plan items (PROPOSED); the manager accepts (they become checklist
  items) or declines them. Scenario and manual items stay ACCEPTED. Resolution rules are unchanged:
  reviewed evidence or a disclosed manager exception, never the AI or a receipt.
- exit_kt_findings and exit_kt_knowledge_items gain an origin (SCENARIO, MANUAL, AI_ENGINE). Knowledge
  items also keep the deterministic risk score and the factors behind it, for explanation.
- exit_kt_cases.discovery: the latest discovery (inventory, deterministic risks, unknowns, model), shown
  until the next run. A proposal: findings, plan items and new areas it suggested are stored as
  proposals in their own tables.
- exit_kt_copilot_messages: one private conversation per case and person (employee, manager side or
  successor), like the Shift Handover copilot. Never copied into a demo run.

All additive with defaults; downgrade drops the table and columns.

Revision ID: 0017
Revises: 0016
"""

from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE workweave.kt_checklist_items
            ADD COLUMN title text CHECK (title IS NULL OR length(title) BETWEEN 1 AND 300),
            ADD COLUMN method text CHECK (method IS NULL OR method IN ('DOCUMENT_REVIEW', 'GUIDED_WALKTHROUGH', 'SHADOWING', 'PRACTICAL_DEMONSTRATION',
                                                                      'HISTORICAL_CASE_REVIEW', 'SOP_VERIFICATION', 'QA_SESSION', 'OWNERSHIP_TRANSFER')),
            ADD COLUMN priority integer CHECK (priority IS NULL OR priority BETWEEN 1 AND 3),
            ADD COLUMN completion_criteria text CHECK (completion_criteria IS NULL OR length(completion_criteria) <= 1000),
            ADD COLUMN origin text NOT NULL DEFAULT 'SCENARIO' CHECK (origin IN ('SCENARIO', 'MANUAL', 'AI_ENGINE')),
            ADD COLUMN proposal_status text NOT NULL DEFAULT 'ACCEPTED' CHECK (proposal_status IN ('PROPOSED', 'ACCEPTED', 'DECLINED')),
            ADD COLUMN evidence_sources jsonb NOT NULL DEFAULT '[]'::jsonb;
        ALTER TABLE workweave.exit_kt_findings
            ADD COLUMN origin text NOT NULL DEFAULT 'SCENARIO' CHECK (origin IN ('SCENARIO', 'MANUAL', 'AI_ENGINE'));
        ALTER TABLE workweave.exit_kt_cases ADD COLUMN discovery jsonb CHECK (discovery IS NULL OR jsonb_typeof(discovery) = 'object');
        ALTER TABLE workweave.exit_kt_knowledge_items
            ADD COLUMN origin text NOT NULL DEFAULT 'SCENARIO' CHECK (origin IN ('SCENARIO', 'MANUAL', 'AI_ENGINE')),
            ADD COLUMN risk_score integer CHECK (risk_score IS NULL OR risk_score >= 0),
            ADD COLUMN risk_factors jsonb NOT NULL DEFAULT '[]'::jsonb;
        CREATE TABLE workweave.exit_kt_copilot_messages (
            message_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            organization_id uuid NOT NULL,
            workspace_id uuid NOT NULL,
            exit_kt_case_id uuid NOT NULL,
            employee_id uuid NOT NULL,
            sender text NOT NULL CHECK (sender IN ('PERSON', 'AI', 'SYSTEM')),
            content text NOT NULL CHECK (length(content) BETWEEN 1 AND 8000),
            citations jsonb NOT NULL DEFAULT '[]'::jsonb,
            unknowns jsonb NOT NULL DEFAULT '[]'::jsonb,
            model text,
            created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (organization_id, workspace_id, message_id),
            FOREIGN KEY (organization_id, workspace_id) REFERENCES workweave.workspaces (organization_id, workspace_id),
            FOREIGN KEY (organization_id, workspace_id, exit_kt_case_id) REFERENCES workweave.exit_kt_cases (organization_id, workspace_id, exit_kt_case_id),
            FOREIGN KEY (organization_id, workspace_id, employee_id) REFERENCES workweave.employees (organization_id, workspace_id, employee_id)
        );
        CREATE INDEX exit_kt_copilot_messages_thread ON workweave.exit_kt_copilot_messages (organization_id, workspace_id, exit_kt_case_id, employee_id, created_at);
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TABLE workweave.exit_kt_copilot_messages;
        ALTER TABLE workweave.exit_kt_knowledge_items DROP COLUMN risk_factors, DROP COLUMN risk_score, DROP COLUMN origin;
        ALTER TABLE workweave.exit_kt_cases DROP COLUMN discovery;
        ALTER TABLE workweave.exit_kt_findings DROP COLUMN origin;
        ALTER TABLE workweave.kt_checklist_items DROP COLUMN evidence_sources, DROP COLUMN proposal_status, DROP COLUMN origin, DROP COLUMN completion_criteria,
            DROP COLUMN priority, DROP COLUMN method, DROP COLUMN title;
        """
    )
