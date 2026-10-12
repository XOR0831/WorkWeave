"""Disposable databases that contain the real SOP-001 v3.4 ingestion output.

The ingestion rows (knowledge_sections, embedded knowledge_chunks, curriculum_sources) exist in
the local dev database but are not produced by the repo's SQL scripts. Tests therefore restore a
read-only pg_dump of the dev database into a template (workweave_scratch_ingest_tpl) once per
session and copy it per test. Nothing is ever written to the dev database.
"""

import subprocess
import uuid
from pathlib import Path

import psycopg

from app.config import get_settings
from tests import prepare_db

LOCAL = Path(__file__).resolve().parents[2] / "local"
TEMPLATE = "workweave_scratch_ingest_tpl"


def _exec(cmd: str) -> None:
    subprocess.run(["docker", "compose", "exec", "-T", "postgres", "sh", "-c", cmd], cwd=LOCAL, check=True, capture_output=True, text=True)


def build_template() -> None:
    s = get_settings()
    u, src = s.postgres_user, s.postgres_db
    assert TEMPLATE != src
    _exec(f"dropdb -U {u} --if-exists --force {TEMPLATE} && createdb -U {u} {TEMPLATE} && pg_dump -U {u} -Fc {src} | pg_restore -U {u} -d {TEMPLATE} --no-owner --exit-on-error")
    # The dev database now has the reconciliation applied (2026-10-03). Remove its three learner-path
    # links in this disposable template only, so tests start from the pre-reconciliation state.
    _exec(
        f"""psql -U {u} -d {TEMPLATE} -v ON_ERROR_STOP=1 -c "DELETE FROM workweave.curriculum_source_sections css USING workweave.curriculum_topics t
            WHERE t.topic_id = css.topic_id AND t.document_version_id IS NULL AND css.workspace_id = '00000001-0000-4000-8000-000000000002'" """
    )
    # Script 15 (applied to dev 2026-10-04) published Machine Fundamentals 1.1 and archived 1.0.
    # Script 12 targets the published 1.0, so restore that pre-15 state here (template only).
    _exec(
        f"""psql -U {u} -d {TEMPLATE} -v ON_ERROR_STOP=1 -c "UPDATE workweave.curricula SET status = CASE version WHEN '1.0' THEN 'PUBLISHED' ELSE 'ARCHIVED' END
            WHERE name = 'Machine Fundamentals' AND workspace_id = '00000001-0000-4000-8000-000000000002' AND version IN ('1.0', '1.1')" """
    )


def copy_template() -> tuple[str, str]:
    name = f"workweave_scratch_{uuid.uuid4().hex[:10]}"
    with psycopg.connect(prepare_db._plain(get_settings().url("postgres")), autocommit=True) as c:
        c.execute(f"CREATE DATABASE {name} TEMPLATE {TEMPLATE}")
    return name, get_settings().url(name)


def reconcile(url: str) -> None:
    """Run the exact reconciliation script file against a disposable database."""
    sql = (LOCAL / "postgres" / "12_reconcile_sop001_v34_sections.sql").read_text()
    with psycopg.connect(prepare_db._plain(url), autocommit=True) as c:
        c.execute(sql)
