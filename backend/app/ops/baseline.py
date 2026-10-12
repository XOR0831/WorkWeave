"""The reviewed baseline SQL scripts (src/local/postgres), in the order a fresh database needs them.

Shared by the migration job (app.ops.migrate) and the disposable test databases (tests/prepare_db).
Scripts not listed (03, 06) are local-only history and are never applied to a new database.
"""

import os
from pathlib import Path

SCRIPTS = [
    "01_schema.sql",
    "02_seed.sql",
    "04_northstar_scenario_alignment.sql",
    "05_northstar_full_sop_approved_test.sql",
    "07_sop_curriculum_links.sql",
    "08_document_scoped_curriculum_topics.sql",
    "09_direct_document_topic_link.sql",
    "10_remove_curriculum_source_order.sql",
    "11_onboarding_supervision_grants.sql",
    "13_curriculum_read_grants.sql",
    "14_sop001_v34_ingestion.sql",
    "12_reconcile_sop001_v34_sections.sql",
    "15_machine_fundamentals_v11.sql",
    "16_distinct_shift_rosters.sql",
    "18_curriculum_manage_grants.sql",
    "19_exit_kt_history.sql",
    "20_northstar_829_owner.sql",
]
PACK_DIRS = ["northstar-manufacturing", "acme-infrastructure", "harbor-support"]

# Repo layout locally (src/backend, src/local/postgres, src/seed/packs); the image keeps the same
# layout under /srv. WORKWEAVE_SRC overrides the root if needed.
SRC = Path(os.environ.get("WORKWEAVE_SRC") or Path(__file__).resolve().parents[3])
SQL_DIR = SRC / "local" / "postgres"
PACKS_DIR = SRC / "seed" / "packs"
