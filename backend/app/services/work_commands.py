"""Work Companion commands: member reports, lead validation, delegation proposals, knowledge notes.

Every command commits its change, audit event, command receipt and notification outbox rows in one
transaction (CLAUDE.md). A retried command (same idempotency key and payload) returns the committed
result; the same key with a different payload is refused.

Rules (blueprint 07/12, ADR-032):
- Lead actions belong to the lead of the team's shift in progress (by schedule), who must also hold
  the grant: other shift leads of the same team can't act during someone else's shift.
- Nobody validates tickets: reports and the ticket system's status are matched in work_sync (ADR-033).
- A delegation proposal creates no assignments until that lead (delegation:confirm) confirms it.
  Confirmation rechecks work status, existing assignments, candidates and availability; a changed
  input needs a new review. Competency gaps are shown, not hidden, and the lead decides.
- Knowledge notes are private drafts until their owner submits one for review.
"""

import uuid as _uuid
from datetime import UTC, datetime
from typing import Any, Callable
from zoneinfo import ZoneInfo

from sqlalchemy import Connection

from app.errors import ApiError
from app.repositories import commands, work
from app.services.companion import OPEN
from app.services.onboarding import _persona

TZ = ZoneInfo("Asia/Manila")


def _id(value: str, what: str) -> _uuid.UUID:
    try:
        return _uuid.UUID(value)
    except ValueError:
        raise ApiError("NOT_FOUND", f"Unknown {what}.") from None


def _command(conn: Connection, token: str | None, command: str, key: str, payload: dict[str, Any], run: Callable[[Any, _uuid.UUID], tuple[dict[str, Any], int]]) -> dict[str, Any]:
    """Runs `run(session, employee_id)` once per idempotency key; it returns (response, revision)."""
    r, employee_id = _persona(conn, token)
    org, ws = r.session["organization_id"], r.session["workspace_id"]
    prior = commands.find_receipt(conn, org, ws, employee_id, command, key)
    if prior:
        if prior["payload_hash"] != commands.payload_hash(payload):
            raise ApiError("MALFORMED_INPUT", "This request ID was already used for a different request.")
        return prior["response"]
    response, revision = run(r, employee_id)
    commands.record_receipt(conn, org, ws, employee_id, command, key, commands.payload_hash(payload), response, revision)
    return response


def acting_lead_teams(conn: Connection, org, ws, me, action: str) -> tuple[list[str], list[dict[str, Any]]]:
    """(teams where `me` holds `action` and leads the shift in progress, the other teams' running shifts)."""
    mine, others = [], []
    for team in work.teams_with(conn, org, ws, me, action):
        shift = work.shift_in_progress(conn, org, ws, team)
        if shift and shift["shift_lead_employee_id"] == me:
            mine.append(team)
        elif shift:
            others.append(shift)
    return mine, others


def _lead_of_shift_now(conn: Connection, org, ws, me, action: str, doing: str) -> list[str]:
    if not work.teams_with(conn, org, ws, me, action):
        raise ApiError("FORBIDDEN", f"Only a shift lead can {doing}.")
    mine, others = acting_lead_teams(conn, org, ws, me, action)
    if mine:
        return mine
    if others:
        s = others[0]
        raise ApiError("FORBIDDEN", f"Only {s['lead_name'] or 'the shift lead'}, who leads the {s['name']} shift in progress, can {doing}.")
    raise ApiError("GUARD_FAILED", f"No shift is in progress for your team, so nobody can {doing} right now.")


def _check_revision(current: int, expected: int | None, what: str) -> None:
    if expected is not None and expected != current:
        raise ApiError("REVISION_CONFLICT", f"The {what} changed since you opened it. Reload to see the latest version.")


# ---------------------------------------------------------------- delegation proposals
def _lead_teams(conn: Connection, org, ws, me) -> list[str]:
    return _lead_of_shift_now(conn, org, ws, me, "delegation:confirm", "review delegation proposals")


def _proposal_dto(conn: Connection, p: dict[str, Any]) -> dict[str, Any]:
    org, ws = p["organization_id"], p["workspace_id"]
    items = []
    for it in work.proposal_items(conn, org, ws, p["delegation_proposal_id"]):
        who = it["final_employee_id"] or it["recommended_employee_id"]
        have = work.validated_competencies(conn, org, ws, who)
        evidence, gaps = [], []
        for req in work.requirements(conn, org, ws, it["work_item_id"]):
            if req["competency_id"] in have:
                evidence.append(f"Validated evidence: {req['name']} ({have[req['competency_id']].replace('_', ' ').lower()})")
            else:
                gaps.append(f"no validated evidence for {req['name']}")
        availability = work.availability_now(conn, org, ws, who)
        if availability == "AVAILABLE":
            evidence.append("Declared available now")
        else:
            gaps.append("marked unavailable now" if availability == "UNAVAILABLE" else "availability not declared")
        items.append(
            {
                "proposal_item_id": str(it["proposal_item_id"]),
                "work_item_id": str(it["work_item_id"]),
                "recommended_employee_id": str(it["recommended_employee_id"]),
                "final_employee_id": str(it["final_employee_id"]) if it["final_employee_id"] else None,
                "recommendation_reason": it["recommendation_reason"],
                "evidence": evidence,
                "uncertainty": ("For the current selection: " + "; ".join(gaps) + ".") if gaps else None,
            }
        )
    synthetic = any((it.get("match_data") or {}).get("synthetic") for it in work.proposal_items(conn, org, ws, p["delegation_proposal_id"]))
    engine = (p.get("context_revisions") or {}).get("origin") == "AI_ENGINE"
    out = {"delegation_proposal_id": str(p["delegation_proposal_id"]), "status": p["status"], "revision": p["revision"], "origin": "AI_ENGINE" if engine else "SYNTHETIC_SEED" if synthetic else "MANUAL", "items": items}
    if p["status"] in ("PROPOSED", "EDITED") and items and all(work.active_assignment(conn, org, ws, _uuid.UUID(i["work_item_id"])) for i in items) and not _same_shift(p):
        out["overtaken"] = True  # every ticket in it already has someone (e.g. assigned automatically, ADR-035)
    if _same_shift(p):
        out["candidate_ids"] = [str(e) for e in _eligible_for(conn, p)]  # only teammates on the lead's shift
    return out


def _same_shift(p: dict[str, Any]) -> bool:
    return bool((p.get("context_revisions") or {}).get("same_shift") and p.get("shift_instance_id"))


def _eligible_for(conn: Connection, p: dict[str, Any]) -> list[_uuid.UUID]:
    """Who may receive this proposal's work. A proposal the AI engine prepared for a shift lead moves
    work between the people on that shift, the lead included (ADR-034)."""
    org, ws = p["organization_id"], p["workspace_id"]
    eligible = work.eligible_members(conn, org, ws, p["team_id"])
    if not _same_shift(p):
        return eligible
    on_shift = set(work.shift_members(conn, org, ws, p["shift_instance_id"]))
    return [e for e in eligible if e in on_shift or e == p["created_by"]]


def list_proposals(conn: Connection, token: str | None) -> list[dict[str, Any]]:
    r, me = _persona(conn, token)
    org, ws = r.session["organization_id"], r.session["workspace_id"]
    return [_proposal_dto(conn, p) for p in work.proposals_for(conn, org, ws, _lead_teams(conn, org, ws, me))]


def _scoped_proposal(conn: Connection, org, ws, me, proposal_id: str, lock: bool = False) -> dict[str, Any]:
    p = work.proposal(conn, org, ws, _id(proposal_id, "proposal"), lock)
    if not p or str(p["team_id"]) not in _lead_teams(conn, org, ws, me):
        raise ApiError("NOT_FOUND", "That delegation proposal isn't available to you.")
    return p


def get_proposal(conn: Connection, token: str | None, proposal_id: str) -> dict[str, Any]:
    r, me = _persona(conn, token)
    return _proposal_dto(conn, _scoped_proposal(conn, r.session["organization_id"], r.session["workspace_id"], me, proposal_id))


def _editable(p: dict[str, Any], expected_revision: int | None) -> None:
    if p["status"] not in ("PROPOSED", "EDITED"):
        raise ApiError("GUARD_FAILED", f"This proposal is already {p['status'].lower()}.")
    _check_revision(p["revision"], expected_revision, "proposal")


def edit_proposal(conn: Connection, token: str | None, proposal_id: str, work_item_id: str, final_employee_id: str, key: str, expected_revision: int | None, request_id: _uuid.UUID) -> dict[str, Any]:
    payload = {"proposal_id": proposal_id, "work_item_id": work_item_id, "final_employee_id": final_employee_id, "expected_revision": expected_revision}

    def run(r: Any, me: _uuid.UUID) -> tuple[dict[str, Any], int]:
        org, ws = r.session["organization_id"], r.session["workspace_id"]
        p = _scoped_proposal(conn, org, ws, me, proposal_id, lock=True)
        _editable(p, expected_revision)
        item = next((i for i in work.proposal_items(conn, org, ws, p["delegation_proposal_id"]) if str(i["work_item_id"]) == work_item_id), None)
        if not item:
            raise ApiError("NOT_FOUND", "That item isn't part of this proposal.")
        final = _id(final_employee_id, "team member")
        if final not in _eligible_for(conn, p):
            raise ApiError("GUARD_FAILED", "That person can't receive this team's work.")
        # The original recommendation stays; only the final selection changes.
        work.edit_proposal_item(conn, org, ws, item["proposal_item_id"], final)
        p = work.set_proposal(conn, p, "EDITED")
        commands.audit(conn, org, ws, me, "delegation_proposal.edited", "delegation_proposal", p["delegation_proposal_id"], p["revision"], request_id)
        return _proposal_dto(conn, p), p["revision"]

    return _command(conn, token, "delegation.edit", key, payload, run)


def confirm_proposal(conn: Connection, token: str | None, proposal_id: str, key: str, expected_revision: int | None, request_id: _uuid.UUID) -> dict[str, Any]:
    payload = {"proposal_id": proposal_id, "expected_revision": expected_revision}

    def run(r: Any, me: _uuid.UUID) -> tuple[dict[str, Any], int]:
        org, ws = r.session["organization_id"], r.session["workspace_id"]
        p = _scoped_proposal(conn, org, ws, me, proposal_id, lock=True)
        _editable(p, expected_revision)
        p = confirm_locked(conn, org, ws, me, p, request_id)
        return _proposal_dto(conn, p), p["revision"]

    return _command(conn, token, "delegation.confirm", key, payload, run)


def confirm_locked(conn: Connection, org, ws, me, p: dict[str, Any], request_id: _uuid.UUID) -> dict[str, Any]:
    """Confirms a proposal the caller already scoped to `me` (the lead of the shift in progress) and
    locked: from the Confirm button, or the lead's "confirm" in the chat (ADR-034). Rechecks every
    item, then assigns them all at once. The lead's own tickets are handed over; a same-shift
    proposal may also move a ticket from whoever on that shift holds it; they are told it was moved."""
    eligible = _eligible_for(conn, p)
    on_shift = set(work.shift_members(conn, org, ws, p["shift_instance_id"])) if _same_shift(p) else set()
    planned, handed_over = [], []
    for it in work.proposal_items(conn, org, ws, p["delegation_proposal_id"]):
        who = it["final_employee_id"] or it["recommended_employee_id"]
        label = it["external_id"] or it["title"]
        work.lock_item(conn, org, ws, it["work_item_id"])
        if it["work_status"] not in OPEN:
            raise ApiError("GUARD_FAILED", f"{label} is no longer open. Review the proposal again.")
        current = work.active_assignment(conn, org, ws, it["work_item_id"])
        if current and current["employee_id"] == who:
            raise ApiError("GUARD_FAILED", f"{label} is already with the person selected. Choose someone else.")
        if current and (current["employee_id"] == me or (_same_shift(p) and current["employee_id"] in on_shift)):
            handed_over.append(current)  # the lead's own ticket, or (same-shift) a teammate's: moved on confirm
        elif current:
            raise ApiError("GUARD_FAILED", f"{label} was assigned since this proposal was made. Review the proposal again.")
        if who not in eligible:
            raise ApiError("GUARD_FAILED", f"The person selected for {label} can't receive this team's work any more.")
        if work.availability_now(conn, org, ws, who) == "UNAVAILABLE":
            raise ApiError("GUARD_FAILED", f"The person selected for {label} is marked unavailable now. Choose someone else.")
        planned.append((it, who))
    # The whole proposal commits at once, with the work revisions it was confirmed against.
    context = {**(p.get("context_revisions") or {}), **{str(it["work_item_id"]): it["work_revision"] for it, _ in planned}}
    p = work.set_proposal(conn, p, "CONFIRMED", confirmed_by=me, context=context)
    for a in handed_over:
        work.set_assignment_status(conn, a, "CANCELLED")
        commands.audit(conn, org, ws, me, "work_item_assignment.handed_over", "work_item_assignment", a["assignment_id"], a["revision"] + 1, request_id)
        if a["employee_id"] != me:
            work.outbox(conn, org, ws, request_id, a["employee_id"], "work_item_assignment", a["assignment_id"], a["revision"] + 1, "work.unassigned", {"work_item_id": str(a["work_item_id"])})
    for it, who in planned:
        # Why this person, as it was when the lead confirmed (ADR-035): what "why" answers from.
        have = work.validated_competencies(conn, org, ws, who)
        match = {
            "rule": "delegation-proposal",
            "delegation_proposal_id": str(p["delegation_proposal_id"]),
            "proposal_origin": (p.get("context_revisions") or {}).get("origin") or "SEEDED_OR_MANUAL",
            "recommendation_reason": it["recommendation_reason"],
            "lead_changed_recommendation": bool(it["final_employee_id"] and it["final_employee_id"] != it["recommended_employee_id"]),
            "requirements": [{"competency_id": str(r["competency_id"]), "name": r["name"], "required_level": r["required_level"], "met": r["competency_id"] in have, "evidence": have.get(r["competency_id"])} for r in work.requirements(conn, org, ws, it["work_item_id"])],
            "availability": work.availability_now(conn, org, ws, who),
        }
        aid = work.assign(conn, org, ws, it["work_item_id"], who, me, it["proposal_item_id"], match)
        commands.audit(conn, org, ws, me, "work_item_assignment.created", "work_item_assignment", aid, 1, request_id)
        work.outbox(conn, org, ws, request_id, who, "work_item_assignment", aid, 1, "work.assigned", {"work_item_id": str(it["work_item_id"]), "external_id": it["external_id"]})
    commands.audit(conn, org, ws, me, "delegation_proposal.confirmed", "delegation_proposal", p["delegation_proposal_id"], p["revision"], request_id)
    return p


def reject_proposal(conn: Connection, token: str | None, proposal_id: str, reason: str, key: str, expected_revision: int | None, request_id: _uuid.UUID) -> dict[str, Any]:
    payload = {"proposal_id": proposal_id, "reason": reason, "expected_revision": expected_revision}

    def run(r: Any, me: _uuid.UUID) -> tuple[dict[str, Any], int]:
        org, ws = r.session["organization_id"], r.session["workspace_id"]
        p = _scoped_proposal(conn, org, ws, me, proposal_id, lock=True)
        _editable(p, expected_revision)
        if not reason.strip():
            raise ApiError("MALFORMED_INPUT", "Say why the proposal is rejected.")
        p = work.set_proposal(conn, p, "REJECTED")
        commands.audit(conn, org, ws, me, "delegation_proposal.rejected", "delegation_proposal", p["delegation_proposal_id"], p["revision"], request_id)
        return _proposal_dto(conn, p), p["revision"]

    return _command(conn, token, "delegation.reject", key, payload, run)


# ---------------------------------------------------------------- knowledge notes
def _draft_dto(d: dict[str, Any]) -> dict[str, Any]:
    audience = (d["requested_audience"] or ["PRIVATE"])[0]
    return {
        "draft_id": str(d["draft_id"]),
        "owner_employee_id": str(d["owner_employee_id"]),
        "content": d["content"],
        "requested_audience": audience,
        "status": d["status"],
        "evidence_type": "REPORTED",  # a person's own account until reviewed
        "revision": d["revision"],
        **({"review_comment": d["review_comment"]} if d.get("review_comment") else {}),
    }


def my_drafts(conn: Connection, token: str | None) -> list[dict[str, Any]]:
    r, me = _persona(conn, token)
    return [_draft_dto(d) for d in work.drafts_of(conn, r.session["organization_id"], r.session["workspace_id"], me)]


def create_draft(conn: Connection, token: str | None, content: str, audience: str, key: str, request_id: _uuid.UUID) -> dict[str, Any]:
    payload = {"content": content, "audience": audience}

    def run(r: Any, me: _uuid.UUID) -> tuple[dict[str, Any], int]:
        org, ws = r.session["organization_id"], r.session["workspace_id"]
        if not content.strip():
            raise ApiError("MALFORMED_INPUT", "Write the explanation first.")
        d = work.create_draft(conn, org, ws, me, content.strip(), audience)
        commands.audit(conn, org, ws, me, "memory_draft.created", "memory_draft", d["draft_id"], d["revision"], request_id)
        return _draft_dto(d), d["revision"]

    return _command(conn, token, "memory_draft.create", key, payload, run)


def _own_draft(conn: Connection, org, ws, me, draft_id: str) -> dict[str, Any]:
    d = work.draft(conn, org, ws, _id(draft_id, "note"), me, lock=True)
    if not d:
        raise ApiError("NOT_FOUND", "That note isn't yours or no longer exists.")
    return d


def submit_draft(conn: Connection, token: str | None, draft_id: str, key: str, expected_revision: int | None, request_id: _uuid.UUID) -> dict[str, Any]:
    payload = {"draft_id": draft_id, "expected_revision": expected_revision}

    def run(r: Any, me: _uuid.UUID) -> tuple[dict[str, Any], int]:
        org, ws = r.session["organization_id"], r.session["workspace_id"]
        d = _own_draft(conn, org, ws, me, draft_id)
        if d["status"] != "DRAFT":
            raise ApiError("GUARD_FAILED", "Only a draft can be submitted for review.")
        _check_revision(d["revision"], expected_revision, "note")
        if (d["requested_audience"] or ["PRIVATE"])[0] == "PRIVATE":
            raise ApiError("GUARD_FAILED", "A private note stays with you; choose a wider audience to submit it.")
        d = work.submit_draft(conn, d)
        teams = work.read_teams(conn, org, ws, me)
        for reviewer in work.holders(conn, org, ws, "knowledge:review", teams):
            if reviewer != me:
                work.outbox(conn, org, ws, request_id, reviewer, "memory_draft", d["draft_id"], d["revision"], "knowledge.note_awaiting_review", {})
        commands.audit(conn, org, ws, me, "memory_draft.submitted", "memory_draft", d["draft_id"], d["revision"], request_id)
        return _draft_dto(d), d["revision"]

    return _command(conn, token, "memory_draft.submit", key, payload, run)


def delete_draft(conn: Connection, token: str | None, draft_id: str, key: str, request_id: _uuid.UUID) -> dict[str, Any]:
    payload = {"draft_id": draft_id}

    def run(r: Any, me: _uuid.UUID) -> tuple[dict[str, Any], int]:
        org, ws = r.session["organization_id"], r.session["workspace_id"]
        d = _own_draft(conn, org, ws, me, draft_id)
        if d["status"] != "DRAFT":
            raise ApiError("GUARD_FAILED", "A submitted note can't be deleted while it's under review.")
        work.delete_draft(conn, d)
        commands.audit(conn, org, ws, me, "memory_draft.deleted", "memory_draft", d["draft_id"], d["revision"], request_id)
        return {"deleted": True}, d["revision"]

    return _command(conn, token, "memory_draft.delete", key, payload, run)


# ---------------------------------------------------------------- delegation the AI engine proposed (ADR-034)
def propose_from_engine(conn: Connection, org, ws, me, delegation: dict[str, Any], request_id: _uuid.UUID) -> tuple[dict[str, Any] | None, list[str]]:
    """Turns the AI engine's suggested hand-overs into a delegation proposal for the shift lead to
    confirm. Everything is rechecked here: `me` holds delegation:confirm and leads the shift in
    progress the engine named; each teammate is on that shift and may receive the team's work; each
    ticket is open, visible to the team, and unassigned or the lead's own. Returns the proposal
    (None when nothing passed) and what was left out, in plain words."""
    try:
        sid = _uuid.UUID(str(delegation.get("shift_instance_id")))
    except ValueError:
        return None, ["the shift couldn't be identified"]
    teams, _ = acting_lead_teams(conn, org, ws, me, "delegation:confirm")
    team = next((t for t in teams if (work.shift_in_progress(conn, org, ws, t) or {}).get("shift_instance_id") == sid), None)
    if team is None:
        return None, ["only the lead of the shift in progress can assign work"]
    on_shift = set(work.shift_members(conn, org, ws, sid))
    members = {e for e in work.eligible_members(conn, org, ws, team) if e in on_shift or e == me}  # the lead may take work too
    visible = {i["work_item_id"]: i for i in work.visible_items(conn, org, ws, [team])}
    valid, dropped, seen = [], [], set()
    for pick in delegation.get("proposal") or []:
        try:
            wid, who = _uuid.UUID(str(pick.get("work_item_id"))), _uuid.UUID(str(pick.get("employee_id")))
        except ValueError:
            dropped.append("a suggestion with an unknown ticket or person")
            continue
        item = visible.get(wid)
        label = (item.get("external_id") or item["title"]) if item else "a ticket"
        current = work.active_assignment(conn, org, ws, wid) if item else None
        if wid in seen:
            dropped.append(f"{label} (suggested twice; the first suggestion is kept)")
        elif not item or item["status"] not in OPEN:
            dropped.append(f"{label} (not an open ticket of your team)")
        elif current and current["employee_id"] != me and current["employee_id"] not in on_shift:
            dropped.append(f"{label} (held by someone who isn't on your shift)")
        elif current and current["employee_id"] == who:
            dropped.append(f"{label} (already with that person)")
        elif who not in members:
            dropped.append(f"{label} (the person suggested isn't on your shift)")
        else:
            seen.add(wid)
            valid.append((wid, who, (pick.get("reason") or "").strip()[:500] or "Suggested by the work assistant."))
    if not valid:
        return None, dropped
    shift = work.shift_in_progress(conn, org, ws, team)
    p = work.create_proposal(conn, org, ws, team, shift["shift_instance_id"], me, {"origin": "AI_ENGINE", "same_shift": True})
    for wid, who, reason in valid:
        work.add_proposal_item(conn, org, ws, p["delegation_proposal_id"], wid, who, reason, {"source": "AI_ENGINE"})
    commands.audit(conn, org, ws, me, "delegation_proposal.proposed", "delegation_proposal", p["delegation_proposal_id"], p["revision"], request_id)
    return p, dropped
