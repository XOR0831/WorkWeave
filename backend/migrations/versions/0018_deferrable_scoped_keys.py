"""Make the newer cross-table foreign keys deferrable, like the rest of the scoped schema.

Written 2026-10-13 after the scheduled demo cleanup failed in the cloud: the purge defers every
foreign key and deletes a visitor run table by table, but the keys added in 0009, 0014, 0016 and
0017 between workspace-scoped tables were created NOT DEFERRABLE, so deleting a parent first (for
example employees before handover_copilot_messages) was rejected and the whole purge rolled back.

DEFERRABLE INITIALLY IMMEDIATE changes nothing for the application: every statement is still
checked immediately unless a transaction runs SET CONSTRAINTS ... DEFERRED, which only the cleanup
does. No data changes. (The cleanup now also deletes children first, so it doesn't rely on this.)

Keys to workspaces and organizations are left as they are: those rows are deleted last.

Revision ID: 0018
Revises: 0017
"""

from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None

# (child table, parent table): every foreign key between them is altered.
KEYS = [
    ("work_session_messages", "work_sessions"),  # 0009
    ("knowledge_ingestion_jobs", "curricula"),  # 0014
    ("knowledge_ingestion_jobs", "employees"),
    ("knowledge_ingestion_jobs", "knowledge_document_versions"),
    ("handover_copilot_messages", "employees"),  # 0016
    ("handover_copilot_messages", "shift_handovers"),
    ("exit_kt_copilot_messages", "employees"),  # 0017
    ("exit_kt_copilot_messages", "exit_kt_cases"),
]


def _alter(deferrable: bool) -> None:
    pairs = ", ".join(f"('{c}', '{p}')" for c, p in KEYS)
    mode = "DEFERRABLE INITIALLY IMMEDIATE" if deferrable else "NOT DEFERRABLE"
    op.execute(
        f"""
        DO $$
        DECLARE k record; n integer := 0;
        BEGIN
            FOR k IN
                SELECT ch.relname AS child, con.conname
                FROM pg_constraint con
                JOIN pg_class ch ON ch.oid = con.conrelid
                JOIN pg_class pa ON pa.oid = con.confrelid
                WHERE con.contype = 'f' AND con.connamespace = 'workweave'::regnamespace
                  AND (ch.relname, pa.relname) IN ({pairs})
            LOOP
                EXECUTE format('ALTER TABLE workweave.%I ALTER CONSTRAINT %I {mode}', k.child, k.conname);
                n := n + 1;
            END LOOP;
            IF n <> {len(KEYS)} THEN
                RAISE EXCEPTION 'expected % foreign keys, found %', {len(KEYS)}, n;
            END IF;
        END $$;
        """
    )


def upgrade() -> None:
    _alter(True)


def downgrade() -> None:
    _alter(False)
