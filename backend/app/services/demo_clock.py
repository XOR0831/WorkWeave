"""Demo shift clock (owner decisions 2026-10-10, ADR-042).

An evaluator tool for a visitor's own demo run, like "Start fresh demo": any persona may move the
run to the middle of the next shift. It is never part of the real app (/app/) and never a business
action. It refuses anything that isn't a visitor run (a DEMO workspace in a visitor organization
with its run proof row), so a pack baseline can't be touched.

How: every changeable time in the run (shifts, ticket due and SLA times, assignments, availability,
cases, drafts) moves back by the same amount, which is the same as the clock advancing: tickets that
were "due in 2 h" can become overdue. Guarded history (append-only rows and approved knowledge),
record times (created_at/updated_at) and demo session, retention and usage rows keep their real
times; the database's integrity rules are never loosened for this (owner decision 2026-10-10). When the new shift has no successor in the
scenario, the same shift a day later is added (same lead and members), so the clock can keep going.

If the shift in progress hasn't published its handover, the move needs confirmation: the next
shift then receives nothing new, and only the lead of the shift in progress can publish, so that
draft stays unpublished.
"""

import uuid as _uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import Connection, text

from app.errors import ApiError
from app.repositories import commands
from app.repositories import handover as handover_repo
from app.services.onboarding import _persona
from app.services.work_commands import _command

W = "workweave"
TZ = ZoneInfo("Asia/Manila")
# Tables whose times are about the visitor's session, its retention or usage caps, not the scenario.
KEEP_REAL_TIME = ("demo_",)


def _visitor_run(conn: Connection, org, ws) -> None:
    ok = conn.execute(
        text(f"""SELECT 1 FROM {W}.workspaces w JOIN {W}.organizations o ON o.organization_id=w.organization_id
                 WHERE w.organization_id=:o AND w.workspace_id=:w AND w.kind='DEMO' AND o.company_key IS NULL
                   AND EXISTS (SELECT 1 FROM {W}.demo_visitor_runs r WHERE r.organization_id=w.organization_id AND r.workspace_id=w.workspace_id)"""),
        {"o": org, "w": ws},
    ).first()
    if not ok:
        raise ApiError("FORBIDDEN", "The shift clock only works in your own demo run.")


def _occurrences(conn: Connection, org, ws) -> list[dict[str, Any]]:
    rows = conn.execute(
        text(f"""SELECT si.*, sh.name, sh.team_id, sh.timezone, e.first_name || ' ' || e.last_name AS lead_name
                 FROM {W}.shift_instances si
                 JOIN {W}.shifts sh ON sh.organization_id=si.organization_id AND sh.workspace_id=si.workspace_id AND sh.shift_id=si.shift_id
                 LEFT JOIN {W}.employees e ON e.organization_id=si.organization_id AND e.workspace_id=si.workspace_id AND e.employee_id=si.shift_lead_employee_id
                 WHERE si.organization_id=:o AND si.workspace_id=:w AND si.status <> 'CANCELLED'
                 ORDER BY sh.team_id, si.scheduled_start_at"""),
        {"o": org, "w": ws},
    ).mappings()
    return [dict(r) for r in rows]


def _plan(conn: Connection, org, ws, now: datetime) -> dict[str, Any]:
    """The shift in progress and the next one (the team whose next shift starts first)."""
    occ = _occurrences(conn, org, ws)
    best = None
    for team in {o["team_id"] for o in occ}:
        mine = [o for o in occ if o["team_id"] == team]
        cur = next((o for o in mine if o["scheduled_start_at"] <= now < o["scheduled_end_at"]), None)
        nxt = next((o for o in mine if o["scheduled_start_at"] >= (cur["scheduled_end_at"] if cur else now)), None)
        if nxt and (best is None or nxt["scheduled_start_at"] < best["next"]["scheduled_start_at"]):
            best = {"current": cur, "next": nxt, "team": team}
    return best or {"current": None, "next": None, "team": None}


def _shift_dto(o: dict[str, Any] | None) -> dict[str, Any] | None:
    if not o:
        return None
    tz = ZoneInfo(o["timezone"] or "Asia/Manila")
    return {"shift_instance_id": str(o["shift_instance_id"]), "name": o["name"], "lead_name": o["lead_name"] or "",
            "window_label": f"{o['scheduled_start_at'].astimezone(tz):%a %H:%M}–{o['scheduled_end_at'].astimezone(tz):%H:%M}"}


def _unpublished(conn: Connection, org, ws, cur: dict[str, Any] | None) -> bool:
    if not cur:
        return False
    h = handover_repo.handover_from(conn, org, ws, cur["shift_instance_id"])
    return not h or h["status"] != "PUBLISHED"


def status(conn: Connection, token: str | None) -> dict[str, Any]:
    r, _ = _persona(conn, token)
    org, ws = r.session["organization_id"], r.session["workspace_id"]
    _visitor_run(conn, org, ws)
    p = _plan(conn, org, ws, datetime.now(UTC))
    return {"current": _shift_dto(p["current"]), "next": _shift_dto(p["next"]), "handover_unpublished": _unpublished(conn, org, ws, p["current"])}


def _ensure_successor(conn: Connection, org, ws, team, after: dict[str, Any]) -> None:
    """The scenario's last shift gets a successor: the same slot a day later (same lead, members)."""
    occ = [o for o in _occurrences(conn, org, ws) if o["team_id"] == team]
    if any(o["scheduled_start_at"] >= after["scheduled_end_at"] for o in occ):
        return
    template = next((o for o in occ if abs((o["scheduled_start_at"] + timedelta(days=1) - after["scheduled_end_at"]).total_seconds()) < 60), None)
    if not template:
        return
    new_id = _uuid.uuid4()
    conn.execute(
        text(f"""INSERT INTO {W}.shift_instances (shift_instance_id, organization_id, workspace_id, shift_id, shift_date, scheduled_start_at, scheduled_end_at, status, shift_lead_employee_id)
                 VALUES (:id, :o, :w, :s, :d, :a, :b, 'SCHEDULED', :lead)"""),
        {"id": new_id, "o": org, "w": ws, "s": template["shift_id"], "d": template["shift_date"] + timedelta(days=1), "a": template["scheduled_start_at"] + timedelta(days=1),
         "b": template["scheduled_end_at"] + timedelta(days=1), "lead": template["shift_lead_employee_id"]},
    )
    conn.execute(
        text(f"""INSERT INTO {W}.shift_instance_memberships (organization_id, workspace_id, shift_instance_id, employee_id, membership_role, availability_status)
                 SELECT organization_id, workspace_id, :id, employee_id, membership_role, availability_status FROM {W}.shift_instance_memberships
                 WHERE organization_id=:o AND workspace_id=:w AND shift_instance_id=:t"""),
        {"id": new_id, "o": org, "w": ws, "t": template["shift_instance_id"]},
    )


# Tables whose rows the database guards against edits (append-only history such as work updates,
# audit, publications, messages and receipts; approved knowledge content). They keep their real
# times (owner decision 2026-10-10): integrity rules are never loosened for the demo clock.
GUARDED = """SELECT DISTINCT cl.relname FROM pg_trigger t JOIN pg_class cl ON cl.oid=t.tgrelid JOIN pg_namespace n ON n.oid=cl.relnamespace
             JOIN pg_proc p ON p.oid=t.tgfoid
             WHERE n.nspname='workweave' AND NOT t.tgisinternal AND (t.tgtype & 16) <> 0 AND p.proname NOT LIKE 'touch%'"""


def _move_everything(conn: Connection, org, ws, delta: timedelta) -> None:
    """Every changeable timestamp and date in this run moves back by `delta`; guarded history and
    demo session rows keep their real times."""
    guarded = set(conn.execute(text(GUARDED)).scalars())
    cols = conn.execute(
        text("""SELECT c.table_name, c.column_name, c.data_type FROM information_schema.columns c
                JOIN information_schema.tables t ON t.table_schema=c.table_schema AND t.table_name=c.table_name AND t.table_type='BASE TABLE'
                WHERE c.table_schema='workweave' AND c.is_generated='NEVER' AND c.data_type IN ('timestamp with time zone', 'date')
                  AND c.column_name NOT IN ('created_at', 'updated_at')
                  AND EXISTS (SELECT 1 FROM information_schema.columns k WHERE k.table_schema=c.table_schema AND k.table_name=c.table_name AND k.column_name='workspace_id')"""),
    ).all()
    cols = [x for x in cols if x[0] not in guarded]
    by_table: dict[str, list[tuple[str, str]]] = {}
    for t, c, kind in cols:
        if t.startswith(KEEP_REAL_TIME) or t in ("workspaces", "organizations"):
            continue
        by_table.setdefault(t, []).append((c, kind))
    conn.execute(text("SET CONSTRAINTS ALL DEFERRED"))
    for t, cs in by_table.items():
        sets = ", ".join(f"{c} = {c} - CAST(:d AS interval)" if kind != "date" else f"{c} = (({c} + time '12:00') - CAST(:d AS interval))::date" for c, kind in cs)
        conn.execute(text(f"UPDATE {W}.{t} SET {sets} WHERE organization_id=:o AND workspace_id=:w"), {"o": org, "w": ws, "d": f"{int(delta.total_seconds())} seconds"})


def advance(conn: Connection, token: str | None, confirm_unpublished: bool, key: str, request_id) -> dict[str, Any]:
    def run(r: Any, me) -> tuple[dict[str, Any], int]:
        org, ws = r.session["organization_id"], r.session["workspace_id"]
        _visitor_run(conn, org, ws)
        conn.execute(text(f"SELECT 1 FROM {W}.workspaces WHERE organization_id=:o AND workspace_id=:w FOR UPDATE"), {"o": org, "w": ws})  # one move at a time
        now = datetime.now(UTC)
        p = _plan(conn, org, ws, now)
        if not p["next"]:
            raise ApiError("GUARD_FAILED", "This scenario has no later shift to move to.")
        if _unpublished(conn, org, ws, p["current"]) and not confirm_unpublished:
            raise ApiError("GUARD_FAILED", f"The {p['current']['name']} shift hasn't published its handover, so the {p['next']['name']} shift receives nothing new. Confirm to move on anyway.")
        nxt = p["next"]
        _ensure_successor(conn, org, ws, p["team"], nxt)
        middle = nxt["scheduled_start_at"] + (nxt["scheduled_end_at"] - nxt["scheduled_start_at"]) / 2
        delta = middle - now
        _move_everything(conn, org, ws, delta)
        commands.audit(conn, org, ws, me, "demo.shift_clock_advanced", "shift_instance", nxt["shift_instance_id"], 1, request_id)
        after = _plan(conn, org, ws, datetime.now(UTC))
        return {"current": _shift_dto(after["current"]), "next": _shift_dto(after["next"]), "handover_unpublished": _unpublished(conn, org, ws, after["current"]),
                "moved_hours": round(delta.total_seconds() / 3600, 1)}, 1

    return _command(conn, token, "demo.advance_shift", key, {"confirm": confirm_unpublished, "key": key}, run)
