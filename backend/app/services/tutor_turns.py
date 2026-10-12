"""Onboarding tutor turns: POST /onboarding/sessions/{id}/turns (blueprint/07, blueprint/17 §2-§6).

Three phases, so no database transaction is open while the engine runs:

1. Claim (short transaction): authorize the owner, check the client_turn_id receipt (a committed
   duplicate replays the committed state; same ID with a different message is rejected), check
   ACTIVE status and expected_revision, build the server-established context and claim the turn
   (stage RECEIVED, no learner text stored).
2. Engine call (no transaction): the injected TutorEngine. Failures and non-ok statuses mark the
   claim FAILED and return an error; the client keeps the learner's text for an explicit retry.
3. Commit (one transaction): re-lock the session and re-check its revision, validate the engine
   output (schema, citations, question, assessment) against fresh state, then write the turn,
   events, attempt, evidence and progress together, or nothing.

Completion is deterministic (POLICY_VERSION): a subtopic completes only when every required
objective (or, for an optional subtopic with no required objective, every objective) has PASSED
evidence for its current criteria version. Evidence is PASSED only for a
CORRECT attempt on the pending question whose criterion results cover exactly the objective's
reviewed required checks, all met, without hints (unless the objective's hint policy allows them).
Self-reports ("I understand"), model metadata/confidence and proposed outcomes alone never pass.
"""

import json
import logging
import uuid as _uuid
from typing import Any

from pydantic import ValidationError
from sqlalchemy import Connection
from sqlalchemy.exc import IntegrityError

from app.db import transaction
from app.errors import ApiError
from app.integrations.tutor import NOT_CONNECTED, ObjectiveContext, PendingQuestion, TutorContext, TutorResult, TurnOutput, get_tutor
from app.repositories import commands, turns
from app.services import usage

log = logging.getLogger(__name__)

POLICY_VERSION = "mvp-objective-evidence-1"
CLAIM_LEASE_SECONDS = 120  # an abandoned RECEIVED claim older than this may be retried
CITATION_REQUIRED = {"TEACHING", "EXAMPLE"}  # factual teaching must cite permitted sources


class InvalidOutput(Exception):
    """The engine output failed backend validation; nothing from it is stored."""


# ---------------------------------------------------------------- context
def _required_checks(criteria: Any) -> list[str]:
    checks = criteria.get("required_checks") if isinstance(criteria, dict) else None
    return [c for c in checks if isinstance(c, str)] if isinstance(checks, list) else []


def pending_question(conn: Connection, org, ws, learning_assignment_id, objectives: list[dict[str, Any]]) -> PendingQuestion | None:
    """The latest question of the assignment, if still open and still valid for the current objectives."""
    q = turns.latest_question(conn, org, ws, learning_assignment_id)
    if not q:
        return None
    d = q["event_data"]
    current = {str(o["objective_id"]): o for o in objectives}
    o = current.get(str(q["objective_id"]))
    # Revalidate before reuse (blueprint/17 §3.4): objective still current, criteria unchanged, not yet passed.
    if not o or o["criteria_version"] != d.get("criteria_version") or turns.question_passed(conn, org, ws, d["question_id"]):
        return None
    return PendingQuestion(d["question_id"], d["question_version"], str(q["objective_id"]), d["criteria_version"], d["text"], d["issued_turn_id"])


def build_context(conn: Connection, s: dict[str, Any], permitted: list[str], recent: list[dict[str, str]], interrupted: bool = False) -> TutorContext:
    org, ws = s["organization_id"], s["workspace_id"]
    objs = turns.subtopic_objectives(conn, org, ws, s["current_subtopic_id"]) if s["current_subtopic_id"] else []
    return TutorContext(
        organization_id=str(org),
        workspace_id=str(ws),
        learning_session_id=str(s["learning_session_id"]),
        thread_id=s["langgraph_thread_id"],
        employee_id=str(s["employee_id"]),
        curriculum_id=str(s["curriculum_id"]),
        current_subtopic_id=str(s["current_subtopic_id"]) if s["current_subtopic_id"] else None,
        permitted_document_version_ids=permitted,
        objectives=[ObjectiveContext(str(o["objective_id"]), o["description"], o["criteria_version"], o["required"], _required_checks(o["assessment_criteria"])) for o in objs],
        pending_question=pending_question(conn, org, ws, s["learning_assignment_id"], objs),
        recent_messages=recent[-12:],
        previous_reply_interrupted=interrupted,
    )


# ---------------------------------------------------------------- validation
def resolve_citation(conn: Connection, org, ws, permitted: set[str], ref) -> dict[str, Any]:
    """A citation DTO for the transcript, or InvalidOutput. Current guidance only."""
    vid = str(ref.document_version_id)
    if vid not in permitted:
        raise InvalidOutput(f"citation to a document version outside this session's permitted sources ({vid})")
    v = turns.current_version(conn, org, ws, ref.document_version_id)
    if not v:
        raise InvalidOutput(f"citation to a version that isn't approved, current and unrevoked ({vid})")
    section = chunk = None
    if ref.chunk_id:
        chunk = turns.chunk_of_version(conn, org, ws, ref.document_version_id, ref.chunk_id)
        if not chunk:
            raise InvalidOutput(f"cited chunk {ref.chunk_id} isn't part of {vid}")
    if ref.section_id:
        section = turns.section_of_version(conn, org, ws, ref.document_version_id, ref.section_id)
        if not section:
            raise InvalidOutput(f"cited section {ref.section_id} isn't part of {vid}")
        if chunk and chunk["source_section_id"] != ref.section_id:
            raise InvalidOutput(f"cited chunk {ref.chunk_id} isn't in section {ref.section_id}")
    if chunk and not section and chunk["source_section_id"]:
        section = turns.section_of_version(conn, org, ws, ref.document_version_id, chunk["source_section_id"])
    heading = [section["topic_heading"], section["subtopic_heading"]] if section else ([chunk["heading"]] if chunk and chunk["heading"] else [])
    return {
        "ref": {"document_version_id": vid, "section_id": str(ref.section_id) if ref.section_id else None, "chunk_id": str(ref.chunk_id) if ref.chunk_id else None},
        "label": f"{v['document_code']} v{v['version']}" + (f" · {section['section_key']}" if section else ""),
        "source_id": str(v["source_id"]),
        "heading_path": heading,
        "evidence_type": v["evidence_type"],
    }


def evidence_outcome(outcome: str, required_checks: list[str], results: dict[str, bool], hints_used: int, hint_policy: Any) -> str:
    if outcome == "UNASSESSABLE":
        return "UNASSESSABLE"
    hints_ok = hints_used == 0 or (isinstance(hint_policy, dict) and hint_policy.get("hinted_attempts_count") is True)
    if outcome == "CORRECT" and required_checks and all(results.get(c) for c in required_checks) and hints_ok:
        return "PASSED"
    return "NOT_PASSED"


def validate(conn: Connection, s: dict[str, Any], ctx: TutorContext, raw: dict[str, Any] | None, insufficient: bool) -> tuple[TurnOutput, list[dict[str, Any]], dict[str, Any] | None]:
    """Schema + every reference against fresh server state. Returns (output, citations, objective for the assessment)."""
    org, ws = s["organization_id"], s["workspace_id"]
    try:
        out = TurnOutput.model_validate(raw)
    except ValidationError as e:
        raise InvalidOutput(f"schema: {e.errors()[0]['loc']} {e.errors()[0]['msg']}") from None
    permitted = set(ctx.permitted_document_version_ids)
    if out.reply.kind in CITATION_REQUIRED and not out.reply.citations and not insufficient:
        raise InvalidOutput("teaching reply without a permitted citation")
    citations = [resolve_citation(conn, org, ws, permitted, ref) for ref in out.reply.citations]
    objectives = {o.objective_id: o for o in ctx.objectives}
    if insufficient and (out.assessment or out.new_check):
        raise InvalidOutput("an insufficient-evidence reply can't assess or ask a check")

    assessed = None
    if out.assessment:
        a, q = out.assessment, ctx.pending_question
        if not q or str(a.question_id) != q.question_id:
            raise InvalidOutput("assessment of a question that isn't the pending one")
        if str(a.objective_id) != q.objective_id or a.criteria_version != q.criteria_version:
            raise InvalidOutput("assessment objective or criteria version doesn't match the pending question")
        o = objectives.get(str(a.objective_id))
        if not o or o.criteria_version != a.criteria_version:
            raise InvalidOutput("assessed objective isn't a current objective of this subtopic")
        checks = [r.check for r in a.criterion_results]
        if len(checks) != len(set(checks)):
            raise InvalidOutput("duplicate criterion results")
        if a.outcome == "UNASSESSABLE":
            if checks:
                raise InvalidOutput("an unassessable result can't carry criterion results")
        else:
            if set(checks) != set(o.required_checks):
                raise InvalidOutput("criterion results must cover exactly the objective's reviewed checks")
            met = [r.met for r in a.criterion_results]
            if a.outcome == "CORRECT" and not all(met):
                raise InvalidOutput("CORRECT with an unmet required criterion")
            if a.outcome in ("PARTIAL", "INCORRECT") and met and all(met):
                raise InvalidOutput(f"{a.outcome} with every criterion met")
        assessed = {"objective": o}

    if out.new_check:
        c = out.new_check
        o = objectives.get(str(c.objective_id))
        if not o or o.criteria_version != c.criteria_version:
            raise InvalidOutput("new check for an objective/criteria version that isn't current for this subtopic")
        if turns.question_used(conn, org, ws, str(c.question_id)):
            raise InvalidOutput("question_id already used")
    return out, citations, assessed


# ---------------------------------------------------------------- phases
def _fail(org, ws, turn_id, reason: str) -> None:
    with transaction() as conn:
        turns.fail_turn(conn, org, ws, turn_id, reason)


def send_turn(owned, view, token: str | None, session_id: str, client_turn_id: str, expected_revision: int, text_: str, input_kind: str, request_id: _uuid.UUID, interrupted: bool = False) -> dict[str, Any]:
    """`owned(conn, token, session_id)` authorizes the owner; `view(conn, token, session)` builds the committed view."""
    try:
        cid = _uuid.UUID(client_turn_id)
    except ValueError:
        raise ApiError("MALFORMED_INPUT", "client_turn_id must be a UUID.") from None
    payload: dict[str, Any] = {"text": text_, "input_kind": input_kind}
    if interrupted:
        payload["interrupted_previous_reply"] = True
    input_hash = commands.payload_hash(payload)
    engine = get_tutor()

    # Phase 1: claim.
    with transaction() as conn:
        r, employee_id, s = owned(conn, token, session_id)
        org, ws = s["organization_id"], s["workspace_id"]
        s = turns.lock_session(conn, org, ws, s["learning_session_id"])
        prior = turns.find_turn(conn, org, ws, s["learning_session_id"], cid)
        if prior and prior["input_hash"] != input_hash:
            raise ApiError("MALFORMED_INPUT", "This turn ID was already used for a different message.")
        if prior and prior["stage"] == "COMMITTED":
            return view(conn, token, s)  # duplicate delivery: the committed state, not a second engine run
        if prior and prior["stage"] == "RECEIVED" and prior["age"].total_seconds() < CLAIM_LEASE_SECONDS:
            raise ApiError("GUARD_FAILED", "This message is still being processed. Try again in a moment.", retryable=True)
        if expected_revision != s["revision"]:
            raise ApiError("REVISION_CONFLICT", "This conversation changed in another tab. Reload to continue from the saved state.")
        if s["status"] != "ACTIVE":
            raise ApiError("GUARD_FAILED", "Resume the conversation before sending a message.")
        if engine.provider == "none":
            # Not connected: nothing is claimed or stored; the client keeps the text.
            raise ApiError("CAPABILITY_UNAVAILABLE", NOT_CONNECTED + " Your message wasn't sent; it's still in the box.")
        usage.charge(conn, "TUTOR_TURN", ws, r.session)  # before the claim; a refusal rolls back and stores nothing
        from app.services.onboarding import permitted_versions, transcript

        permitted = permitted_versions(conn, s)
        ctx = build_context(conn, s, permitted, [{"sender": m["sender"], "text": m["text"]} for m in transcript(conn, s)], interrupted)
        turn = turns.reclaim_turn(conn, org, ws, prior, s["revision"]) if prior else turns.claim_turn(conn, org, ws, s["learning_session_id"], cid, input_hash, s["revision"])

    # Phase 2: engine call, outside any transaction.
    try:
        result = engine.process_turn(ctx, text_, input_kind)
    except Exception:
        log.exception("tutor engine failed")
        result = TutorResult("unavailable", message="The tutor failed to respond.")
    if result.status not in ("ok", "insufficient_evidence"):
        _fail(org, ws, turn["turn_id"], result.status)
        if result.status == "unsupported_capability":
            raise ApiError("CAPABILITY_UNAVAILABLE", "The tutor can't handle that kind of message yet. Your message wasn't saved.")
        raise ApiError("DEPENDENCY_UNAVAILABLE", "The tutor couldn't reply. Nothing was saved; your message is still in the box, so you can try again.", retryable=True)

    # Phase 3: validate and commit atomically.
    try:
        with transaction() as conn:
            s = turns.lock_session(conn, org, ws, s["learning_session_id"])
            if s["status"] != "ACTIVE" or s["revision"] != expected_revision:
                raise ApiError("REVISION_CONFLICT", "This conversation changed while the tutor was replying. Reload to continue from the saved state.")
            ctx = build_context(conn, s, permitted_versions(conn, s), ctx.recent_messages, interrupted)  # fresh: revocations/answers since phase 1
            out, citations, assessed = validate(conn, s, ctx, result.output, result.status == "insufficient_evidence")
            return _commit(conn, view, token, s, turn, employee_id, ctx, out, citations, assessed, payload, result, request_id)
    except InvalidOutput as e:
        log.warning("tutor output rejected: %s", e)
        _fail(org, ws, turn["turn_id"], "invalid_output")
        raise ApiError("DEPENDENCY_UNAVAILABLE", "The tutor's reply didn't pass validation, so nothing was saved. Try sending your message again.", retryable=True) from None
    except ApiError:
        _fail(org, ws, turn["turn_id"], "conflict")
        raise
    except IntegrityError:
        _fail(org, ws, turn["turn_id"], "conflict")
        raise ApiError("REVISION_CONFLICT", "This conversation changed while the tutor was replying. Reload to continue.") from None


def _commit(conn: Connection, view, token, s, turn, employee_id, ctx: TutorContext, out: TurnOutput, citations, assessed, learner_input: dict[str, Any], result: TutorResult, request_id) -> dict[str, Any]:
    org, ws, sid = s["organization_id"], s["workspace_id"], s["learning_session_id"]
    la, sub = s["learning_assignment_id"], s["current_subtopic_id"]
    tid = turn["turn_id"]
    key = f"turn:{tid}"
    info = turns.subtopic_info(conn, org, ws, sub) if sub else None
    topic = info["topic_id"] if info else None
    refs = [c["ref"] for c in citations]
    envelope: dict[str, Any] = {
        "contract_version": out.contract_version,
        "provider": result.provider,
        "status": result.status,
        "reply": {"kind": out.reply.kind, "text": out.reply.text, "strategy": out.reply.strategy, "citations": citations},
        "metadata": out.metadata,
    }

    # First committed work on the current item starts it (NOT_STARTED -> IN_PROGRESS), once.
    progress = turns.lock_progress(conn, org, ws, la, sub) if sub else None
    if progress and progress["status"] == "NOT_STARTED":
        turns.set_progress(conn, org, ws, progress["progress_id"], "IN_PROGRESS")
        turns.add_event(conn, org, ws, sid, employee_id, "SUBTOPIC_STARTED", f"subtopic-started:{la}:{sub}", topic_id=topic, subtopic_id=sub)
        progress = turns.lock_progress(conn, org, ws, la, sub)
    if out.event:
        turns.add_event(conn, org, ws, sid, employee_id, out.event, f"{key}:event", topic_id=topic, subtopic_id=sub, strategy=out.reply.strategy, source_refs=refs)

    if out.assessment and assessed:
        a, o = out.assessment, assessed["objective"]
        results = {r.check: r.met for r in a.criterion_results}
        ev = evidence_outcome(a.outcome, o.required_checks, results, a.hints_used, _hint_policy(conn, org, ws, sub, o.objective_id))
        attempt_id = turns.add_attempt(
            conn, org, ws, tid, a.question_id, a.objective_id, a.criteria_version,
            {"turn_id": str(tid)},  # the answer text lives in the turn row, not duplicated here
            {"results": [r.model_dump(mode="json") for r in a.criterion_results]},
            a.outcome,
            {"hints_used": a.hints_used, "provider": result.provider, **{k: v for k, v in out.metadata.items() if k in ("model_id", "prompt_version")}},
        )
        turns.add_evidence(conn, org, ws, la, a.objective_id, a.criteria_version, attempt_id, ev, POLICY_VERSION)
        turns.add_event(conn, org, ws, sid, employee_id, "ASSESSMENT_RESULT", f"{key}:assessment", topic_id=topic, subtopic_id=sub, objective_id=a.objective_id,
                        data={"attempt_id": str(attempt_id), "outcome": a.outcome, "evidence": ev, "policy_version": POLICY_VERSION})
        envelope["assessment"] = {"outcome": a.outcome, "criteria_version": a.criteria_version, "evidence": ev}

        # Deterministic completion: every required objective has PASSED evidence for its current criteria.
        # An optional subtopic (no required objective) completes when its objectives have passed.
        objs = turns.subtopic_objectives(conn, org, ws, sub)
        required = [x for x in objs if x["required"]] or objs
        if ev == "PASSED" and progress and progress["status"] != "COMPLETED" and required and {x["objective_id"] for x in required} <= turns.passed_objective_ids(conn, org, ws, la, required):
            turns.set_progress(conn, org, ws, progress["progress_id"], "COMPLETED")
            turns.add_event(conn, org, ws, sid, employee_id, "SUBTOPIC_COMPLETED", f"subtopic-completed:{la}:{sub}", topic_id=topic, subtopic_id=sub, data={"policy_version": POLICY_VERSION})
            if topic and turns.topic_complete(conn, org, ws, la, topic):
                turns.add_event(conn, org, ws, sid, employee_id, "TOPIC_COMPLETED", f"topic-completed:{la}:{topic}", topic_id=topic)
            envelope["completed_subtopic"] = {"subtopic_id": str(sub), "name": info["name"] if info else ""}

    if out.new_check:
        c = out.new_check
        turns.add_event(conn, org, ws, sid, employee_id, "COMPREHENSION_QUESTION", f"{key}:question", topic_id=topic, subtopic_id=sub, objective_id=c.objective_id,
                        data={"question_id": str(c.question_id), "question_version": c.question_version, "criteria_version": c.criteria_version, "text": c.text, "issued_turn_id": str(tid)},
                        source_refs=refs)
        envelope["new_check"] = {"question_id": str(c.question_id), "objective_id": str(c.objective_id)}

    s2 = turns.advance_session(conn, org, ws, sid, s["revision"])
    if not s2:
        raise ApiError("REVISION_CONFLICT", "This conversation changed while the tutor was replying. Reload to continue.")
    if not turns.commit_turn(conn, org, ws, tid, learner_input, envelope, s2["revision"]):
        raise ApiError("REVISION_CONFLICT", "This message was already handled. Reload to see the saved conversation.")
    commands.audit(conn, org, ws, employee_id, "learning_turn.committed", "learning_turn", tid, s2["revision"], request_id)
    return view(conn, token, s2)


def _hint_policy(conn: Connection, org, ws, subtopic_id, objective_id: str) -> Any:
    for o in turns.subtopic_objectives(conn, org, ws, subtopic_id):
        if str(o["objective_id"]) == objective_id:
            return o["hint_policy"]
    return None


def envelope_json(env: Any) -> dict[str, Any]:
    return env if isinstance(env, dict) else json.loads(env or "{}")
