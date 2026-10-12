"""Scoped SQL for tutor turns, assessment evidence and progress (canonical learning tables).

learning_turns: one row per client_turn_id (the idempotency receipt). RECEIVED is a short claim
taken before the engine call and stores no learner text; COMMITTED stores the learner input and the
validated reply envelope; FAILED stores no text. employee_learning_events, learning_assessment_attempts
and objective_evidence are append-only (database triggers).

The pending comprehension question is the latest COMPREHENSION_QUESTION event of the assignment
(event_data carries question_id/version, criteria_version, text and issued_turn_id) until an attempt
on it produces PASSED evidence or a newer question replaces it.
"""

import json
import uuid
from typing import Any

from sqlalchemy import Connection, text

W = "workweave"


def _one(conn: Connection, sql: str, p: dict[str, Any]) -> dict[str, Any] | None:
    r = conn.execute(text(sql), p).first()
    return dict(r._mapping) if r else None


def _all(conn: Connection, sql: str, p: dict[str, Any]) -> list[dict[str, Any]]:
    return [dict(r._mapping) for r in conn.execute(text(sql), p)]


# ---------------------------------------------------------------- session and turn receipts
def lock_session(conn: Connection, org, ws, session_id) -> dict[str, Any] | None:
    return _one(conn, f"SELECT * FROM {W}.learning_sessions WHERE organization_id=:o AND workspace_id=:w AND learning_session_id=:s FOR UPDATE", {"o": org, "w": ws, "s": session_id})


def advance_session(conn: Connection, org, ws, session_id, expected_revision: int) -> dict[str, Any] | None:
    """Revision guard: bumps the revision (touch trigger) only if it is still the expected one."""
    return _one(
        conn,
        f"""UPDATE {W}.learning_sessions SET status = status
            WHERE organization_id=:o AND workspace_id=:w AND learning_session_id=:s AND revision=:r AND status='ACTIVE'
            RETURNING *""",
        {"o": org, "w": ws, "s": session_id, "r": expected_revision},
    )


def find_turn(conn: Connection, org, ws, session_id, client_turn_id: uuid.UUID) -> dict[str, Any] | None:
    return _one(
        conn,
        f"""SELECT *, (now() - updated_at) AS age FROM {W}.learning_turns
            WHERE organization_id=:o AND workspace_id=:w AND learning_session_id=:s AND client_turn_id=:c""",
        {"o": org, "w": ws, "s": session_id, "c": client_turn_id},
    )


def _next_sequence(conn: Connection, org, ws, session_id) -> int:
    return conn.execute(
        text(f"SELECT COALESCE(max(sequence), -1) + 1 FROM {W}.learning_turns WHERE organization_id=:o AND workspace_id=:w AND learning_session_id=:s"),
        {"o": org, "w": ws, "s": session_id},
    ).scalar_one()


def claim_turn(conn: Connection, org, ws, session_id, client_turn_id: uuid.UUID, input_hash: str, revision: int) -> dict[str, Any]:
    """Call with the session row locked. Stores no learner text."""
    return _one(
        conn,
        f"""INSERT INTO {W}.learning_turns (organization_id, workspace_id, learning_session_id, client_turn_id, input_hash, sequence, committed_revision, stage)
            VALUES (:o, :w, :s, :c, :h, :seq, :r, 'RECEIVED') RETURNING *""",
        {"o": org, "w": ws, "s": session_id, "c": client_turn_id, "h": input_hash, "seq": _next_sequence(conn, org, ws, session_id), "r": revision},
    )  # type: ignore[return-value]


def reclaim_turn(conn: Connection, org, ws, turn: dict[str, Any], revision: int) -> dict[str, Any]:
    """Retry of a FAILED (or abandoned RECEIVED) turn: claim it again at the end of the sequence."""
    return _one(
        conn,
        f"""UPDATE {W}.learning_turns SET stage='RECEIVED', sequence=:seq, committed_revision=:r, input_reference='{{}}'::jsonb, response_envelope='{{}}'::jsonb
            WHERE organization_id=:o AND workspace_id=:w AND turn_id=:t RETURNING *""",
        {"o": org, "w": ws, "t": turn["turn_id"], "seq": _next_sequence(conn, org, ws, turn["learning_session_id"]), "r": revision},
    )  # type: ignore[return-value]


def fail_turn(conn: Connection, org, ws, turn_id, reason: str) -> None:
    conn.execute(
        text(
            f"""UPDATE {W}.learning_turns SET stage='FAILED', input_reference='{{}}'::jsonb, response_envelope=CAST(:e AS jsonb)
                WHERE organization_id=:o AND workspace_id=:w AND turn_id=:t AND stage='RECEIVED'"""
        ),
        {"o": org, "w": ws, "t": turn_id, "e": json.dumps({"failure": reason})},
    )


def commit_turn(conn: Connection, org, ws, turn_id, input_reference: dict[str, Any], envelope: dict[str, Any], revision: int) -> int:
    return conn.execute(
        text(
            f"""UPDATE {W}.learning_turns SET stage='COMMITTED', input_reference=CAST(:i AS jsonb), response_envelope=CAST(:e AS jsonb), committed_revision=:r
                WHERE organization_id=:o AND workspace_id=:w AND turn_id=:t AND stage='RECEIVED'"""
        ),
        {"o": org, "w": ws, "t": turn_id, "i": json.dumps(input_reference), "e": json.dumps(envelope), "r": revision},
    ).rowcount


def committed_turns(conn: Connection, org, ws, session_id) -> list[dict[str, Any]]:
    return _all(
        conn,
        f"""SELECT turn_id, sequence, input_reference, response_envelope, created_at, updated_at FROM {W}.learning_turns
            WHERE organization_id=:o AND workspace_id=:w AND learning_session_id=:s AND stage='COMMITTED' ORDER BY sequence""",
        {"o": org, "w": ws, "s": session_id},
    )


def committed_reply(conn: Connection, org, ws, session_id, turn_id) -> str | None:
    """The validated tutor reply text of one COMMITTED turn in this session, or None."""
    return conn.execute(
        text(
            f"""SELECT response_envelope->'reply'->>'text' FROM {W}.learning_turns
                WHERE organization_id=:o AND workspace_id=:w AND learning_session_id=:s AND turn_id=:t AND stage='COMMITTED'"""
        ),
        {"o": org, "w": ws, "s": session_id, "t": turn_id},
    ).scalar()


# ---------------------------------------------------------------- curriculum context
def subtopic_objectives(conn: Connection, org, ws, subtopic_id) -> list[dict[str, Any]]:
    return _all(
        conn,
        f"""SELECT objective_id, description, assessment_criteria, criteria_version, required, hint_policy FROM {W}.learning_objectives
            WHERE organization_id=:o AND workspace_id=:w AND subtopic_id=:s ORDER BY created_at, objective_id""",
        {"o": org, "w": ws, "s": subtopic_id},
    )


def curriculum_subtopic_ids(conn: Connection, org, ws, curriculum_id) -> list[uuid.UUID]:
    return [
        r[0]
        for r in conn.execute(
            text(
                f"""SELECT s.subtopic_id FROM {W}.curriculum_subtopics s
                    JOIN {W}.curriculum_topics t ON t.organization_id = s.organization_id AND t.workspace_id = s.workspace_id AND t.topic_id = s.topic_id
                    WHERE t.organization_id=:o AND t.workspace_id=:w AND t.curriculum_id=:c AND t.active AND s.active"""
            ),
            {"o": org, "w": ws, "c": curriculum_id},
        )
    ]


def subtopic_info(conn: Connection, org, ws, subtopic_id) -> dict[str, Any] | None:
    return _one(conn, f"SELECT subtopic_id, topic_id, name FROM {W}.curriculum_subtopics WHERE organization_id=:o AND workspace_id=:w AND subtopic_id=:s", {"o": org, "w": ws, "s": subtopic_id})


# ---------------------------------------------------------------- citation checks (current guidance only)
def current_version(conn: Connection, org, ws, document_version_id) -> dict[str, Any] | None:
    """The version, if it is approved, CURRENT, its document's current pointer and its source unrevoked."""
    return _one(
        conn,
        f"""SELECT v.document_version_id, v.version, v.source_id, d.document_code, d.title, r.evidence_type
            FROM {W}.knowledge_document_versions v
            JOIN {W}.knowledge_documents d ON d.organization_id = v.organization_id AND d.workspace_id = v.workspace_id AND d.document_id = v.document_id
            JOIN {W}.source_records r ON r.organization_id = v.organization_id AND r.workspace_id = v.workspace_id AND r.source_id = v.source_id
            WHERE v.organization_id=:o AND v.workspace_id=:w AND v.document_version_id=:v
              AND v.approval_status='APPROVED' AND v.temporal_status='CURRENT' AND d.current_version_id = v.document_version_id AND r.revoked_at IS NULL""",
        {"o": org, "w": ws, "v": document_version_id},
    )


def section_of_version(conn: Connection, org, ws, document_version_id, section_id) -> dict[str, Any] | None:
    return _one(
        conn,
        f"""SELECT section_id, section_key, topic_heading, subtopic_heading FROM {W}.knowledge_sections
            WHERE organization_id=:o AND workspace_id=:w AND document_version_id=:v AND section_id=:s""",
        {"o": org, "w": ws, "v": document_version_id, "s": section_id},
    )


def chunk_of_version(conn: Connection, org, ws, document_version_id, chunk_id) -> dict[str, Any] | None:
    return _one(
        conn,
        f"""SELECT c.chunk_id, c.source_section_id, c.content, c.heading, c.source_id FROM {W}.knowledge_chunks c
            JOIN {W}.source_records r ON r.organization_id = c.organization_id AND r.workspace_id = c.workspace_id AND r.source_id = c.source_id
            WHERE c.organization_id=:o AND c.workspace_id=:w AND c.document_version_id=:v AND c.chunk_id=:c AND r.revoked_at IS NULL""",
        {"o": org, "w": ws, "v": document_version_id, "c": chunk_id},
    )


def section_text(conn: Connection, org, ws, section_id, limit_chars: int = 1200) -> str:
    rows = conn.execute(
        text(
            f"""SELECT c.content FROM {W}.knowledge_chunks c
                JOIN {W}.source_records r ON r.organization_id = c.organization_id AND r.workspace_id = c.workspace_id AND r.source_id = c.source_id
                WHERE c.organization_id=:o AND c.workspace_id=:w AND c.source_section_id=:s AND r.revoked_at IS NULL ORDER BY c.chunk_index"""
        ),
        {"o": org, "w": ws, "s": section_id},
    )
    return "\n\n".join(r[0] for r in rows)[:limit_chars]


# ---------------------------------------------------------------- events, questions, attempts, evidence, progress
def add_event(conn: Connection, org, ws, session_id, employee_id, event_type: str, operation_key: str, *, topic_id=None, subtopic_id=None, objective_id=None, strategy=None, data=None, source_refs=None) -> None:
    conn.execute(
        text(
            f"""INSERT INTO {W}.employee_learning_events (organization_id, workspace_id, learning_session_id, employee_id, topic_id, subtopic_id, objective_id,
                    event_type, strategy, event_data, source_refs, operation_key)
                VALUES (:o, :w, :s, :e, :t, :st, :ob, :ty, :str, CAST(:d AS jsonb), CAST(:sr AS jsonb), :k)
                ON CONFLICT (organization_id, workspace_id, operation_key) DO NOTHING"""
        ),
        {"o": org, "w": ws, "s": session_id, "e": employee_id, "t": topic_id, "st": subtopic_id, "ob": objective_id, "ty": event_type, "str": strategy,
         "d": json.dumps(data or {}), "sr": json.dumps(source_refs or []), "k": operation_key},
    )


def latest_question(conn: Connection, org, ws, learning_assignment_id) -> dict[str, Any] | None:
    return _one(
        conn,
        f"""SELECT ev.learning_event_id, ev.subtopic_id, ev.objective_id, ev.event_data FROM {W}.employee_learning_events ev
            JOIN {W}.learning_sessions s ON s.organization_id = ev.organization_id AND s.workspace_id = ev.workspace_id AND s.learning_session_id = ev.learning_session_id
            WHERE ev.organization_id=:o AND ev.workspace_id=:w AND s.learning_assignment_id=:la AND ev.event_type='COMPREHENSION_QUESTION'
            ORDER BY ev.created_at DESC, ev.learning_event_id DESC LIMIT 1""",
        {"o": org, "w": ws, "la": learning_assignment_id},
    )


def question_used(conn: Connection, org, ws, question_id: str) -> bool:
    return bool(
        conn.execute(
            text(f"SELECT 1 FROM {W}.employee_learning_events WHERE organization_id=:o AND workspace_id=:w AND event_type='COMPREHENSION_QUESTION' AND event_data->>'question_id' = :q LIMIT 1"),
            {"o": org, "w": ws, "q": question_id},
        ).first()
    )


def question_passed(conn: Connection, org, ws, question_id) -> bool:
    return bool(
        conn.execute(
            text(
                f"""SELECT 1 FROM {W}.learning_assessment_attempts a
                    JOIN {W}.objective_evidence e ON e.organization_id = a.organization_id AND e.workspace_id = a.workspace_id AND e.attempt_id = a.attempt_id
                    WHERE a.organization_id=:o AND a.workspace_id=:w AND a.pending_question_id=:q AND e.outcome='PASSED' LIMIT 1"""
            ),
            {"o": org, "w": ws, "q": question_id},
        ).first()
    )


def add_attempt(conn: Connection, org, ws, turn_id, question_id, objective_id, criteria_version: str, answer_reference: dict, criterion_results: dict, outcome: str, support: dict) -> uuid.UUID:
    return conn.execute(
        text(
            f"""INSERT INTO {W}.learning_assessment_attempts (organization_id, workspace_id, turn_id, pending_question_id, objective_id, criteria_version,
                    answer_reference, criterion_results, outcome, support_metadata)
                VALUES (:o, :w, :t, :q, :ob, :cv, CAST(:a AS jsonb), CAST(:cr AS jsonb), :out, CAST(:sup AS jsonb)) RETURNING attempt_id"""
        ),
        {"o": org, "w": ws, "t": turn_id, "q": question_id, "ob": objective_id, "cv": criteria_version, "a": json.dumps(answer_reference),
         "cr": json.dumps(criterion_results), "out": outcome, "sup": json.dumps(support)},
    ).scalar_one()


def add_evidence(conn: Connection, org, ws, learning_assignment_id, objective_id, criteria_version: str, attempt_id, outcome: str, policy_version: str) -> None:
    conn.execute(
        text(
            f"""INSERT INTO {W}.objective_evidence (organization_id, workspace_id, learning_assignment_id, objective_id, criteria_version, attempt_id, outcome, accepted_at, policy_version)
                VALUES (:o, :w, :la, :ob, :cv, :a, :out, CASE WHEN :out = 'PASSED' THEN now() END, :pv)"""
        ),
        {"o": org, "w": ws, "la": learning_assignment_id, "ob": objective_id, "cv": criteria_version, "a": attempt_id, "out": outcome, "pv": policy_version},
    )


def passed_objective_ids(conn: Connection, org, ws, learning_assignment_id, objectives: list[dict[str, Any]]) -> set:
    """Objectives with PASSED evidence for their CURRENT criteria version in this assignment."""
    if not objectives:
        return set()
    rows = conn.execute(
        text(
            f"""SELECT DISTINCT e.objective_id FROM {W}.objective_evidence e
                JOIN {W}.learning_objectives lo ON lo.organization_id = e.organization_id AND lo.workspace_id = e.workspace_id
                     AND lo.objective_id = e.objective_id AND lo.criteria_version = e.criteria_version
                WHERE e.organization_id=:o AND e.workspace_id=:w AND e.learning_assignment_id=:la AND e.outcome='PASSED' AND e.objective_id = ANY(:ids)"""
        ),
        {"o": org, "w": ws, "la": learning_assignment_id, "ids": [x["objective_id"] for x in objectives]},
    )
    return {r[0] for r in rows}


def lock_progress(conn: Connection, org, ws, learning_assignment_id, subtopic_id) -> dict[str, Any] | None:
    return _one(
        conn,
        f"SELECT * FROM {W}.employee_learning_progress WHERE organization_id=:o AND workspace_id=:w AND learning_assignment_id=:la AND subtopic_id=:s FOR UPDATE",
        {"o": org, "w": ws, "la": learning_assignment_id, "s": subtopic_id},
    )


def set_progress(conn: Connection, org, ws, progress_id, status: str) -> None:
    conn.execute(
        text(
            f"""UPDATE {W}.employee_learning_progress
                SET status=:st, started_at=COALESCE(started_at, now()), completed_at=CASE WHEN :st = 'COMPLETED' THEN now() ELSE completed_at END
                WHERE organization_id=:o AND workspace_id=:w AND progress_id=:p"""
        ),
        {"o": org, "w": ws, "p": progress_id, "st": status},
    )


def topic_complete(conn: Connection, org, ws, learning_assignment_id, topic_id) -> bool:
    return not conn.execute(
        text(
            f"""SELECT 1 FROM {W}.curriculum_subtopics s
                LEFT JOIN {W}.employee_learning_progress p ON p.organization_id = s.organization_id AND p.workspace_id = s.workspace_id
                     AND p.subtopic_id = s.subtopic_id AND p.learning_assignment_id = :la
                WHERE s.organization_id=:o AND s.workspace_id=:w AND s.topic_id=:t AND s.active AND COALESCE(p.status, 'NOT_STARTED') <> 'COMPLETED' LIMIT 1"""
        ),
        {"o": org, "w": ws, "la": learning_assignment_id, "t": topic_id},
    ).first()
