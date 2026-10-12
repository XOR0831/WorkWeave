"""Onboarding read paths (blueprint/07: GET /onboarding, GET /onboarding/progress).

Deterministic only: assigned curriculum, ordered learning path, saved progress and resume
position. The tutor conversation (sessions, turns, assessment) is the AI engineer's and is not
wired here; session state is persisted by the tutor shell below and every reply comes from the
injected TutorEngine. Learner projections never include assessment criteria, attempts or conversations.
"""

import uuid as _uuid
from typing import Any

from sqlalchemy import Connection

from app.errors import ApiError
from app.integrations.tutor import NOT_CONNECTED, TutorContext, get_tutor
from app.repositories import commands, learning, turns
from app.repositories import demo as repo
from app.services import engine_turns, tutor_turns
from app.services import usage
from app.services.demo import resolve


def _persona(conn: Connection, token: str | None):
    r = resolve(conn, token)
    assert r is not None
    if not r.session["active_employee_id"]:
        raise ApiError("GUARD_FAILED", "Choose a persona first.")
    return r, r.session["active_employee_id"]


def _topics(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    topics: dict[str, dict[str, Any]] = {}
    for row in rows:
        t = topics.setdefault(str(row["topic_id"]), {"topic_id": str(row["topic_id"]), "name": row["topic_name"], "order_index": row["topic_order"], "subtopics": []})
        t["subtopics"].append({"subtopic_id": str(row["subtopic_id"]), "name": row["name"], "order_index": row["order_index"], "objective": row["objective"] or "", "status": row["status"], "optional": bool(row["optional"])})
    return list(topics.values())


def resume_position(rows: list[dict[str, Any]]) -> str | None:
    """First IN_PROGRESS subtopic; else the first NOT_STARTED one whose prerequisites are complete."""
    status = {str(r["subtopic_id"]): r["status"] for r in rows}
    for r in rows:
        if r["status"] == "IN_PROGRESS":
            return str(r["subtopic_id"])
    for r in rows:
        if r["status"] == "NOT_STARTED" and all(status.get(str(p)) == "COMPLETED" for p in r["prerequisites"]):
            return str(r["subtopic_id"])
    return None


def _session_status(conn: Connection, org, ws, learning_assignment_id) -> str:
    st = learning.latest_session_status(conn, org, ws, learning_assignment_id)
    return st if st in ("ACTIVE", "PAUSED") else "NONE"


def _source_versions(conn: Connection, org, ws, subtopic_ids) -> list[dict[str, Any]]:
    """Typed curriculum_source_sections links when the path has them; otherwise legacy mappings.

    Never a union of both paths, so the same document version is never listed twice.
    """
    if repo.has_typed_links(conn, org, ws, subtopic_ids):
        return repo.typed_source_versions(conn, org, ws, subtopic_ids)
    return repo.legacy_source_versions(conn, org, ws, subtopic_ids)


def _open_session_id(conn: Connection, org, ws, learning_assignment_id) -> str | None:
    s = learning.open_session(conn, org, ws, learning_assignment_id)
    return str(s["learning_session_id"]) if s else None


def overview(conn: Connection, token: str | None) -> dict[str, Any] | None:
    r, employee_id = _persona(conn, token)
    org, ws = r.session["organization_id"], r.session["workspace_id"]
    a = repo.learner_assignment(conn, org, ws, employee_id)
    if not a:
        return None
    rows = repo.learning_path(conn, org, ws, a["curriculum_id"], a["learning_assignment_id"])
    saved = max((x["progress_at"] for x in rows if x["progress_at"]), default=None)
    # Curriculum completion counts required subtopics only; optional ones can still be studied.
    all_done = bool(rows) and all(x["status"] == "COMPLETED" for x in rows if not x["optional"])
    return {
        "learning_assignment_id": str(a["learning_assignment_id"]),
        "curriculum_name": a["name"],
        "curriculum_version": a["version"],
        "source_versions": [
            {
                "document_version_id": str(v["document_version_id"]),
                "document_id": str(v["document_id"]),
                "document_code": v["document_code"] or "",
                "title": v["title"],
                "version": v["version"],
                "approval_status": v["approval_status"],
                "temporal_status": v["temporal_status"],
                "approved_by": v["approved_by"],
                "effective_label": f"Effective {v['effective_at']:%d %b %Y}" if v["effective_at"] else "Current approved version",
                "document_type": v["document_type"],
            }
            for v in _source_versions(conn, org, ws, [x["subtopic_id"] for x in rows])
        ],
        "topics": _topics(rows),
        "current_subtopic_id": resume_position(rows),
        "session_status": "COMPLETED" if all_done else _session_status(conn, org, ws, a["learning_assignment_id"]),
        # Resume information (blueprint/07 GET /onboarding): the open session, if any.
        "learning_session_id": _open_session_id(conn, org, ws, a["learning_assignment_id"]),
        "saved_at": f"Progress saved {saved:%d %b %Y}" if saved else None,
    }


def team_progress(conn: Connection, token: str | None) -> list[dict[str, Any]]:
    r, employee_id = _persona(conn, token)
    org, ws = r.session["organization_id"], r.session["workspace_id"]
    teams = repo.supervision_teams(conn, org, ws, employee_id)
    if not teams:
        raise ApiError("FORBIDDEN", "Team onboarding progress needs an explicit supervision permission.")
    out = []
    for learner in repo.team_learners(conn, org, ws, teams, employee_id):
        a = repo.learner_assignment(conn, org, ws, learner["employee_id"])
        if not a:
            continue
        rows = repo.learning_path(conn, org, ws, a["curriculum_id"], a["learning_assignment_id"])
        out.append(
            {
                "employee_name": f"{learner['first_name']} {learner['last_name']}",
                "curriculum_name": a["name"],
                "curriculum_version": a["version"],
                # Outcome by subtopic only: no conversations, attempts, criteria or rankings.
                "subtopics": [{"name": x["name"], "status": x["status"]} for x in rows],
            }
        )
    return out


# ---------------------------------------------------------------- tutor shell (sessions)
# POST /onboarding/sessions, GET /onboarding/sessions/{id}, POST .../turns, POST .../pause.
# The backend persists session state deterministically; every tutor reply comes from the
# injected TutorEngine, which is NotConnectedTutor until the AI package is integrated.


def _context(r, s: dict[str, Any]) -> TutorContext:
    return TutorContext(
        organization_id=str(s["organization_id"]),
        workspace_id=str(s["workspace_id"]),
        learning_session_id=str(s["learning_session_id"]),
        thread_id=s["langgraph_thread_id"],
        employee_id=str(s["employee_id"]),
        curriculum_id=str(s["curriculum_id"]),
        current_subtopic_id=str(s["current_subtopic_id"]) if s["current_subtopic_id"] else None,
    )


def permitted_versions(conn: Connection, s: dict[str, Any]) -> list[str]:
    """Current-guidance document versions this session may cite (same paths as the overview's sources)."""
    org, ws = s["organization_id"], s["workspace_id"]
    return [str(v["document_version_id"]) for v in _source_versions(conn, org, ws, turns.curriculum_subtopic_ids(conn, org, ws, s["curriculum_id"]))]


def _citation(conn: Connection, org, ws, turn_id, i: int, c: dict[str, Any]) -> dict[str, Any]:
    ref = c["ref"]
    live = turns.current_version(conn, org, ws, ref["document_version_id"])
    if live and ref.get("chunk_id"):
        chunk = turns.chunk_of_version(conn, org, ws, ref["document_version_id"], ref["chunk_id"])
        excerpt = chunk["content"] if chunk else ""
    elif live and ref.get("section_id"):
        excerpt = turns.section_text(conn, org, ws, ref["section_id"])
    else:
        excerpt = ""
    return {
        "citation_id": f"{turn_id}:{i}",
        # Revocation/supersession after the reply withholds the excerpt immediately (blueprint/17 §6).
        "label": c["label"] if live else f"{c['label']} (no longer current guidance; excerpt withheld)",
        "excerpt": {"source_id": c["source_id"], "document_version_id": ref["document_version_id"], "heading_path": c["heading_path"], "text": excerpt, "evidence_type": c["evidence_type"]},
    }


NOTE = {"PASSED": "Counted as evidence for this objective.", "NOT_PASSED": "Not counted yet: every reviewed criterion must be met without hints.", "UNASSESSABLE": "Couldn't be assessed; no credit either way."}
# Turns saved by the AI engineer's graph (contract "engine-1", ADR-030): its grader's overall outcome decides.
ENGINE_NOTE = {"PASSED": "Counted as evidence for this objective.", "NOT_PASSED": "Not counted yet; the tutor goes over what was missing.", "UNASSESSABLE": "Couldn't be assessed; no credit either way."}


def _engine_citation(conn: Connection, org, ws, ref: dict[str, Any]) -> dict[str, Any]:
    """An engine-1 source reference ({document_version_id, section_id, chunk_id}) in the stored citation
    shape. Resolved when read, so a revoked or superseded source is shown as such."""
    v = turns.current_version(conn, org, ws, ref.get("document_version_id"))
    section = turns.section_of_version(conn, org, ws, ref["document_version_id"], ref["section_id"]) if v and ref.get("section_id") else None
    if not v:
        return {"ref": ref, "label": "A source", "source_id": "", "heading_path": [], "evidence_type": "UNKNOWN"}
    heading = [section["topic_heading"], section["subtopic_heading"]] if section else []
    return {
        "ref": ref,
        "label": f"{v['document_code']} v{v['version']}" + (f" · {section['section_key']}" if section else ""),
        "source_id": str(v["source_id"]),
        "heading_path": [h for h in heading if h],
        "evidence_type": v["evidence_type"],
    }


def transcript(conn: Connection, s: dict[str, Any]) -> list[dict[str, Any]]:
    """Committed turns only: the learner's message, the validated tutor reply and recorded outcomes."""
    org, ws = s["organization_id"], s["workspace_id"]
    out: list[dict[str, Any]] = []
    for t in turns.committed_turns(conn, org, ws, s["learning_session_id"]):
        inp, env, at = t["input_reference"], t["response_envelope"], t["updated_at"].isoformat()
        tid = str(t["turn_id"])
        engine = env.get("contract_version") == "engine-1"
        # The tutor's opening has no learner message (engine-1).
        if inp.get("text"):
            out.append({"message_id": f"{tid}:in", "sender": "EMPLOYEE", "input_kind": inp.get("input_kind", "TEXT"), "kind": "TEACHING", "text": inp["text"], "citations": [], "provenance": "EMPLOYEE_INPUT", "created_at": at})
        reply = env.get("reply", {})
        stored = [_engine_citation(conn, org, ws, c) for c in reply.get("citations", [])] if engine else reply.get("citations", [])
        assessment = None
        if env.get("assessment"):
            a = env["assessment"]
            assessment = {"outcome": a["outcome"], "criteria_version": a["criteria_version"], "note": (ENGINE_NOTE if engine else NOTE)[a["evidence"]]}
        # A completing answer has no reply text (engine-1): its outcome goes on the completion line.
        if reply.get("text"):
            msg: dict[str, Any] = {
                "message_id": f"{tid}:out",
                "sender": "AI",
                "kind": reply.get("kind", "TEACHING"),
                "text": reply["text"],
                "citations": [_citation(conn, org, ws, tid, i, c) for i, c in enumerate(stored)],
                "provenance": "TUTOR_ENGINE",
                "created_at": at,
            }
            if assessment:
                msg["assessment"] = assessment
                assessment = None
            out.append(msg)
        if env.get("completed_subtopic"):
            done: dict[str, Any] = {"message_id": f"{tid}:done", "sender": "SYSTEM", "kind": "COMPLETION", "text": f"{env['completed_subtopic']['name']} is complete.", "citations": [], "provenance": "BACKEND_RECORD", "created_at": at}
            if assessment:
                done["assessment"] = assessment
            out.append(done)
    return out


def _engine_pending_check(conn: Connection, s: dict[str, Any]) -> dict[str, Any] | None:
    """engine-1: the open question is the latest reply when it is a check question."""
    org, ws = s["organization_id"], s["workspace_id"]
    last = next(reversed(turns.committed_turns(conn, org, ws, s["learning_session_id"])), None)
    reply = (last or {}).get("response_envelope", {}).get("reply", {}) if last else {}
    if not last or reply.get("kind") != "CHECK" or last["response_envelope"].get("contract_version") != "engine-1":
        return None
    q = turns.latest_question(conn, org, ws, s["learning_assignment_id"])
    data = (q or {}).get("event_data") or {}
    return {"question_id": str(data.get("question_id") or last["turn_id"]), "objective_id": str((q or {}).get("objective_id") or ""), "text": reply.get("text", "")}


def _view(conn: Connection, token: str | None, s: dict[str, Any], tutor_status: str, tutor_message: str) -> dict[str, Any]:
    org, ws, sub = s["organization_id"], s["workspace_id"], s["current_subtopic_id"]
    objs = turns.subtopic_objectives(conn, org, ws, sub) if sub else []
    engine_check = _engine_pending_check(conn, s) if engine_turns.active() else None
    q = None if engine_turns.active() else tutor_turns.pending_question(conn, org, ws, s["learning_assignment_id"], objs)
    current = next((x for x in repo.learning_path(conn, org, ws, s["curriculum_id"], s["learning_assignment_id"]) if str(x["subtopic_id"]) == str(sub)), None) if sub else None
    return {
        "learning_session_id": str(s["learning_session_id"]),
        "revision": s["revision"],
        "overview": overview(conn, token),
        # Committed turns only; nothing is invented while the tutor isn't connected.
        "transcript": transcript(conn, s),
        "pending_check": engine_check or ({"question_id": q.question_id, "objective_id": q.objective_id, "text": q.text} if q else None),
        # The current item is complete: the next one starts only on explicit continuation.
        "awaiting_continue": bool(current and current["status"] == "COMPLETED"),
        "script_prompts": [],
        "status": s["status"],
        "tutor": {"status": tutor_status, "message": tutor_message},
        # Public-demo daily caps for this run (app/services/usage.py).
        "demo_limits": usage.status(conn, ws, resolve(conn, token).session if token else None),
    }


def start_session(conn: Connection, token: str | None, request_id: _uuid.UUID) -> dict[str, Any]:
    r, employee_id = _persona(conn, token)
    org, ws = r.session["organization_id"], r.session["workspace_id"]
    a = repo.learner_assignment(conn, org, ws, employee_id)
    if not a:
        raise ApiError("NOT_FOUND", "No onboarding is assigned to you.")
    learning.lock_assignment(conn, org, ws, a["learning_assignment_id"])
    rows = repo.learning_path(conn, org, ws, a["curriculum_id"], a["learning_assignment_id"])
    position = resume_position(rows)
    if rows and position is None and all(x["status"] == "COMPLETED" for x in rows):
        raise ApiError("GUARD_FAILED", "This curriculum is already complete.")
    topic = learning.topic_of(conn, org, ws, position)
    tutor = get_tutor()
    s = learning.open_session(conn, org, ws, a["learning_assignment_id"])
    if s is None:
        s = learning.create_session(conn, org, ws, employee_id, a, topic, position, tutor.graph_version)
        commands.audit(conn, org, ws, employee_id, "learning_session.started", "learning_session", s["learning_session_id"], s["revision"], request_id)
    elif s["status"] == "PAUSED":
        # Resume restores the deterministic position (blueprint/17: unfinished work or next eligible item).
        s = learning.set_status(conn, s, "ACTIVE", topic, position)
        commands.audit(conn, org, ws, employee_id, "learning_session.resumed", "learning_session", s["learning_session_id"], s["revision"], request_id)
    result = tutor.open_session(_context(r, s))
    return _view(conn, token, s, result.status, result.message)


def _tutor_state() -> tuple[str, str]:
    t = get_tutor()
    return ("unavailable", NOT_CONNECTED) if t.provider == "none" else ("ok", "")


def _committed_view(conn: Connection, token: str | None, s: dict[str, Any]) -> dict[str, Any]:
    return _view(conn, token, s, *_tutor_state())


def get_session(conn: Connection, token: str | None, session_id: str) -> dict[str, Any]:
    """Committed session state for its owner only; never checkpoint data."""
    _, _, s = _owned_session(conn, token, session_id, None)
    return _committed_view(conn, token, s)


def _owned_session(conn: Connection, token: str | None, session_id: str, expected_revision: int | None):
    r, employee_id = _persona(conn, token)
    try:
        sid = _uuid.UUID(session_id)
    except ValueError as e:
        raise ApiError("MALFORMED_INPUT", "Unknown session ID.") from e
    s = learning.session_for_employee(conn, r.session["organization_id"], r.session["workspace_id"], sid, employee_id)
    if not s:
        raise ApiError("NOT_FOUND", "This learning session isn't yours or no longer exists.")
    if expected_revision is not None and expected_revision != s["revision"]:
        raise ApiError("REVISION_CONFLICT", "This conversation changed in another tab. Reload to continue from the saved state.")
    return r, employee_id, s


def send_turn(token: str | None, session_id: str, client_turn_id: str, expected_revision: int, text_: str, input_kind: str, request_id: _uuid.UUID, interrupted: bool = False) -> dict[str, Any]:
    """Manages its own transactions (see tutor_turns / engine_turns): none is open during the engine call."""
    if engine_turns.active():
        return engine_turns.send_turn(token, session_id, client_turn_id, expected_revision, text_, input_kind, request_id, interrupted)
    return tutor_turns.send_turn(
        lambda conn, tok, sid: _owned_session(conn, tok, sid, None), _committed_view, token, session_id, client_turn_id, expected_revision, text_, input_kind, request_id, interrupted
    )


def pause(conn: Connection, token: str | None, session_id: str, client_turn_id: str, expected_revision: int, request_id: _uuid.UUID) -> dict[str, Any]:
    payload = {"session_id": session_id, "expected_revision": expected_revision}
    r, employee_id = _persona(conn, token)
    org, ws = r.session["organization_id"], r.session["workspace_id"]
    prior = commands.find_receipt(conn, org, ws, employee_id, "onboarding.pause", client_turn_id)
    if prior:
        if prior["payload_hash"] != commands.payload_hash(payload):
            raise ApiError("MALFORMED_INPUT", "This request ID was already used for a different request.")
        r2, _, s = _owned_session(conn, token, session_id, None)
        return _view(conn, token, s, "unavailable", get_tutor().pause(_context(r2, s)).message)
    _, _, s = _owned_session(conn, token, session_id, expected_revision)
    if s["status"] != "ACTIVE":
        raise ApiError("GUARD_FAILED", "Only an active conversation can be paused.")
    # A break never completes unfinished content: progress rows are untouched.
    s = learning.set_status(conn, s, "PAUSED")
    commands.audit(conn, org, ws, employee_id, "learning_session.paused", "learning_session", s["learning_session_id"], s["revision"], request_id)
    commands.record_receipt(conn, org, ws, employee_id, "onboarding.pause", client_turn_id, commands.payload_hash(payload), {"learning_session_id": str(s["learning_session_id"]), "status": s["status"]}, s["revision"])
    result = get_tutor().pause(_context(r, s))
    return _view(conn, token, s, result.status, result.message)
