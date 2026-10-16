"""Fuller Acme and Harbor procedures for onboarding (owner decision 2026-10-16, option A).

Written 2026-10-16. A live test showed the Acme and Harbor tutors stop at the first reply ("No approved
knowledge was found for the current learning context"): their curricula's subtopics had no document
sections. This loads local/postgres/22_acme_harbor_sop_v12.sql, the same shape as Northstar's
SOP-001 v3.4 (scripts 05, 14, 12):
- OPS-SOP-001 v1.2 (Acme) and BPO-SOP-001 v1.2 (Harbor), approved and current, with the sections, chunks
  and vectors the AI engineer's ingestion produced (exported from a disposable database; no model is
  called here); v1.1 stays as approved history;
- each curriculum TEACHES v1.2 instead of v1.1, and its existing subtopics are linked to their v1.2
  sections. Subtopic names, objectives and learner progress don't change.

Skipped when the Acme or Harbor baseline isn't there. Idempotent. Visitor workspaces that already exist
keep what they were copied with; new demo runs get this. Downgrade leaves the rows (content, not schema).

Revision ID: 0021
Revises: 0020
"""

from alembic import op
from sqlalchemy import text

from app.ops.baseline import SQL_DIR

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None

SCRIPT = "22_acme_harbor_sop_v12.sql"
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
