"""Searchable procedures for the Acme and Harbor demo companies (owner decision 2026-10-16).

Written 2026-10-16. Only Northstar's baseline had embedded knowledge, so the Work Companion found no
procedure for any Acme or Harbor question. This loads local/postgres/21_acme_harbor_procedures.sql
into the two baselines:
- OPS-RB-007 (Acme) and BPO-PRC-004 (Harbor) v1.0, approved and current, with the sections, chunks and
  vectors that the AI engineer's ingestion produced (exported from a disposable database; no model is
  called here);
- vectors for the existing chunks of the short current SOPs (OPS-SOP-001 v1.1, BPO-SOP-001 v1.1);
- a TEACHES link from each company's curriculum to both documents, so a fresh visitor demo copies
  them. Learning paths (topics, subtopics, objectives) don't change.

Skipped when the Acme or Harbor baseline isn't there. Idempotent (fixed IDs, ON CONFLICT DO NOTHING).
Visitor workspaces that already exist keep what they were copied with; new demo runs get this.

Downgrade leaves the rows: they're baseline content, not schema, and nothing before 0020 depends on
their absence. Upgrading again is a no-op.

Revision ID: 0020
Revises: 0019
"""

from alembic import op
from sqlalchemy import text

from app.ops.baseline import SQL_DIR

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None

SCRIPT = "21_acme_harbor_procedures.sql"
CURRICULA = ("00000003-0000-4000-8000-000000000098", "00000002-0000-4000-8000-000000000068")


def upgrade() -> None:
    bind = op.get_bind()
    present = bind.execute(
        text("SELECT count(*) FROM workweave.curricula WHERE curriculum_id = ANY(CAST(:c AS uuid[]))"), {"c": list(CURRICULA)}
    ).scalar_one()
    if present != len(CURRICULA):
        return
    # Raw driver call: the document text contains ':' and '%', which bound-parameter parsing would misread.
    bind.connection.dbapi_connection.cursor().execute((SQL_DIR / SCRIPT).read_text())


def downgrade() -> None:
    pass
