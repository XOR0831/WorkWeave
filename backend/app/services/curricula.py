"""Read-only curricula catalog and detail (PROPOSED GET /curricula, GET /curricula/{id}).

Authorization (approved 2026-10-03, option 2): reads require an explicit, currently valid
`curriculum:read` grant scoped to the whole workspace (resource_scope.scope = "WORKSPACE", no
team/department/employee key). Workspace scope means the holder may read every curriculum in this
workspace and nothing in any other. No other grant authorizes these reads; in particular
`knowledge:review` (team-scoped) no longer does. Every query is scoped by the session's
organization and workspace, so another workspace's curricula are never visible (an ID from
elsewhere is simply NOT_FOUND).

What is returned is what PostgreSQL stores. The preview's authoring workflow fields (processing
stage, section kind, excerpts, filenames, reference-only mappings, review receipts) have no
columns and are not invented: `sources` is always empty here and `linked_sources` carries the
stored curriculum_sources rows. Section headings of a revoked source are withheld; section or
chunk content is never returned.
"""

import json
import uuid as _uuid
from typing import Any

from sqlalchemy import Connection, text

from app.errors import ApiError
from app.repositories import curricula as repo
from app.services.onboarding import _persona

READ_ACTION = "curriculum:read"


def _authorize(conn: Connection, token: str | None):
    conn.execute(text("SET TRANSACTION READ ONLY"))  # reads never write; authoring is curriculum_authoring
    r, employee_id = _persona(conn, token)
    org, ws = r.session["organization_id"], r.session["workspace_id"]
    if not repo.has_workspace_grant(conn, org, ws, employee_id, READ_ACTION):
        raise ApiError("FORBIDDEN", "Curricula & sources needs a workspace-wide curriculum read permission.")
    return org, ws, employee_id


def catalog(conn: Connection, token: str | None) -> dict[str, Any]:
    org, ws, _ = _authorize(conn, token)
    return {
        "curricula": [
            {
                "curriculum_id": str(c["curriculum_id"]),
                "name": c["name"],
                "version": c["version"],
                "status": c["status"],
                "topic_count": c["topic_count"],
                "subtopic_count": c["subtopic_count"],
                "source_count": c["source_count"],
                "pending_review_count": c["pending_review_count"],
            }
            for c in repo.list_curricula(conn, org, ws)
        ],
        "receipts": [],  # review receipts have no table yet
        "sample_available": False,  # the backend has no sample source
    }


def detail(conn: Connection, token: str | None, curriculum_id: str) -> dict[str, Any]:
    org, ws, employee_id = _authorize(conn, token)
    try:
        cid = _uuid.UUID(curriculum_id)
    except ValueError:
        raise ApiError("MALFORMED_INPUT", "That isn't a valid curriculum ID.") from None
    c = repo.curriculum(conn, org, ws, cid)
    if not c:
        raise ApiError("NOT_FOUND", "This curriculum doesn't exist in this workspace.")

    from app.services import curriculum_authoring as authoring
    from app.services import curriculum_revisions as revisions

    editing = c["status"] == "DRAFT" and authoring.can_manage(conn, org, ws, employee_id)
    topics = repo.topics(conn, org, ws, cid)
    subs = repo.subtopics(conn, org, ws, [t["topic_id"] for t in topics], include_left_out=editing)
    objs = repo.objectives(conn, org, ws, [s["subtopic_id"] for s in subs])
    objectives_by_sub: dict[Any, list[dict[str, Any]]] = {}
    for o in objs:
        objectives_by_sub.setdefault(o["subtopic_id"], []).append(
            {
                "objective_id": str(o["objective_id"]),
                "description": o["description"],
                # Stored JSON, verbatim (compact): its structure is pack-defined, not interpreted here.
                "assessment_criteria": json.dumps(o["assessment_criteria"], separators=(",", ":"), sort_keys=True),
                "criteria_version": o["criteria_version"],
                "required": o["required"],
            }
        )
    subs_by_topic: dict[Any, list[dict[str, Any]]] = {}
    for s in subs:
        subs_by_topic.setdefault(s["topic_id"], []).append(
            {"subtopic_id": str(s["subtopic_id"]), "name": s["name"], "order_index": s["order_index"], "objectives": objectives_by_sub.get(s["subtopic_id"], []),
             **({} if s["active"] else {"left_out": True})}
        )

    sources = repo.linked_sources(conn, org, ws, cid)
    visible_versions = [s["document_version_id"] for s in sources if not s["source_revoked"]]
    secs = repo.sections(conn, org, ws, visible_versions)
    links = repo.section_links(conn, org, ws, [s["curriculum_source_id"] for s in sources])
    links_by = {}
    for link in links:
        links_by.setdefault((link["curriculum_source_id"], link["section_id"]), []).append(
            {"topic_id": str(link["topic_id"]), "subtopic_id": str(link["subtopic_id"]), "relationship_type": link["relationship_type"]}
        )

    from app.integrations import ingestion

    jobs = authoring.jobs_for(conn, org, ws, cid)
    manager = authoring.can_manage(conn, org, ws, employee_id)

    def ingestion_dto(s: dict[str, Any]) -> dict[str, Any] | None:
        j = jobs.get(s["document_version_id"])
        if not j:
            return None
        # The stored summary is for operators (CLI/logs); people only hear that an error was encountered.
        failed = "Ingestion couldn't complete because an error was encountered. Try again; if it keeps failing, check the document's headings." if j["error_summary"] else None
        return {"job_id": str(j["job_id"]), "status": j["status"], "attempts": j["attempts"], "error_summary": failed}

    def source_dto(s: dict[str, Any]) -> dict[str, Any]:
        return {
            "ingestion": ingestion_dto(s),
            "curriculum_source_id": str(s["curriculum_source_id"]),
            "document_id": str(s["document_id"]),
            "document_version_id": str(s["document_version_id"]),
            "document_code": s["document_code"],
            "title": s["title"],
            "version": s["version"],
            "relationship_type": s["relationship_type"],
            "approval_status": s["approval_status"],
            "temporal_status": s["temporal_status"],
            "is_current_version": bool(s["is_current_version"]),
            "approved_by": s["approved_by"],
            "approved_at": s["approved_at"].isoformat() if s["approved_at"] else None,
            "source_revoked": bool(s["source_revoked"]),
            "revision": s["revision"],
            # Withheld (null) for a revoked source; otherwise the parsed headings and recorded links.
            "sections": None
            if s["source_revoked"]
            else [
                {
                    "section_id": str(x["section_id"]),
                    "section_key": x["section_key"],
                    "topic_heading": x["topic_heading"],
                    "subtopic_heading": x["subtopic_heading"],
                    "topic_order_index": x["topic_order_index"],
                    "subtopic_order_index": x["subtopic_order_index"],
                    "links": links_by.get((s["curriculum_source_id"], x["section_id"]), []),
                }
                for x in secs
                if x["document_version_id"] == s["document_version_id"]
            ],
        }

    return {
        "curriculum_id": str(c["curriculum_id"]),
        "name": c["name"],
        "version": c["version"],
        "status": c["status"],
        "description": c["description"],
        "revision": c["revision"],
        "published_at": c["published_at"].isoformat() if c["published_at"] else None,
        "seeded": True,
        "topics": [
            {
                "topic_id": str(t["topic_id"]),
                "name": t["name"],
                "order_index": t["order_index"],
                "document_version_id": str(t["document_version_id"]) if t["document_version_id"] else None,
                "subtopics": subs_by_topic.get(t["topic_id"], []),
            }
            for t in topics
        ],
        "sources": [],  # preview authoring workflow state; see linked_sources
        "linked_sources": [source_dto(s) for s in sources],
        # ADR-040: authoring for curriculum:manage holders on drafts.
        "can_manage": manager,
        "ingestion_available": ingestion.available(),
        **({"readiness": authoring.readiness(conn, org, ws, c)} if manager and c["status"] == "DRAFT" else {}),
        # ADR-050: the other versions of this curriculum, and an open draft revision to continue.
        "other_versions": [{"curriculum_id": str(v["curriculum_id"]), "version": v["version"], "status": v["status"]} for v in revisions.other_versions(conn, org, ws, c)],
        **({"draft_revision": {"curriculum_id": str(d["curriculum_id"]), "version": d["version"]}} if manager and c["status"] == "PUBLISHED" and (d := revisions.draft_revision_of(conn, org, ws, c)) else {}),
    }
