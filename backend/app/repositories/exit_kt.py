"""Exit KT queries (blueprint 04/07, ADR-039). Every query is scoped to one workspace."""

import json
import uuid
from typing import Any

from sqlalchemy import Connection, text

W = "workweave"

# Table -> primary key, for the generic insert/update below (table names are constants, never input).
KEYS = {
    "exit_kt_cases": "exit_kt_case_id",
    "exit_kt_knowledge_items": "kt_item_id",
    "exit_kt_sources": "source_id",
    "exit_kt_findings": "finding_id",
    "exit_kt_artifacts": "artifact_id",
    "exit_kt_artifact_revisions": "artifact_revision_id",
    "knowledge_approvals": "approval_id",
    "knowledge_promotions": "promotion_id",
    "knowledge_documents": "document_id",
    "knowledge_document_versions": "document_version_id",
    "responsibilities": "responsibility_id",
    "responsibility_transfers": "transfer_id",
    "exit_kt_packages": "package_id",
    "exit_kt_package_versions": "package_version_id",
    "kt_checklist_items": "checklist_item_id",
    "consent_sessions": "consent_session_id",
    "exit_kt_interviews": "interview_id",
    "exit_kt_interview_messages": "message_id",
    "exit_kt_copilot_messages": "message_id",
}
JSON_COLS = {"evidence_refs", "source_refs", "relevance_data", "draft_sections", "sections", "artifact_revision_refs", "source_revisions", "context_revisions", "recommendation_data",
             "discovery", "risk_factors", "evidence_sources", "citations", "unknowns", "metadata", "extracted_data", "requested_audience", "raw_retention"}


def _all(conn: Connection, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    return [dict(r._mapping) for r in conn.execute(text(sql), params)]


def _one(conn: Connection, sql: str, params: dict[str, Any]) -> dict[str, Any] | None:
    rows = _all(conn, sql, params)
    return rows[0] if rows else None


def _values(fields: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    params, exprs = {}, {}
    for k, v in fields.items():
        if k in JSON_COLS:
            params[k], exprs[k] = json.dumps(v), f"CAST(:{k} AS jsonb)"
        else:
            params[k], exprs[k] = v, f":{k}"
    return params, exprs


def insert(conn: Connection, table: str, org, ws, **fields: Any) -> dict[str, Any]:
    assert table in KEYS
    params, exprs = _values(fields)
    cols = ", ".join(["organization_id", "workspace_id", *exprs])
    vals = ", ".join([":o", ":w", *exprs.values()])
    return dict(conn.execute(text(f"INSERT INTO {W}.{table} ({cols}) VALUES ({vals}) RETURNING *"), {**params, "o": org, "w": ws}).one()._mapping)


def update(conn: Connection, table: str, row: dict[str, Any], **fields: Any) -> dict[str, Any]:
    """Updates one row and bumps its revision (and updated_at where the table has one)."""
    assert table in KEYS
    key = KEYS[table]
    params, exprs = _values(fields)
    sets = [f"{k} = {e}" for k, e in exprs.items()]
    if "revision" in row and "revision" not in fields:
        sets.append("revision = revision + 1")
    if "updated_at" in row and "updated_at" not in fields:
        sets.append("updated_at = now()")
    return dict(
        conn.execute(text(f"UPDATE {W}.{table} SET {', '.join(sets)} WHERE organization_id=:o AND workspace_id=:w AND {key}=:pk RETURNING *"),
                     {**params, "o": row["organization_id"], "w": row["workspace_id"], "pk": row[key]}).one()._mapping
    )


def get(conn: Connection, table: str, org, ws, pk, lock: bool = False) -> dict[str, Any] | None:
    assert table in KEYS
    return _one(conn, f"SELECT * FROM {W}.{table} WHERE organization_id=:o AND workspace_id=:w AND {KEYS[table]}=:pk{' FOR UPDATE' if lock else ''}", {"o": org, "w": ws, "pk": pk})


def of_case(conn: Connection, table: str, org, ws, case_id, order: str = "created_at") -> list[dict[str, Any]]:
    assert table in KEYS and order in ("created_at", "started_at")
    return _all(conn, f"SELECT * FROM {W}.{table} WHERE organization_id=:o AND workspace_id=:w AND exit_kt_case_id=:c ORDER BY {order}, {KEYS[table]}", {"o": org, "w": ws, "c": case_id})


# ---------------------------------------------------------------- cases and people
def cases(conn: Connection, org, ws) -> list[dict[str, Any]]:
    """Cases newest first, with their package's successor and the proposed new owners."""
    return _all(
        conn,
        f"""SELECT c.*, p.successor_employee_id,
                   COALESCE(array_agg(DISTINCT COALESCE(t.final_owner_employee_id, t.recommended_owner_employee_id))
                            FILTER (WHERE COALESCE(t.final_owner_employee_id, t.recommended_owner_employee_id) IS NOT NULL), '{{}}') AS proposed_owners
            FROM {W}.exit_kt_cases c
            LEFT JOIN {W}.exit_kt_packages p ON p.organization_id=c.organization_id AND p.workspace_id=c.workspace_id AND p.exit_kt_case_id=c.exit_kt_case_id
            LEFT JOIN {W}.responsibility_transfers t ON t.organization_id=c.organization_id AND t.workspace_id=c.workspace_id AND t.exit_kt_case_id=c.exit_kt_case_id
            WHERE c.organization_id=:o AND c.workspace_id=:w
            GROUP BY c.exit_kt_case_id, p.successor_employee_id
            ORDER BY c.started_at DESC""",
        {"o": org, "w": ws},
    )


def employee_teams(conn: Connection, org, ws, employee_id) -> list[str]:
    return [r["team_id"] for r in _all(conn, f"SELECT team_id::text AS team_id FROM {W}.employee_team_memberships WHERE organization_id=:o AND workspace_id=:w AND employee_id=:e AND is_active",
                                       {"o": org, "w": ws, "e": employee_id})]


def active_employee(conn: Connection, org, ws, employee_id) -> dict[str, Any] | None:
    return _one(conn, f"SELECT employee_id, first_name, last_name FROM {W}.employees WHERE organization_id=:o AND workspace_id=:w AND employee_id=:e AND employment_status IN ('ACTIVE','NOTICE_PERIOD','ONBOARDING')",
                {"o": org, "w": ws, "e": employee_id})


def open_work_of(conn: Connection, org, ws, employee_id) -> list[str]:
    """External IDs of open tickets whose latest assignment is this employee's."""
    return [
        r["external_id"]
        for r in _all(
            conn,
            f"""SELECT wi.external_id FROM {W}.work_items wi
                JOIN LATERAL (SELECT employee_id FROM {W}.work_item_assignments a WHERE a.organization_id=wi.organization_id AND a.workspace_id=wi.workspace_id
                              AND a.work_item_id=wi.work_item_id ORDER BY a.assigned_at DESC LIMIT 1) last ON true
                WHERE wi.organization_id=:o AND wi.workspace_id=:w AND last.employee_id=:e AND wi.status NOT IN ('COMPLETED','CLOSED','CANCELLED')
                  AND coalesce(wi.metadata->>'historical_only', 'false') <> 'true'
                ORDER BY wi.external_id""",
            {"o": org, "w": ws, "e": employee_id},
        )
    ]


# ---------------------------------------------------------------- knowledge
def items(conn: Connection, org, ws, case_id) -> list[dict[str, Any]]:
    return _all(conn, f"SELECT * FROM {W}.exit_kt_knowledge_items WHERE organization_id=:o AND workspace_id=:w AND exit_kt_case_id=:c ORDER BY created_at, title", {"o": org, "w": ws, "c": case_id})


def sources(conn: Connection, org, ws, item_ids: list) -> list[dict[str, Any]]:
    if not item_ids:
        return []
    return _all(conn, f"SELECT * FROM {W}.exit_kt_sources WHERE organization_id=:o AND workspace_id=:w AND kt_item_id = ANY(:i) ORDER BY created_at", {"o": org, "w": ws, "i": item_ids})


def document_version(conn: Connection, org, ws, version_id: str) -> dict[str, Any] | None:
    """A document version with its document, and the document's current approved version."""
    try:
        vid = uuid.UUID(version_id)
    except ValueError:
        return None
    return _one(
        conn,
        f"""SELECT v.document_version_id, v.version, v.approval_status, v.temporal_status, d.document_id, d.document_code, d.title,
                   cur.document_version_id AS current_version_id, cur.version AS current_version
            FROM {W}.knowledge_document_versions v
            JOIN {W}.knowledge_documents d ON d.organization_id=v.organization_id AND d.workspace_id=v.workspace_id AND d.document_id=v.document_id
            LEFT JOIN {W}.knowledge_document_versions cur ON cur.organization_id=d.organization_id AND cur.workspace_id=d.workspace_id AND cur.document_id=d.document_id
                 AND cur.approval_status='APPROVED' AND cur.temporal_status='CURRENT'
            WHERE v.organization_id=:o AND v.workspace_id=:w AND v.document_version_id=:v""",
        {"o": org, "w": ws, "v": vid},
    )


def source_records(conn: Connection, org, ws, ids: list[str]) -> dict[str, dict[str, Any]]:
    keep = []
    for i in ids:
        try:
            keep.append(uuid.UUID(str(i)))
        except ValueError:
            pass
    if not keep:
        return {}
    return {str(r["source_id"]): r for r in _all(conn, f"SELECT source_id, source_type, evidence_type, access_partition FROM {W}.source_records WHERE organization_id=:o AND workspace_id=:w AND source_id = ANY(:s)",
                                                 {"o": org, "w": ws, "s": keep})}


def interviews(conn: Connection, org, ws, item_ids: list) -> list[dict[str, Any]]:
    if not item_ids:
        return []
    return _all(conn, f"SELECT * FROM {W}.exit_kt_interviews WHERE organization_id=:o AND workspace_id=:w AND kt_item_id = ANY(:i) ORDER BY started_at", {"o": org, "w": ws, "i": item_ids})


def interview_messages(conn: Connection, org, ws, interview_ids: list) -> list[dict[str, Any]]:
    if not interview_ids:
        return []
    return _all(conn, f"SELECT * FROM {W}.exit_kt_interview_messages WHERE organization_id=:o AND workspace_id=:w AND interview_id = ANY(:i) ORDER BY created_at, message_id", {"o": org, "w": ws, "i": interview_ids})


# ---------------------------------------------------------------- artifacts and promotion
def artifacts(conn: Connection, org, ws, item_ids: list) -> list[dict[str, Any]]:
    if not item_ids:
        return []
    return _all(conn, f"SELECT * FROM {W}.exit_kt_artifacts WHERE organization_id=:o AND workspace_id=:w AND kt_item_id = ANY(:i) ORDER BY created_at, artifact_id", {"o": org, "w": ws, "i": item_ids})


def revisions(conn: Connection, org, ws, artifact_ids: list) -> list[dict[str, Any]]:
    if not artifact_ids:
        return []
    return _all(
        conn,
        f"""SELECT r.*, a.review_comment, a.reviewer_employee_id AS reviewed_by_id
            FROM {W}.exit_kt_artifact_revisions r
            LEFT JOIN LATERAL (SELECT review_comment, reviewer_employee_id FROM {W}.knowledge_approvals k WHERE k.organization_id=r.organization_id AND k.workspace_id=r.workspace_id
                               AND k.artifact_revision_id=r.artifact_revision_id AND k.status <> 'PENDING' ORDER BY k.reviewed_at DESC LIMIT 1) a ON true
            WHERE r.organization_id=:o AND r.workspace_id=:w AND r.artifact_id = ANY(:a) ORDER BY r.version""",
        {"o": org, "w": ws, "a": artifact_ids},
    )


def approval(conn: Connection, org, ws, revision_id, reviewer_id) -> dict[str, Any] | None:
    return _one(conn, f"SELECT * FROM {W}.knowledge_approvals WHERE organization_id=:o AND workspace_id=:w AND artifact_revision_id=:r AND reviewer_employee_id=:e FOR UPDATE",
                {"o": org, "w": ws, "r": revision_id, "e": reviewer_id})


def promotions(conn: Connection, org, ws, revision_ids: list) -> list[dict[str, Any]]:
    if not revision_ids:
        return []
    return _all(
        conn,
        f"""SELECT p.*, d.document_code, v.version FROM {W}.knowledge_promotions p
            JOIN {W}.knowledge_document_versions v ON v.organization_id=p.organization_id AND v.workspace_id=p.workspace_id AND v.document_version_id=p.document_version_id
            JOIN {W}.knowledge_documents d ON d.organization_id=v.organization_id AND d.workspace_id=v.workspace_id AND d.document_id=v.document_id
            WHERE p.organization_id=:o AND p.workspace_id=:w AND p.artifact_revision_id = ANY(:r)""",
        {"o": org, "w": ws, "r": revision_ids},
    )


# ---------------------------------------------------------------- responsibilities and the package
def responsibilities(conn: Connection, org, ws, ids: list, owner_id) -> list[dict[str, Any]]:
    return _all(conn, f"SELECT * FROM {W}.responsibilities WHERE organization_id=:o AND workspace_id=:w AND (responsibility_id = ANY(:i) OR owner_employee_id=:e) ORDER BY created_at, title",
                {"o": org, "w": ws, "i": ids, "e": owner_id})


def package(conn: Connection, org, ws, case_id, lock: bool = False) -> dict[str, Any] | None:
    return _one(conn, f"SELECT * FROM {W}.exit_kt_packages WHERE organization_id=:o AND workspace_id=:w AND exit_kt_case_id=:c ORDER BY created_at LIMIT 1{' FOR UPDATE' if lock else ''}",
                {"o": org, "w": ws, "c": case_id})


def package_responsibilities(conn: Connection, org, ws, package_id) -> list:
    return [r["responsibility_id"] for r in _all(conn, f"SELECT responsibility_id FROM {W}.exit_kt_package_responsibilities WHERE organization_id=:o AND workspace_id=:w AND package_id=:p",
                                                 {"o": org, "w": ws, "p": package_id})]


def package_versions(conn: Connection, org, ws, package_id) -> list[dict[str, Any]]:
    return _all(conn, f"SELECT * FROM {W}.exit_kt_package_versions WHERE organization_id=:o AND workspace_id=:w AND package_id=:p ORDER BY content_revision", {"o": org, "w": ws, "p": package_id})


def receipts(conn: Connection, org, ws, version_ids: list) -> list[dict[str, Any]]:
    if not version_ids:
        return []
    return _all(conn, f"SELECT * FROM {W}.successor_receipts WHERE organization_id=:o AND workspace_id=:w AND package_version_id = ANY(:v) ORDER BY received_at", {"o": org, "w": ws, "v": version_ids})


def add_receipt(conn: Connection, org, ws, version_id, employee_id) -> bool:
    """Idempotent: one receipt per successor and approved version. True when newly recorded."""
    return conn.execute(
        text(f"""INSERT INTO {W}.successor_receipts (organization_id, workspace_id, package_version_id, successor_employee_id, received_at)
                 VALUES (:o, :w, :v, :e, now()) ON CONFLICT (organization_id, workspace_id, package_version_id, successor_employee_id) DO NOTHING RETURNING receipt_id"""),
        {"o": org, "w": ws, "v": version_id, "e": employee_id},
    ).first() is not None
