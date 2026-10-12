"""Work Companion conversation through the AI engineer's LangGraph graph (ADR-034).

Her graph decides what to say: the opening brief, intent, guidance from approved knowledge and
reading work updates (which it saves itself as reports). The backend authorizes, applies the demo
cap, drives the graph and records the exchange:

- The transcript is saved here (work_session_messages): her graph keeps only its latest message.
- The canvas follows the steps that actually ran (streamed by the graph), mapped to the allowlisted
  ui_action values. No keyword routing, and nothing the model writes can pick a component.
- Citations are the approved chunks her guidance step retrieved, checked against this workspace and
  resolved when read, so a revoked or superseded source is never shown as current guidance.
- Reports her graph saved during the turn get the ADR-033 bookkeeping in the same transaction as the
  transcript: older waiting reports are superseded, a report the ticket system already agrees with
  is matched, the shift lead is told about "done" (informational), and each report is audited.
- Delegation: when her graph suggests handing the shift lead's tickets to teammates on the same
  shift, the backend rechecks every pick and creates a delegation proposal that opens in the work
  area. Nothing is assigned until the lead confirms it (work_commands.confirm_proposal).
- Calendar and scheduling run in her graph (her calendar service; one Google account for now). The
  run stops in front of those steps while the backend asks her service whether it is signed in to
  Google: if so the run carries on; if not, the reply asks the employee to connect (a button opens the
  Google sign-in, then the question is asked again). The employee approves a proposed schedule in the
  chat before her graph creates any event. With COMPANION_CALENDAR=false a fixed reply says calendar
  is off. Their replies stay in the chat and don't change the work area (no calendar view yet).

No database transaction is open while the graph runs (it writes in its own transactions). A message
is identified by the client's turn ID: a retry of an answered message returns the saved answer.
"""

import logging
import uuid as _uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Connection, text

from app.config import get_settings
from app.db import transaction
from app.errors import ApiError
from app.integrations import calendar_service
from app.integrations.companion_engine import CompanionBusy, CompanionEngine, CompanionEngineError, Trace, get_companion
from app.repositories import commands, work
from app.services import usage
from app.services.companion import OPEN, _context, said

log = logging.getLogger(__name__)

NO_REPLY = "The work assistant couldn't reply. Nothing was saved; your message is still in the box, so you can try again."
NOT_STARTED = "The work assistant couldn't start this conversation. Your work below still comes from the database; reload the page to try again."
CALENDAR_OFF = (
    "Scheduling and calendar requests are turned off in this WorkWeave app. "
    "I can help with your assigned work, guidance from approved procedures, or recording an update."
)
CALENDAR_CONNECT = "Your Google Calendar isn't connected yet. Connect it with the button below, and I'll ask again for you."
CALENDAR_DOWN = "I can't reach the calendar service right now, so I couldn't check your calendar. Try again in a moment."
CALENDAR_STEPS = ["schedule_work", "calendar_inquiry", "handle_schedule_approval"]
NO_PROPOSAL = "I couldn't prepare that delegation proposal: "
# Her scheduling flow, for the audit trail (calendar contents are never copied into the audit).
SCHEDULE_STEPS = {"schedule_work": "requested", "modify_schedule_proposal": "changed", "create_approved_calendar_events": "events_created"}
# Steps of her main graph → the allowlisted canvas action (07-api-contracts §AI Work Companion).
STEP_ACTIONS = {
    "focus_work": "SHOW_WORK_ITEMS",
    "work_overview": "SHOW_WORK_ITEMS",
    "reprioritize_work": "SHOW_WORK_ITEMS",
    "work_guidance": "SHOW_GUIDANCE",
    "work_update": "SHOW_WORK_UPDATES",
    "explain_assignment": "SHOW_WORK_ITEMS",  # the ticket the "why" was about (ADR-035)
    "clarify_request": "REQUEST_CLARIFICATION",
}
MAX_TEXT = 4000
MAX_CITATIONS = 5


def engine() -> CompanionEngine | None:
    return get_companion()


def _stop_before() -> list[str]:
    """Runs always stop in front of calendar steps, so the app can check the connection first."""
    return CALENDAR_STEPS


def _thread(s: dict[str, Any]) -> str:
    """One LangGraph thread per work session. LangGraph thread IDs must be UUIDs, so it is the work
    session's own ID (sessions opened before 2026-10-10 stored a "ww-work-" label instead)."""
    return str(s["work_session_id"])


def _employee(s: dict[str, Any]) -> dict[str, str]:
    return {"employee_id": str(s["employee_id"]), "organization_id": str(s["organization_id"]), "workspace_id": str(s["workspace_id"])}


def _reply(trace: Trace) -> str:
    conv = (trace.thread.values if trace.thread else {}).get("conversation") or {}
    return (conv.get("assistant_message") or "").strip()


def _db_now(conn: Connection) -> datetime:
    return conn.execute(text("SELECT clock_timestamp()")).scalar_one()


# ---------------------------------------------------------------- what the reply may show
def _ui_action(trace: Trace) -> str:
    for step in reversed(trace.steps):
        if step in STEP_ACTIONS:
            return STEP_ACTIONS[step]
    return "NO_VIEW_CHANGE"


def _resource_refs(conn: Connection, s: dict[str, Any], trace: Trace, ui_action: str, teams: list[str]) -> list[str]:
    """The work item the reply is about, only if this employee may see it."""
    if ui_action not in ("SHOW_WORK_ITEMS", "SHOW_GUIDANCE"):
        return []
    values = trace.thread.values if trace.thread else {}
    if "explain_assignment" in trace.steps:
        ref = (values.get("assignment_question") or {}).get("work_item_id")
    else:
        ref = (values.get("response_analysis") or {}).get("referenced_work_item_id") or (values.get("session") or {}).get("focused_work_item_id")
    if not ref:
        return []
    from app.services.companion import visible_to

    visible = {str(i["work_item_id"]) for i in visible_to(conn, s["organization_id"], s["workspace_id"], s["employee_id"], teams)}
    return [ref] if ref in visible else []


def _citations(conn: Connection, s: dict[str, Any], trace: Trace, ui_action: str) -> list[dict[str, Any]]:
    """The approved chunks guidance used, kept only when they belong to this workspace."""
    if ui_action != "SHOW_GUIDANCE":
        return []
    out, seen = [], set()
    for chunk in trace.retrieved:
        try:
            cid = _uuid.UUID(str(chunk.get("chunk_id")))
        except ValueError:
            continue
        if cid in seen or not work.chunk_source(conn, s["organization_id"], s["workspace_id"], cid):
            continue
        seen.add(cid)
        out.append({"chunk_id": str(cid)})
        if len(out) == MAX_CITATIONS:
            break
    return out


# ---------------------------------------------------------------- reports the graph saved (ADR-033)
def _bookkeep_reports(conn: Connection, s: dict[str, Any], me, since: datetime, request_id: _uuid.UUID) -> None:
    from app.services.work_sync import MATCHES, _lead_now

    org, ws = s["organization_id"], s["workspace_id"]
    teams = work.teams_with(conn, org, ws, me, "work:report")
    for rep in work.session_reports_since(conn, org, ws, s["work_session_id"], me, since):
        work.supersede_older(conn, rep)
        item = work.lock_item(conn, org, ws, rep["work_item_id"])
        if rep["source_sync_status"] == "AWAITING_SOURCE" and item and item["status"] in MATCHES[said(rep)]:
            rep = work.set_report_sync(conn, rep, "MATCHED")  # the ticket system already agrees
        if item and said(rep) == "DONE" and rep["source_sync_status"] == "AWAITING_SOURCE" and item["status"] in OPEN:
            for lead in _lead_now(conn, org, ws, teams):
                if lead != me:  # informational: leads monitor, they don't validate
                    work.outbox(conn, org, ws, request_id, lead, "work_item", item["work_item_id"], item["revision"], "work.reported_done", {"work_item_id": str(item["work_item_id"]), "external_id": item["external_id"]})
        kind = (rep.get("update_type") or "status_change").lower()
        commands.audit(conn, org, ws, me, f"work_report.{kind}", "work_item_reported_update", rep["reported_update_id"], rep["revision"], request_id)


NO_PENDING = "There's no delegation proposal waiting for your confirmation here. Ask me to assign a ticket first, then say \"confirm\"."


def _confirm_from_chat(conn: Connection, s: dict[str, Any], me, request_id) -> tuple[str, str, str, list[str]]:
    """A chat "confirm" counts only for the proposal shown in the companion's previous reply, and only
    for the lead of the shift in progress (the same checks as the Confirm button)."""
    from app.services.work_commands import _editable, _scoped_proposal, confirm_locked

    org, ws = s["organization_id"], s["workspace_id"]
    def notice(m: dict[str, Any]) -> bool:  # announcements (sync_notices) don't count as the previous reply
        return m["provenance"] == "BACKEND_RECORD" and any(str(r).startswith(("outbox:", "report:")) for r in m["resource_refs"] or [])

    previous = next((m for m in reversed(work.messages_of(conn, org, ws, s["work_session_id"], limit=20)) if m["sender"] == "AI" and not notice(m)), None)
    if not previous or previous["ui_action"] != "SHOW_DELEGATION_PROPOSAL" or not previous["resource_refs"]:
        return NO_PENDING, "BACKEND_RECORD", "NO_VIEW_CHANGE", []
    pid = previous["resource_refs"][0]
    try:
        p = _scoped_proposal(conn, org, ws, me, pid, lock=True)
        _editable(p, None)
        with conn.begin_nested():  # a refused confirmation changes nothing, and the turn is still saved
            p = confirm_locked(conn, org, ws, me, p, request_id)
    except ApiError as e:
        return f"I couldn't confirm it: {e.message}", "BACKEND_RECORD", "SHOW_DELEGATION_PROPOSAL", [pid]
    items = work.proposal_items(conn, org, ws, p["delegation_proposal_id"])
    names = work.employee_names(conn, org, ws, [i["final_employee_id"] or i["recommended_employee_id"] for i in items])
    done = "; ".join(f"{i['external_id'] or i['title']} is now with {names.get(i['final_employee_id'] or i['recommended_employee_id'], 'the person selected')}" for i in items)
    return f"Confirmed. {done}. They've been notified, and their work lists are updated.", "BACKEND_RECORD", "SHOW_DELEGATION_PROPOSAL", [pid]


# ---------------------------------------------------------------- app actions from the chat
def _find_item(items: list[dict[str, Any]], ref: str | None) -> dict[str, Any] | None:
    """A work item the employee may see, by ticket number ("910", "#910", "Ticket #910") or title."""
    if not ref:
        return None
    want = ref.strip().lower()
    digits = "".join(ch for ch in want if ch.isdigit())
    for i in items:
        ext = (i.get("external_id") or "").lower()
        if ext and (want == ext or (digits and "".join(ch for ch in ext if ch.isdigit()) == digits)):
            return i
    return next((i for i in items if want and want in (i["title"] or "").lower()), None)


def _label(i: dict[str, Any]) -> str:
    return i.get("external_id") or i["title"]


def _previous_proposal(conn: Connection, s: dict[str, Any]) -> str | None:
    """The delegation proposal the companion's previous reply showed (announcements don't count)."""
    org, ws = s["organization_id"], s["workspace_id"]
    for m in reversed(work.messages_of(conn, org, ws, s["work_session_id"], limit=20)):
        if m["sender"] != "AI" or (m["provenance"] == "BACKEND_RECORD" and any(str(r).startswith(("outbox:", "report:")) for r in m["resource_refs"] or [])):
            continue
        return m["resource_refs"][0] if m["ui_action"] == "SHOW_DELEGATION_PROPOSAL" and m["resource_refs"] else None
    return None


VOICE_REPLIES = {
    "READ_ALOUD_ON": "Okay, I'll read my replies aloud.",
    "READ_ALOUD_OFF": "Okay, I'll stop reading my replies aloud. You can turn it back on any time.",
    "STOP_READING": "Okay.",
    "SPEAK_SLOWER": "Okay, I'll speak a little slower.",
    "SPEAK_FASTER": "Okay, I'll speak a little faster.",
    "NORMAL_SPEED": "Okay, back to normal speed.",
}


def perform_action(conn: Connection, s: dict[str, Any], me, teams: list[str], action: dict[str, Any], request_id) -> tuple[str, str, str, list[str]]:
    """Performs the app action her graph named, with the same checks as the matching button. Returns
    (reply, provenance, ui_action, resource_refs). A refused action changes nothing and says why."""
    from app.services.companion import visible_to

    org, ws = s["organization_id"], s["workspace_id"]
    kind = action.get("action") or "NONE"
    done = lambda text_, ui="NO_VIEW_CHANGE", refs=None: (text_, "BACKEND_RECORD", ui, refs or [])  # noqa: E731
    items = visible_to(conn, org, ws, me, teams)
    try:
        with conn.begin_nested():  # a refused action changes nothing; the conversation is still saved
            if kind == "SHOW_BRIEFING":
                return done("Here's your briefing.", "SHOW_BRIEFING")
            if kind == "SHOW_WORK_UPDATES":
                return done("Here are the recent work updates.", "SHOW_WORK_UPDATES")
            if kind == "SHOW_WORK_ITEMS":
                statuses = [x for x in action.get("status_filter") or [] if x in OPEN]
                which = " and ".join(x.replace("_", " ").lower() for x in statuses)
                return done(f"Here are your {which + ' ' if which else ''}tickets.", "SHOW_WORK_ITEMS", [f"status:{x}" for x in statuses])
            if kind in VOICE_REPLIES:
                return done(VOICE_REPLIES[kind], refs=[f"client:{kind}"])

            if kind in ("OPEN_TICKET_SYSTEM", "ACCEPT_ASSIGNMENT"):
                item = _find_item(items, action.get("work_item_reference"))
                if not item:
                    return done(f"I couldn't find {action.get('work_item_reference') or 'that ticket'} among the tickets you can see.")
                if kind == "OPEN_TICKET_SYSTEM":
                    system = work.system_name(conn, work.scenario_of(conn, org, ws))
                    return done(f"Here's {_label(item)}. Open it in the {system} to change its status.", "SHOW_WORK_ITEMS",
                                [str(item["work_item_id"]), f"link:/companion/tool/?item={item['work_item_id']}"])
                a = work.active_assignment(conn, org, ws, item["work_item_id"], me)
                if not a:
                    return done(f"{_label(item)} isn't assigned to you, so there's nothing to accept.")
                if a["status"] != "ASSIGNED":
                    return done(f"You've already taken {_label(item)}.", "SHOW_WORK_ITEMS", [str(item["work_item_id"])])
                work.set_assignment_status(conn, a, "ACCEPTED")
                commands.audit(conn, org, ws, me, "work_item_assignment.accepted", "work_item_assignment", a["assignment_id"], a["revision"] + 1, request_id)
                return done(f"Got it: {_label(item)} is yours.", "SHOW_WORK_ITEMS", [str(item["work_item_id"])])

            if kind in ("CHANGE_PROPOSAL_PERSON", "REJECT_PROPOSAL"):
                from app.services.work_commands import _editable, _eligible_for, _scoped_proposal

                pid = _previous_proposal(conn, s)
                if not pid:
                    return done("There's no delegation proposal open here to change. Ask me to assign a ticket first.")
                p = _scoped_proposal(conn, org, ws, me, pid, lock=True)
                _editable(p, None)
                if kind == "REJECT_PROPOSAL":
                    p = work.set_proposal(conn, p, "REJECTED")
                    commands.audit(conn, org, ws, me, "delegation_proposal.rejected", "delegation_proposal", p["delegation_proposal_id"], p["revision"], request_id)
                    return done("Cancelled. Nothing was assigned.", "SHOW_DELEGATION_PROPOSAL", [pid])
                candidates = _eligible_for(conn, p)
                names = work.employee_names(conn, org, ws, candidates)
                said = (action.get("person_name") or "").strip().lower()
                who = [e for e, n in names.items() if said and (said == n.lower() or said in n.lower().split() or (said in ("me", "myself") and e == me))]
                if len(who) != 1:
                    return done(f"I couldn't tell who {action.get('person_name') or 'you meant'} is among the people on your shift.", "SHOW_DELEGATION_PROPOSAL", [pid])
                its = work.proposal_items(conn, org, ws, p["delegation_proposal_id"])
                target = _find_item(its, action.get("work_item_reference")) if len(its) > 1 else its[0]
                if not target:
                    return done("Which ticket in the proposal should change?", "SHOW_DELEGATION_PROPOSAL", [pid])
                work.edit_proposal_item(conn, org, ws, target["proposal_item_id"], who[0])
                p = work.set_proposal(conn, p, "EDITED")
                commands.audit(conn, org, ws, me, "delegation_proposal.edited", "delegation_proposal", p["delegation_proposal_id"], p["revision"], request_id)
                return done(f"Changed: {_label(target)} now goes to {names[who[0]]}. Say \"confirm\" to assign it.", "SHOW_DELEGATION_PROPOSAL", [pid])

            if kind == "SAVE_NOTE":
                content = (action.get("note_text") or "").strip()
                if not content:
                    return done("What should the note say?")
                audience = action.get("note_audience") or "PRIVATE"
                d = work.create_draft(conn, org, ws, me, content[:4000], audience)
                commands.audit(conn, org, ws, me, "memory_draft.created", "memory_draft", d["draft_id"], d["revision"], request_id)
                return done(f"Saved as a private draft note: \"{content[:200]}\". Say \"submit my note\" when it's ready for review.")
            if kind == "SUBMIT_NOTE":
                draft = next((d for d in work.drafts_of(conn, org, ws, me) if d["status"] == "DRAFT"), None)
                if not draft:
                    return done("You don't have a draft note to submit.")
                if (draft["requested_audience"] or ["PRIVATE"])[0] == "PRIVATE":
                    return done("That note is private, so it stays with you. Use Capture knowledge to choose who should see it, then submit.")
                d = work.submit_draft(conn, draft)
                for reviewer in work.holders(conn, org, ws, "knowledge:review", work.read_teams(conn, org, ws, me)):
                    if reviewer != me:
                        work.outbox(conn, org, ws, request_id, reviewer, "memory_draft", d["draft_id"], d["revision"], "knowledge.note_awaiting_review", {})
                commands.audit(conn, org, ws, me, "memory_draft.submitted", "memory_draft", d["draft_id"], d["revision"], request_id)
                return done("Submitted your note for review.")
    except ApiError as e:
        return done(f"I couldn't do that: {e.message}")
    return done("I can't do that from the chat yet. The buttons in the work area can.")


def _calendar_gate() -> str | None:
    """None when her calendar step may run; otherwise the backend's fixed reply."""
    if not get_settings().companion_calendar:
        return CALENDAR_OFF
    state = calendar_service.status()
    if state == "CONNECTED":
        return None
    return CALENDAR_CONNECT if state == "NOT_CONNECTED" else CALENDAR_DOWN


def calendar_status(token: str | None) -> dict[str, Any]:
    with transaction() as conn:
        _context(conn, token)  # any persona with work access; nothing about the calendar is returned
    # The calendar service is asked after the transaction closes (external calls stay outside it).
    if not get_settings().companion_calendar:
        return {"enabled": False, "connected": False}
    state = calendar_service.status()
    return {"enabled": True, "connected": state == "CONNECTED", "reachable": state != "UNREACHABLE"}


def calendar_sign_in(token: str | None) -> str | None:
    """The Google address for the "Connect Google Calendar" window; any persona with work access may
    start it (the calendar service accepts only its configured account). None if it can't start."""
    with transaction() as conn:
        _context(conn, token)
    if not get_settings().companion_calendar:
        return None
    return calendar_service.sign_in_redirect()


# ---------------------------------------------------------------- the view
def _citation_dtos(conn: Connection, org, ws, message_id: str, refs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from app.services.onboarding import _citation, _engine_citation

    out = []
    for i, ref in enumerate(refs):
        chunk = work.chunk_source(conn, org, ws, ref.get("chunk_id"))
        if not chunk:
            continue
        engine_ref = {"document_version_id": str(chunk["document_version_id"]), "section_id": str(chunk["source_section_id"]) if chunk["source_section_id"] else None, "chunk_id": str(chunk["chunk_id"])}
        out.append(_citation(conn, org, ws, message_id, i, _engine_citation(conn, org, ws, engine_ref)))
    return out


def message_dto(conn: Connection, m: dict[str, Any]) -> dict[str, Any]:
    mid = str(m["message_id"])
    out: dict[str, Any] = {
        "message_id": mid,
        "sender": m["sender"],
        "text": m["text"],
        "citations": _citation_dtos(conn, m["organization_id"], m["workspace_id"], mid, m["citations"] or []),
        "provenance": m["provenance"],
    }
    if m["ui_action"]:
        out["ui_action"] = m["ui_action"]
    for ref in m["resource_refs"] or []:
        if str(ref).startswith("link:"):  # e.g. open the ticket on the ticket system page
            out["link"] = {"label": "Open in the ticket system", "href": str(ref)[5:]}
        elif str(ref).startswith("client:"):  # a setting in the employee's browser (read-aloud)
            out["client_action"] = str(ref)[7:]
    return out


def _canvas(messages: list[dict[str, Any]]) -> dict[str, Any]:
    """The work area follows the latest reply that changed it; the briefing until one does."""
    for m in reversed(messages):
        action = m["ui_action"]
        if action == "SHOW_WORK_ITEMS":
            refs = [str(r) for r in m["resource_refs"] or []]
            statuses = [r[7:] for r in refs if r.startswith("status:")]
            ids = [r for r in refs if ":" not in r]
            if ids:
                return {"view": "WORK_ITEMS", "selected_id": ids[0]}
            return {"view": "WORK_ITEMS", "filters": {"status": statuses}} if statuses else {"view": "WORK_ITEMS"}
        if action == "SHOW_WORK_UPDATES":
            return {"view": "WORK_UPDATES"}
        if action == "SHOW_DELEGATION_PROPOSAL" and m["resource_refs"]:
            return {"view": "DELEGATION_PROPOSAL", "proposal_id": m["resource_refs"][0]}
        if action == "SHOW_GUIDANCE":
            return {"view": "GUIDANCE", "guidance_id": str(m["message_id"])}
        if action == "SHOW_BRIEFING":
            return {"view": "BRIEFING"}
    return {"view": "BRIEFING"}


def _calendar_connect(msgs: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The latest reply asked the employee to connect Google Calendar: the button and what to re-ask."""
    if not msgs or msgs[-1]["sender"] != "AI" or msgs[-1]["provenance"] != "BACKEND_RECORD" or msgs[-1]["text"] != CALENDAR_CONNECT:
        return None
    asked = next((m["text"] for m in reversed(msgs) if m["sender"] == "EMPLOYEE" and m["client_turn_id"] == msgs[-1]["client_turn_id"]), "")
    return {"connect_url": calendar_service.connect_url(), "retry_text": asked}


def view(conn: Connection, s: dict[str, Any], status: str = "ok", message: str = "") -> dict[str, Any]:
    msgs = work.messages_of(conn, s["organization_id"], s["workspace_id"], s["work_session_id"])
    connect = _calendar_connect(msgs)
    return {
        **({"calendar_connect": connect} if connect else {}),
        "work_session_id": str(s["work_session_id"]),
        "revision": s["revision"],
        "transcript": [message_dto(conn, m) for m in msgs],
        "canvas": _canvas(msgs),
        "script_prompts": [],
        "assistant": {"status": status, "message": message},
    }


def _owned(conn: Connection, token: str | None, work_session_id: str) -> tuple[Any, Any, list[str], dict[str, Any]]:
    r, me, teams = _context(conn, token)
    try:
        sid = _uuid.UUID(work_session_id)
    except ValueError:
        raise ApiError("MALFORMED_INPUT", "Unknown work session.") from None
    s = work.work_session_for(conn, r.session["organization_id"], r.session["workspace_id"], sid, me)
    if not s:
        raise ApiError("NOT_FOUND", "This work session isn't yours or no longer exists.")
    return r, me, teams, s


# ---------------------------------------------------------------- opening
def _save_opening(token: str | None, sid: str, trace: Trace, after_turn: bool = False) -> None:
    """Saves the brief the graph is waiting on. Two requests opening the same session save it once:
    the first opening is skipped when the conversation already has messages."""
    text_ = _reply(trace)
    if not text_ or not (trace.thread and trace.thread.waiting):
        return
    with transaction() as conn:
        _, me, _, s = _owned(conn, token, sid)
        work.lock_employee_sessions(conn, s["organization_id"], s["workspace_id"], me)
        msgs = work.messages_of(conn, s["organization_id"], s["workspace_id"], s["work_session_id"], limit=1)
        if msgs and not after_turn:
            return
        if msgs and msgs[-1]["sender"] == "AI" and msgs[-1]["text"] == text_:
            return  # the same restart brief, saved by another request
        work.add_message(conn, s["organization_id"], s["workspace_id"], s["work_session_id"], "AI", text_, "WORK_ENGINE", ui_action="NO_VIEW_CHANGE")
        work.bump_session(conn, s)


def ensure_opening(token: str | None, sid: str) -> dict[str, Any]:
    """After the session opens: the companion's opening brief, saved once. Never raises for the
    engine: if it can't start (unreachable, an error, the demo cap), the view says so. Every re-read
    also adds notices for what changed for this person since (sync_notices)."""
    eng = engine()
    assert eng is not None
    with transaction() as conn:
        r, me, _, s = _owned(conn, token, sid)
        if work.messages_of(conn, s["organization_id"], s["workspace_id"], s["work_session_id"], limit=1):
            work.lock_employee_sessions(conn, s["organization_id"], s["workspace_id"], me)
            if sync_notices(conn, s, me):
                s = _owned(conn, token, sid)[3]
            return view(conn, s)
    try:
        eng.wait_idle(_thread(s))  # another page load may be opening this session right now
        st = eng.thread(_thread(s))
        if st.waiting:
            # Opened by that request, or opened before and the brief wasn't saved: keep what it said.
            _save_opening(token, sid, Trace(thread=st))
        else:
            with transaction() as conn:
                usage.charge(conn, "TUTOR_TURN", s["workspace_id"], r.session)
            try:
                _save_opening(token, sid, eng.start(_thread(s), _employee(s), str(s["work_session_id"]), _stop_before()))
            except CompanionBusy:
                # Another request started it a moment ago: wait for its brief instead of failing.
                eng.wait_idle(_thread(s))
                _save_opening(token, sid, Trace(thread=eng.thread(_thread(s))))
    except ApiError as e:
        if e.code != "LIMIT_REACHED":
            raise
        with transaction() as conn:
            return view(conn, _owned(conn, token, sid)[3], "unavailable", e.message)
    except CompanionEngineError:
        log.exception("companion engine couldn't open work session %s", sid)
        with transaction() as conn:
            return view(conn, _owned(conn, token, sid)[3], "unavailable", NOT_STARTED)
    with transaction() as conn:
        return view(conn, _owned(conn, token, sid)[3])


# ---------------------------------------------------------------- a message
def _ready(eng: CompanionEngine, token: str | None, sid: str, s: dict[str, Any]) -> None:
    """The graph waits for the employee. After a pause (her graph ends there) or a lost run it starts
    again, and its new opening brief is saved before the message."""
    eng.wait_idle(_thread(s))  # e.g. the opening brief is still being written
    st = eng.thread(_thread(s))
    if st.waiting:
        return
    if st.exists and st.next and st.next[0] in CALENDAR_STEPS:
        # A run left in front of a calendar step (e.g. a lost request): back to waiting first.
        eng.hand_back(_thread(s), (st.values.get("conversation") or {}), CALENDAR_OFF if not get_settings().companion_calendar else CALENDAR_DOWN)
        return
    _save_opening(token, sid, eng.start(_thread(s), _employee(s), str(s["work_session_id"]), _stop_before()), after_turn=True)
    if not eng.thread(_thread(s)).waiting:
        raise CompanionEngineError("The graph didn't reach wait_for_user.")


def send(token: str | None, sid: str, client_turn_id: str, expected_revision: int | None, text_: str, input_kind: str, request_id: _uuid.UUID, on_step: Any = None) -> dict[str, Any]:
    eng = engine()
    assert eng is not None
    try:
        cid = _uuid.UUID(client_turn_id)
    except ValueError:
        raise ApiError("MALFORMED_INPUT", "client_turn_id must be a UUID.") from None
    body = (text_ or "").strip()
    if not body:
        raise ApiError("MALFORMED_INPUT", "Type or say a message first.")
    if len(body) > MAX_TEXT:
        raise ApiError("MALFORMED_INPUT", f"Keep messages under {MAX_TEXT} characters.")

    with transaction() as conn:
        r, me, _, s = _owned(conn, token, sid)
        if work.turn_messages(conn, s["organization_id"], s["workspace_id"], s["work_session_id"], cid):
            return view(conn, s)  # already answered: the saved reply, not a second run
        if s["status"] != "ACTIVE":
            raise ApiError("GUARD_FAILED", "Open the work session again before sending a message.")
        if expected_revision is not None and expected_revision != s["revision"]:
            raise ApiError("REVISION_CONFLICT", "This conversation changed in another tab. Reload to continue from the saved state.")
        usage.charge(conn, "TUTOR_TURN", s["workspace_id"], r.session)

    try:
        _ready(eng, token, sid, s)
        with transaction() as conn:
            since = _db_now(conn)
        trace = eng.resume(_thread(s), body, input_kind, str(cid), _stop_before(), on_step=on_step)
        provenance = "WORK_ENGINE"
        if trace.stopped_before in CALENDAR_STEPS:
            fixed = _calendar_gate()
            if fixed is None:
                more = eng.proceed(_thread(s), on_step=on_step)  # connected: her calendar step runs now
                trace = Trace(steps=trace.steps + more.steps, retrieved=more.retrieved or trace.retrieved, thread=more.thread)
            else:
                eng.hand_back(_thread(s), (trace.thread.values.get("conversation") or {}), fixed)
                trace.thread = None
                provenance = "BACKEND_RECORD"
        if provenance == "BACKEND_RECORD":
            reply, ui_action = fixed, "NO_VIEW_CHANGE"
        else:
            reply, ui_action = _reply(trace), _ui_action(trace)
    except CompanionEngineError:
        log.exception("companion engine failed on work session %s", sid)
        raise ApiError("DEPENDENCY_UNAVAILABLE", NO_REPLY, retryable=True) from None
    if not reply:
        log.error("companion engine finished work session %s turn %s without a reply", sid, cid)
        raise ApiError("DEPENDENCY_UNAVAILABLE", NO_REPLY, retryable=True)

    with transaction() as conn:
        _, me, teams, s = _owned(conn, token, sid)
        org, ws = s["organization_id"], s["workspace_id"]
        work.lock_employee_sessions(conn, org, ws, me)
        if work.turn_messages(conn, org, ws, s["work_session_id"], cid):
            return view(conn, s)
        work.add_message(conn, org, ws, s["work_session_id"], "EMPLOYEE", body, "EMPLOYEE_INPUT", client_turn_id=cid, input_kind=input_kind)
        refs = _resource_refs(conn, s, trace, ui_action, teams)
        left_out: list[str] = []
        if "delegate_work" in trace.steps and trace.thread:
            # Her graph suggested hand-overs; the backend rechecks them and makes the proposal the
            # shift lead confirms (nothing is assigned here).
            from app.services.work_commands import propose_from_engine

            suggested = trace.thread.values.get("delegation") or {}
            if suggested.get("proposal"):
                proposal, left_out = propose_from_engine(conn, org, ws, me, suggested, request_id)
                if proposal:
                    ui_action, refs = "SHOW_DELEGATION_PROPOSAL", [str(proposal["delegation_proposal_id"])]
                else:
                    reply, provenance, ui_action = NO_PROPOSAL + "; ".join(left_out) + ".", "BACKEND_RECORD", "NO_VIEW_CHANGE"
                    left_out = []
        if "confirm_delegation" in trace.steps:
            # The lead said "confirm": WorkWeave confirms the proposal it just showed, or says why not.
            reply, provenance, ui_action, refs = _confirm_from_chat(conn, s, me, request_id)
        if "request_app_action" in trace.steps and trace.thread:
            # Her graph named an app action; WorkWeave checks it and performs it (ADR-036 plan).
            reply, provenance, ui_action, refs = perform_action(conn, s, me, teams, trace.thread.values.get("app_action") or {}, request_id)
        work.add_message(conn, org, ws, s["work_session_id"], "AI", reply, provenance, client_turn_id=cid, ui_action=ui_action,
                         resource_refs=refs, citations=_citations(conn, s, trace, ui_action))
        if left_out:
            work.add_message(conn, org, ws, s["work_session_id"], "SYSTEM", "Left out of the proposal: " + "; ".join(left_out) + ".", "BACKEND_RECORD", client_turn_id=None)
        _bookkeep_reports(conn, s, me, since, request_id)
        s = work.bump_session(conn, s)
        commands.audit(conn, org, ws, me, "work_session.turn", "work_session", s["work_session_id"], s["revision"], request_id)
        for step in dict.fromkeys(x for x in trace.steps if x in SCHEDULE_STEPS):
            commands.audit(conn, org, ws, me, f"work_schedule.{SCHEDULE_STEPS[step]}", "work_session", s["work_session_id"], s["revision"], request_id)
        return view(conn, s)


# ---------------------------------------------------------------- guidance projection
def guidance(conn: Connection, token: str | None, sid: str, guidance_id: str) -> dict[str, Any]:
    _, _, _, s = _owned(conn, token, sid)
    org, ws = s["organization_id"], s["workspace_id"]
    msgs = work.messages_of(conn, org, ws, s["work_session_id"])
    m = next((x for x in msgs if str(x["message_id"]) == guidance_id and x["ui_action"] == "SHOW_GUIDANCE"), None)
    if not m:
        raise ApiError("NOT_FOUND", "That guidance isn't in this conversation.")
    question = next((x["text"] for x in msgs if x["sender"] == "EMPLOYEE" and x["client_turn_id"] == m["client_turn_id"]), "")
    citations = _citation_dtos(conn, org, ws, guidance_id, m["citations"] or [])
    out: dict[str, Any] = {
        "guidance_id": guidance_id,
        "question": question,
        "answer": m["text"],
        # No approved source behind it: shown as such (her graph says when knowledge is missing).
        "answer_status": "ANSWERED" if citations else "INSUFFICIENT_EVIDENCE",
        "citations": citations,
        "unknowns": [],
    }
    if m["resource_refs"]:
        out["related_work_item_id"] = m["resource_refs"][0]
    return out


# ---------------------------------------------------------------- progress while the companion works
# Fixed, plain-language labels for what comes next, chosen from the step that just finished (and, after
# the intent step, from its chosen action). They describe the work, never model output. Unknown steps
# are ignored, so changes to her graph are safe.
FIRST_STEP = "Understanding your message…"
AFTER_ANALYSIS = {
    "FOCUS": "Opening it…",
    "OVERVIEW": "Looking at your work…",
    "GUIDE": "Finding the right part of the procedure…",
    "UPDATE_STATUS": "Recording your update…",
    "HANDLE_BLOCKER": "Recording your update…",
    "REPRIORITIZE": "Weighing your priorities…",
    "SCHEDULE": "Checking your calendar…",
    "CALENDAR": "Checking your calendar…",
    "DELEGATE": "Checking who's on your shift…",
    "CONFIRM_DELEGATION": "Confirming…",
    "EXPLAIN_ASSIGNMENT": "Looking up why it was assigned…",
    "CLARIFY": "Working out what you mean…",
    "APP_ACTION": "On it…",
    "ANSWER_WORK_DATA": "Looking at the work…",
}
AFTER_STEP = {
    "retrieve_relevant_chunks": "Writing guidance from the procedure…",
    "load_shift_work": "Preparing the proposal…",
    "calculate_free_slots": "Preparing a schedule…",
    "load_assignment_options": "Writing the explanation…",
}


def progress_label(step: str, update: dict[str, Any]) -> str | None:
    if step == "analyze_user_response":
        return AFTER_ANALYSIS.get(((update.get("response_analysis") or {}).get("recommended_action")) or "")
    return AFTER_STEP.get(step)


def send_stream(token: str | None, sid: str, client_turn_id: str, expected_revision: int | None, text_: str, input_kind: str, request_id: _uuid.UUID):
    """send() with progress: yields ("progress", {"label"}) while the graph works, then ("done", view)
    or ("error", ApiError fields). The turn runs in a worker thread so labels arrive as steps finish."""
    import queue
    import threading

    events: queue.Queue = queue.Queue()
    last: list[str | None] = [None]

    def on_step(step: str, update: dict[str, Any]) -> None:
        label = progress_label(step, update)
        if label and label != last[0]:
            last[0] = label
            events.put(("progress", {"label": label}))

    def run() -> None:
        try:
            events.put(("done", send(token, sid, client_turn_id, expected_revision, text_, input_kind, request_id, on_step=on_step)))
        except ApiError as e:
            events.put(("error", {"code": e.code, "message": e.message, "retryable": e.retryable, **e.details}))
        except Exception:  # noqa: BLE001 - reported to the employee as a retryable failure
            log.exception("companion turn failed on work session %s", sid)
            events.put(("error", {"code": "DEPENDENCY_UNAVAILABLE", "message": NO_REPLY, "retryable": True}))

    threading.Thread(target=run, daemon=True).start()
    yield "progress", {"label": FIRST_STEP}
    while True:
        event, data = events.get()
        yield event, data
        if event in ("done", "error"):
            return


# ---------------------------------------------------------------- the companion speaks first
def _notice_text(event_type: str, payload: dict[str, Any]) -> str | None:
    ref = payload.get("external_id") or "A ticket"
    return {
        "work.assigned": f"{ref} was assigned to you. Say \"open {ref.split('#')[-1]}\" to see it, or ask me how to start.",
        "work.unassigned": "One of your tickets was moved to someone else, so it's off your list.",
        "work.report_needs_review": f"The ticket system closed {ref} differently from what was reported, so that report needs review.",
        "work.reported_done": f"{ref} was reported done. It stays open until the ticket system shows it resolved.",
    }.get(event_type)


def sync_notices(conn: Connection, s: dict[str, Any], me) -> int:
    """Adds a short chat notice for what changed for this person since the session opened: tickets
    assigned to or moved away from them, reports the ticket system confirmed or closed differently,
    and (for the lead) reports of "done". Each is announced once. Notices name tickets, never private
    text, and they're read aloud like other replies when read-aloud is on."""
    org, ws, sid = s["organization_id"], s["workspace_id"], s["work_session_id"]
    events = work.notice_events_since(conn, org, ws, me, s["started_at"])
    matched = work.matched_reports_since(conn, org, ws, me, s["started_at"])
    refs = [f"outbox:{e['event_id']}" for e in events] + [f"report:{m['reported_update_id']}" for m in matched]
    done = work.announced(conn, org, ws, sid, refs)
    new = []
    for e in events:
        ref, text_ = f"outbox:{e['event_id']}", _notice_text(e["event_type"], e["payload"] or {})
        if text_ and ref not in done:
            new.append((e["created_at"], text_, ref))
    for m in matched:
        ref = f"report:{m['reported_update_id']}"
        if ref not in done:
            new.append((m["source_reconciled_at"], f"{m['external_id'] or m['title']} is resolved in the ticket system and matches what you reported, so it's off your list.", ref))
    for _, text_, ref in sorted(new, key=lambda x: x[0]):
        work.add_message(conn, org, ws, sid, "AI", text_, "BACKEND_RECORD", ui_action="NO_VIEW_CHANGE", resource_refs=[ref])
    if new:
        work.bump_session(conn, s)
    return len(new)
