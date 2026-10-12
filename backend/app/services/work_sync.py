"""Employee reports vs the ticket system (ADR-033).

Two states are kept apart on purpose:
- What an employee *says* in the Work Companion ("done", "blocked", a progress note) is a report in
  `work_item_reported_updates`. It never changes the ticket.
- The ticket's real status comes only from the company's ticket system. In the demo that system is
  simulated inside WorkWeave (`/ticket-system`); its changes are recorded as OBSERVED work events.

A report waits (AWAITING_SOURCE) until the ticket system shows the same status (MATCHED). If the
ticket system closes the ticket some other way, the report NEEDS_REVIEW. A newer report from the same
assignee SUPERSEDES an older waiting one. Nobody validates tickets: leads assign and monitor.
"""

import uuid as _uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Connection

from app.errors import ApiError
from app.repositories import commands, work
from app.services.companion import OPEN, TZ, _when, due_label, item_dto, said, visible_to
from app.services.onboarding import _persona
from app.services.work_commands import _check_revision, _command, _id, acting_lead_teams

CLOSED = ("COMPLETED", "CLOSED", "CANCELLED")
# Which ticket statuses confirm what the employee reported.
MATCHES = {"DONE": ("COMPLETED", "CLOSED"), "IN_PROGRESS": ("IN_PROGRESS",), "BLOCKED": ("BLOCKED",)}
TOOL_STATUSES = ("IN_PROGRESS", "BLOCKED", "COMPLETED", "CANCELLED")


def report_dto(rep: dict[str, Any], now: datetime) -> dict[str, Any]:
    return {
        "reported_update_id": str(rep["reported_update_id"]),
        "work_item_id": str(rep["work_item_id"]),
        "employee_id": str(rep["employee_id"]),
        "reported_status": said(rep),
        "description": rep["description"] or "",
        "sync_status": rep["source_sync_status"],
        "reported_label": _when(rep["reported_at"], now, TZ),
    }


def _lead_now(conn: Connection, org, ws, teams: list[str]) -> list[_uuid.UUID]:
    leads = []
    for t in teams:
        s = work.shift_in_progress(conn, org, ws, t)
        if s and s["shift_lead_employee_id"]:
            leads.append(s["shift_lead_employee_id"])
    return leads


def _reconcile(conn: Connection, org, ws, item: dict[str, Any], status: str, request_id: _uuid.UUID, teams: list[str]) -> None:
    """Match waiting reports against the ticket system's new status (same transaction)."""
    for rep in work.awaiting_reports(conn, org, ws, item["work_item_id"]):
        if status in MATCHES[said(rep)]:
            work.set_report_sync(conn, rep, "MATCHED")
        elif status in CLOSED:
            # Closed differently from what was reported (e.g. said blocked, or cancelled after "done").
            work.set_report_sync(conn, rep, "NEEDS_REVIEW")
            for who in {rep["employee_id"], *_lead_now(conn, org, ws, teams)}:
                work.outbox(conn, org, ws, request_id, who, "work_item", item["work_item_id"], item["revision"], "work.report_needs_review", {"work_item_id": str(item["work_item_id"]), "external_id": item["external_id"]})


# ---------------------------------------------------------------- Companion: an employee's report
def report(conn: Connection, token: str | None, work_item_id: str, reported_status: str, description: str, key: str, expected_revision: int | None, request_id: _uuid.UUID) -> dict[str, Any]:
    wid = _id(work_item_id, "work item")
    payload = {"work_item_id": work_item_id, "reported_status": reported_status, "description": description, "expected_revision": expected_revision}

    def run(r: Any, me: _uuid.UUID) -> tuple[dict[str, Any], int]:
        org, ws = r.session["organization_id"], r.session["workspace_id"]
        teams = work.teams_with(conn, org, ws, me, "work:report")
        if not teams:
            raise ApiError("FORBIDDEN", "This persona can't report on work.")
        if not any(i["work_item_id"] == wid for i in visible_to(conn, org, ws, me, work.read_teams(conn, org, ws, me))):
            raise ApiError("NOT_FOUND", "That work item isn't available to you.")
        item = work.lock_item(conn, org, ws, wid)
        if item["status"] not in OPEN:
            raise ApiError("GUARD_FAILED", "The ticket system already shows this item as closed.")
        assignment = work.active_assignment(conn, org, ws, wid, me)
        if not assignment:
            raise ApiError("FORBIDDEN", "Only the member assigned to this item can report on it.")
        _check_revision(item["revision"], expected_revision, "work item")
        if not description.strip():
            raise ApiError("MALFORMED_INPUT", "Say what you did or saw.")
        session = work.open_work_session(conn, org, ws, me)
        work.supersede_awaiting(conn, org, ws, assignment["assignment_id"])
        rep = work.add_report(conn, org, ws, assignment, session["work_session_id"] if session else None, reported_status, description.strip(), item["status"])
        if item["status"] in MATCHES[reported_status]:
            rep = work.set_report_sync(conn, rep, "MATCHED")  # the ticket system already agrees
        if reported_status == "DONE" and rep["source_sync_status"] == "AWAITING_SOURCE":
            for lead in _lead_now(conn, org, ws, teams):
                if lead != me:  # informational: leads monitor, they don't validate
                    work.outbox(conn, org, ws, request_id, lead, "work_item", wid, item["revision"], "work.reported_done", {"work_item_id": str(wid), "external_id": item["external_id"]})
        commands.audit(conn, org, ws, me, f"work_report.{reported_status.lower()}", "work_item_reported_update", rep["reported_update_id"], rep["revision"], request_id)
        return report_dto(rep, datetime.now(UTC)), item["revision"]

    return _command(conn, token, "work.report", key, payload, run)


# ---------------------------------------------------------------- the (simulated) ticket system
def _tool_event_dto(e: dict[str, Any], now: datetime) -> dict[str, Any]:
    data = e.get("event_data") or {}
    return {
        "work_event_id": str(e["work_event_id"]),
        "employee_id": str(e["employee_id"]),
        "event_type": e["event_type"],
        "from_status": data.get("from"),
        "to_status": data.get("to"),
        "note": e.get("description") or "",
        "observed_label": _when(e["observed_at"], now, TZ),
    }


def ticket_system(conn: Connection, token: str | None) -> dict[str, Any]:
    r, me = _persona(conn, token)
    org, ws = r.session["organization_id"], r.session["workspace_id"]
    teams = work.read_teams(conn, org, ws, me)
    if not teams:
        raise ApiError("FORBIDDEN", "This persona has no access to the team's tickets.")
    now = datetime.now(UTC)
    items = visible_to(conn, org, ws, me, teams)
    ids = [i["work_item_id"] for i in items]
    history: dict[Any, list[dict[str, Any]]] = {}
    for e in work.events_for(conn, org, ws, ids, limit=200):
        if (e.get("event_data") or {}).get("source") == "TICKET_SYSTEM":
            history.setdefault(e["work_item_id"], []).append(_tool_event_dto(e, now))
    can_report = bool(work.teams_with(conn, org, ws, me, "work:report"))
    reports = work.latest_reports(conn, org, ws, ids)
    out = []
    for i in sorted(items, key=lambda x: (x["status"] in CLOSED, x.get("external_id") or "")):
        a = work.latest_assignment(conn, org, ws, i["work_item_id"])
        # The assignee of an open ticket, or the last assignee of a closed one (who may reopen it).
        mine = bool(a and a["employee_id"] == me and (a["status"] not in ("COMPLETED", "CANCELLED") or i["status"] in CLOSED))
        mine = mine and not (i.get("metadata") or {}).get("historical_only")  # past records stay as they were (docs/32)
        out.append({**item_dto(i, now, reports.get(i["work_item_id"])), "due_label": due_label(i, now), "can_update": can_report and mine, "history": history.get(i["work_item_id"], [])})
    return {"system_name": work.system_name(conn, r.session["scenario_id"]), "items": out}


def update_ticket(conn: Connection, token: str | None, work_item_id: str, status: str, note: str, key: str, expected_revision: int | None, request_id: _uuid.UUID) -> dict[str, Any]:
    """A status change made *in the ticket system* by the item's assignee. This is the real status."""
    wid = _id(work_item_id, "ticket")
    payload = {"work_item_id": work_item_id, "status": status, "note": note, "expected_revision": expected_revision}

    def run(r: Any, me: _uuid.UUID) -> tuple[dict[str, Any], int]:
        org, ws = r.session["organization_id"], r.session["workspace_id"]
        teams = work.teams_with(conn, org, ws, me, "work:report")
        if not teams or not any(i["work_item_id"] == wid for i in visible_to(conn, org, ws, me, work.read_teams(conn, org, ws, me))):
            raise ApiError("NOT_FOUND", "That ticket isn't available to you.")
        item = work.lock_item(conn, org, ws, wid)
        if (item.get("metadata") or {}).get("historical_only"):
            raise ApiError("GUARD_FAILED", "This is a historical record; it can't be reopened or changed.")
        a = work.latest_assignment(conn, org, ws, wid)
        if not a or a["employee_id"] != me:
            raise ApiError("FORBIDDEN", "Only the ticket's assignee can change it in the ticket system.")
        _check_revision(item["revision"], expected_revision, "ticket")
        before = item["status"]
        if before == status:
            raise ApiError("GUARD_FAILED", "The ticket already has that status.")
        if before in CLOSED and status != "IN_PROGRESS":
            raise ApiError("GUARD_FAILED", "Reopen the ticket first.")
        if before not in CLOSED and a["status"] in ("COMPLETED", "CANCELLED"):
            raise ApiError("FORBIDDEN", "Only the ticket's assignee can change it in the ticket system.")
        item = work.set_item_status(conn, item, status)
        reopened = before in CLOSED
        event_type = "REOPENED" if reopened else "COMPLETED" if status == "COMPLETED" else "STATUS_CHANGED"
        shift = work.current_shift(conn, org, ws, me)
        text_ = note.strip() or f"Status changed to {status.replace('_', ' ').lower()} in the ticket system."
        ev = work.add_event(conn, org, ws, wid, me, shift["shift_instance_id"] if shift else None, event_type, text_, {"source": "TICKET_SYSTEM", "from": before, "to": status})
        # The assignment follows the ticket system's status.
        if status == "COMPLETED":
            work.set_assignment_status(conn, a, "COMPLETED")
        elif status == "CANCELLED":
            work.set_assignment_status(conn, a, "CANCELLED")
        elif reopened or a["status"] in ("ASSIGNED", "ACCEPTED"):
            work.set_assignment_status(conn, a, "IN_PROGRESS")
        _reconcile(conn, org, ws, item, status, request_id, teams)
        from app.services import handover  # imports work_commands, which imports this module's peers

        # Linked Shift Handover items follow the ticket system too (completion cycle, acknowledgement).
        handover.on_ticket_change(conn, org, ws, wid, before, status, me, shift["shift_instance_id"] if shift else None, ev["work_event_id"], request_id)
        commands.audit(conn, org, ws, me, f"ticket_system.{event_type.lower()}", "work_item", wid, item["revision"], request_id)
        latest = work.latest_reports(conn, org, ws, [wid]).get(wid)
        return {**item_dto({**item, "assignee_id": a["employee_id"]}, datetime.now(UTC), latest), "history_event": _tool_event_dto(ev, datetime.now(UTC))}, item["revision"]

    return _command(conn, token, "ticket_system.update", key, payload, run)


def can_lead(conn: Connection, org, ws, me) -> bool:
    return bool(acting_lead_teams(conn, org, ws, me, "delegation:confirm")[0])
