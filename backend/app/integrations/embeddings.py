"""Text embeddings for the backend's KT indexer (ADR-053), run as a separate process.

The backend has no Gemini SDK of its own; embedding_runner.py runs with the AI environment's Python
(INGESTION_PYTHON) in her vector_embedding folder, with the same model and size as her ingestion
(GEMINI_EMBED_MODEL / GEMINI_EMBED_DIM), so the vectors match the ones every graph searches. The
subprocess gets a minimal environment, like app/integrations/ingestion.py: no database URL, no
document IDs; the texts go over stdin.

Unconfigured = not connected. Tests install a stand-in with install_test_embedder().
"""

import json
import os
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from app.config import get_settings
from app.integrations.ingestion import _gemini_env

RUNNER = Path(__file__).with_name("embedding_runner.py")
TIMEOUT_SECONDS = 180


class EmbeddingFailed(Exception):
    pass


@dataclass(frozen=True)
class Embedded:
    model: str
    dimension: int
    vectors: list[list[float]]


_test_embedder: Callable[[list[str]], Embedded] | None = None


def install_test_embedder(fn: Callable[[list[str]], Embedded] | None) -> None:
    """Tests only (WORKWEAVE_ENV=test)."""
    global _test_embedder
    if fn is not None and os.environ.get("WORKWEAVE_ENV") != "test":
        raise RuntimeError("install_test_embedder is for tests only")
    _test_embedder = fn


def available() -> bool:
    if _test_embedder:
        return True
    s = get_settings()
    return bool(s.ingestion_python and s.ingestion_dir and Path(s.ingestion_python).exists() and Path(s.ingestion_dir).is_dir())


def embed(texts: list[str]) -> Embedded:
    """Blocks until every text is embedded. Raises EmbeddingFailed with a short summary."""
    if _test_embedder:
        return _test_embedder(texts)
    s = get_settings()
    if not available():
        raise EmbeddingFailed("Embeddings aren't connected on this server.")
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", ""),
        **(_gemini_env() if s.ingestion_pass_gemini_env else {}),
    }
    try:
        p = subprocess.run([s.ingestion_python, str(RUNNER)], cwd=s.ingestion_dir, env=env, input=json.dumps({"texts": texts}),
                           capture_output=True, text=True, timeout=TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        raise EmbeddingFailed(f"Embedding took longer than {TIMEOUT_SECONDS} seconds and was stopped.") from None
    if p.returncode != 0:
        lines = [x for x in (p.stderr or "").splitlines() if x.startswith("EMBEDDING_ERROR:")]
        raise EmbeddingFailed((lines[-1].removeprefix("EMBEDDING_ERROR:").strip() if lines else f"Embedding exited with code {p.returncode}.")[:300])
    try:
        out = json.loads(p.stdout)
        e = Embedded(str(out["model"]), int(out["dimension"]), [[float(x) for x in v] for v in out["vectors"]])
    except (ValueError, KeyError, TypeError):
        raise EmbeddingFailed("The embedding output couldn't be read.") from None
    if len(e.vectors) != len(texts) or any(len(v) != e.dimension for v in e.vectors):
        raise EmbeddingFailed("The embedding output doesn't match the texts sent.")
    return e
