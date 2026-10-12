"""Work Companion: database-backed work context, the conversation and voice.

Reads (blueprint 07 §AI Work Companion): what the persona may see comes from its own valid
`work:read` grants (team-scoped). Counts, due labels, priorities and the temporary work state are
deterministic; nothing here ranks people or keeps permanent labels.

The conversation runs through the AI engineer's Companion graph when it is connected
(companion_turns, ADR-034). Without it, a session can be opened but messages are answered honestly as
"not connected" and nothing is stored. The left canvas changes only from validated ui_action values
(no tabs or keyword routing, CLAUDE.md).
"""

import uuid as _uuid
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import Connection, text

from app.db import transaction
from app.errors import ApiError
from app.integrations.voice import Mode, VoiceUnavailable, get_voice
from app.repositories import work
from app.services import usage
from app.services.onboarding import _persona

NOT_CONNECTED = "The work assistant isn't connected yet. Your work, shift and updates below come from the database; replies arrive with the assistant."
OPEN = ("ACTIVE", "IN_PROGRESS", "BLOCKED")
PRIORITY_RANK = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
TZ = ZoneInfo("Asia/Manila")
REPORT_AS_EVENT = {"DONE": "REPORTED_COMPLETE", "BLOCKED": "BLOCKED", "IN_PROGRESS": "COMMENTED"}
# A person's account of the work vs a recorded transition (CLAUDE.md: distinguish OBSERVED/REPORTED).
REPORTED = {"STARTED", "INVESTIGATED", "BLOCKED", "UNBLOCKED", "ESCALATED", "COMMENTED", "REPORTED_COMPLETE"}


def _context(conn: Connection, token: str | None) -> tuple[Any, _uuid.UUID, list[str]]:
    r, employee_id = _persona(conn, token)
    teams = work.read_teams(conn, r.session["organization_id"], r.session["workspace_id"], employee_id)
    if not teams:
        raise ApiError("FORBIDDEN", "Work Companion isn't available for this persona (no work access).")
    return r, employee_id, teams


def visible_to(conn: Connection, org, ws, me, teams: list[str]) -> list[dict[str, Any]]:
    """The work this persona may see (owner decision 2026-10-10). The lead of a team's shift in
    progress sees the team's tickets; everyone else sees only tickets assigned to them (their latest
    assignment, so finished work they did stays in their history; a ticket moved to someone else
    leaves their view). Unassigned tickets are the lead's to see and assign."""
    from app.services import work_commands  # imports this module

    leading = work_commands.acting_lead_teams(conn, org, ws, me, "delegation:confirm")[0]
    rows = work.visible_items(conn, org, ws, teams)
    team = {i["work_item_id"] for i in work.visible_items(conn, org, ws, leading)} if leading else set()
    # "Mine" is the latest assignment of any status: a ticket cancelled in the ticket system stays
    # with its last assignee (who may reopen it) until someone else is assigned.
    return [i for i in rows if i["work_item_id"] in team or i["assignee_id"] == me or (not i["assignee_id"] and i["last_holder_id"] == me)]


def _span(minutes: float) -> str:
    m = int(abs(minutes))
    if m < 60:
        return f"{max(m, 1)} min"
    h, rest = divmod(m, 60)
    if h < 24:
        return f"{h} h" if rest < 15 else f"{h} h {rest} min"
    return f"{h // 24} d"


def due_label(item: dict[str, Any], now: datetime) -> str:
    due = item.get("due_at") or item.get("sla_due_at")
    if not due or item["status"] not in OPEN:
        return ""
    minutes = (due - now).total_seconds() / 60
    return f"Overdue by {_span(minutes)}" if minutes < 0 else f"Due in {_span(minutes)}"


def _historical(item: dict[str, Any]) -> bool:
    return item["status"] in ("COMPLETED", "CANCELLED", "CLOSED") or (item.get("metadata") or {}).get("historical_only") is True


# What a report says, in the app's three words. Reports come from the Companion's report form
# (DONE / IN_PROGRESS / BLOCKED) or from the AI engine (ADR-034), which writes its own status words
# (COMPLETED, RESOLVED, ACTIVE) and blocker reports with no status.
SAID_DONE = ("DONE", "COMPLETED", "RESOLVED")


def said(report: dict[str, Any]) -> str:
    status = (report.get("reported_status") or "").strip().upper()
    if status in SAID_DONE:
        return "DONE"
    if status == "BLOCKED" or (not status and report.get("update_type") == "BLOCKER"):
        return "BLOCKED"
    return "IN_PROGRESS"


def _awaiting_done(report: dict[str, Any] | None) -> bool:
    """The employee said "done" but the ticket system hasn't confirmed it yet (ADR-033)."""
    return bool(report and said(report) == "DONE" and report["source_sync_status"] == "AWAITING_SOURCE")


def item_dto(item: dict[str, Any], now: datetime, report: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "work_item_id": str(item["work_item_id"]),
        "external_id": item.get("external_id") or "",
        "work_item_type": item["work_item_type"],
        "title": item["title"],
        "description": item.get("description") or "",
        "priority": "HIGH" if item["priority"] == "CRITICAL" else item["priority"],
        "status": item["status"],
        "due_label": due_label(item, now),
        "assignee_id": str(item["assignee_id"]) if item.get("assignee_id") else None,
        "assignment_source": item.get("assignment_source"),
        "revision": item["revision"],
        "historical": _historical(item),
        # The latest thing someone reported about it in the Companion; never the ticket's status.
        "report": {"reported_status": said(report), "sync_status": report["source_sync_status"], "employee_id": str(report["employee_id"]), "reported_label": _when(report["reported_at"], now, TZ)} if report else None,
    }


def _when(ts: datetime, now: datetime, tz: ZoneInfo) -> str:
    minutes = (now - ts).total_seconds() / 60
    if 0 <= minutes < 24 * 60:
        return f"{_span(minutes)} ago"
    return ts.astimezone(tz).strftime("%d %b %Y")


def event_dto(e: dict[str, Any], now: datetime, tz: ZoneInfo) -> dict[str, Any]:
    out = {
        "work_event_id": str(e["work_event_id"]),
        "work_item_id": str(e["work_item_id"]),
        "employee_id": str(e["employee_id"]),
        "event_type": e["event_type"],
        "description": e.get("description") or "",
        "evidence_type": "REPORTED" if e["event_type"] in REPORTED else "OBSERVED",
        "observed_label": _when(e["observed_at"], now, tz),
        "source": "TICKET_SYSTEM" if (e.get("event_data") or {}).get("source") == "TICKET_SYSTEM" else "RECORD",
    }
    return out


def report_event_dto(rep: dict[str, Any], now: datetime, tz: ZoneInfo) -> dict[str, Any]:
    """An employee's Companion report, shown in the updates next to the ticket system's changes."""
    return {
        "work_event_id": str(rep["reported_update_id"]),
        "work_item_id": str(rep["work_item_id"]),
        "employee_id": str(rep["employee_id"]),
        "event_type": REPORT_AS_EVENT[said(rep)],
        "description": rep["description"] or "",
        "evidence_type": "REPORTED",
        "observed_label": _when(rep["reported_at"], now, tz),
        "source": "COMPANION",
        "sync_status": rep["source_sync_status"],
    }


def _sorted_open(items: list[dict[str, Any]], reports: dict[Any, dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Open work by priority and due time; items reported done but not yet confirmed by the ticket
    system go last (still open, so still reminded, at lower priority)."""
    far = datetime.max.replace(tzinfo=UTC)
    reports = reports or {}
    return sorted(
        (i for i in items if i["status"] in OPEN and not _historical(i)),
        key=lambda i: (_awaiting_done(reports.get(i["work_item_id"])), PRIORITY_RANK.get(i["priority"], 9), i.get("due_at") or far),
    )


def dashboard(conn: Connection, token: str | None) -> dict[str, Any]:
    from app.services import work_commands  # imports this module

    r, employee_id, teams = _context(conn, token)
    org, ws = r.session["organization_id"], r.session["workspace_id"]
    now = datetime.now(UTC)
    items = visible_to(conn, org, ws, employee_id, teams)
    reports = work.latest_reports(conn, org, ws, [i["work_item_id"] for i in items])
    open_items = _sorted_open(items, reports)
    blocked = sum(1 for i in open_items if i["status"] == "BLOCKED")
    overdue = sum(1 for i in open_items if (i.get("due_at") or i.get("sla_due_at")) and (i.get("due_at") or i.get("sla_due_at")) < now)
    # Temporary, explainable state of the work (never a label on the person).
    state = "BLOCKED" if blocked else "NEEDS_FOCUS" if overdue else "HIGH_WORKLOAD" if len(open_items) >= 6 else "ON_TRACK"
    shift = work.current_shift(conn, org, ws, employee_id)
    shift_label = None
    if shift:
        # Relative, so a demo's moved schedule never shows odd clock times.
        if shift["scheduled_start_at"] <= now:
            shift_label = f"{shift['name']} shift · ends in {_span((shift['scheduled_end_at'] - now).total_seconds() / 60)}"
        else:
            shift_label = f"Next: {shift['name']} shift · starts in {_span((shift['scheduled_start_at'] - now).total_seconds() / 60)}"
    return {
        "active_count": len(open_items),
        "blocked_count": blocked,
        "overdue_count": overdue,
        "work_state": state,
        "shift_label": shift_label,
        "incoming_continuity": None,  # published handovers arrive with the Shift Handover module
        "priorities": [
            " · ".join(x for x in (i.get("external_id"), i["title"], "reported done, waiting for the ticket system" if _awaiting_done(reports.get(i["work_item_id"])) else due_label(i, now)) if x)
            for i in open_items[:3]
        ],
        "awaiting_sync_count": sum(1 for i in open_items if _awaiting_done(reports.get(i["work_item_id"]))),
        "needs_review_count": sum(1 for r in reports.values() if r["source_sync_status"] == "NEEDS_REVIEW"),
        # Lead actions (assigning) belong to the lead of the shift in progress, which changes with the clock.
        "can_delegate": (leading := bool(work_commands.acting_lead_teams(conn, org, ws, employee_id, "delegation:confirm")[0])),
        # What the lists cover: the team (lead of the shift in progress) or only this person's tickets.
        "scope": "TEAM" if leading else "OWN",
        # The shift lead sees how many of the team's open tickets nobody holds (ADR-035).
        **({"unassigned_count": sum(1 for i in open_items if not i["assignee_id"])} if leading else {}),
        "system_name": work.system_name(conn, r.session["scenario_id"]),
        # Screens compare it to re-read when someone else changed the team's work (e.g. a reassignment).
        "changes_token": work.changes_token(conn, org, ws),
    }


def items(conn: Connection, token: str | None) -> list[dict[str, Any]]:
    r, me, teams = _context(conn, token)
    now = datetime.now(UTC)
    org, ws = r.session["organization_id"], r.session["workspace_id"]
    rows = visible_to(conn, org, ws, me, teams)
    reports = work.latest_reports(conn, org, ws, [i["work_item_id"] for i in rows])
    open_first = _sorted_open(rows, reports) + sorted((i for i in rows if i["status"] not in OPEN or _historical(i)), key=lambda i: i["title"])
    return [item_dto(i, now, reports.get(i["work_item_id"])) for i in open_first]


def events(conn: Connection, token: str | None) -> list[dict[str, Any]]:
    r, employee_id, teams = _context(conn, token)
    org, ws = r.session["organization_id"], r.session["workspace_id"]
    ids = [i["work_item_id"] for i in visible_to(conn, org, ws, employee_id, teams)]
    shift = work.current_shift(conn, org, ws, employee_id)
    tz = ZoneInfo((shift or {}).get("timezone") or "Asia/Manila")
    now = datetime.now(UTC)
    merged = [(e["observed_at"], event_dto(e, now, tz)) for e in work.events_for(conn, org, ws, ids)]
    merged += [(rep["reported_at"], report_event_dto(rep, now, tz)) for rep in work.reports_for(conn, org, ws, ids)]
    return [dto for _, dto in sorted(merged, key=lambda x: x[0], reverse=True)][:50]


# ---------------------------------------------------------------- conversation shell
def _session_view(conn: Connection, s: dict[str, Any]) -> dict[str, Any]:
    """The saved conversation; without the AI engine, an honest "not connected" (nothing is answered)."""
    from app.services import companion_turns

    if companion_turns.engine() is not None:
        return companion_turns.view(conn, s)
    return {
        "work_session_id": str(s["work_session_id"]),
        "revision": s["revision"],
        "transcript": [],
        "canvas": {"view": "BRIEFING"},
        "script_prompts": [],
        "assistant": {"status": "unavailable", "message": NOT_CONNECTED},
    }


def start_session(conn: Connection, token: str | None) -> dict[str, Any]:
    """Opens (or resumes) this persona's work session; the opening brief comes from the AI engine."""
    r, employee_id, _ = _context(conn, token)
    org, ws = r.session["organization_id"], r.session["workspace_id"]
    work.lock_employee_sessions(conn, org, ws, employee_id)  # two page loads never open two sessions
    from app.services import assignment

    # ADR-035: open tickets nobody holds go to members on the shift in progress, by competency.
    assignment.auto_assign(conn, org, ws, work.read_teams(conn, org, ws, employee_id), _uuid.uuid4())
    s = work.open_work_session(conn, org, ws, employee_id)
    if not s:
        shift = work.current_shift(conn, org, ws, employee_id)
        s = work.create_work_session(conn, org, ws, employee_id, shift["shift_instance_id"] if shift else None)
    return _session_view(conn, s)


def _owned(conn: Connection, token: str | None, work_session_id: str) -> tuple[Any, dict[str, Any]]:
    r, employee_id, _ = _context(conn, token)
    try:
        sid = _uuid.UUID(work_session_id)
    except ValueError:
        raise ApiError("MALFORMED_INPUT", "Unknown work session.") from None
    s = work.work_session_for(conn, r.session["organization_id"], r.session["workspace_id"], sid, employee_id)
    if not s:
        raise ApiError("NOT_FOUND", "This work session isn't yours or no longer exists.")
    return r, s


def get_session(conn: Connection, token: str | None, work_session_id: str) -> dict[str, Any]:
    return _session_view(conn, _owned(conn, token, work_session_id)[1])


def send_message(conn: Connection, token: str | None, work_session_id: str) -> dict[str, Any]:
    _owned(conn, token, work_session_id)
    raise ApiError("CAPABILITY_UNAVAILABLE", "Not sent: the work assistant isn't connected yet. Your message is still in the box.")


def listen_grant(token: str | None, work_session_id: str, mode: Mode) -> dict[str, Any]:
    """Voice input for the Companion: the same transport and caps as onboarding (ADR-027/029)."""
    with transaction() as conn:
        conn.execute(text("SET TRANSACTION READ ONLY"))
        r, s = _owned(conn, token, work_session_id)
        if s["status"] != "ACTIVE":
            raise ApiError("GUARD_FAILED", "Open the work session again before using voice.")
    if not get_voice().available:
        raise ApiError("CAPABILITY_UNAVAILABLE", "Voice isn't configured on this server. Type your message instead.")
    with transaction() as conn:
        tier = usage.charge(conn, "VOICE_LISTEN", s["workspace_id"], r.session)
    try:
        return asdict(get_voice(paid=tier == "EVALUATOR").listen_grant(mode))
    except VoiceUnavailable as e:
        raise ApiError("DEPENDENCY_UNAVAILABLE" if e.retryable else "CAPABILITY_UNAVAILABLE", e.message, retryable=e.retryable) from None
