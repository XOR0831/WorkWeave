"""The ingestion runner starts her code without her .env (as in the container image)."""

import json
import subprocess
import sys
from pathlib import Path

from app.integrations import ingestion

# Stand-ins with her modules' import-time behaviour: database.py reads PORT from the environment on import.
DATABASE = """import os
engine_port = int(os.getenv("PORT"))
configured = None
def configure(url):
    global configured
    configured = url
"""
INGESTION = """import database
class Document:
    def __init__(self, code, curriculum_id, workspace_id, save_json=True):
        assert database.configured == "postgresql+psycopg://x@/db" and save_json is False
    def ingest(self):
        print("ingested")
"""


def test_runner_imports_her_modules_without_a_dotenv(tmp_path: Path):
    (tmp_path / "database.py").write_text(DATABASE)
    (tmp_path / "ingestion.py").write_text(INGESTION)
    env = {"PATH": "/usr/bin:/bin", "WORKWEAVE_DATABASE_URL": "postgresql+psycopg://x@/db",
           "WORKWEAVE_INGEST": json.dumps({"document_code": "D", "curriculum_id": "c", "workspace_id": "w"})}
    p = subprocess.run([sys.executable, str(ingestion.RUNNER)], cwd=tmp_path, env=env, capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr
    assert "ingested" in p.stdout
