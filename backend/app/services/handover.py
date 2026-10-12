"""Shift Handover from the database (owner decisions 2026-10-09/10; ADR-019, ADR-022, ADR-033).

Who (owner decision 2026-10-10, superseding ADR-038's member access): Shift Handover is only for
shift leads, meaning holders of the team's handover:publish grant who lead one of its shifts. The lead of
the shift in progress edits the draft for the next shift and publishes it directly; there is no
second reviewer (ADR-019). The incoming shift's lead reads it and confirms receipt. Members don't
see Shift Handover; their work still comes from the ticket system and the Work Companion.

What:
- A handover goes from the team's shift in progress to the next one. Its draft lives on the
  handover row; publishing writes an immutable publication and one entry per persistent item, and
  moves open items to the receiving shift. Published snapshots never change.
- Persistent items carry across shifts. A linked ticket's status comes only from the ticket system
  (ADR-033): when it's resolved there, the item is completed and the shift it came from is asked to
  acknowledge. Acknowledgement never blocks later shifts; a dispute only flags the item and tells
  the ticket's assignee (owner decision). Nobody "validates" completion here.
- Suggestions are the ones stored in the database (AI suggestions come with the AI engineer's
  engine); the lead accepts or ignores them. The copilot isn't connected yet and says so.
- Undo isn't offered yet; every change is audited and can be edited again.

Every command commits its change, receipt, audit and notifications together (work_commands._command).
"""

import uuid as _uuid
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import Connection

from app.errors import ApiError
from app.repositories import commands, handover as repo, work
from app.services.companion import _when
from app.services.onboarding import _persona
from app.services.work_commands import _check_revision, _command, _id

NOT_CONNECTED = "The handover companion isn't connected yet. The handover itself, its items and publications come from the database."
EVIDENCE = {"TICKET": "OBSERVED", "INCIDENT": "OBSERVED", "WORK_EVENT": "REPORTED", "EMAIL": "REPORTED", "CALENDAR": "REPORTED", "MANUAL": "REPORTED", "DOCUMENT": "OBSERVED"}
SOURCE_NAME = {"TICKET": "Ticket", "INCIDENT": "Incident", "WORK_EVENT": "Work event", "EMAIL": "Email", "CALENDAR": "Calendar", "MANUAL": "Entered by hand", "DOCUMENT": "Document"}
CLOSED_WORK = ("COMPLETED", "CLOSED", "CANCELLED")


# ---------------------------------------------------------------- context
class Ctx:
    """The persona, its team, the team's shifts, and the handover from the shift in progress."""

    def __init__(self, conn: Connection, token: str | None):
        r, me = _persona(conn, token)
        self.conn, self.session, self.me = conn, r.session, me
        self.org, self.ws = r.session["organization_id"], r.session["workspace_id"]
        teams = work.teams_with(conn, self.org, self.ws, me, "handover:publish")
        if not teams:
            raise ApiError("FORBIDDEN", "Shift Handover is for shift leads.")
        self.team = sorted(teams)[0]
        self.occurrences = repo.team_occurrences(conn, self.org, self.ws, self.team)
        running = work.shift_in_progress(conn, self.org, self.ws, self.team)
        if not running:
            raise ApiError("GUARD_FAILED", "No shift is in progress for your team, so there's no handover to prepare or receive right now.")
        ids = [o["shift_instance_id"] for o in self.occurrences]
        i = ids.index(running["shift_instance_id"])
        self.source = self.occurrences[i]
        self.target = self.occurrences[i + 1] if i + 1 < len(self.occurrences) else None
        if me not in {o["shift_lead_employee_id"] for o in self.occurrences}:
            raise ApiError("FORBIDDEN", "Shift Handover is for shift leads, and you don't lead one of these shifts.")
        self.is_lead = self.source["shift_lead_employee_id"] == me
        self.template = repo.team_template(conn, self.org, self.ws, self.team)

    def handover(self, lock: bool = False) -> dict[str, Any] | None:
        return repo.handover_from(self.conn, self.org, self.ws, self.source["shift_instance_id"], lock)

    def require_lead(self) -> None:
        if not self.is_lead:
            raise ApiError("FORBIDDEN", "Only the lead of the shift in progress can change or publish this handover. Members can't publish, and no second reviewer is involved.")


def _lead_draft(c: Ctx, handover_id: str, expected_revision: int | None) -> dict[str, Any]:
    """The lead's handover, locked, at the revision they saw. A published one becomes a new draft revision."""
    c.require_lead()
    h = c.handover(lock=True)
    if not h or str(h["handover_id"]) != handover_id:
        raise ApiError("NOT_FOUND", "That handover isn't the one for your shift in progress.")
    _check_revision(h["revision"], expected_revision, "handover")
    if h["status"] != "DRAFT":
        h = repo.update_handover(c.conn, h, status="DRAFT")
    return h


# ---------------------------------------------------------------- the view
def _window(o: dict[str, Any]) -> str:
    tz = ZoneInfo(o["timezone"] or "Asia/Manila")
    return f"{o['scheduled_start_at'].astimezone(tz):%H:%M}–{o['scheduled_end_at'].astimezone(tz):%H:%M}"


def _occ_status(o: dict[str, Any], now: datetime) -> str:
    if o["scheduled_end_at"] <= now:
        return "COMPLETED"
    return "ACTIVE" if o["scheduled_start_at"] <= now else "SCHEDULED"


def _occurrence(o: dict[str, Any], now: datetime) -> dict[str, Any]:
    return {
        "shift_instance_id": str(o["shift_instance_id"]),
        "name": o["name"],
        "window_label": _window(o),
        "lead_employee_id": str(o["shift_lead_employee_id"]) if o["shift_lead_employee_id"] else "",
        "member_ids": [str(m) for m in o["member_ids"]],
        "status": _occ_status(o, now),
    }


def _work_status(it: dict[str, Any]) -> str:
    """A linked ticket's real status comes from the ticket system (ADR-033); the item's own status
    records the handover lifecycle (e.g. CLOSED once the originating shift acknowledged)."""
    if it["work_status"] == "CLOSED" or not it.get("ticket_status"):
        return it["work_status"]
    return it["ticket_status"]


def _item_dto(it: dict[str, Any], n: int) -> dict[str, Any]:
    src = it.get("source_type") or "MANUAL"
    return {
        "handover_item_id": str(it["handover_item_id"]),
        "display_id": it.get("external_id") or f"HI-{n}",
        **({"work_item_id": str(it["work_item_id"])} if it["work_item_id"] else {}),
        "title": it["title"],
        "description": it["description"] or "",
        "originating_shift_instance_id": str(it["originating_shift_instance_id"]),
        "work_status": _work_status(it),
        "acknowledgement_status": it["acknowledgement_status"],
        **({"completion_cycle_id": str(it["completion_cycle_id"])} if it["completion_cycle_id"] else {}),
        "section_id": str(it["section_id"]) if it["section_id"] else "",
        "evidence_type": EVIDENCE.get(src, "UNKNOWN"),
        "source_label": " · ".join(x for x in (SOURCE_NAME.get(src, src.title()), it.get("source_external_id")) if x),
    }


EVENT_LABEL = {
    "CREATED": "Added to the handover",
    "UPDATED": "Updated in the draft",
    "CONFIRMED_COMPLETE": "Resolved in the ticket system",
    "ACKNOWLEDGED": "Completion acknowledged by the originating shift; item closed",
    "DISPUTED": "Completion disputed",
    "REOPENED": "Reopened in the ticket system",
    "CLOSED": "Closed",
}


def _event_label(e: dict[str, Any]) -> str:
    d = e["details"] or {}
    if d.get("publication_number"):
        return f"Included in publication #{d['publication_number']}"
    label = EVENT_LABEL.get(e["event_type"], e["event_type"].replace("_", " ").capitalize())
    return f"{label}: {d['comment']}" if d.get("comment") else label


def _suggestion_dto(conn: Connection, c: Ctx, sg: dict[str, Any], items_by_id: dict[Any, dict[str, Any]], n_of: dict[Any, int]) -> dict[str, Any]:
    data = sg["suggested_data"] or {}
    it = items_by_id.get(sg["handover_item_id"])
    label = _item_dto(it, n_of[it["handover_item_id"]])["display_id"] if it else None
    src = sg.get("source_type") or "MANUAL"
    proposed = data.get("title") or ""
    if sg["suggestion_type"] in ("STALE_INFORMATION", "STATUS_UPDATE") and data.get("work_event_id"):
        ev = repo._one(conn, "SELECT description FROM workweave.work_events WHERE organization_id=:o AND workspace_id=:w AND work_event_id=CAST(:e AS uuid)",
                       {"o": c.org, "w": c.ws, "e": data["work_event_id"]})
        proposed = (ev or {}).get("description") or proposed
    if sg["suggestion_type"] == "MISSING_ITEM" and data.get("time_confirmation") == "PENDING":
        proposed = f"{proposed} (time to be confirmed)"
    if data.get("origin") == "AI_ENGINE":  # docs/31: proposed by the handover graph, with its evidence
        refs = sg.get("source_refs") or []
        return {
            "suggestion_id": str(sg["suggestion_id"]),
            "suggestion_type": sg["suggestion_type"],
            **({"handover_item_id": str(sg["handover_item_id"])} if sg["handover_item_id"] else {}),
            "title": data.get("title") or sg["suggestion_type"].replace("_", " ").capitalize(),
            "reason": sg["reason"] or "",
            **({"before": it["description"]} if it else {}),
            "proposed": data.get("proposed_note") or "",
            "source_label": " · ".join(x.get("label") for x in refs[:2] if x.get("label")) or "Handover records",
            "evidence_type": data.get("evidence_type") or "INFERRED",
            "status": sg["status"],
            "origin": "AI_ENGINE",
        }
    title = {
        "MISSING_ITEM": f"Missing from the draft: {data.get('title') or 'an item'}",
        "STALE_INFORMATION": f"{label or 'An item'} may be out of date",
        "STATUS_UPDATE": f"{label or 'An item'} has a status update",
        "SCHEDULE_CHANGE": f"{label or 'An item'} has a schedule change",
        "POSSIBLE_DUPLICATE": f"{label or 'An item'} may be a duplicate",
    }[sg["suggestion_type"]]
    return {
        "suggestion_id": str(sg["suggestion_id"]),
        "suggestion_type": sg["suggestion_type"],
        **({"handover_item_id": str(sg["handover_item_id"])} if sg["handover_item_id"] else {}),
        "title": title,
        "reason": sg["reason"] or "",
        **({"before": it["description"]} if it else {}),
        "proposed": proposed or (sg["reason"] or ""),
        "source_label": " · ".join(x for x in (SOURCE_NAME.get(src, src.title()), sg.get("source_external_id")) if x),
        "evidence_type": EVIDENCE.get(src, "UNKNOWN"),
        "status": sg["status"],
    }


def view(c: Ctx, last_change_section_id: str | None = None) -> dict[str, Any]:
    from app.services import handover_ai  # handover_ai uses this module

    conn, now = c.conn, datetime.now(UTC)
    h = c.handover()
    version = repo.template_version(conn, c.org, c.ws, h["template_version_id"]) if h else (repo.latest_version(conn, c.org, c.ws, c.template["template_id"]) if c.template else None)
    secs = repo.sections(conn, c.org, c.ws, version["template_version_id"]) if version else []
    shift_ids = [o["shift_instance_id"] for o in c.occurrences]
    names = {o["shift_instance_id"]: o["name"] for o in c.occurrences}
    raw_items = repo.items(conn, c.org, c.ws, shift_ids)
    n_of = {it["handover_item_id"]: n for n, it in enumerate(raw_items, start=1)}
    items_by_id = {it["handover_item_id"]: it for it in raw_items}
    handovers = repo.team_handovers(conn, c.org, c.ws, shift_ids)
    pubs = repo.publications(conn, c.org, c.ws, [x["handover_id"] for x in handovers])
    by_handover = {x["handover_id"]: x for x in handovers}
    pub_ids = [p["publication_id"] for p in pubs]
    ents, rcpts = repo.entries(conn, c.org, c.ws, pub_ids), repo.receipts(conn, c.org, c.ws, pub_ids)
    tz = ZoneInfo(c.source["timezone"] or "Asia/Manila")
    publications = []
    for p in pubs:
        src = by_handover[p["handover_id"]]
        v = repo.template_version(conn, c.org, c.ws, p["template_version_id"])
        publications.append({
            "publication_id": str(p["publication_id"]),
            "publication_number": p["publication_number"],
            "source_shift_instance_id": str(src["source_shift_instance_id"]),
            "target_shift_instance_id": str(src["target_shift_instance_id"]) if src["target_shift_instance_id"] else "",
            "template_version": str(v["version"]) if v else "",
            "sections": [{"section_id": s["section_id"], "content": s.get("content") or "", **({"declaration": s["declaration"], "declaration_reason": s.get("declaration_reason") or ""} if s.get("declaration") else {})} for s in p["section_content"] or []],
            "entries": [
                {"handover_item_id": str(e["handover_item_id"]), "display_id": _item_dto(items_by_id[e["handover_item_id"]], n_of[e["handover_item_id"]])["display_id"] if e["handover_item_id"] in items_by_id else "",
                 "title": items_by_id[e["handover_item_id"]]["title"] if e["handover_item_id"] in items_by_id else "", "section_id": str(e["section_id"]) if e["section_id"] else "",
                 "snapshot_work_status": e["snapshot_work_status"], "snapshot_acknowledgement_status": e["snapshot_acknowledgement_status"], "snapshot_description": e["snapshot_description"] or ""}
                for e in ents if e["publication_id"] == p["publication_id"]
            ],
            "published_by": str(p["published_by"]),
            "published_label": f"{_when(p['published_at'], now, tz)}, {names.get(src['source_shift_instance_id'], '')} shift",
            "receipts": [{"employee_id": str(x["recipient_employee_id"]), "received_label": _when(x["received_at"], now, tz)} for x in rcpts if x["publication_id"] == p["publication_id"]],
        })
    cyc = repo.cycles(conn, c.org, c.ws, list(items_by_id))
    events = repo.item_events(conn, c.org, c.ws, list(items_by_id))
    draft = (h["draft_sections"] if h else []) or []
    return {
        "handover_id": str(h["handover_id"]) if h else "",
        "revision": h["revision"] if h else 1,
        "status": h["status"] if h else "DRAFT",
        "template_name": c.template["name"] if c.template else "",
        "template_version": str(version["version"]) if version else "",
        "sections": [{"section_id": str(s["section_id"]), "name": s["name"], "order_index": s["order_index"], "is_required": s["is_required"]} for s in secs],
        # Lead-only: drafts and suggestions aren't visible to members (15-handover-user-flow).
        "draft_sections": [
            {"section_id": d["section_id"], "content": d.get("content") or "", **({"declaration": d["declaration"], "declaration_reason": d.get("declaration_reason") or ""} if d.get("declaration") else {})}
            for d in draft
        ] if c.is_lead else [],
        "source": _occurrence(c.source, now),
        "target": _occurrence(c.target, now) if c.target else _occurrence(c.source, now),
        "occurrences": [_occurrence(o, now) for o in c.occurrences],
        "items": [_item_dto(it, n_of[it["handover_item_id"]]) for it in raw_items],
        "suggestions": [_suggestion_dto(conn, c, sg, items_by_id, n_of) for sg in repo.suggestions(conn, c.org, c.ws, h["handover_id"])] if c.is_lead and h else [],
        "publications": publications,
        "cycles": [
            {"completion_cycle_id": str(x["completion_cycle_id"]), "handover_item_id": str(x["handover_item_id"]), "completed_in_shift_instance_id": str(x["completed_in_shift_instance_id"]),
             "requested_from_shift_instance_id": str(x["requested_from_shift_instance_id"]) if x["requested_from_shift_instance_id"] else "",
             "status": x["ack_status"] or ("ACKNOWLEDGED" if x["status"] == "ACKNOWLEDGED" else "PENDING"), **({"comment": x["comment"]} if x["comment"] else {})}
            for x in cyc if x["requested_from_shift_instance_id"]
        ],
        "item_events": [{"event_id": str(e["event_id"]), "handover_item_id": str(e["handover_item_id"]), "label": _event_label(e), "shift_name": names.get(e["shift_instance_id"], "")} for e in events],
        **({"last_change_section_id": last_change_section_id} if last_change_section_id and c.is_lead else {}),
        "can_configure_template": c.is_lead,
        "script_prompts": [],
        # docs/31: the lead's own copilot conversation; the gap check and drafts are for the outgoing lead.
        "copilot": handover_ai.messages(conn, c, h),
        "copilot_available": handover_ai.available(),
        "can_check": c.is_lead and handover_ai.available() and bool(h),
    }


def workspace(conn: Connection, token: str | None) -> dict[str, Any]:
    """Opens the handover for the shift in progress. When its lead opens it first, the draft is created
    from the team's template (POST, so the page never writes on a plain read)."""
    c = Ctx(conn, token)
    if c.is_lead and c.target and not c.handover() and c.template:
        version = repo.latest_version(conn, c.org, c.ws, c.template["template_id"])
        repo.create_handover(conn, c.org, c.ws, c.source["shift_instance_id"], c.target["shift_instance_id"], version["template_version_id"], c.me, [])
    return view(c)


# ---------------------------------------------------------------- lead commands
def _sections(c: Ctx, h: dict[str, Any]) -> list[dict[str, Any]]:
    return repo.sections(c.conn, c.org, c.ws, h["template_version_id"])


def _touch(c: Ctx, h: dict[str, Any], action: str, request_id) -> dict[str, Any]:
    h = repo.update_handover(c.conn, h, updated_at=datetime.now(UTC))
    commands.audit(c.conn, c.org, c.ws, c.me, action, "shift_handover", h["handover_id"], h["revision"], request_id)
    return h


def edit_section(conn: Connection, token: str | None, handover_id: str, section_id: str, content: str, declaration: str | None, reason: str, key: str, expected_revision: int | None, request_id) -> dict[str, Any]:
    payload = {"handover_id": handover_id, "section_id": section_id, "content": content, "declaration": declaration, "reason": reason, "expected_revision": expected_revision}

    def run(r: Any, me) -> tuple[dict[str, Any], int]:
        c = Ctx(conn, token)
        h = _lead_draft(c, handover_id, expected_revision)
        if section_id not in {str(s["section_id"]) for s in _sections(c, h)}:
            raise ApiError("NOT_FOUND", "Section not found in this template version.")
        if declaration and not reason.strip():
            raise ApiError("MALFORMED_INPUT", "Add a reason or follow-up for the declaration.")
        draft = [d for d in (h["draft_sections"] or []) if d.get("section_id") != section_id]
        entry: dict[str, Any] = {"section_id": section_id, "content": content.strip()}
        if declaration:
            entry |= {"declaration": declaration, "declaration_reason": reason.strip()}
        h = repo.update_handover(conn, h, draft_sections=draft + [entry])
        h = _touch(c, h, "shift_handover.section_edited", request_id)
        return view(c, section_id), h["revision"]

    return _command(conn, token, "handover.edit_section", key, payload, run)


def _item_shift(c: Ctx) -> Any:
    return c.source["shift_instance_id"]


def accept_suggestion(conn: Connection, token: str | None, handover_id: str, suggestion_id: str, mode: str, note: str | None, key: str, expected_revision: int | None, request_id) -> dict[str, Any]:
    payload = {"handover_id": handover_id, "suggestion_id": suggestion_id, "mode": mode, "note": note, "expected_revision": expected_revision}

    def run(r: Any, me) -> tuple[dict[str, Any], int]:
        c = Ctx(conn, token)
        h = _lead_draft(c, handover_id, expected_revision)
        sg = repo.suggestion(conn, c.org, c.ws, _id(suggestion_id, "suggestion"), lock=True)
        if not sg or sg["handover_id"] != h["handover_id"]:
            raise ApiError("NOT_FOUND", "Suggestion not found.")
        if sg["status"] != "PENDING":
            raise ApiError("GUARD_FAILED", "This suggestion has already been reviewed.")
        if mode == "VALIDATE_COMPLETION":
            raise ApiError("GUARD_FAILED", "Completion comes from the ticket system, not from the handover (ADR-033). Add it as a report instead.")
        data, text_ = sg["suggested_data"] or {}, (note or "").strip()
        secs = _sections(c, h)
        if sg["suggestion_type"] == "MISSING_ITEM" and not sg["handover_item_id"]:
            wanted = (data.get("section") or "Scheduled Activities").lower()
            sec = next((s for s in secs if s["name"].lower() == wanted), None) or next((s for s in secs if not s["is_required"]), secs[-1])
            ai = data.get("origin") == "AI_ENGINE"
            title = data.get("title") or "New item"
            item_note = text_ or (data.get("proposed_note") if ai else None) or data.get("title") or ""
            work_item = _uuid.UUID(data["work_item_id"]) if ai and data.get("work_item_id") else None
            it = repo.create_item(conn, c.org, c.ws, title, item_note, _item_shift(c), _item_shift(c), me, sec["section_id"], work_item)
            repo.link_source(conn, c.org, c.ws, sg["suggestion_id"], it["handover_item_id"])
            repo.add_item_event(conn, it, "CREATED", me, _item_shift(c), None, "ACTIVE", {"suggestion_id": str(sg["suggestion_id"])})
            changed = it
        else:
            it = repo.item(conn, c.org, c.ws, sg["handover_item_id"], lock=True)
            if not it:
                raise ApiError("NOT_FOUND", "Item not found.")
            if mode == "REPORT_ONLY":
                desc = text_ or f"{it['description'] or ''} A completion was reported; the ticket system decides when it's done.".strip()
            else:
                desc = text_ or (_suggestion_dto(conn, c, sg, {it["handover_item_id"]: it}, {it["handover_item_id"]: 1})["proposed"])
            changed = repo.update_item(conn, it, description=desc, updated_at=datetime.now(UTC))
            repo.add_item_event(conn, it, "UPDATED", me, _item_shift(c), it["work_status"], it["work_status"], {"suggestion_id": str(sg["suggestion_id"])})
        repo.review_suggestion(conn, sg, "ACCEPTED", me)
        h = _touch(c, h, "handover_suggestion.accepted", request_id)
        return view(c, str(changed["section_id"]) if changed["section_id"] else None), h["revision"]

    return _command(conn, token, "handover.accept_suggestion", key, payload, run)


def ignore_suggestion(conn: Connection, token: str | None, handover_id: str, suggestion_id: str, key: str, expected_revision: int | None, request_id) -> dict[str, Any]:
    payload = {"handover_id": handover_id, "suggestion_id": suggestion_id, "expected_revision": expected_revision}

    def run(r: Any, me) -> tuple[dict[str, Any], int]:
        c = Ctx(conn, token)
        h = _lead_draft(c, handover_id, expected_revision)
        sg = repo.suggestion(conn, c.org, c.ws, _id(suggestion_id, "suggestion"), lock=True)
        if not sg or sg["handover_id"] != h["handover_id"] or sg["status"] != "PENDING":
            raise ApiError("GUARD_FAILED", "This suggestion has already been reviewed.")
        repo.review_suggestion(conn, sg, "IGNORED", me)
        h = _touch(c, h, "handover_suggestion.ignored", request_id)
        return view(c), h["revision"]

    return _command(conn, token, "handover.ignore_suggestion", key, payload, run)


def create_template_version(conn: Connection, token: str | None, handover_id: str, rows: list[dict[str, Any]], key: str, expected_revision: int | None, request_id) -> dict[str, Any]:
    payload = {"handover_id": handover_id, "sections": rows, "expected_revision": expected_revision}

    def run(r: Any, me) -> tuple[dict[str, Any], int]:
        c = Ctx(conn, token)
        h = _lead_draft(c, handover_id, expected_revision)
        current = _sections(c, h)
        names = [(x.get("name") or "").strip() for x in rows]
        if any(not n for n in names):
            raise ApiError("MALFORMED_INPUT", "Every section needs a name.")
        if len({n.lower() for n in names}) != len(names):
            raise ApiError("MALFORMED_INPUT", "Section names must be unique.")
        kept = {x.get("section_id") for x in rows if x.get("section_id")}
        if any(str(s["section_id"]) not in kept for s in current):
            raise ApiError("GUARD_FAILED", "Existing sections can't be removed; mark them optional instead (older snapshots keep resolving their names).")
        if not any(x.get("is_required") for x in rows):
            raise ApiError("GUARD_FAILED", "Keep at least one required section.")
        version = repo.latest_version(conn, c.org, c.ws, c.template["template_id"])
        nv = repo.add_version(conn, c.org, c.ws, c.template["template_id"], version["version"] + 1)
        moved: dict[str, str] = {}
        for i, x in enumerate(rows, start=1):
            s = repo.add_section(conn, c.org, c.ws, nv["template_version_id"], names[i - 1], i, bool(x.get("is_required")))
            if x.get("section_id"):
                moved[str(x["section_id"])] = str(s["section_id"])
        # The draft and the shift's items move to the new version's sections; publications keep theirs.
        draft = [{**d, "section_id": moved.get(d["section_id"], d["section_id"])} for d in h["draft_sections"] or [] if d["section_id"] in moved]
        h = repo.update_handover(conn, h, draft_sections=draft, template_version_id=nv["template_version_id"])
        for it in repo.items(conn, c.org, c.ws, [_item_shift(c)]):
            if it["section_id"] and str(it["section_id"]) in moved:
                repo.update_item(conn, it, section_id=_uuid.UUID(moved[str(it["section_id"])]))
        h = _touch(c, h, "handover_template.version_created", request_id)
        return view(c), h["revision"]

    return _command(conn, token, "handover.template_version", key, payload, run)


def publish(conn: Connection, token: str | None, handover_id: str, key: str, expected_revision: int | None, request_id) -> dict[str, Any]:
    payload = {"handover_id": handover_id, "expected_revision": expected_revision}

    def run(r: Any, me) -> tuple[dict[str, Any], int]:
        c = Ctx(conn, token)
        c.require_lead()
        h = c.handover(lock=True)
        if not h or str(h["handover_id"]) != handover_id:
            raise ApiError("NOT_FOUND", "That handover isn't the one for your shift in progress.")
        _check_revision(h["revision"], expected_revision, "handover")
        if h["status"] == "PUBLISHED":
            raise ApiError("GUARD_FAILED", "This revision is already published. Edit the draft to publish a new version.")
        secs = _sections(c, h)
        draft = {d["section_id"]: d for d in h["draft_sections"] or []}
        own = repo.items(conn, c.org, c.ws, [_item_shift(c)])
        own = [it for it in own if it["current_owner_shift_instance_id"] == _item_shift(c) and _work_status(it) not in ("CLOSED", "CANCELLED")]
        missing = [s["name"] for s in secs if s["is_required"] and not ((draft.get(str(s["section_id"])) or {}).get("content") or (draft.get(str(s["section_id"])) or {}).get("declaration")
                                                                       or any(it["section_id"] == s["section_id"] for it in own))]
        if missing:
            raise ApiError("GUARD_FAILED", f"Required sections need content or an explicit unknown/not-applicable declaration: {', '.join(missing)}.")
        number = max([p["publication_number"] for p in repo.publications(conn, c.org, c.ws, [h["handover_id"]])] + [0]) + 1
        audience = [str(c.target["shift_lead_employee_id"])] if c.target["shift_lead_employee_id"] else []  # the incoming lead
        content = [draft[str(s["section_id"])] for s in secs if str(s["section_id"]) in draft]
        pub = repo.add_publication(conn, h, number, {"target_shift_instance_id": str(c.target["shift_instance_id"]), "audience": audience}, content, me)
        for it in own:
            repo.add_entry(conn, pub, it, _work_status(it), [str(it["work_item_id"])] if it["work_item_id"] else [])
            repo.add_item_event(conn, it, "UPDATED", me, _item_shift(c), None, None, {"publication_number": number})
            repo.update_item(conn, it, current_owner_shift_instance_id=c.target["shift_instance_id"])  # the next shift carries it
        h = repo.update_handover(conn, h, status="PUBLISHED", published_by_employee_id=me, published_at=pub["published_at"], current_publication_id=pub["publication_id"])
        for who in audience:
            if who != str(me):
                work.outbox(conn, c.org, c.ws, request_id, _uuid.UUID(who), "handover_publication", pub["publication_id"], 1, "handover.published", {"publication_number": number})
        commands.audit(conn, c.org, c.ws, me, "shift_handover.published", "handover_publication", pub["publication_id"], h["revision"], request_id)
        return view(c), h["revision"]

    return _command(conn, token, "handover.publish", key, payload, run)


# ---------------------------------------------------------------- the receiving shift
def confirm_receipt(conn: Connection, token: str | None, publication_id: str, key: str, request_id) -> dict[str, Any]:
    payload = {"publication_id": publication_id}

    def run(r: Any, me) -> tuple[dict[str, Any], int]:
        c = Ctx(conn, token)
        pub = repo.publication(conn, c.org, c.ws, _id(publication_id, "publication"))
        src = repo.handover(conn, c.org, c.ws, pub["handover_id"]) if pub else None
        target = next((o for o in c.occurrences if src and o["shift_instance_id"] == src["target_shift_instance_id"]), None)
        if not pub or not target:
            raise ApiError("NOT_FOUND", "Publication not found.")
        if me != target["shift_lead_employee_id"]:
            raise ApiError("FORBIDDEN", "Only the receiving shift's lead confirms receipt.")
        if repo.add_receipt(conn, pub, target["shift_instance_id"], me):
            commands.audit(conn, c.org, c.ws, me, "handover_publication.received", "handover_publication", pub["publication_id"], 1, request_id)
        return view(c), 1

    return _command(conn, token, "handover.receipt", key, payload, run)


def respond(conn: Connection, token: str | None, cycle_id: str, decision: str, comment: str, key: str, request_id) -> dict[str, Any]:
    """The originating shift's lead acknowledges a completion (the item closes) or disputes it (the
    item is flagged and the ticket's assignee told; its status still comes from the ticket system)."""
    payload = {"cycle_id": cycle_id, "decision": decision, "comment": comment}

    def run(r: Any, me) -> tuple[dict[str, Any], int]:
        c = Ctx(conn, token)
        cy = repo.cycle(conn, c.org, c.ws, _id(cycle_id, "completion cycle"), lock=True)
        if not cy or not cy["acknowledgement_id"]:
            raise ApiError("NOT_FOUND", "Completion cycle not found.")
        origin = next((o for o in c.occurrences if o["shift_instance_id"] == cy["requested_from_shift_instance_id"]), None)
        if not origin or origin["shift_lead_employee_id"] != me:
            raise ApiError("FORBIDDEN", "Only the originating shift's lead can acknowledge or dispute this completion.")
        it = repo.item(conn, c.org, c.ws, cy["handover_item_id"], lock=True)
        if cy["ack_status"] != "PENDING" or it["completion_cycle_id"] != cy["completion_cycle_id"]:
            raise ApiError("GUARD_FAILED", "This response is for an older completion cycle, so it can't change the item's current state.")
        if decision == "DISPUTE" and not comment.strip():
            raise ApiError("MALFORMED_INPUT", "Explain what's disputed so the current shift can follow up.")
        if decision == "ACKNOWLEDGE":
            repo.respond_ack(conn, cy, "ACKNOWLEDGED", comment.strip() or None)
            repo.set_cycle(conn, cy, "ACKNOWLEDGED")
            repo.update_item(conn, it, acknowledgement_status="ACKNOWLEDGED", work_status="CLOSED", closed_at=datetime.now(UTC))
            repo.add_item_event(conn, it, "ACKNOWLEDGED", me, origin["shift_instance_id"], it["work_status"], "CLOSED", {}, cy["completion_cycle_id"])
        else:
            repo.respond_ack(conn, cy, "DISPUTED", comment.strip())
            repo.set_cycle(conn, cy, "DISPUTED")
            repo.update_item(conn, it, acknowledgement_status="DISPUTED")
            repo.add_item_event(conn, it, "DISPUTED", me, origin["shift_instance_id"], None, None, {"comment": comment.strip()}, cy["completion_cycle_id"])
            holder = work.latest_assignment(conn, c.org, c.ws, it["work_item_id"]) if it["work_item_id"] else None
            if holder and holder["employee_id"] != me:
                work.outbox(conn, c.org, c.ws, request_id, holder["employee_id"], "handover_item", it["handover_item_id"], it["revision"] + 1, "handover.completion_disputed", {"work_item_id": str(it["work_item_id"])})
        commands.audit(conn, c.org, c.ws, me, f"handover_acknowledgement.{decision.lower()}d", "handover_acknowledgement", cy["acknowledgement_id"], 1, request_id)
        return view(c), 1

    return _command(conn, token, "handover.acknowledge", key, payload, run)


# ---------------------------------------------------------------- from the ticket system (ADR-033)
def on_ticket_change(conn: Connection, org, ws, work_item_id, before: str, status: str, actor, shift_instance_id, event_id, request_id) -> None:
    """A ticket resolved in the ticket system completes its handover items: a new completion cycle, and
    when the item came from another shift, that shift's lead is asked to acknowledge (never blocking).
    Reopening it there reopens the item and makes the old cycle obsolete. Same transaction as the change."""
    for it in repo.items_for_work(conn, org, ws, work_item_id):
        if it["work_status"] == "CLOSED" and status not in ("IN_PROGRESS", "ACTIVE"):
            continue
        if status == "COMPLETED":
            where = shift_instance_id or it["current_owner_shift_instance_id"]
            cy = repo.open_cycle(conn, it, where, actor, event_id)
            other_shift = it["originating_shift_instance_id"] != where
            ack = "PENDING" if other_shift else "NOT_REQUIRED"
            repo.update_item(conn, it, work_status="COMPLETED", acknowledgement_status=ack, completion_cycle_id=cy["completion_cycle_id"])
            repo.add_item_event(conn, it, "CONFIRMED_COMPLETE", actor, where, it["work_status"], "COMPLETED", {"source": "TICKET_SYSTEM"}, cy["completion_cycle_id"])
            if other_shift:
                lead = repo._one(conn, "SELECT shift_lead_employee_id FROM workweave.shift_instances WHERE organization_id=:o AND workspace_id=:w AND shift_instance_id=:s",
                                 {"o": org, "w": ws, "s": it["originating_shift_instance_id"]})
                lead_id = (lead or {}).get("shift_lead_employee_id")
                repo.request_ack(conn, it, cy["completion_cycle_id"], it["originating_shift_instance_id"], lead_id)
                if lead_id:
                    work.outbox(conn, org, ws, request_id, lead_id, "handover_item", it["handover_item_id"], it["revision"] + 1, "handover.ack_requested", {"work_item_id": str(work_item_id)})
            else:
                repo.set_cycle(conn, cy, "ACKNOWLEDGED")  # nothing to acknowledge within the same shift
        elif before in CLOSED_WORK and status in ("IN_PROGRESS", "ACTIVE"):
            if it["completion_cycle_id"]:
                cy = repo.cycle(conn, org, ws, it["completion_cycle_id"], lock=True)
                if cy and cy["status"] in ("PENDING", "DISPUTED"):
                    repo.set_cycle(conn, cy, "OBSOLETE")
            repo.update_item(conn, it, work_status="IN_PROGRESS", acknowledgement_status="NOT_REQUIRED", completion_cycle_id=None, closed_at=None)
            repo.add_item_event(conn, it, "REOPENED", actor, shift_instance_id, it["work_status"], "IN_PROGRESS", {"source": "TICKET_SYSTEM"})
        elif status in ("BLOCKED", "IN_PROGRESS", "CANCELLED") and it["work_status"] != "CLOSED":
            repo.update_item(conn, it, work_status=status)
