"""Scoped SQL for learning sessions (blueprint/04 learning_sessions; tutor turns not stored yet)."""

import uuid
from typing import Any

from sqlalchemy import Connection, text

W = "workweave"


def lock_assignment(conn: Connection, org: uuid.UUID, ws: uuid.UUID, learning_assignment_id: uuid.UUID) -> None:
    """Serialize session creation per assignment so concurrent starts can't open two sessions."""
    conn.execute(
        text(f"SELECT 1 FROM {W}.learning_assignments WHERE organization_id=:o AND workspace_id=:w AND learning_assignment_id=:la FOR UPDATE"),
        {"o": org, "w": ws, "la": learning_assignment_id},
    )


def open_session(conn: Connection, org: uuid.UUID, ws: uuid.UUID, learning_assignment_id: uuid.UUID) -> dict[str, Any] | None:
    r = conn.execute(
        text(
            f"""SELECT * FROM {W}.learning_sessions
                WHERE organization_id=:o AND workspace_id=:w AND learning_assignment_id=:la AND status IN ('ACTIVE', 'PAUSED')
                ORDER BY started_at DESC LIMIT 1"""
        ),
        {"o": org, "w": ws, "la": learning_assignment_id},
    ).first()
    return dict(r._mapping) if r else None


def session_for_employee(conn: Connection, org: uuid.UUID, ws: uuid.UUID, session_id: uuid.UUID, employee_id: uuid.UUID) -> dict[str, Any] | None:
    r = conn.execute(
        text(f"SELECT * FROM {W}.learning_sessions WHERE organization_id=:o AND workspace_id=:w AND learning_session_id=:s AND employee_id=:e"),
        {"o": org, "w": ws, "s": session_id, "e": employee_id},
    ).first()
    return dict(r._mapping) if r else None


def topic_of(conn: Connection, org: uuid.UUID, ws: uuid.UUID, subtopic_id: str | None) -> uuid.UUID | None:
    if not subtopic_id:
        return None
    return conn.execute(
        text(f"SELECT topic_id FROM {W}.curriculum_subtopics WHERE organization_id=:o AND workspace_id=:w AND subtopic_id=:s"),
        {"o": org, "w": ws, "s": subtopic_id},
    ).scalar()


def create_session(conn: Connection, org: uuid.UUID, ws: uuid.UUID, employee_id: uuid.UUID, assignment: dict[str, Any], topic_id: uuid.UUID | None, subtopic_id: str | None, graph_version: str) -> dict[str, Any]:
    sid = uuid.uuid4()
    r = conn.execute(
        text(
            f"""INSERT INTO {W}.learning_sessions (learning_session_id, organization_id, workspace_id, employee_id, learning_assignment_id, curriculum_id,
                    current_topic_id, current_subtopic_id, started_at, status, langgraph_thread_id, graph_version)
                VALUES (:s, :o, :w, :e, :la, :c, :t, :st, now(), 'ACTIVE', :thread, :gv)
                RETURNING *"""
        ),
        # The thread ID is server-generated and scoped to this visitor workspace (blueprint/04).
        {"s": sid, "o": org, "w": ws, "e": employee_id, "la": assignment["learning_assignment_id"], "c": assignment["curriculum_id"], "t": topic_id, "st": subtopic_id, "thread": f"ww-{sid}", "gv": graph_version},
    ).one()
    return dict(r._mapping)


def set_status(conn: Connection, s: dict[str, Any], status: str, topic_id: uuid.UUID | None = None, subtopic_id: str | None = None) -> dict[str, Any]:
    """Status change with the touch_revision trigger bumping revision and updated_at."""
    r = conn.execute(
        text(
            f"""UPDATE {W}.learning_sessions
                SET status=:st, current_topic_id=COALESCE(CAST(:t AS uuid), current_topic_id), current_subtopic_id=COALESCE(CAST(:sub AS uuid), current_subtopic_id)
                WHERE organization_id=:o AND workspace_id=:w AND learning_session_id=:s
                RETURNING *"""
        ),
        {"st": status, "t": topic_id, "sub": subtopic_id, "o": s["organization_id"], "w": s["workspace_id"], "s": s["learning_session_id"]},
    ).one()
    return dict(r._mapping)


def latest_session_status(conn: Connection, org: uuid.UUID, ws: uuid.UUID, learning_assignment_id: uuid.UUID) -> str | None:
    return conn.execute(
        text(f"SELECT status FROM {W}.learning_sessions WHERE organization_id=:o AND workspace_id=:w AND learning_assignment_id=:la ORDER BY started_at DESC LIMIT 1"),
        {"o": org, "w": ws, "la": learning_assignment_id},
    ).scalar()
