"""Tracked ingestion of approved curriculum sources (owner decisions 2026-10-10, ADR-040).

Written for review 2026-10-10 (not applied to the local dev database).

After a manager approves an exact uploaded source version, the backend queues one job that runs
the AI engineer's ingestion (sections, learning path, chunks and Gemini embeddings) outside the
request transaction. The job row is the page's status (QUEUED, RUNNING, SUCCEEDED, FAILED) and
the retry guard. It keeps no document content and no model output: only who asked, attempts,
timings and a short error summary.

Downgrade drops the table.

Revision ID: 0014
Revises: 0013
"""

from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE workweave.knowledge_ingestion_jobs (
            job_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            organization_id uuid NOT NULL,
            workspace_id uuid NOT NULL,
            curriculum_id uuid NOT NULL,
            document_version_id uuid NOT NULL,
            status text NOT NULL DEFAULT 'QUEUED' CHECK (status IN ('QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED')),
            attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
            requested_by uuid NOT NULL,
            error_summary text CHECK (error_summary IS NULL OR length(error_summary) <= 300),
            started_at timestamptz,
            finished_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
            UNIQUE (organization_id, workspace_id, job_id),
            UNIQUE (organization_id, workspace_id, curriculum_id, document_version_id),
            FOREIGN KEY (organization_id, workspace_id) REFERENCES workweave.workspaces (organization_id, workspace_id),
            FOREIGN KEY (organization_id, workspace_id, curriculum_id) REFERENCES workweave.curricula (organization_id, workspace_id, curriculum_id),
            FOREIGN KEY (organization_id, workspace_id, document_version_id)
                REFERENCES workweave.knowledge_document_versions (organization_id, workspace_id, document_version_id),
            FOREIGN KEY (organization_id, workspace_id, requested_by) REFERENCES workweave.employees (organization_id, workspace_id, employee_id)
        );
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE workweave.knowledge_ingestion_jobs;")
