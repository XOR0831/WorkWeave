"""Deferrable cross-table keys (0018), on a disposable database."""

import uuid

from alembic import command
from sqlalchemy import create_engine, text

from tests import prepare_db

IMMEDIATE_SCOPED_KEYS = """
SELECT count(*) FROM pg_constraint k
JOIN pg_class ch ON ch.oid = k.conrelid
JOIN pg_class pa ON pa.oid = k.confrelid
WHERE k.contype = 'f' AND NOT k.condeferrable AND k.conrelid <> k.confrelid
  AND k.connamespace = 'workweave'::regnamespace AND ch.relname IN (
      'work_session_messages', 'knowledge_ingestion_jobs', 'handover_copilot_messages', 'exit_kt_copilot_messages')
  AND pa.relname NOT IN ('workspaces', 'organizations')
"""


def test_upgrade_makes_the_keys_deferrable_and_downgrade_restores_them():
    name = f"workweave_scratch_{uuid.uuid4().hex[:8]}"
    url = prepare_db.build(name, revision="0017", catalog=False)
    eng = create_engine(url)
    try:
        cfg = prepare_db.alembic_config(url)
        with eng.connect() as c:
            assert c.execute(text(IMMEDIATE_SCOPED_KEYS)).scalar_one() == 8
        command.upgrade(cfg, "0018")
        with eng.connect() as c:
            assert c.execute(text(IMMEDIATE_SCOPED_KEYS)).scalar_one() == 0
        command.downgrade(cfg, "0017")
        with eng.connect() as c:
            assert c.execute(text(IMMEDIATE_SCOPED_KEYS)).scalar_one() == 8
        command.upgrade(cfg, "0018")
    finally:
        eng.dispose()
        prepare_db.drop(name)
