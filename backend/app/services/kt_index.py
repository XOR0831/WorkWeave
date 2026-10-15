"""Indexing of promoted Exit KT knowledge (ADR-053), so the assistants can find it.

Promotion (exit_kt.promote_artifact) makes an approved artifact revision a new document version
(KT-nnn v1) and marks it PENDING for the index. This worker, in the API process, claims due pending
promotions, embeds the approved text and writes what every graph's retrieval reads:
- the chunks point at the version's source record (APPROVED_EXCERPT, REPORTED: the employee's own
  account), created with the version at promotion; the searches require it and revocation acts on it.
  A promotion from before this indexer has none and can't get one (an approved version's source is
  immutable), so it fails with that reason; a fresh demo run doesn't have that problem;
- one knowledge section (topic = the artifact's title) and its chunks with embeddings, using the same
  embedding model and size as the AI engineer's ingestion (app/integrations/embeddings.py).
Then the promotion is READY. Everything stays in the promotion's own workspace, so a demo visitor's
knowledge is only searchable in their run and is purged with it.

KT artifacts are short lists without Markdown headings, so the AI engineer's H2/H3 ingestion doesn't
fit them; this is the backend's own, deliberately small chunker (owner decision 2026-10-15).

Embedding runs outside any transaction. The write re-checks the lease and that the version is still
approved and current, and replaces any earlier chunks of that version in the same transaction.
Failures are retried with growing waits; after MAX_ATTEMPTS the promotion is FAILED, and a reviewer
can retry it (exit_kt.retry_indexing). index_error keeps a short summary for operators, never text.
"""

import json
import logging
import threading
from datetime import timedelta
from typing import Any

from sqlalchemy import Connection, text

from app.config import get_settings
from app.db import transaction
from app.integrations import embeddings

log = logging.getLogger("workweave.kt_index")
W = "workweave"
MAX_ATTEMPTS = 5
LOCK_TIMEOUT = timedelta(minutes=5)  # a worker that stopped mid-attempt (redeploy, crash)
CHUNK_WORDS = 150
MAX_CHUNKS = 40
SUBTOPIC = "Transferred knowledge"
PARTITION = {"PRIVATE": "PRIVATE", "TEAM": "TEAM", "ORGANIZATION": "ORGANIZATION"}


# ---------------------------------------------------------------- chunks
def chunks_of(content: str) -> list[str]:
    """Consecutive lines grouped into pieces of at most CHUNK_WORDS words (a longer line is split
    by words), so each list item stays whole where it fits."""
    lines: list[str] = []
    for line in (x.strip() for x in content.splitlines()):
        words = line.split()
        lines += [" ".join(words[i:i + CHUNK_WORDS]) for i in range(0, len(words), CHUNK_WORDS)] if len(words) > CHUNK_WORDS else [line] if line else []
    pieces: list[str] = []
    cur: list[str] = []
    n = 0
    for line in lines:
        k = len(line.split())
        if cur and n + k > CHUNK_WORDS:
            pieces.append("\n".join(cur))
            cur, n = [], 0
        cur.append(line)
        n += k
    if cur:
        pieces.append("\n".join(cur))
    return pieces[:MAX_CHUNKS]


def embed_text(title: str, chunk: str) -> str:
    """What is embedded: the title gives a short item its context (the stored chunk is the text alone)."""
    return f"{title}\n\n{chunk}"


# ---------------------------------------------------------------- the version's source record
def create_source(conn: Connection, org, ws, owner_employee_id, audience: str | None, artifact_revision_id) -> str:
    """The source record a promoted KT version is searched through (the graphs require one, unrevoked).
    Created before the version: an approved version's source can't change afterwards."""
    return str(conn.execute(
        text(f"""INSERT INTO {W}.source_records (organization_id, workspace_id, source_type, owner_employee_id, evidence_type, access_partition, metadata)
                 VALUES (:o, :w, 'APPROVED_EXCERPT', :e, 'REPORTED', :p, CAST(:m AS jsonb)) RETURNING source_id"""),
        {"o": org, "w": ws, "e": owner_employee_id, "p": PARTITION.get(audience or "", "TEAM"),
         "m": json.dumps({"origin": "EXIT_KT_PROMOTION", "artifact_revision_id": str(artifact_revision_id)})},
    ).scalar_one())


# ---------------------------------------------------------------- one attempt
CLAIM = f"""
UPDATE {W}.knowledge_promotions SET index_locked_at=now(), index_attempts=index_attempts+1, updated_at=now()
WHERE promotion_id = (
  SELECT promotion_id FROM {W}.knowledge_promotions
  WHERE index_status='PENDING' AND index_next_attempt_at <= now()
    AND (CAST(:only AS uuid) IS NULL OR workspace_id = CAST(:only AS uuid))
    AND (index_locked_at IS NULL OR index_locked_at < now() - CAST(:stale AS interval))
  ORDER BY index_next_attempt_at LIMIT 1 FOR UPDATE SKIP LOCKED)
RETURNING promotion_id, organization_id, workspace_id, document_version_id, artifact_revision_id, index_attempts, index_locked_at
"""

SUBJECT = f"""
SELECT v.content, v.source_id, v.approval_status, v.temporal_status, d.title, d.current_version_id
FROM {W}.knowledge_document_versions v
JOIN {W}.knowledge_documents d ON d.organization_id=v.organization_id AND d.workspace_id=v.workspace_id AND d.document_id=v.document_id
WHERE v.organization_id=:o AND v.workspace_id=:w AND v.document_version_id=:v
"""


class _Permanent(Exception):
    """Retrying can't help (the version is no longer approved and current, or has no text)."""


def _searchable(s: dict[str, Any] | None, version_id) -> None:
    if not s:
        raise _Permanent("The document version no longer exists.")
    if s["approval_status"] != "APPROVED" or s["temporal_status"] != "CURRENT" or s["current_version_id"] != version_id:
        raise _Permanent("The document version is no longer the approved current version.")
    if not s["source_id"]:
        raise _Permanent("Promoted before indexing was available: the version has no source record.")


def _write(conn: Connection, p: dict[str, Any], s: dict[str, Any], pieces: list[str], e: embeddings.Embedded) -> None:
    o, w, v = p["organization_id"], p["workspace_id"], p["document_version_id"]
    sid = s["source_id"]
    q = {"o": o, "w": w, "v": v}
    conn.execute(text(f"DELETE FROM {W}.knowledge_chunks WHERE organization_id=:o AND workspace_id=:w AND document_version_id=:v"), q)
    conn.execute(text(f"DELETE FROM {W}.knowledge_sections WHERE organization_id=:o AND workspace_id=:w AND document_version_id=:v"), q)
    title = s["title"].strip() or "Transferred knowledge"
    section = conn.execute(
        text(f"""INSERT INTO {W}.knowledge_sections (organization_id, workspace_id, document_version_id, section_key, topic_heading, subtopic_heading, topic_order_index, subtopic_order_index)
                 VALUES (:o, :w, :v, 'kt:1', :t, :st, 1, 1) RETURNING section_id"""),
        {**q, "t": title, "st": SUBTOPIC},
    ).scalar_one()
    for i, (piece, vec) in enumerate(zip(pieces, e.vectors, strict=True)):
        conn.execute(
            text(f"""INSERT INTO {W}.knowledge_chunks (organization_id, workspace_id, document_version_id, source_id, source_section_id, section_path, heading, content,
                                                       chunk_index, embedding, embedding_model, embedding_dimension, index_generation, metadata)
                     VALUES (:o, :w, :v, :s, :sec, CAST(:path AS jsonb), :h, :c, :i, CAST(:emb AS public.vector), :m, :d, 'kt-index-1', CAST(:meta AS jsonb))"""),
            {**q, "s": sid, "sec": section, "path": json.dumps([title]), "h": SUBTOPIC, "c": piece, "i": i, "emb": json.dumps(vec), "m": e.model, "d": e.dimension,
             "meta": json.dumps({"origin": "EXIT_KT_PROMOTION"})},
        )
    conn.execute(
        text(f"""UPDATE {W}.knowledge_promotions SET index_status='READY', indexed_at=now(), index_locked_at=NULL, index_error=NULL, updated_at=now(), revision=revision+1
                 WHERE promotion_id=:p"""),
        {"p": p["promotion_id"]},
    )


def _fail(p: dict[str, Any], error: str, permanent: bool) -> str:
    attempts = int(p["index_attempts"])
    failed = permanent or attempts >= MAX_ATTEMPTS
    wait = min(600, 15 * 2 ** (attempts - 1))  # 15 s, 30 s, 1 min, 2 min ...
    with transaction() as conn:
        conn.execute(
            text(f"""UPDATE {W}.knowledge_promotions SET index_status=:st, index_error=:e, index_locked_at=NULL, updated_at=now(), revision=revision+1,
                       index_next_attempt_at = now() + CAST(:wait AS interval)
                     WHERE promotion_id=:p AND index_status='PENDING' AND index_locked_at=:lock"""),
            {"st": "FAILED" if failed else "PENDING", "e": error[:300], "wait": f"{wait} seconds", "p": p["promotion_id"], "lock": p["index_locked_at"]},
        )
    return "failed" if failed else "retry"


def index_once(only_workspace: str | None = None) -> str | None:
    """Indexes the next due promotion (of one workspace, if given), if any. Returns "ready", "retry",
    "failed", or None (nothing due)."""
    with transaction() as conn:
        row = conn.execute(text(CLAIM), {"stale": f"{int(LOCK_TIMEOUT.total_seconds())} seconds", "only": only_workspace}).mappings().first()
        p = dict(row) if row else None
        if p:
            s = conn.execute(text(SUBJECT), {"o": p["organization_id"], "w": p["workspace_id"], "v": p["document_version_id"]}).mappings().first()
            s = dict(s) if s else None
    if not p:
        return None
    try:
        _searchable(s, p["document_version_id"])
        pieces = chunks_of(s["content"])
        if not pieces:
            raise _Permanent("The approved text is empty.")
        e = embeddings.embed([embed_text(s["title"], x) for x in pieces])
        with transaction() as conn:
            lease = conn.execute(text(f"SELECT index_status, index_locked_at FROM {W}.knowledge_promotions WHERE promotion_id=:p FOR UPDATE"), {"p": p["promotion_id"]}).one()
            if lease.index_status != "PENDING" or lease.index_locked_at != p["index_locked_at"]:
                return "retry"  # another worker took it over; it'll finish it
            s2 = conn.execute(text(SUBJECT), {"o": p["organization_id"], "w": p["workspace_id"], "v": p["document_version_id"]}).mappings().first()
            _searchable(dict(s2) if s2 else None, p["document_version_id"])
            _write(conn, p, s, pieces, e)
        log.info("kt index: promotion %s ready (%d chunks)", p["promotion_id"], len(pieces))
        return "ready"
    except _Permanent as err:
        return _fail(p, str(err), permanent=True)
    except embeddings.EmbeddingFailed as err:
        log.warning("kt index: promotion %s embedding failed: %s", p["promotion_id"], err)
        return _fail(p, f"Embedding failed: {err}", permanent=False)
    except Exception as err:  # noqa: BLE001 - a database or unexpected error: retried
        log.exception("kt index: promotion %s failed", p["promotion_id"])
        return _fail(p, f"{type(err).__name__}", permanent=False)


def index_due(limit: int = 10) -> int:
    """Indexes up to `limit` due promotions. Returns how many were attempted."""
    n = 0
    while n < limit and index_once() is not None:
        n += 1
    return n


# ---------------------------------------------------------------- in-process worker
_stop = threading.Event()
_wake = threading.Event()
_thread: threading.Thread | None = None


def nudge() -> None:
    """A promotion or retry just committed: look now instead of at the next interval."""
    _wake.set()


def start_worker() -> None:
    """Indexes from the API process every few seconds (KT_INDEX_IN_PROCESS). Errors never reach requests."""
    global _thread
    s = get_settings()
    if not s.kt_index_in_process or not embeddings.available() or (_thread and _thread.is_alive()):
        return
    _stop.clear()

    def loop() -> None:
        while not _stop.is_set():
            _wake.wait(s.kt_index_interval_seconds)
            _wake.clear()
            if _stop.is_set():
                break
            try:
                index_due()
            except Exception:  # noqa: BLE001 - keep the worker alive; the promotions stay due
                log.exception("kt index pass failed")

    _thread = threading.Thread(target=loop, name="kt-indexer", daemon=True)
    _thread.start()


def stop_worker() -> None:
    _stop.set()
    _wake.set()
