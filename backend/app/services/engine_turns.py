"""Onboarding conversation through the AI engineer's LangGraph graph (ADR-030).

Her graph is the system of record for learning data: each reply it produces is saved by the graph
itself as a learning turn (contract "engine-1"), together with its events, evidence and progress.
This service authorizes, applies the demo caps, drives the graph and reads the result back. It
writes no learning rows; it only records content-free audit entries and the session's PAUSED status.

No database transaction is open while the graph runs (the graph writes in its own transactions).
A message is identified by the client's turn ID, which the graph stores on the turn, so a retried
message that was already answered returns the saved answer instead of running the graph again.
"""

import logging
import uuid as _uuid
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from app.db import transaction
from app.errors import ApiError
from app.integrations.langgraph_engine import EngineError, LangGraphEngine, ThreadState
from app.integrations.tutor import get_tutor
from app.repositories import commands, learning, turns
from app.services import usage

log = logging.getLogger(__name__)

NOT_STARTED = "The tutor couldn't start this conversation. Reload the page to try again."
NO_REPLY = "The tutor couldn't reply. Nothing was saved; your message is still in the box, so you can try again."


def active() -> LangGraphEngine | None:
    engine = get_tutor()
    return engine if isinstance(engine, LangGraphEngine) else None


def _thread(s: dict[str, Any]) -> str:
    return str(s["learning_session_id"])


def _employee(s: dict[str, Any]) -> dict[str, str]:
    return {
        "employee_id": str(s["employee_id"]),
        "organization_id": str(s["organization_id"]),
        "workspace_id": str(s["workspace_id"]),
        "session_id": str(s["learning_session_id"]),
    }


def _completed(st: ThreadState) -> bool:
    return (st.values.get("learning") or {}).get("current_status") == "COMPLETED"


def _paused_by_learner(values: dict[str, Any]) -> bool:
    return ((values.get("response_analysis") or {}).get("recommended_action")) == "PAUSE"


def ensure_opening(token: str | None, session_id: str) -> dict[str, Any]:
    """After Start/Resume: the conversation has the tutor's opening, or is waiting for the learner.

    Never raises for the engine: if it can't start (unreachable, an error, a demo cap), the view
    says so and the learner can reload; their session and progress are already saved."""
    from app.services.onboarding import _committed_view, _owned_session, _view

    engine = active()
    assert engine is not None
    with transaction() as conn:
        r, _, s = _owned_session(conn, token, session_id, None)
        if s["status"] != "ACTIVE":
            return _committed_view(conn, token, s)
    try:
        st = engine.state(_thread(s))
        if st.waiting:
            with transaction() as conn:
                return _committed_view(conn, token, _owned_session(conn, token, session_id, None)[2])
        if st.exists and _completed(st):
            with transaction() as conn:
                view = _committed_view(conn, token, _owned_session(conn, token, session_id, None)[2])
            # Still on the completed item (e.g. a reload): the learner chooses Continue.
            if view["awaiting_continue"]:
                return view
            # Resumed after a break: the saved position already moved to the next item, so the tutor
            # opens it now, exactly as Continue would (otherwise there'd be no Continue and no reply).
        # Never opened, stopped by an error, or resumed past a completed item: start from the current
        # item (the graph re-reads progress).
        with transaction() as conn:
            usage.charge(conn, "TUTOR_TURN", s["workspace_id"], r.session)
        engine.start(_thread(s), _employee(s))
    except ApiError as e:
        if e.code != "LIMIT_REACHED":
            raise
    except EngineError:
        log.exception("tutor engine couldn't open session %s", session_id)
        with transaction() as conn:
            return _view(conn, token, _owned_session(conn, token, session_id, None)[2], "unavailable", NOT_STARTED)
    with transaction() as conn:
        return _committed_view(conn, token, _owned_session(conn, token, session_id, None)[2])


@dataclass
class _Prepared:
    """A message that passed the checks and was charged; the graph is ready for it."""

    cid: _uuid.UUID
    session: dict[str, Any]
    employee_id: Any
    pending_answer: bool  # the learner is answering an open check question


def _prepare(token: str | None, session_id: str, client_turn_id: str, expected_revision: int) -> _Prepared | dict[str, Any]:
    """Checks, demo cap and readiness before the graph runs. Returns the saved view instead when this
    message was already answered (a retry), so the graph never runs twice for one message."""
    from app.services.onboarding import _committed_view, _owned_session

    engine = active()
    assert engine is not None
    try:
        cid = _uuid.UUID(client_turn_id)
    except ValueError:
        raise ApiError("MALFORMED_INPUT", "client_turn_id must be a UUID.") from None

    with transaction() as conn:
        r, employee_id, s = _owned_session(conn, token, session_id, None)
        prior = turns.find_turn(conn, s["organization_id"], s["workspace_id"], s["learning_session_id"], cid)
        if prior and prior["stage"] == "COMMITTED":
            return _committed_view(conn, token, s)  # already answered: the saved reply, not a second run
        if s["status"] != "ACTIVE":
            raise ApiError("GUARD_FAILED", "Resume the conversation before sending a message.")
        if expected_revision != s["revision"]:
            raise ApiError("REVISION_CONFLICT", "This conversation changed in another tab. Reload to continue from the saved state.")
        usage.charge(conn, "TUTOR_TURN", s["workspace_id"], r.session)

    try:
        st = engine.state(_thread(s))
    except EngineError:
        log.exception("tutor engine unreachable on session %s", session_id)
        raise ApiError("DEPENDENCY_UNAVAILABLE", NO_REPLY, retryable=True) from None
    if not st.waiting:
        if st.exists and _completed(st):
            raise ApiError("GUARD_FAILED", "This item is complete. Choose Continue to start the next one.")
        raise ApiError("DEPENDENCY_UNAVAILABLE", "The tutor isn't ready for a message. Reload the page to restart the conversation.", retryable=True)
    pending = bool((st.values.get("learning") or {}).get("pending_question"))
    return _Prepared(cid, s, employee_id, pending)


def _finish(token: str | None, session_id: str, p: _Prepared, request_id: _uuid.UUID) -> dict[str, Any]:
    """After the run: the reply the graph saved, or the break the learner asked for."""
    from app.services.onboarding import _committed_view, _owned_session

    engine = active()
    assert engine is not None
    with transaction() as conn:
        _, _, s = _owned_session(conn, token, session_id, None)
        org, ws = s["organization_id"], s["workspace_id"]
        saved = turns.find_turn(conn, org, ws, s["learning_session_id"], p.cid)
        if saved and saved["stage"] == "COMMITTED":
            commands.audit(conn, org, ws, p.employee_id, "learning_turn.recorded", "learning_turn", saved["turn_id"], s["revision"], request_id)
            return _committed_view(conn, token, s)
    try:
        values = engine.state(_thread(s)).values
    except EngineError:
        values = {}
    with transaction() as conn:
        _, _, s = _owned_session(conn, token, session_id, None)
        if _paused_by_learner(values) and s["status"] == "ACTIVE":
            # The learner asked to stop: the same saved break as the "Take a break" button.
            s = learning.set_status(conn, s, "PAUSED")
            commands.audit(conn, s["organization_id"], s["workspace_id"], p.employee_id, "learning_session.paused", "learning_session", s["learning_session_id"], s["revision"], request_id)
            return _committed_view(conn, token, s)
    log.error("tutor engine finished session %s turn %s without saving a reply", session_id, p.cid)
    raise ApiError("DEPENDENCY_UNAVAILABLE", NO_REPLY, retryable=True)


def send_turn(token: str | None, session_id: str, client_turn_id: str, expected_revision: int, text_: str, input_kind: str, request_id: _uuid.UUID, interrupted: bool = False) -> dict[str, Any]:
    p = _prepare(token, session_id, client_turn_id, expected_revision)
    if not isinstance(p, _Prepared):
        return p
    engine = active()
    assert engine is not None
    try:
        engine.resume(_thread(p.session), text_, input_kind, str(p.cid), interrupted)
    except EngineError:
        log.exception("tutor engine failed on session %s", session_id)
        raise ApiError("DEPENDENCY_UNAVAILABLE", NO_REPLY, retryable=True) from None
    return _finish(token, session_id, p, request_id)


# ---------------------------------------------------------------- progress while the tutor works (ADR-030)
# Fixed, plain-language labels for the step that comes NEXT (an update arrives when a step finishes).
# They describe the work, never model output. Unknown steps are ignored, so graph changes are safe.
FIRST_STEP = {True: "Checking your answer…", False: "Understanding your message…"}
AFTER_ANALYSIS = {
    "TEACH": "Finding the right part of the procedure…",
    "ASSESS": "Preparing a question to check your understanding…",
    "CLARIFY": "Working out what you mean…",
    "PROGRESS": "Recording your progress…",
    "PAUSE": "Saving your place…",
}
AFTER_GRADING = {
    "CORRECT": "Recording your progress…",
    "PARTIAL": "Preparing feedback on your answer…",
    "INCORRECT": "Finding the right part of the procedure…",
    "UNASSESSABLE": "Finding the right part of the procedure…",
}
AFTER_STEP = {"retrieve_knowledge": "Writing a reply…"}


def progress_label(step: str, update: dict[str, Any]) -> str | None:
    if step == "analyze_user_response":
        return AFTER_ANALYSIS.get(((update.get("response_analysis") or {}).get("recommended_action")) or "")
    if step == "evaluate_assessment":
        return AFTER_GRADING.get(((update.get("assessment") or {}).get("outcome")) or "")
    return AFTER_STEP.get(step)


def send_turn_stream(token: str | None, session_id: str, client_turn_id: str, expected_revision: int, text_: str, input_kind: str, request_id: _uuid.UUID, interrupted: bool = False) -> Iterator[tuple[str, dict[str, Any]]]:
    """send_turn with progress: the checks run now (errors raise before anything streams); the
    returned iterator yields ("progress", {"label"}) while the graph works, then ("done", view) or
    ("error", ApiError fields)."""
    p = _prepare(token, session_id, client_turn_id, expected_revision)
    if not isinstance(p, _Prepared):
        view = p
        return iter([("done", view)])
    engine = active()
    assert engine is not None

    def events() -> Iterator[tuple[str, dict[str, Any]]]:
        yield "progress", {"label": FIRST_STEP[p.pending_answer]}
        try:
            last = None
            for step, update in engine.resume_stream(_thread(p.session), text_, input_kind, str(p.cid), interrupted):
                label = progress_label(step, update)
                if label and label != last:
                    last = label
                    yield "progress", {"label": label}
            yield "done", _finish(token, session_id, p, request_id)
        except EngineError:
            log.exception("tutor engine failed on session %s", session_id)
            yield "error", {"code": "DEPENDENCY_UNAVAILABLE", "message": NO_REPLY, "retryable": True}
        except ApiError as e:
            yield "error", {"code": e.code, "message": e.message, "retryable": e.retryable, **e.details}

    return events()


def continue_session(token: str | None, session_id: str, expected_revision: int, request_id: _uuid.UUID) -> dict[str, Any]:
    """After a completed item: the graph opens the next eligible item (it re-reads progress)."""
    from app.services.onboarding import _committed_view, _owned_session

    engine = active()
    assert engine is not None
    with transaction() as conn:
        r, employee_id, s = _owned_session(conn, token, session_id, None)
        if s["status"] != "ACTIVE":
            raise ApiError("GUARD_FAILED", "Resume the conversation first.")
        if expected_revision != s["revision"]:
            raise ApiError("REVISION_CONFLICT", "This conversation changed in another tab. Reload to continue from the saved state.")
        usage.charge(conn, "TUTOR_TURN", s["workspace_id"], r.session)
    try:
        st = engine.state(_thread(s))
        if st.waiting:
            raise ApiError("GUARD_FAILED", "The tutor is waiting for your answer to the current item.")
        engine.start(_thread(s), _employee(s))
    except EngineError:
        log.exception("tutor engine couldn't continue session %s", session_id)
        raise ApiError("DEPENDENCY_UNAVAILABLE", "The tutor couldn't start the next item. Try again in a moment.", retryable=True) from None
    with transaction() as conn:
        _, _, s = _owned_session(conn, token, session_id, None)
        commands.audit(conn, s["organization_id"], s["workspace_id"], employee_id, "learning_session.continued", "learning_session", s["learning_session_id"], s["revision"], request_id)
        return _committed_view(conn, token, s)
