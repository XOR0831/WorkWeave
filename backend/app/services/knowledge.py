"""Knowledge and history from the database (owner decision 2026-10-10, ADR-040).

Everyone in the workspace reads it; nobody edits here. It shows every APPROVED document version,
current and superseded (promoted Exit KT artifacts included), and approved knowledge notes whose
audience includes the reader. Drafts, pending reviews, interviews and private notes never appear.

"Index pending" is honest about retrieval: an approved current version whose chunks haven't been
embedded yet (the AI engineer's ingestion) isn't in AI answers yet.
"""

from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import Connection, text

from app.errors import ApiError
from app.services.onboarding import _persona
from app.services.work_commands import _id

W = "workweave"
TZ = ZoneInfo("Asia/Manila")


def _versions(conn: Connection, org, ws) -> list[dict[str, Any]]:
    return [
        dict(r._mapping)
        for r in conn.execute(
            text(
                f"""SELECT v.document_version_id, v.document_id, v.version, v.temporal_status, v.approved_at, v.effective_at, v.content,
                           d.document_code, d.title, d.document_type,
                           e.first_name || ' ' || e.last_name AS approved_by,
                           p.index_status AS promotion_index,
                           EXISTS (SELECT 1 FROM {W}.knowledge_chunks k WHERE k.organization_id=v.organization_id AND k.workspace_id=v.workspace_id
                                   AND k.document_version_id=v.document_version_id) AS indexed,
                           (SELECT n.version FROM {W}.knowledge_document_versions n WHERE n.organization_id=v.organization_id AND n.workspace_id=v.workspace_id
                                   AND n.document_id=v.document_id AND n.approval_status='APPROVED' AND n.temporal_status='CURRENT' LIMIT 1) AS current_version
                    FROM {W}.knowledge_document_versions v
                    JOIN {W}.knowledge_documents d ON d.organization_id=v.organization_id AND d.workspace_id=v.workspace_id AND d.document_id=v.document_id
                    LEFT JOIN {W}.employees e ON e.organization_id=v.organization_id AND e.workspace_id=v.workspace_id AND e.employee_id=v.approved_by_employee_id
                    LEFT JOIN {W}.knowledge_promotions p ON p.organization_id=v.organization_id AND p.workspace_id=v.workspace_id AND p.document_version_id=v.document_version_id
                    WHERE v.organization_id=:o AND v.workspace_id=:w AND v.approval_status='APPROVED'
                    ORDER BY d.document_code, v.approved_at DESC NULLS LAST, v.version DESC"""
            ),
            {"o": org, "w": ws},
        )
    ]


def _index(v: dict[str, Any]) -> str | None:
    if v["temporal_status"] != "CURRENT":
        return None
    return "READY" if v["indexed"] else (v["promotion_index"] or "PENDING")


def _effective(v: dict[str, Any]) -> str:
    if v["temporal_status"] == "CURRENT":
        return f"Current since {v['effective_at'].astimezone(TZ):%d %b %Y}" if v["effective_at"] else "Current"
    if v["current_version"]:
        return f"Superseded by v{v['current_version']}"
    return "Superseded; not current instructions"


def _dto(v: dict[str, Any]) -> dict[str, Any]:
    return {
        "document_version_id": str(v["document_version_id"]),
        "document_id": str(v["document_id"]),
        "document_code": v["document_code"] or "",
        "title": v["title"],
        "version": v["version"],
        "approval_status": "APPROVED",
        "temporal_status": v["temporal_status"],
        **({"approved_by": v["approved_by"]} if v["approved_by"] else {}),
        "effective_label": _effective(v),
        "document_type": v["document_type"],
        **({"index_status": i} if (i := _index(v)) else {}),
    }


def documents(conn: Connection, token: str | None) -> list[dict[str, Any]]:
    r, _ = _persona(conn, token)
    return [_dto(v) for v in _versions(conn, r.session["organization_id"], r.session["workspace_id"])]


def content(conn: Connection, token: str | None, document_version_id: str) -> dict[str, Any]:
    r, _ = _persona(conn, token)
    vid = _id(document_version_id, "document version")
    v = next((x for x in _versions(conn, r.session["organization_id"], r.session["workspace_id"]) if x["document_version_id"] == vid), None)
    if not v:
        raise ApiError("NOT_FOUND", "No approved document version with that ID in this workspace.")
    return {"version": _dto(v), "text": v["content"]}


def _notes(conn: Connection, org, ws, me) -> list[dict[str, Any]]:
    """Approved knowledge notes for this reader: organization-wide ones, and team ones from the
    reader's own team."""
    return [
        dict(r._mapping)
        for r in conn.execute(
            text(
                f"""SELECT m.memory_id, m.content, m.evidence_type, m.approved_at, m.approved_audience
                    FROM {W}.memory_records m
                    JOIN {W}.memory_drafts d ON d.organization_id=m.organization_id AND d.workspace_id=m.workspace_id AND d.draft_id=m.originating_draft_id
                    WHERE m.organization_id=:o AND m.workspace_id=:w
                      AND (m.approved_audience ? 'ORGANIZATION'
                           OR (m.approved_audience ? 'TEAM' AND EXISTS (
                               SELECT 1 FROM {W}.employee_team_memberships a JOIN {W}.employee_team_memberships b
                                 ON b.organization_id=a.organization_id AND b.workspace_id=a.workspace_id AND b.team_id=a.team_id AND b.is_active
                               WHERE a.organization_id=m.organization_id AND a.workspace_id=m.workspace_id AND a.employee_id=d.owner_employee_id AND a.is_active
                                 AND b.employee_id=:me)))
                    ORDER BY m.approved_at DESC"""
            ),
            {"o": org, "w": ws, "me": me},
        )
    ]


def timeline(conn: Connection, token: str | None) -> list[dict[str, Any]]:
    r, me = _persona(conn, token)
    org, ws = r.session["organization_id"], r.session["workspace_id"]
    rows: list[tuple[datetime, dict[str, Any]]] = []
    for v in _versions(conn, org, ws):
        promoted = v["document_type"] == "KT_ARTIFACT"
        index = _index(v)
        detail = f"{v['title']}. {_effective(v)}."
        if index == "PENDING":
            detail += " Waiting for indexing, so it isn't in AI answers yet."
        rows.append((v["approved_at"] or datetime.min.replace(tzinfo=UTC), {
            "entry_id": f"dv-{v['document_version_id']}",
            "label": f"{v['document_code']} v{v['version']} {'approved from Exit KT' if promoted else 'approved'}",
            "detail": detail,
            "kind": "KT_PROMOTION" if promoted else "DOCUMENT_VERSION",
            "temporal": "HISTORICAL" if v["temporal_status"] != "CURRENT" else "PENDING" if index == "PENDING" else "CURRENT",
            "evidence_type": "REPORTED" if promoted else "OBSERVED",
            "document_version_id": str(v["document_version_id"]),
        }))
    for n in _notes(conn, org, ws, me):
        rows.append((n["approved_at"], {
            "entry_id": f"mr-{n['memory_id']}",
            "label": "Knowledge note approved",
            "detail": n["content"],
            "kind": "MEMORY_RECORD",
            "temporal": "CURRENT",
            "evidence_type": n["evidence_type"],
        }))
    return [e for _, e in sorted(rows, key=lambda x: x[0], reverse=True)]
