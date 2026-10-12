"""The AI engineer's curriculum source ingestion (ADR-040), run as a separate process.

Her package (vector_embedding: H2/H3 sections, the document-bound learning path, chunks and Gemini
embeddings) runs with her own Python environment and .env, outside any request transaction. The
subprocess gets a minimal environment: our database URL and the job IDs. Locally our GEMINI_API_KEY and
other secrets are not passed, so her embedding configuration stays hers. In the container image there is
no .env of hers, so INGESTION_PASS_GEMINI_ENV=true passes the Gemini settings the deployment gives this
process (ADR-052): the embedding model and size, and either the API key or the Vertex AI settings.

Unconfigured (INGESTION_PYTHON / INGESTION_DIR unset or missing) = not connected.
"""

import json
import os
import subprocess
from pathlib import Path

from app.config import get_settings

RUNNER = Path(__file__).with_name("ingestion_runner.py")


class IngestionFailed(Exception):
    pass


def available() -> bool:
    s = get_settings()
    return bool(s.ingestion_python and s.ingestion_dir and Path(s.ingestion_python).exists() and (Path(s.ingestion_dir) / "ingestion.py").exists())


def _gemini_env() -> dict[str, str]:
    names = ["GEMINI_MODEL", "GEMINI_EMBED_MODEL", "GEMINI_EMBED_DIM"]
    if os.environ.get("AI_GEMINI") == "vertex":
        names += ["GOOGLE_GENAI_USE_VERTEXAI", "GOOGLE_CLOUD_PROJECT", "GOOGLE_CLOUD_LOCATION"]
    else:
        names += ["GEMINI_API_KEY"]
    return {n: os.environ[n] for n in names if os.environ.get(n)}


def run(document_code: str, curriculum_id: str, workspace_id: str) -> None:
    """Blocks until her ingestion finishes. Raises IngestionFailed with a short summary."""
    s = get_settings()
    if not available():
        raise IngestionFailed("Ingestion isn't connected on this server.")
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", ""),
        "WORKWEAVE_DATABASE_URL": s.url(),
        "WORKWEAVE_INGEST": json.dumps({"document_code": document_code, "curriculum_id": curriculum_id, "workspace_id": workspace_id}),
        **(_gemini_env() if s.ingestion_pass_gemini_env else {}),
    }
    try:
        p = subprocess.run([s.ingestion_python, str(RUNNER)], cwd=s.ingestion_dir, env=env, capture_output=True, text=True, timeout=s.ingestion_timeout_seconds)
    except subprocess.TimeoutExpired:
        raise IngestionFailed(f"Ingestion took longer than {s.ingestion_timeout_seconds} seconds and was stopped.") from None
    if p.returncode != 0:
        lines = [x for x in (p.stderr or "").splitlines() if x.startswith("INGESTION_ERROR:")]
        raise IngestionFailed((lines[-1].removeprefix("INGESTION_ERROR:").strip() if lines else f"Ingestion exited with code {p.returncode}.")[:300])
