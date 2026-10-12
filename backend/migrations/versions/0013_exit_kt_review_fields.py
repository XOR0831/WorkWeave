"""Exit KT review fields the screens show (owner decisions 2026-10-10, ADR-039).

Written for review 2026-10-10 (not applied to the local dev database).

- exit_kt_artifact_revisions.audience: who the employee submitted the exact revision for
  (PRIVATE until submitted, then TEAM or ORGANIZATION). Existing revisions are PRIVATE drafts.
- exit_kt_findings.review_reason: the reason or evidence given when a finding is confirmed,
  dismissed or resolved (required by the review command).
- exit_kt_packages.review_comment: what the reviewer asked to change when sending a package back.
- kt_checklist_items.exception_reason: an authorized manager's disclosed exception, which resolves
  a required item without evidence (shown on the case).

All additive and nullable (audience has a default). Downgrade drops the four columns.

Revision ID: 0013
Revises: 0012
"""

from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE workweave.exit_kt_artifact_revisions
            ADD COLUMN audience text NOT NULL DEFAULT 'PRIVATE' CHECK (audience IN ('PRIVATE', 'TEAM', 'ORGANIZATION'));
        ALTER TABLE workweave.exit_kt_findings ADD COLUMN review_reason text;
        ALTER TABLE workweave.exit_kt_packages ADD COLUMN review_comment text;
        ALTER TABLE workweave.kt_checklist_items ADD COLUMN exception_reason text;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE workweave.kt_checklist_items DROP COLUMN exception_reason;
        ALTER TABLE workweave.exit_kt_packages DROP COLUMN review_comment;
        ALTER TABLE workweave.exit_kt_findings DROP COLUMN review_reason;
        ALTER TABLE workweave.exit_kt_artifact_revisions DROP COLUMN audience;
        """
    )
