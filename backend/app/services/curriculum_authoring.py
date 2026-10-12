"""Creating curricula from uploaded Markdown sources (owner decisions 2026-10-10, ADR-040).

Who: holders of a workspace-wide `curriculum:manage` grant (the manager: Morgan / Ravi). The packs
have no separate learning team, so the manager may approve their own upload, but only after
confirming they reviewed that exact version; the audit records it as approved by the uploader.

Flow (each step a separate, audited command):
1. Create a DRAFT curriculum.
2. Upload a Markdown source: a new version of a document (new or existing code), PENDING_REVIEW.
   The original is kept privately (local folder in dev; Cloud Storage later).
3. Approve or reject that exact version. Approval makes it the document's current approved version
   (older versions become superseded, never overwritten) and queues ingestion.
4. Ingestion (the AI engineer's package) runs as a tracked background job outside the request:
   H2/H3 sections, the document-bound learning path, chunks and embeddings.
5. The manager writes each subtopic's objective and assessment criteria.
6. Publish once every source is approved and ingested and every subtopic has an objective.
Publishing is separate from approval and from assigning the curriculum to anyone.
"""

import hashlib
import json
import re
import uuid as _uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import Connection, text

from app.config import get_settings
from app.db import transaction
from app.errors import ApiError
from app.integrations import ingestion
from app.repositories import commands
from app.repositories import curricula as repo
from app.services.onboarding import _persona
from app.services.work_commands import _check_revision, _command, _id

W = "workweave"
MANAGE = "curriculum:manage"
MAX_BYTES = 300_000
STALE_RUN = timedelta(minutes=20)


def _one(conn: Connection, sql: str, params: dict[str, Any]) -> dict[str, Any] | None:
    r = conn.execute(text(sql), params).mappings().first()
    return dict(r) if r else None


def can_manage(conn: Connection, org, ws, employee_id) -> bool:
    return repo.has_workspace_grant(conn, org, ws, employee_id, MANAGE)


def _manager(conn: Connection, r: Any, me) -> tuple[Any, Any]:
    org, ws = r.session["organization_id"], r.session["workspace_id"]
    if not can_manage(conn, org, ws, me):
        raise ApiError("FORBIDDEN", "Creating curricula and approving their sources needs the curriculum management permission.")
    return org, ws


def _draft(conn: Connection, org, ws, curriculum_id: str, lock: bool = True) -> dict[str, Any]:
    c = _one(conn, f"SELECT * FROM {W}.curricula WHERE organization_id=:o AND workspace_id=:w AND curriculum_id=:c{' FOR UPDATE' if lock else ''}",
             {"o": org, "w": ws, "c": _id(curriculum_id, "curriculum")})
    if not c:
        raise ApiError("NOT_FOUND", "This curriculum doesn't exist in this workspace.")
    if c["status"] != "DRAFT":
        raise ApiError("GUARD_FAILED", "Only a draft curriculum can change. Published curricula are frozen.")
    return c


def _bump(conn: Connection, c: dict[str, Any]) -> int:
    return conn.execute(text(f"UPDATE {W}.curricula SET revision = revision + 1, updated_at = now() WHERE organization_id=:o AND workspace_id=:w AND curriculum_id=:c RETURNING revision"),
                        {"o": c["organization_id"], "w": c["workspace_id"], "c": c["curriculum_id"]}).scalar_one()


# ---------------------------------------------------------------- 1. create
def create(conn: Connection, token, name: str, version: str, description: str, key: str, request_id) -> dict[str, Any]:
    def run(r: Any, me) -> tuple[dict[str, Any], int]:
        org, ws = _manager(conn, r, me)
        if not name.strip() or not version.strip():
            raise ApiError("MALFORMED_INPUT", "Give the curriculum a name and a version.")
        if _one(conn, f"SELECT 1 AS x FROM {W}.curricula WHERE organization_id=:o AND workspace_id=:w AND lower(name)=lower(:n) AND version=:v", {"o": org, "w": ws, "n": name.strip(), "v": version.strip()}):
            raise ApiError("GUARD_FAILED", "A curriculum with this name and version already exists. Change the version.")
        cid = conn.execute(text(f"""INSERT INTO {W}.curricula (organization_id, workspace_id, name, version, description, status, completion_policy_version)
                                    VALUES (:o, :w, :n, :v, :d, 'DRAFT', '1') RETURNING curriculum_id"""),
                           {"o": org, "w": ws, "n": name.strip(), "v": version.strip(), "d": description.strip() or None}).scalar_one()
        commands.audit(conn, org, ws, me, "curriculum.created", "curriculum", cid, 1, request_id)
        return {"curriculum_id": str(cid)}, 1

    return _command(conn, token, "curriculum.create", key, {"name": name, "version": version, "description": description}, run)


# ---------------------------------------------------------------- 2. upload a Markdown source
def _store(ws, data: bytes) -> tuple[str, str]:
    """Keeps the private original (dev adapter: a local folder, named by checksum)."""
    digest = hashlib.sha256(data).hexdigest()
    root = Path(get_settings().local_storage_dir)
    if not root.is_absolute():
        root = (Path(__file__).resolve().parents[2] / root).resolve()
    path = root / str(ws) / f"{digest}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_bytes(data)
    return f"local://{ws}/{digest}.md", f"sha256:{digest}"


def add_source(conn: Connection, token, curriculum_id: str, document_code: str, title: str, version: str, document_type: str, filename: str, content: str,
               key: str, expected_revision: int | None, request_id) -> dict[str, Any]:
    payload = {"curriculum_id": curriculum_id, "document_code": document_code, "title": title, "version": version, "document_type": document_type, "filename": filename,
               "content_sha256": hashlib.sha256(content.encode()).hexdigest(), "expected_revision": expected_revision}

    def run(r: Any, me) -> tuple[dict[str, Any], int]:
        org, ws = _manager(conn, r, me)
        c = _draft(conn, org, ws, curriculum_id)
        _check_revision(c["revision"], expected_revision, "curriculum")
        code, ver = document_code.strip().upper(), version.strip()
        data = content.encode()
        if not code or not title.strip() or not ver:
            raise ApiError("MALFORMED_INPUT", "Give the document a code, a title and a version.")
        if not filename.lower().endswith((".md", ".markdown")):
            raise ApiError("MALFORMED_INPUT", "Upload a Markdown file (.md).")
        if not data.strip() or len(data) > MAX_BYTES:
            raise ApiError("MALFORMED_INPUT", f"The file must be non-empty and at most {MAX_BYTES // 1000} KB.")
        if not re.search(r"(?m)^##\s+\S", content) or not re.search(r"(?m)^###\s+\S", content):
            raise ApiError("MALFORMED_INPUT", "The document needs ## topic and ### subtopic headings; they become the learning path.")
        # The ingestion parser reads the first word of each ## / ### heading as its number (like
        # SOP-001: "## 1. Fundamentals", "### 2. Separate history from evidence").
        unnumbered = [h.strip() for h in re.findall(r"(?m)^#{2,3}\s+(.*)$", content) if not re.match(r"^\d+(\.\d+)*\.?\s+\S", h.strip())]
        if unnumbered:
            raise ApiError("MALFORMED_INPUT", f"Number every ## and ### heading, like \"## 1. Start-up\" and \"### 1. Pre-start checks\". Not numbered: {', '.join(unnumbered[:3])}.")
        doc = _one(conn, f"SELECT * FROM {W}.knowledge_documents WHERE organization_id=:o AND workspace_id=:w AND document_code=:c FOR UPDATE", {"o": org, "w": ws, "c": code})
        if doc and _one(conn, f"SELECT 1 AS x FROM {W}.knowledge_document_versions WHERE organization_id=:o AND workspace_id=:w AND document_id=:d AND version=:v",
                        {"o": org, "w": ws, "d": doc["document_id"], "v": ver}):
            raise ApiError("GUARD_FAILED", f"{code} v{ver} already exists. Upload it as a new version.")
        if not doc:
            doc = _one(conn, f"""INSERT INTO {W}.knowledge_documents (organization_id, workspace_id, document_code, title, document_type)
                                 VALUES (:o, :w, :c, :t, :ty) RETURNING *""", {"o": org, "w": ws, "c": code, "t": title.strip(), "ty": document_type})
        storage, checksum = _store(ws, data)
        src = conn.execute(text(f"""INSERT INTO {W}.source_records (organization_id, workspace_id, source_type, storage_object, checksum, owner_employee_id, evidence_type, access_partition, metadata)
                                    VALUES (:o, :w, 'DOCUMENT', :s, :k, :me, 'OBSERVED', 'SUBMITTED', CAST(:m AS jsonb)) RETURNING source_id"""),
                           {"o": org, "w": ws, "s": storage, "k": checksum, "me": me, "m": json.dumps({"filename": filename[:200], "uploaded_for_curriculum": str(c["curriculum_id"])})}).scalar_one()
        dv = conn.execute(text(f"""INSERT INTO {W}.knowledge_document_versions (organization_id, workspace_id, document_id, version, content, source_id, approval_status, temporal_status)
                                   VALUES (:o, :w, :d, :v, :t, :s, 'PENDING_REVIEW', 'CURRENT') RETURNING document_version_id"""),
                          {"o": org, "w": ws, "d": doc["document_id"], "v": ver, "t": content, "s": src}).scalar_one()
        conn.execute(text(f"""INSERT INTO {W}.curriculum_sources (organization_id, workspace_id, curriculum_id, document_id, document_version_id, relationship_type)
                              VALUES (:o, :w, :c, :d, :v, 'TEACHES')"""), {"o": org, "w": ws, "c": c["curriculum_id"], "d": doc["document_id"], "v": dv})
        rev = _bump(conn, c)
        commands.audit(conn, org, ws, me, "knowledge_document_version.uploaded", "knowledge_document_version", dv, 1, request_id)
        return {"curriculum_id": str(c["curriculum_id"]), "document_version_id": str(dv)}, rev

    return _command(conn, token, "curriculum.add_source", key, payload, run)


# ---------------------------------------------------------------- 3. review the exact version
def _source(conn: Connection, org, ws, c: dict[str, Any], curriculum_source_id: str) -> dict[str, Any]:
    s = _one(conn, f"""SELECT cs.*, v.approval_status, v.version, v.source_id, v.revision AS version_revision, d.document_code, r.owner_employee_id AS uploaded_by
                       FROM {W}.curriculum_sources cs
                       JOIN {W}.knowledge_document_versions v ON v.organization_id=cs.organization_id AND v.workspace_id=cs.workspace_id AND v.document_version_id=cs.document_version_id
                       JOIN {W}.knowledge_documents d ON d.organization_id=v.organization_id AND d.workspace_id=v.workspace_id AND d.document_id=v.document_id
                       JOIN {W}.source_records r ON r.organization_id=v.organization_id AND r.workspace_id=v.workspace_id AND r.source_id=v.source_id
                       WHERE cs.organization_id=:o AND cs.workspace_id=:w AND cs.curriculum_id=:c AND cs.curriculum_source_id=:s FOR UPDATE OF cs, v""",
             {"o": org, "w": ws, "c": c["curriculum_id"], "s": _id(curriculum_source_id, "source")})
    if not s:
        raise ApiError("NOT_FOUND", "This source isn't linked to this curriculum.")
    return s


def review(conn: Connection, token, curriculum_id: str, curriculum_source_id: str, decision: str, reason: str, reviewed_exact_version: bool,
           key: str, expected_revision: int | None, request_id) -> tuple[dict[str, Any], str | None]:
    """Returns (response, job_id to start after commit)."""
    payload = {"curriculum_id": curriculum_id, "source": curriculum_source_id, "decision": decision, "reason": reason, "confirm": reviewed_exact_version, "expected_revision": expected_revision}
    started: dict[str, str | None] = {"job": None}

    def run(r: Any, me) -> tuple[dict[str, Any], int]:
        org, ws = _manager(conn, r, me)
        c = _draft(conn, org, ws, curriculum_id)
        _check_revision(c["revision"], expected_revision, "curriculum")
        s = _source(conn, org, ws, c, curriculum_source_id)
        if s["approval_status"] != "PENDING_REVIEW":
            raise ApiError("GUARD_FAILED", "This version was already reviewed.")
        p = {"o": org, "w": ws, "v": s["document_version_id"], "d": s["document_id"], "me": me}
        if decision == "REJECTED":
            if not reason.strip():
                raise ApiError("MALFORMED_INPUT", "Give a reason for rejecting this version.")
            conn.execute(text(f"UPDATE {W}.knowledge_document_versions SET approval_status='REJECTED', temporal_status='ARCHIVED', updated_at=now(), revision=revision+1 WHERE organization_id=:o AND workspace_id=:w AND document_version_id=:v"), p)
            conn.execute(text(f"DELETE FROM {W}.curriculum_sources WHERE organization_id=:o AND workspace_id=:w AND curriculum_source_id=:s"), {**p, "s": s["curriculum_source_id"]})
            rev = _bump(conn, c)
            commands.audit(conn, org, ws, me, "knowledge_document_version.rejected", "knowledge_document_version", s["document_version_id"], s["version_revision"] + 1, request_id)
            return {"curriculum_id": curriculum_id, "decision": "REJECTED"}, rev
        if not reviewed_exact_version:
            raise ApiError("MALFORMED_INPUT", "Confirm that you reviewed this exact version before approving it.")
        now = datetime.now(UTC)
        # The previous current version stays readable as history; it is never overwritten.
        conn.execute(text(f"""UPDATE {W}.knowledge_document_versions SET temporal_status='SUPERSEDED', updated_at=now(), revision=revision+1
                              WHERE organization_id=:o AND workspace_id=:w AND document_id=:d AND document_version_id <> :v AND temporal_status='CURRENT' AND approval_status='APPROVED'"""), p)
        conn.execute(text(f"""UPDATE {W}.knowledge_document_versions SET approval_status='APPROVED', approved_by_employee_id=:me, approved_at=:t, effective_at=:t, updated_at=now(), revision=revision+1
                              WHERE organization_id=:o AND workspace_id=:w AND document_version_id=:v"""), {**p, "t": now})
        conn.execute(text(f"UPDATE {W}.knowledge_documents SET current_version_id=:v, updated_at=now(), revision=revision+1 WHERE organization_id=:o AND workspace_id=:w AND document_id=:d"), p)
        conn.execute(text(f"UPDATE {W}.source_records SET access_partition='ORGANIZATION', updated_at=now(), revision=revision+1 WHERE organization_id=:o AND workspace_id=:w AND source_id=:s"), {**p, "s": s["source_id"]})
        if ingestion.available():
            started["job"] = str(conn.execute(text(f"""INSERT INTO {W}.knowledge_ingestion_jobs (organization_id, workspace_id, curriculum_id, document_version_id, requested_by)
                                                       VALUES (:o, :w, :c, :v, :me) RETURNING job_id"""), {**p, "c": c["curriculum_id"]}).scalar_one())
        rev = _bump(conn, c)
        own = s["uploaded_by"] == me
        commands.audit(conn, org, ws, me, "knowledge_document_version.approved_by_uploader" if own else "knowledge_document_version.approved",
                       "knowledge_document_version", s["document_version_id"], s["version_revision"] + 1, request_id)
        return {"curriculum_id": curriculum_id, "decision": "APPROVED", "ingestion_job_id": started["job"]}, rev

    out = _command(conn, token, "curriculum.review_source", key, payload, run)
    return out, started["job"]


# ---------------------------------------------------------------- 4. ingestion job (outside the request transaction)
def run_job(job_id: str) -> None:
    """Runs one queued job: RUNNING, her ingestion, then SUCCEEDED (sections and chunks verified)
    or FAILED with a short summary. Each state change is its own transaction."""
    with transaction() as conn:
        job = _one(conn, f"""UPDATE {W}.knowledge_ingestion_jobs SET status='RUNNING', attempts=attempts+1, started_at=now(), finished_at=NULL, error_summary=NULL,
                                    updated_at=now(), revision=revision+1
                             WHERE job_id=:j AND status='QUEUED' RETURNING *""", {"j": _uuid.UUID(job_id)})
        if not job:
            return
        meta = _one(conn, f"""SELECT d.document_code FROM {W}.knowledge_document_versions v JOIN {W}.knowledge_documents d
                              ON d.organization_id=v.organization_id AND d.workspace_id=v.workspace_id AND d.document_id=v.document_id
                              WHERE v.organization_id=:o AND v.workspace_id=:w AND v.document_version_id=:v""",
                      {"o": job["organization_id"], "w": job["workspace_id"], "v": job["document_version_id"]})
    error = None
    try:
        ingestion.run(meta["document_code"], str(job["curriculum_id"]), str(job["workspace_id"]))
    except ingestion.IngestionFailed as e:
        error = str(e)
    except Exception as e:  # noqa: BLE001 - never leave the job RUNNING
        error = f"{type(e).__name__}: unexpected error while running ingestion."
    with transaction() as conn:
        if not error:
            got = conn.execute(text(f"""SELECT (SELECT count(*) FROM {W}.knowledge_sections WHERE organization_id=:o AND workspace_id=:w AND document_version_id=:v),
                                               (SELECT count(*) FROM {W}.knowledge_chunks WHERE organization_id=:o AND workspace_id=:w AND document_version_id=:v AND embedding IS NOT NULL)"""),
                               {"o": job["organization_id"], "w": job["workspace_id"], "v": job["document_version_id"]}).one()
            if not got[0] or not got[1]:
                error = "Ingestion finished but stored no sections or embeddings for this version."
            else:  # a newer version replaces the older one in the draft, objectives following their headings (ADR-050)
                from app.services import curriculum_revisions

                curriculum_revisions.replace_after_ingestion(conn, job["organization_id"], job["workspace_id"], job["curriculum_id"], job["document_version_id"])
        conn.execute(text(f"""UPDATE {W}.knowledge_ingestion_jobs SET status=:s, error_summary=:e, finished_at=now(), updated_at=now(), revision=revision+1 WHERE job_id=:j"""),
                     {"s": "FAILED" if error else "SUCCEEDED", "e": error[:300] if error else None, "j": job["job_id"]})


def retry(conn: Connection, token, curriculum_id: str, job_id: str, key: str, request_id) -> tuple[dict[str, Any], str | None]:
    started: dict[str, str | None] = {"job": None}

    def run(r: Any, me) -> tuple[dict[str, Any], int]:
        org, ws = _manager(conn, r, me)
        c = _draft(conn, org, ws, curriculum_id)
        job = _one(conn, f"SELECT * FROM {W}.knowledge_ingestion_jobs WHERE organization_id=:o AND workspace_id=:w AND job_id=:j AND curriculum_id=:c FOR UPDATE",
                   {"o": org, "w": ws, "j": _id(job_id, "ingestion job"), "c": c["curriculum_id"]})
        if not job:
            raise ApiError("NOT_FOUND", "Ingestion job not found.")
        stale = job["status"] == "RUNNING" and job["started_at"] and datetime.now(UTC) - job["started_at"] > STALE_RUN
        if job["status"] != "FAILED" and not stale:
            raise ApiError("GUARD_FAILED", "Only a failed ingestion can be retried.")
        if not ingestion.available():
            raise ApiError("CAPABILITY_UNAVAILABLE", "Ingestion isn't connected on this server.")
        conn.execute(text(f"UPDATE {W}.knowledge_ingestion_jobs SET status='QUEUED', updated_at=now(), revision=revision+1 WHERE job_id=:j"), {"j": job["job_id"]})
        started["job"] = str(job["job_id"])
        commands.audit(conn, org, ws, me, "knowledge_ingestion.retried", "knowledge_ingestion_job", job["job_id"], job["revision"] + 1, request_id)
        return {"curriculum_id": curriculum_id, "ingestion_job_id": started["job"]}, _bump(conn, c)

    out = _command(conn, token, "curriculum.retry_ingestion", key, {"curriculum_id": curriculum_id, "job_id": job_id}, run)
    return out, started["job"]


def jobs_for(conn: Connection, org, ws, curriculum_id) -> dict[Any, dict[str, Any]]:
    return {j["document_version_id"]: j for j in (dict(x) for x in conn.execute(text(f"SELECT * FROM {W}.knowledge_ingestion_jobs WHERE organization_id=:o AND workspace_id=:w AND curriculum_id=:c"),
                                                                                    {"o": org, "w": ws, "c": curriculum_id}).mappings())}


# ---------------------------------------------------------------- 5. objectives
def save_objective(conn: Connection, token, curriculum_id: str, subtopic_id: str, description: str, criteria: str, key: str, expected_revision: int | None, request_id) -> dict[str, Any]:
    def run(r: Any, me) -> tuple[dict[str, Any], int]:
        org, ws = _manager(conn, r, me)
        c = _draft(conn, org, ws, curriculum_id)
        _check_revision(c["revision"], expected_revision, "curriculum")
        if not description.strip() or not criteria.strip():
            raise ApiError("MALFORMED_INPUT", "Write the objective and how it's assessed.")
        sub = _one(conn, f"""SELECT s.subtopic_id FROM {W}.curriculum_subtopics s JOIN {W}.curriculum_topics t ON t.organization_id=s.organization_id AND t.workspace_id=s.workspace_id AND t.topic_id=s.topic_id
                             WHERE s.organization_id=:o AND s.workspace_id=:w AND s.subtopic_id=:s AND t.curriculum_id=:c""",
                   {"o": org, "w": ws, "s": _id(subtopic_id, "subtopic"), "c": c["curriculum_id"]})
        if not sub:
            raise ApiError("NOT_FOUND", "That subtopic isn't in this curriculum.")
        p = {"o": org, "w": ws, "s": sub["subtopic_id"], "d": description.strip(), "a": json.dumps({"criteria": criteria.strip()})}
        existing = _one(conn, f"SELECT objective_id FROM {W}.learning_objectives WHERE organization_id=:o AND workspace_id=:w AND subtopic_id=:s ORDER BY created_at LIMIT 1 FOR UPDATE", p)
        if existing:
            conn.execute(text(f"""UPDATE {W}.learning_objectives SET description=:d, assessment_criteria=CAST(:a AS jsonb), updated_at=now(), revision=revision+1
                                  WHERE organization_id=:o AND workspace_id=:w AND objective_id=:id"""), {**p, "id": existing["objective_id"]})
            oid = existing["objective_id"]
        else:
            oid = conn.execute(text(f"""INSERT INTO {W}.learning_objectives (organization_id, workspace_id, subtopic_id, description, assessment_criteria, criteria_version)
                                        VALUES (:o, :w, :s, :d, CAST(:a AS jsonb), '1') RETURNING objective_id"""), p).scalar_one()
        commands.audit(conn, org, ws, me, "learning_objective.saved", "learning_objective", oid, 1, request_id)
        return {"curriculum_id": curriculum_id}, _bump(conn, c)

    return _command(conn, token, "curriculum.save_objective", key, {"curriculum_id": curriculum_id, "subtopic_id": subtopic_id, "description": description, "criteria": criteria, "expected_revision": expected_revision}, run)


# ---------------------------------------------------------------- 6. publish
def readiness(conn: Connection, org, ws, c: dict[str, Any]) -> list[dict[str, Any]]:
    cid = c["curriculum_id"]
    sources = repo.linked_sources(conn, org, ws, cid)
    jobs = jobs_for(conn, org, ws, cid)
    topics = repo.topics(conn, org, ws, cid)
    subs = repo.subtopics(conn, org, ws, [t["topic_id"] for t in topics])
    objs = {o["subtopic_id"] for o in repo.objectives(conn, org, ws, [s["subtopic_id"] for s in subs])}
    pending = [s for s in sources if s["approval_status"] != "APPROVED"]
    # A version carried into a revision was ingested before: its stored sections and embeddings count.
    stored = {r[0] for r in conn.execute(text(f"""SELECT v FROM unnest(CAST(:vs AS uuid[])) AS v
                                                WHERE EXISTS (SELECT 1 FROM {W}.knowledge_sections k WHERE k.organization_id=:o AND k.workspace_id=:w AND k.document_version_id=v)
                                                  AND EXISTS (SELECT 1 FROM {W}.knowledge_chunks k WHERE k.organization_id=:o AND k.workspace_id=:w AND k.document_version_id=v AND k.embedding IS NOT NULL)"""),
                                         {"o": org, "w": ws, "vs": [s["document_version_id"] for s in sources]})}
    not_ingested = [s for s in sources if s["approval_status"] == "APPROVED" and (jobs.get(s["document_version_id"]) or {}).get("status") != "SUCCEEDED"
                    and not (s["document_version_id"] not in jobs and s["document_version_id"] in stored)]
    missing = [s for s in subs if s["subtopic_id"] not in objs]
    return [
        {"key": "SOURCE_APPROVED", "label": "At least one approved source", "passed": any(s["approval_status"] == "APPROVED" for s in sources), "detail": f"{len(sources)} linked"},
        {"key": "SOURCES_SETTLED", "label": "Every source approved and ingested", "passed": bool(sources) and not pending and not not_ingested,
         "detail": "; ".join([f"{len(pending)} waiting for review"] * bool(pending) + [f"{len(not_ingested)} not ingested yet"] * bool(not_ingested)) or "All settled"},
        {"key": "PATH", "label": "A learning path with subtopics", "passed": bool(subs), "detail": f"{len(topics)} topics, {len(subs)} subtopics"},
        {"key": "OBJECTIVES", "label": "Every subtopic has an objective and assessment criteria", "passed": bool(subs) and not missing,
         "detail": f"{len(missing)} missing" if missing else "All written"},
    ]


def publish(conn: Connection, token, curriculum_id: str, key: str, expected_revision: int | None, request_id) -> dict[str, Any]:
    def run(r: Any, me) -> tuple[dict[str, Any], int]:
        org, ws = _manager(conn, r, me)
        c = _draft(conn, org, ws, curriculum_id)
        _check_revision(c["revision"], expected_revision, "curriculum")
        failing = [x["label"].lower() for x in readiness(conn, org, ws, c) if not x["passed"]]
        if failing:
            raise ApiError("GUARD_FAILED", f"Not ready to publish: {'; '.join(failing)}.")
        rev = conn.execute(text(f"""UPDATE {W}.curricula SET status='PUBLISHED', published_at=now(), updated_at=now(), revision=revision+1
                                    WHERE organization_id=:o AND workspace_id=:w AND curriculum_id=:c RETURNING revision"""),
                           {"o": org, "w": ws, "c": c["curriculum_id"]}).scalar_one()
        commands.audit(conn, org, ws, me, "curriculum.published", "curriculum", c["curriculum_id"], rev, request_id)
        from app.services import curriculum_revisions

        archived = curriculum_revisions.after_publish(conn, org, ws, c, me, request_id)  # ADR-050: the previous version
        return {"curriculum_id": curriculum_id, "archived": archived}, rev

    return _command(conn, token, "curriculum.publish", key, {"curriculum_id": curriculum_id, "expected_revision": expected_revision}, run)
