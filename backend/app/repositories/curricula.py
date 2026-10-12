"""Read-only curriculum queries. Every query is scoped by organization AND workspace."""

import uuid
from typing import Any

from sqlalchemy import Connection, text

W = "workweave"


def _rows(conn: Connection, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    return [dict(r._mapping) for r in conn.execute(text(sql), params)]


# Keys that narrow a grant below the whole workspace. A workspace-scoped grant must have none.
NARROWING_KEYS = ["team_id", "department_id", "employee_id"]


def has_workspace_grant(conn: Connection, org: uuid.UUID, ws: uuid.UUID, employee_id: uuid.UUID, action: str) -> bool:
    """A currently valid grant of `action` to this actor in this workspace whose scope is explicitly
    the whole workspace: resource_scope.scope = "WORKSPACE" and no narrowing key. A missing marker is
    never read as workspace-wide."""
    return bool(
        conn.execute(
            text(
                f"""SELECT 1 FROM {W}.permission_grants
                    WHERE organization_id = :o AND workspace_id = :w AND actor_id = :e AND action = :a
                      AND valid_from <= now() AND (valid_until IS NULL OR valid_until > now())
                      AND resource_scope->>'scope' = 'WORKSPACE'
                      AND NOT (resource_scope ?| CAST(:narrow AS text[]))
                    LIMIT 1"""
            ),
            {"o": org, "w": ws, "e": employee_id, "a": action, "narrow": NARROWING_KEYS},
        ).first()
    )


def list_curricula(conn: Connection, org: uuid.UUID, ws: uuid.UUID) -> list[dict[str, Any]]:
    return _rows(
        conn,
        f"""SELECT c.curriculum_id, c.name, c.version, c.status,
                   (SELECT count(*) FROM {W}.curriculum_topics t
                     WHERE t.organization_id = c.organization_id AND t.workspace_id = c.workspace_id
                       AND t.curriculum_id = c.curriculum_id AND t.active) AS topic_count,
                   (SELECT count(*) FROM {W}.curriculum_subtopics s
                      JOIN {W}.curriculum_topics t
                        ON t.organization_id = s.organization_id AND t.workspace_id = s.workspace_id AND t.topic_id = s.topic_id
                     WHERE t.organization_id = c.organization_id AND t.workspace_id = c.workspace_id
                       AND t.curriculum_id = c.curriculum_id AND t.active AND s.active) AS subtopic_count,
                   (SELECT count(*) FROM {W}.curriculum_sources cs
                     WHERE cs.organization_id = c.organization_id AND cs.workspace_id = c.workspace_id
                       AND cs.curriculum_id = c.curriculum_id) AS source_count,
                   (SELECT count(*) FROM {W}.curriculum_sources cs
                      JOIN {W}.knowledge_document_versions v
                        ON v.organization_id = cs.organization_id AND v.workspace_id = cs.workspace_id
                       AND v.document_version_id = cs.document_version_id
                     WHERE cs.organization_id = c.organization_id AND cs.workspace_id = c.workspace_id
                       AND cs.curriculum_id = c.curriculum_id AND v.approval_status = 'PENDING_REVIEW') AS pending_review_count
            FROM {W}.curricula c
            WHERE c.organization_id = :o AND c.workspace_id = :w
            ORDER BY c.name, c.version""",
        {"o": org, "w": ws},
    )


def curriculum(conn: Connection, org: uuid.UUID, ws: uuid.UUID, curriculum_id: uuid.UUID) -> dict[str, Any] | None:
    rows = _rows(
        conn,
        f"""SELECT curriculum_id, name, version, status, description, published_at, revision
            FROM {W}.curricula WHERE organization_id = :o AND workspace_id = :w AND curriculum_id = :c""",
        {"o": org, "w": ws, "c": curriculum_id},
    )
    return rows[0] if rows else None


def topics(conn: Connection, org: uuid.UUID, ws: uuid.UUID, curriculum_id: uuid.UUID) -> list[dict[str, Any]]:
    """Active topics: version-null learner topics first, then document-bound topics by version."""
    return _rows(
        conn,
        f"""SELECT t.topic_id, t.name, t.order_index, t.document_version_id
            FROM {W}.curriculum_topics t
            WHERE t.organization_id = :o AND t.workspace_id = :w AND t.curriculum_id = :c AND t.active
            ORDER BY t.document_version_id NULLS FIRST, t.order_index, t.name""",
        {"o": org, "w": ws, "c": curriculum_id},
    )


def subtopics(conn: Connection, org: uuid.UUID, ws: uuid.UUID, topic_ids: list[uuid.UUID], include_left_out: bool = False) -> list[dict[str, Any]]:
    """Active subtopics; a draft's editor also gets the ones left out of the path (`active` false)."""
    if not topic_ids:
        return []
    return _rows(
        conn,
        f"""SELECT s.subtopic_id, s.topic_id, s.name, s.order_index, s.active
            FROM {W}.curriculum_subtopics s
            WHERE s.organization_id = :o AND s.workspace_id = :w AND s.topic_id = ANY(:t) AND (s.active OR :all)
            ORDER BY s.order_index, s.name""",
        {"o": org, "w": ws, "t": topic_ids, "all": include_left_out},
    )


def objectives(conn: Connection, org: uuid.UUID, ws: uuid.UUID, subtopic_ids: list[uuid.UUID]) -> list[dict[str, Any]]:
    if not subtopic_ids:
        return []
    return _rows(
        conn,
        f"""SELECT lo.objective_id, lo.subtopic_id, lo.description, lo.assessment_criteria, lo.criteria_version, lo.required
            FROM {W}.learning_objectives lo
            WHERE lo.organization_id = :o AND lo.workspace_id = :w AND lo.subtopic_id = ANY(:s)
            ORDER BY lo.created_at, lo.objective_id""",
        {"o": org, "w": ws, "s": subtopic_ids},
    )


def linked_sources(conn: Connection, org: uuid.UUID, ws: uuid.UUID, curriculum_id: uuid.UUID) -> list[dict[str, Any]]:
    """curriculum_sources rows with their exact document version, as stored. No inference."""
    return _rows(
        conn,
        f"""SELECT cs.curriculum_source_id, cs.document_id, cs.document_version_id, cs.relationship_type, cs.revision,
                   d.document_code, d.title, v.version, v.approval_status, v.temporal_status,
                   (d.current_version_id = v.document_version_id) AS is_current_version,
                   v.approved_at, e.first_name || ' ' || e.last_name AS approved_by,
                   (r.revoked_at IS NOT NULL) AS source_revoked
            FROM {W}.curriculum_sources cs
            JOIN {W}.knowledge_document_versions v
              ON v.organization_id = cs.organization_id AND v.workspace_id = cs.workspace_id AND v.document_version_id = cs.document_version_id
            JOIN {W}.knowledge_documents d
              ON d.organization_id = v.organization_id AND d.workspace_id = v.workspace_id AND d.document_id = v.document_id
            JOIN {W}.source_records r
              ON r.organization_id = v.organization_id AND r.workspace_id = v.workspace_id AND r.source_id = v.source_id
            LEFT JOIN {W}.employees e
              ON e.organization_id = v.organization_id AND e.workspace_id = v.workspace_id AND e.employee_id = v.approved_by_employee_id
            WHERE cs.organization_id = :o AND cs.workspace_id = :w AND cs.curriculum_id = :c
            ORDER BY d.document_code, v.version""",
        {"o": org, "w": ws, "c": curriculum_id},
    )


def sections(conn: Connection, org: uuid.UUID, ws: uuid.UUID, document_version_ids: list[uuid.UUID]) -> list[dict[str, Any]]:
    """Parsed H2/H3 headings of the given versions (headings only: no section or chunk content)."""
    if not document_version_ids:
        return []
    return _rows(
        conn,
        f"""SELECT section_id, document_version_id, section_key, topic_heading, subtopic_heading, topic_order_index, subtopic_order_index
            FROM {W}.knowledge_sections
            WHERE organization_id = :o AND workspace_id = :w AND document_version_id = ANY(:v)
            ORDER BY topic_order_index, subtopic_order_index, section_key""",
        {"o": org, "w": ws, "v": document_version_ids},
    )


def section_links(conn: Connection, org: uuid.UUID, ws: uuid.UUID, curriculum_source_ids: list[uuid.UUID]) -> list[dict[str, Any]]:
    """Recorded section → subtopic links (curriculum_source_sections), as stored."""
    if not curriculum_source_ids:
        return []
    return _rows(
        conn,
        f"""SELECT curriculum_source_id, section_id, topic_id, subtopic_id, relationship_type
            FROM {W}.curriculum_source_sections
            WHERE organization_id = :o AND workspace_id = :w AND curriculum_source_id = ANY(:cs)
            ORDER BY section_id, subtopic_id""",
        {"o": org, "w": ws, "cs": curriculum_source_ids},
    )
