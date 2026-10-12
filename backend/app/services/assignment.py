"""Who works on which ticket: automatic competency-based assignment, the shift lead's override, and
why a ticket went to a person (ADR-035).

Automatic assignment (owner decision 2026-10-10, replacing "the lead confirms first" for the initial
assignment): an open ticket of a team with no assignee goes to a member on the team's shift in
progress, chosen by a deterministic rule (blueprint 12's requirements/evidence/availability matcher;
no AI). The rule, `competency-v1`, picks among members holding the team's work:report grant who are
on that shift, aren't its lead and aren't marked unavailable now:
  1. fewest of the ticket's required competencies without validated evidence (validated evidence
     counts as meeting a level-1 requirement; evidence strength isn't recorded yet);
  2. then the fewest open tickets;
  3. then name, so the same data always gives the same result.
The facts used are saved on the assignment (match_data), so "why" answers from what was true then.
Competency gaps are kept, never hidden.

The shift lead of the shift in progress can override any open ticket of the team to another person
on that shift, themself included: the current assignment is cancelled and a MANUAL one created, both audited and both
people notified.

Why: the assignee may see the reasons for their own ticket; the lead of the shift in progress may
see them for the team's tickets, including how the teammates compared. Nobody else may.
"""

import uuid as _uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Connection

from app.config import get_settings
from app.errors import ApiError
from app.repositories import commands, work
from app.services.companion import OPEN, TZ, _historical, _when
from app.services.onboarding import _persona
from app.services.work_commands import _check_revision, _command, _id, acting_lead_teams

RULE = "competency-v1"
PRIORITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}


def _requirements(conn: Connection, org, ws, work_item_id, employee_id) -> list[dict[str, Any]]:
    have = work.validated_competencies(conn, org, ws, employee_id)
    return [
        {"competency_id": str(r["competency_id"]), "name": r["name"], "required_level": r["required_level"], "met": r["competency_id"] in have, "evidence": have.get(r["competency_id"])}
        for r in work.requirements(conn, org, ws, work_item_id)
    ]


def _shift_members(conn: Connection, org, ws, team, include_lead: bool = False) -> tuple[dict[str, Any] | None, list[_uuid.UUID]]:
    """Who may hold the team's work on its shift in progress. Automatic assignment leaves the lead out
    (leads assign and monitor); a lead choosing by hand may take a ticket themself."""
    shift = work.shift_in_progress(conn, org, ws, team)
    if not shift:
        return None, []
    on_shift = set(work.shift_members(conn, org, ws, shift["shift_instance_id"]))
    lead = shift["shift_lead_employee_id"]
    members = [e for e in work.eligible_members(conn, org, ws, team) if (e in on_shift and e != lead) or (include_lead and e == lead)]
    return shift, members


# ---------------------------------------------------------------- automatic assignment
def auto_assign(conn: Connection, org, ws, teams: list[str], request_id: _uuid.UUID) -> list[dict[str, Any]]:
    """Assigns the teams' open, unassigned tickets (caller holds the transaction). Returns the new assignments."""
    if not get_settings().auto_assign_work or not teams:
        return []
    work.lock_workspace_assignment(conn, org, ws)
    made = []
    for team in teams:
        shift, members = _shift_members(conn, org, ws, team)
        if not shift:
            continue
        members = [m for m in members if work.availability_now(conn, org, ws, m) != "UNAVAILABLE"]
        if not members:
            continue
        waiting = [i for i in work.visible_items(conn, org, ws, [team]) if i["status"] in OPEN and not _historical(i) and not i["assignee_id"]]
        far = datetime.max.replace(tzinfo=UTC)
        waiting.sort(key=lambda i: (PRIORITY_ORDER.get(i["priority"], 9), i.get("due_at") or far, i.get("external_id") or ""))
        load = work.open_work_counts(conn, org, ws, members)
        names = work.employee_names(conn, org, ws, members)
        for item in waiting:
            work.lock_item(conn, org, ws, item["work_item_id"])
            if work.active_assignment(conn, org, ws, item["work_item_id"]):
                continue  # assigned meanwhile
            scored = []
            for m in members:
                reqs = _requirements(conn, org, ws, item["work_item_id"], m)
                scored.append({"employee_id": m, "gaps": sum(1 for r in reqs if not r["met"]), "open_work": load[m], "availability": work.availability_now(conn, org, ws, m), "requirements": reqs})
            scored.sort(key=lambda c: (c["gaps"], c["open_work"], names.get(c["employee_id"], "")))
            best = scored[0]
            match = {
                "rule": RULE,
                "shift_instance_id": str(shift["shift_instance_id"]),
                "requirements": best["requirements"],
                "availability": best["availability"],
                "open_work_before": best["open_work"],
                "compared": [{"employee_id": str(c["employee_id"]), "gaps": c["gaps"], "open_work": c["open_work"], "availability": c["availability"]} for c in scored],
            }
            a = work.assign_with(conn, org, ws, item["work_item_id"], best["employee_id"], None, "AUTOMATIC", match)
            load[best["employee_id"]] += 1
            commands.audit(conn, org, ws, None, "work_item_assignment.automatic", "work_item_assignment", a["assignment_id"], a["revision"], request_id)
            work.outbox(conn, org, ws, request_id, best["employee_id"], "work_item_assignment", a["assignment_id"], a["revision"], "work.assigned", {"work_item_id": str(item["work_item_id"]), "external_id": item["external_id"]})
            made.append(a)
    return made


# ---------------------------------------------------------------- the shift lead's override
def _lead_team_for(conn: Connection, org, ws, me, wid) -> str:
    teams, others = acting_lead_teams(conn, org, ws, me, "delegation:confirm")
    for t in teams:
        if any(i["work_item_id"] == wid for i in work.visible_items(conn, org, ws, [t])):
            return t
    if others:
        s = others[0]
        raise ApiError("FORBIDDEN", f"Only {s['lead_name'] or 'the shift lead'}, who leads the {s['name']} shift in progress, can change who works on this ticket.")
    raise ApiError("FORBIDDEN", "Only the lead of the shift in progress can change who works on a ticket.")


def reassign(conn: Connection, token: str | None, work_item_id: str, employee_id: str, key: str, expected_revision: int | None, request_id: _uuid.UUID) -> dict[str, Any]:
    wid = _id(work_item_id, "ticket")
    payload = {"work_item_id": work_item_id, "employee_id": employee_id, "expected_revision": expected_revision}

    def run(r: Any, me: _uuid.UUID) -> tuple[dict[str, Any], int]:
        org, ws = r.session["organization_id"], r.session["workspace_id"]
        team = _lead_team_for(conn, org, ws, me, wid)
        item = work.lock_item(conn, org, ws, wid)
        _check_revision(item["revision"], expected_revision, "ticket")
        if item["status"] not in OPEN:
            raise ApiError("GUARD_FAILED", "This ticket is closed in the ticket system.")
        who = _id(employee_id, "team member")
        _, members = _shift_members(conn, org, ws, team, include_lead=True)
        if who not in members:
            raise ApiError("GUARD_FAILED", "Choose someone on your shift.")
        current = work.active_assignment(conn, org, ws, wid)
        if current and current["employee_id"] == who:
            raise ApiError("GUARD_FAILED", "This ticket is already assigned to that person.")
        match = {"rule": "lead-override", "requirements": _requirements(conn, org, ws, wid, who), "availability": work.availability_now(conn, org, ws, who)}
        if current:
            match |= {"replaced_assignment_id": str(current["assignment_id"]), "replaced_employee_id": str(current["employee_id"]), "replaced_source": current["assignment_source"]}
            work.set_assignment_status(conn, current, "CANCELLED")
            commands.audit(conn, org, ws, me, "work_item_assignment.overridden", "work_item_assignment", current["assignment_id"], current["revision"] + 1, request_id)
            if current["employee_id"] != me:
                work.outbox(conn, org, ws, request_id, current["employee_id"], "work_item_assignment", current["assignment_id"], current["revision"] + 1, "work.unassigned", {"work_item_id": str(wid), "external_id": item["external_id"]})
        a = work.assign_with(conn, org, ws, wid, who, me, "MANUAL", match)
        commands.audit(conn, org, ws, me, "work_item_assignment.created", "work_item_assignment", a["assignment_id"], a["revision"], request_id)
        work.outbox(conn, org, ws, request_id, who, "work_item_assignment", a["assignment_id"], a["revision"], "work.assigned", {"work_item_id": str(wid), "external_id": item["external_id"]})
        return explanation_for(conn, org, ws, me, wid, as_lead=True), item["revision"]

    return _command(conn, token, "work.reassign", key, payload, run)


def candidates(conn: Connection, token: str | None, work_item_id: str) -> list[dict[str, Any]]:
    """Members the lead may assign this ticket to, with their fit for its requirements."""
    r, me = _persona(conn, token)
    org, ws = r.session["organization_id"], r.session["workspace_id"]
    wid = _id(work_item_id, "ticket")
    team = _lead_team_for(conn, org, ws, me, wid)
    _, members = _shift_members(conn, org, ws, team, include_lead=True)
    load = work.open_work_counts(conn, org, ws, members)
    names = work.employee_names(conn, org, ws, members)
    out = []
    for m in members:
        reqs = _requirements(conn, org, ws, wid, m)
        out.append({"employee_id": str(m), "name": names.get(m, ""), "gaps": [x["name"] for x in reqs if not x["met"]], "open_work": load[m], "availability": work.availability_now(conn, org, ws, m)})
    return sorted(out, key=lambda c: (len(c["gaps"]), c["open_work"], c["name"]))


# ---------------------------------------------------------------- why
def _summary(source: str, by: str | None, reqs: list[dict[str, Any]], match: dict[str, Any], name: str) -> str:
    met = [x["name"] for x in reqs if x["met"]]
    gaps = [x["name"] for x in reqs if not x["met"]]
    fit = []
    if met:
        fit.append(f"validated evidence for {', '.join(met)}")
    if gaps:
        fit.append(f"no validated evidence yet for {', '.join(gaps)}")
    fit_text = "; ".join(fit) if fit else "this ticket lists no required competencies"
    if source == "AUTOMATIC":
        n = len(match.get("compared") or [])
        load = match.get("open_work_before")
        return (f"Assigned automatically to {name} by the competency rule: {fit_text}. "
                f"Of {n} member{'s' if n != 1 else ''} on the shift, {name} had the fewest gaps for this ticket"
                + (f" and {load} other open ticket{'s' if load != 1 else ''} at the time." if load is not None else "."))
    if match.get("rule") == "lead-override":
        return f"{by or 'The shift lead'} assigned it to {name}, replacing the previous assignment. {name} has {fit_text}."
    if match.get("rule") == "delegation-proposal":
        why = match.get("recommendation_reason")
        changed = " The lead chose a different person from the one recommended." if match.get("lead_changed_recommendation") else ""
        return f"{by or 'The shift lead'} confirmed a delegation proposal assigning it to {name}" + (f" (recommended because: {why})" if why else "") + f". {name} has {fit_text}.{changed}"
    return f"{(by + ' assigned it') if by else 'It was assigned'} to {name}. {name} has {fit_text}."


def explanation_for(conn: Connection, org, ws, me, wid, as_lead: bool) -> dict[str, Any]:
    a = work.active_assignment(conn, org, ws, wid) or work.latest_assignment(conn, org, ws, wid)
    if not a:
        return {"work_item_id": str(wid), "assigned": False, "summary": "This ticket isn't assigned to anyone yet."}
    match = a.get("match_data") or {}
    # The facts at assignment time when they were saved; otherwise the person's current evidence.
    reqs = match.get("requirements") if match.get("requirements") is not None else _requirements(conn, org, ws, wid, a["employee_id"])
    ids = [a["employee_id"]] + ([a["assigned_by_employee_id"]] if a["assigned_by_employee_id"] else [])
    compared = match.get("compared") or []
    if as_lead:
        ids += [_uuid.UUID(c["employee_id"]) for c in compared]
    names = work.employee_names(conn, org, ws, ids)
    name, by = names.get(a["employee_id"], "this person"), names.get(a["assigned_by_employee_id"]) if a["assigned_by_employee_id"] else None
    out: dict[str, Any] = {
        "work_item_id": str(wid),
        "assigned": True,
        "assignee_id": str(a["employee_id"]),
        "assignee_name": name,
        "source": a["assignment_source"],
        "rule": match.get("rule"),
        "assigned_by_name": by,
        "assigned_label": _when(a["assigned_at"], datetime.now(UTC), TZ),
        "requirements": [{"name": x["name"], "required_level": x.get("required_level"), "met": x["met"], "evidence": x.get("evidence")} for x in reqs],
        "availability": match.get("availability"),
        "summary": _summary(a["assignment_source"], by, reqs, match, name),
    }
    if as_lead and compared:
        # Only the lead sees how teammates compared (their own evidence stays private otherwise).
        out["compared"] = [{"name": names.get(_uuid.UUID(c["employee_id"]), ""), "gaps": c["gaps"], "open_work": c["open_work"], "availability": c["availability"]} for c in compared]
    return out


def explain(conn: Connection, token: str | None, work_item_id: str) -> dict[str, Any]:
    r, me = _persona(conn, token)
    org, ws = r.session["organization_id"], r.session["workspace_id"]
    wid = _id(work_item_id, "ticket")
    a = work.active_assignment(conn, org, ws, wid) or work.latest_assignment(conn, org, ws, wid)
    if a and a["employee_id"] == me:
        return explanation_for(conn, org, ws, me, wid, as_lead=False)
    try:
        _lead_team_for(conn, org, ws, me, wid)
    except ApiError:
        raise ApiError("FORBIDDEN", "Only the person assigned and the lead of the shift in progress can see why a ticket was assigned.") from None
    return explanation_for(conn, org, ws, me, wid, as_lead=True)
