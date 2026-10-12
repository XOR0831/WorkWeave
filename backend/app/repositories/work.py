"""Work Companion reads (blueprint 07 §AI Work Companion). Every query is scoped to one workspace."""

import json
import uuid
from typing import Any

from sqlalchemy import Connection, text

W = "workweave"


def _all(conn: Connection, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    return [dict(r._mapping) for r in conn.execute(text(sql), params)]


def teams_with(conn: Connection, org, ws, employee_id, action: str) -> list[str]:
    """Teams for which this employee holds a valid, team-scoped grant of `action`."""
    return [
        r["team_id"]
        for r in _all(
            conn,
            f"""SELECT DISTINCT resource_scope->>'team_id' AS team_id FROM {W}.permission_grants
                WHERE organization_id=:o AND workspace_id=:w AND actor_id=:e AND action=:a
                  AND valid_from <= now() AND (valid_until IS NULL OR valid_until > now()) AND resource_scope ? 'team_id'""",
            {"o": org, "w": ws, "e": employee_id, "a": action},
        )
    ]


def read_teams(conn: Connection, org, ws, employee_id) -> list[str]:
    """Teams whose work this employee may read: valid work:read grants scoped to a team."""
    return teams_with(conn, org, ws, employee_id, "work:read")


def holders(conn: Connection, org, ws, action: str, teams: list[str]) -> list[uuid.UUID]:
    """Active employees holding a valid `action` grant for any of these teams (e.g. who validates)."""
    if not teams:
        return []
    return [
        r["actor_id"]
        for r in _all(
            conn,
            f"""SELECT DISTINCT g.actor_id FROM {W}.permission_grants g
                JOIN {W}.employees e ON e.organization_id=g.organization_id AND e.workspace_id=g.workspace_id AND e.employee_id=g.actor_id
                WHERE g.organization_id=:o AND g.workspace_id=:w AND g.action=:a AND e.employment_status <> 'EXITED'
                  AND g.valid_from <= now() AND (g.valid_until IS NULL OR g.valid_until > now())
                  AND g.resource_scope->>'team_id' = ANY(:teams)""",
            {"o": org, "w": ws, "a": action, "teams": teams},
        )
    ]


# An item belongs to a team when it is assigned to, or updated by, one of the team's active members,
# or is in one of the team's delegation proposals (work items carry no team column; owner decision 2026-10-05).
VISIBLE = f"""
WITH members AS (
    SELECT employee_id FROM {W}.employee_team_memberships
    WHERE organization_id=:o AND workspace_id=:w AND is_active AND team_id = ANY(CAST(:teams AS uuid[]))
)
SELECT wi.* FROM {W}.work_items wi
WHERE wi.organization_id=:o AND wi.workspace_id=:w AND (
    EXISTS (SELECT 1 FROM {W}.work_item_assignments a WHERE a.organization_id=wi.organization_id AND a.workspace_id=wi.workspace_id
            AND a.work_item_id=wi.work_item_id AND a.employee_id IN (SELECT employee_id FROM members))
 OR EXISTS (SELECT 1 FROM {W}.work_events e WHERE e.organization_id=wi.organization_id AND e.workspace_id=wi.workspace_id
            AND e.work_item_id=wi.work_item_id AND e.employee_id IN (SELECT employee_id FROM members))
 OR EXISTS (SELECT 1 FROM {W}.delegation_proposal_items pi JOIN {W}.delegation_proposals p
              ON p.organization_id=pi.organization_id AND p.workspace_id=pi.workspace_id AND p.delegation_proposal_id=pi.delegation_proposal_id
            WHERE pi.organization_id=wi.organization_id AND pi.workspace_id=wi.workspace_id AND pi.work_item_id=wi.work_item_id
              AND p.team_id = ANY(CAST(:teams AS uuid[])))
)
"""


def visible_items(conn: Connection, org, ws, teams: list[str]) -> list[dict[str, Any]]:
    if not teams:
        return []
    return _all(
        conn,
        f"""SELECT v.*, la.employee_id AS assignee_id, la.assignment_source, lh.employee_id AS last_holder_id
            FROM ({VISIBLE}) v
            LEFT JOIN LATERAL (SELECT a.employee_id, a.assignment_source FROM {W}.work_item_assignments a
                        WHERE a.organization_id=v.organization_id AND a.workspace_id=v.workspace_id AND a.work_item_id=v.work_item_id
                          AND a.status <> 'CANCELLED' ORDER BY a.assigned_at DESC LIMIT 1) la ON TRUE
            LEFT JOIN LATERAL (SELECT a.employee_id FROM {W}.work_item_assignments a
                        WHERE a.organization_id=v.organization_id AND a.workspace_id=v.workspace_id AND a.work_item_id=v.work_item_id
                        ORDER BY a.assigned_at DESC LIMIT 1) lh ON TRUE""",
        {"o": org, "w": ws, "teams": teams},
    )


def events_for(conn: Connection, org, ws, item_ids: list[uuid.UUID], limit: int = 50) -> list[dict[str, Any]]:
    if not item_ids:
        return []
    return _all(
        conn,
        f"""SELECT e.* FROM {W}.work_events e
            WHERE e.organization_id=:o AND e.workspace_id=:w AND e.work_item_id = ANY(:ids)
            ORDER BY e.observed_at DESC LIMIT :n""",
        {"o": org, "w": ws, "ids": item_ids, "n": limit},
    )


def current_shift(conn: Connection, org, ws, employee_id) -> dict[str, Any] | None:
    """The shift this employee is on now (or the next one today)."""
    rows = _all(
        conn,
        f"""SELECT si.shift_instance_id, si.shift_lead_employee_id, si.scheduled_start_at, si.scheduled_end_at, sh.name, sh.timezone
            FROM {W}.shift_instance_memberships m
            JOIN {W}.shift_instances si ON si.organization_id=m.organization_id AND si.workspace_id=m.workspace_id AND si.shift_instance_id=m.shift_instance_id
            JOIN {W}.shifts sh ON sh.organization_id=si.organization_id AND sh.workspace_id=si.workspace_id AND sh.shift_id=si.shift_id
            WHERE m.organization_id=:o AND m.workspace_id=:w AND m.employee_id=:e AND si.scheduled_end_at > now()
            ORDER BY (si.scheduled_start_at <= now()) DESC, si.scheduled_start_at LIMIT 1""",
        {"o": org, "w": ws, "e": employee_id},
    )
    return rows[0] if rows else None


def shift_in_progress(conn: Connection, org, ws, team_id) -> dict[str, Any] | None:
    """The team's shift running now by its schedule (not cancelled or completed), with its lead.

    By the clock, so a demo hands over naturally: Afternoon, then Evening, then the next Morning."""
    rows = _all(
        conn,
        f"""SELECT si.shift_instance_id, si.shift_lead_employee_id, sh.name, e.first_name || ' ' || e.last_name AS lead_name
            FROM {W}.shift_instances si
            JOIN {W}.shifts sh ON sh.organization_id=si.organization_id AND sh.workspace_id=si.workspace_id AND sh.shift_id=si.shift_id
            LEFT JOIN {W}.employees e ON e.organization_id=si.organization_id AND e.workspace_id=si.workspace_id AND e.employee_id=si.shift_lead_employee_id
            WHERE si.organization_id=:o AND si.workspace_id=:w AND sh.team_id=CAST(:t AS uuid) AND si.status NOT IN ('CANCELLED', 'COMPLETED')
              AND si.scheduled_start_at <= now() AND si.scheduled_end_at > now()
            ORDER BY si.scheduled_start_at DESC LIMIT 1""",
        {"o": org, "w": ws, "t": team_id},
    )
    return rows[0] if rows else None


def open_work_session(conn: Connection, org, ws, employee_id) -> dict[str, Any] | None:
    rows = _all(
        conn,
        f"""SELECT * FROM {W}.work_sessions WHERE organization_id=:o AND workspace_id=:w AND employee_id=:e AND status='ACTIVE'
            ORDER BY started_at DESC LIMIT 1""",
        {"o": org, "w": ws, "e": employee_id},
    )
    return rows[0] if rows else None


def create_work_session(conn: Connection, org, ws, employee_id, shift_instance_id) -> dict[str, Any]:
    sid = uuid.uuid4()
    return dict(
        conn.execute(
            text(
                f"""INSERT INTO {W}.work_sessions (work_session_id, organization_id, workspace_id, employee_id, shift_instance_id, started_at, status, langgraph_thread_id)
                    VALUES (:s, :o, :w, :e, :si, now(), 'ACTIVE', :t) RETURNING *"""
            ),
            {"s": sid, "o": org, "w": ws, "e": employee_id, "si": shift_instance_id, "t": str(sid)},
        ).one()._mapping
    )


def work_session_for(conn: Connection, org, ws, work_session_id, employee_id) -> dict[str, Any] | None:
    rows = _all(
        conn,
        f"SELECT * FROM {W}.work_sessions WHERE organization_id=:o AND workspace_id=:w AND work_session_id=:s AND employee_id=:e",
        {"o": org, "w": ws, "s": work_session_id, "e": employee_id},
    )
    return rows[0] if rows else None


# ---------------------------------------------------------------- commands (callers hold the transaction)
def lock_item(conn: Connection, org, ws, work_item_id) -> dict[str, Any] | None:
    rows = _all(conn, f"SELECT * FROM {W}.work_items WHERE organization_id=:o AND workspace_id=:w AND work_item_id=:i FOR UPDATE", {"o": org, "w": ws, "i": work_item_id})
    return rows[0] if rows else None


def active_assignment(conn: Connection, org, ws, work_item_id, employee_id=None) -> dict[str, Any] | None:
    """The item's current (not cancelled or completed) assignment, optionally for one employee."""
    rows = _all(
        conn,
        f"""SELECT * FROM {W}.work_item_assignments WHERE organization_id=:o AND workspace_id=:w AND work_item_id=:i
              AND status NOT IN ('CANCELLED', 'COMPLETED') AND (CAST(:e AS uuid) IS NULL OR employee_id = CAST(:e AS uuid))
            ORDER BY assigned_at DESC LIMIT 1""",
        {"o": org, "w": ws, "i": work_item_id, "e": employee_id},
    )
    return rows[0] if rows else None


def set_assignment_status(conn: Connection, a: dict[str, Any], status: str) -> None:
    conn.execute(
        text(
            f"""UPDATE {W}.work_item_assignments SET status=:s, revision=revision+1, updated_at=now(),
                       completed_at = CASE WHEN :s = 'COMPLETED' THEN now() ELSE completed_at END
                WHERE organization_id=:o AND workspace_id=:w AND assignment_id=:a"""
        ),
        {"s": status, "o": a["organization_id"], "w": a["workspace_id"], "a": a["assignment_id"]},
    )


def add_event(conn: Connection, org, ws, work_item_id, employee_id, shift_instance_id, event_type: str, description: str, data: dict[str, Any]) -> dict[str, Any]:
    return dict(
        conn.execute(
            text(
                f"""INSERT INTO {W}.work_events (organization_id, workspace_id, work_item_id, employee_id, shift_instance_id, event_type, description, event_data, observed_at)
                    VALUES (:o, :w, :i, :e, :si, :t, :d, CAST(:data AS jsonb), clock_timestamp()) RETURNING *"""
            ),
            {"o": org, "w": ws, "i": work_item_id, "e": employee_id, "si": shift_instance_id, "t": event_type, "d": description, "data": json.dumps(data)},
        ).one()._mapping
    )


def set_item_status(conn: Connection, item: dict[str, Any], status: str) -> dict[str, Any]:
    return dict(
        conn.execute(
            text(f"""UPDATE {W}.work_items SET status=:s, revision=revision+1, updated_at=now() WHERE organization_id=:o AND workspace_id=:w AND work_item_id=:i RETURNING *"""),
            {"s": status, "o": item["organization_id"], "w": item["workspace_id"], "i": item["work_item_id"]},
        ).one()._mapping
    )


def outbox(conn: Connection, org, ws, operation_id, recipient, resource_type: str, resource_id, revision: int, event_type: str, payload: dict[str, Any]) -> None:
    """A notification for the dispatcher, committed with the business change. The payload carries no
    private text (CLAUDE.md: no notification previews of private content)."""
    conn.execute(
        text(
            f"""INSERT INTO {W}.outbox_events (organization_id, workspace_id, business_operation_id, recipient_employee_id, resource_type, resource_id, resource_revision, event_type, payload)
                VALUES (:o, :w, :op, :r, :rt, :rid, :rev, :t, CAST(:p AS jsonb))"""
        ),
        {"o": org, "w": ws, "op": operation_id, "r": recipient, "rt": resource_type, "rid": resource_id, "rev": revision, "t": event_type, "p": json.dumps(payload)},
    )


# ---------------------------------------------------------------- delegation
def proposals_for(conn: Connection, org, ws, teams: list[str]) -> list[dict[str, Any]]:
    return _all(
        conn,
        f"""SELECT * FROM {W}.delegation_proposals WHERE organization_id=:o AND workspace_id=:w AND team_id = ANY(CAST(:teams AS uuid[]))
            ORDER BY (status IN ('PROPOSED', 'EDITED')) DESC, created_at DESC""",
        {"o": org, "w": ws, "teams": teams},
    )


def proposal(conn: Connection, org, ws, proposal_id, lock: bool = False) -> dict[str, Any] | None:
    rows = _all(conn, f"SELECT * FROM {W}.delegation_proposals WHERE organization_id=:o AND workspace_id=:w AND delegation_proposal_id=:p" + (" FOR UPDATE" if lock else ""), {"o": org, "w": ws, "p": proposal_id})
    return rows[0] if rows else None


def proposal_items(conn: Connection, org, ws, proposal_id) -> list[dict[str, Any]]:
    return _all(
        conn,
        f"""SELECT pi.*, wi.external_id, wi.title, wi.status AS work_status, wi.revision AS work_revision
            FROM {W}.delegation_proposal_items pi
            JOIN {W}.work_items wi ON wi.organization_id=pi.organization_id AND wi.workspace_id=pi.workspace_id AND wi.work_item_id=pi.work_item_id
            WHERE pi.organization_id=:o AND pi.workspace_id=:w AND pi.delegation_proposal_id=:p ORDER BY wi.external_id""",
        {"o": org, "w": ws, "p": proposal_id},
    )


def eligible_members(conn: Connection, org, ws, team_id) -> list[uuid.UUID]:
    """Who may receive this team's work: active, not exited members holding work:report for the team."""
    return [
        r["employee_id"]
        for r in _all(
            conn,
            f"""SELECT DISTINCT m.employee_id FROM {W}.employee_team_memberships m
                JOIN {W}.employees e ON e.organization_id=m.organization_id AND e.workspace_id=m.workspace_id AND e.employee_id=m.employee_id
                JOIN {W}.permission_grants g ON g.organization_id=m.organization_id AND g.workspace_id=m.workspace_id AND g.actor_id=m.employee_id
                WHERE m.organization_id=:o AND m.workspace_id=:w AND m.team_id=:t AND m.is_active AND e.employment_status <> 'EXITED'
                  AND g.action='work:report' AND g.resource_scope->>'team_id' = CAST(:t AS text)
                  AND g.valid_from <= now() AND (g.valid_until IS NULL OR g.valid_until > now())""",
            {"o": org, "w": ws, "t": team_id},
        )
    ]


def availability_now(conn: Connection, org, ws, employee_id) -> str:
    rows = _all(
        conn,
        f"""SELECT status FROM {W}.employee_availability WHERE organization_id=:o AND workspace_id=:w AND employee_id=:e
              AND start_at <= now() AND end_at > now() ORDER BY (status='UNAVAILABLE') DESC LIMIT 1""",
        {"o": org, "w": ws, "e": employee_id},
    )
    return rows[0]["status"] if rows else "UNKNOWN"


def requirements(conn: Connection, org, ws, work_item_id) -> list[dict[str, Any]]:
    return _all(
        conn,
        f"""SELECT c.competency_id, c.name, r.required_level FROM {W}.work_item_competency_requirements r
            JOIN {W}.competencies c ON c.organization_id=r.organization_id AND c.workspace_id=r.workspace_id AND c.competency_id=r.competency_id
            WHERE r.organization_id=:o AND r.workspace_id=:w AND r.work_item_id=:i ORDER BY c.name""",
        {"o": org, "w": ws, "i": work_item_id},
    )


def validated_competencies(conn: Connection, org, ws, employee_id) -> dict[uuid.UUID, str]:
    """Competency → evidence type of this employee's validated evidence (only validated evidence counts)."""
    return {
        r["competency_id"]: r["evidence_type"]
        for r in _all(
            conn,
            f"""SELECT DISTINCT ON (competency_id) competency_id, evidence_type FROM {W}.employee_competency_evidence
                WHERE organization_id=:o AND workspace_id=:w AND employee_id=:e AND validation_status='VALIDATED'
                ORDER BY competency_id, observed_at DESC""",
            {"o": org, "w": ws, "e": employee_id},
        )
    }


def edit_proposal_item(conn: Connection, org, ws, proposal_item_id, final_employee_id) -> None:
    conn.execute(
        text(f"""UPDATE {W}.delegation_proposal_items SET final_employee_id=:f, revision=revision+1, updated_at=now()
                 WHERE organization_id=:o AND workspace_id=:w AND proposal_item_id=:i"""),
        {"f": final_employee_id, "o": org, "w": ws, "i": proposal_item_id},
    )


def set_proposal(conn: Connection, p: dict[str, Any], status: str, confirmed_by=None, context: dict[str, Any] | None = None) -> dict[str, Any]:
    return dict(
        conn.execute(
            text(
                f"""UPDATE {W}.delegation_proposals SET status=:s, revision=revision+1, updated_at=now(),
                           confirmed_at = CASE WHEN :s='CONFIRMED' THEN now() ELSE confirmed_at END,
                           confirmed_by_employee_id = CASE WHEN :s='CONFIRMED' THEN CAST(:by AS uuid) ELSE confirmed_by_employee_id END,
                           context_revisions = CASE WHEN CAST(:ctx AS jsonb) IS NULL THEN context_revisions ELSE CAST(:ctx AS jsonb) END
                    WHERE organization_id=:o AND workspace_id=:w AND delegation_proposal_id=:p RETURNING *"""
            ),
            {"s": status, "by": confirmed_by, "ctx": json.dumps(context) if context is not None else None, "o": p["organization_id"], "w": p["workspace_id"], "p": p["delegation_proposal_id"]},
        ).one()._mapping
    )


def assign(conn: Connection, org, ws, work_item_id, employee_id, assigned_by, proposal_item_id, match_data: dict[str, Any] | None = None) -> uuid.UUID:
    return conn.execute(
        text(
            f"""INSERT INTO {W}.work_item_assignments (organization_id, workspace_id, work_item_id, employee_id, assigned_by_employee_id, assignment_source, status, assigned_at, proposal_item_id, match_data)
                VALUES (:o, :w, :i, :e, :by, 'MANUAL', 'ASSIGNED', now(), :pi, CAST(:m AS jsonb)) RETURNING assignment_id"""
        ),
        {"o": org, "w": ws, "i": work_item_id, "e": employee_id, "by": assigned_by, "pi": proposal_item_id, "m": json.dumps(match_data or {})},
    ).scalar_one()


# ---------------------------------------------------------------- knowledge notes (memory drafts)
def drafts_of(conn: Connection, org, ws, owner) -> list[dict[str, Any]]:
    return _all(conn, f"SELECT * FROM {W}.memory_drafts WHERE organization_id=:o AND workspace_id=:w AND owner_employee_id=:e ORDER BY created_at DESC", {"o": org, "w": ws, "e": owner})


def draft(conn: Connection, org, ws, draft_id, owner, lock: bool = False) -> dict[str, Any] | None:
    rows = _all(
        conn,
        f"SELECT * FROM {W}.memory_drafts WHERE organization_id=:o AND workspace_id=:w AND draft_id=:d AND owner_employee_id=:e" + (" FOR UPDATE" if lock else ""),
        {"o": org, "w": ws, "d": draft_id, "e": owner},
    )
    return rows[0] if rows else None


def create_draft(conn: Connection, org, ws, owner, content: str, audience: str) -> dict[str, Any]:
    return dict(
        conn.execute(
            text(
                f"""INSERT INTO {W}.memory_drafts (organization_id, workspace_id, owner_employee_id, content, requested_audience)
                    VALUES (:o, :w, :e, :c, CAST(:a AS jsonb)) RETURNING *"""
            ),
            {"o": org, "w": ws, "e": owner, "c": content, "a": json.dumps([audience])},
        ).one()._mapping
    )


def submit_draft(conn: Connection, d: dict[str, Any]) -> dict[str, Any]:
    # The reviewer decides on exactly this revision (submitted_revision); later edits need a new review.
    return dict(
        conn.execute(
            text(
                f"""UPDATE {W}.memory_drafts SET status='PENDING_REVIEW', revision=revision+1, submitted_revision=revision+1, updated_at=now()
                    WHERE organization_id=:o AND workspace_id=:w AND draft_id=:d RETURNING *"""
            ),
            {"o": d["organization_id"], "w": d["workspace_id"], "d": d["draft_id"]},
        ).one()._mapping
    )


def delete_draft(conn: Connection, d: dict[str, Any]) -> None:
    conn.execute(text(f"DELETE FROM {W}.memory_drafts WHERE organization_id=:o AND workspace_id=:w AND draft_id=:d"), {"o": d["organization_id"], "w": d["workspace_id"], "d": d["draft_id"]})


# ---------------------------------------------------------------- employee reports vs the ticket system (ADR-033)
def system_name(conn: Connection, scenario_id) -> str:
    """What the company's (simulated) ticket tool is called, e.g. "Northstar Manufacturing ticket system"."""
    r = conn.execute(
        text(
            f"""SELECT o.name, coalesce(c.presentation->'terminology'->>'workItem', 'ticket') AS term FROM {W}.scenario_catalog c
                JOIN {W}.organizations o ON o.organization_id = c.organization_id WHERE c.scenario_id = :s"""
        ),
        {"s": scenario_id},
    ).first()
    return f"{r.name} {r.term} system" if r else "Ticket system"


def latest_assignment(conn: Connection, org, ws, work_item_id) -> dict[str, Any] | None:
    rows = _all(conn, f"SELECT * FROM {W}.work_item_assignments WHERE organization_id=:o AND workspace_id=:w AND work_item_id=:i ORDER BY assigned_at DESC LIMIT 1", {"o": org, "w": ws, "i": work_item_id})
    return rows[0] if rows else None


def add_report(conn: Connection, org, ws, assignment: dict[str, Any], work_session_id, reported_status: str, description: str, source_status: str) -> dict[str, Any]:
    return dict(
        conn.execute(
            text(
                f"""INSERT INTO {W}.work_item_reported_updates (organization_id, workspace_id, assignment_id, work_item_id, employee_id, work_session_id,
                        reported_status, blocker, description, source_status_at_report, reported_at)
                    VALUES (:o, :w, :a, :i, :e, :s, :rs, CASE WHEN :rs = 'BLOCKED' THEN :d END, :d, :src, clock_timestamp()) RETURNING *"""
            ),
            {"o": org, "w": ws, "a": assignment["assignment_id"], "i": assignment["work_item_id"], "e": assignment["employee_id"], "s": work_session_id, "rs": reported_status, "d": description, "src": source_status},
        ).one()._mapping
    )


def supersede_awaiting(conn: Connection, org, ws, assignment_id) -> None:
    conn.execute(
        text(f"""UPDATE {W}.work_item_reported_updates SET source_sync_status='SUPERSEDED'
                 WHERE organization_id=:o AND workspace_id=:w AND assignment_id=:a AND source_sync_status='AWAITING_SOURCE'"""),
        {"o": org, "w": ws, "a": assignment_id},
    )


def awaiting_reports(conn: Connection, org, ws, work_item_id) -> list[dict[str, Any]]:
    return _all(
        conn,
        f"""SELECT * FROM {W}.work_item_reported_updates WHERE organization_id=:o AND workspace_id=:w AND work_item_id=:i AND source_sync_status='AWAITING_SOURCE' FOR UPDATE""",
        {"o": org, "w": ws, "i": work_item_id},
    )


def set_report_sync(conn: Connection, report: dict[str, Any], status: str) -> dict[str, Any]:
    return dict(
        conn.execute(
            text(
                f"""UPDATE {W}.work_item_reported_updates SET source_sync_status=:s, source_reconciled_at=clock_timestamp()
                    WHERE organization_id=:o AND workspace_id=:w AND reported_update_id=:r RETURNING *"""
            ),
            {"s": status, "o": report["organization_id"], "w": report["workspace_id"], "r": report["reported_update_id"]},
        ).one()._mapping
    )


def reports_for(conn: Connection, org, ws, item_ids: list[uuid.UUID], limit: int = 50) -> list[dict[str, Any]]:
    if not item_ids:
        return []
    return _all(
        conn,
        f"""SELECT * FROM {W}.work_item_reported_updates WHERE organization_id=:o AND workspace_id=:w AND work_item_id = ANY(:ids)
            ORDER BY reported_at DESC LIMIT :n""",
        {"o": org, "w": ws, "ids": item_ids, "n": limit},
    )


def latest_reports(conn: Connection, org, ws, item_ids: list[uuid.UUID]) -> dict[uuid.UUID, dict[str, Any]]:
    """Per work item, the newest report that isn't superseded."""
    if not item_ids:
        return {}
    rows = _all(
        conn,
        f"""SELECT DISTINCT ON (work_item_id) * FROM {W}.work_item_reported_updates
            WHERE organization_id=:o AND workspace_id=:w AND work_item_id = ANY(:ids) AND source_sync_status <> 'SUPERSEDED'
            ORDER BY work_item_id, reported_at DESC""",
        {"o": org, "w": ws, "ids": item_ids},
    )
    return {r["work_item_id"]: r for r in rows}


# ---------------------------------------------------------------- Companion conversation (ADR-034)
def lock_employee_sessions(conn: Connection, org, ws, employee_id) -> None:
    """Serializes opening a work session per employee, so two page loads never create two."""
    conn.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": f"work_session:{org}:{ws}:{employee_id}"})


def messages_of(conn: Connection, org, ws, work_session_id, limit: int = 200) -> list[dict[str, Any]]:
    return _all(
        conn,
        f"""SELECT * FROM (SELECT * FROM {W}.work_session_messages WHERE organization_id=:o AND workspace_id=:w AND work_session_id=:s
                              ORDER BY seq DESC LIMIT :n) m ORDER BY seq""",
        {"o": org, "w": ws, "s": work_session_id, "n": limit},
    )


def turn_messages(conn: Connection, org, ws, work_session_id, client_turn_id) -> list[dict[str, Any]]:
    return _all(
        conn,
        f"SELECT * FROM {W}.work_session_messages WHERE organization_id=:o AND workspace_id=:w AND work_session_id=:s AND client_turn_id=:c ORDER BY seq",
        {"o": org, "w": ws, "s": work_session_id, "c": client_turn_id},
    )


def add_message(conn: Connection, org, ws, work_session_id, sender: str, text_: str, provenance: str, *, client_turn_id=None, input_kind=None,
                ui_action=None, resource_refs: list[str] | None = None, citations: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return dict(
        conn.execute(
            text(
                f"""INSERT INTO {W}.work_session_messages (organization_id, workspace_id, work_session_id, sender, client_turn_id, input_kind, text, provenance,
                        ui_action, resource_refs, citations, created_at)
                    VALUES (:o, :w, :s, :sender, :c, :k, :t, :p, :ui, CAST(:refs AS jsonb), CAST(:cit AS jsonb), clock_timestamp()) RETURNING *"""
            ),
            {"o": org, "w": ws, "s": work_session_id, "sender": sender, "c": client_turn_id, "k": input_kind, "t": text_, "p": provenance, "ui": ui_action,
             "refs": json.dumps(resource_refs or []), "cit": json.dumps(citations or [])},
        ).one()._mapping
    )


def bump_session(conn: Connection, s: dict[str, Any]) -> dict[str, Any]:
    return dict(
        conn.execute(
            text(f"UPDATE {W}.work_sessions SET updated_at=now() WHERE organization_id=:o AND workspace_id=:w AND work_session_id=:s RETURNING *"),
            {"o": s["organization_id"], "w": s["workspace_id"], "s": s["work_session_id"]},
        ).one()._mapping
    )


def session_reports_since(conn: Connection, org, ws, work_session_id, employee_id, since) -> list[dict[str, Any]]:
    """Reports the AI engine saved during one turn of this session (it writes them itself)."""
    return _all(
        conn,
        f"""SELECT * FROM {W}.work_item_reported_updates WHERE organization_id=:o AND workspace_id=:w AND work_session_id=:s AND employee_id=:e
              AND reported_at >= :since ORDER BY reported_at FOR UPDATE""",
        {"o": org, "w": ws, "s": work_session_id, "e": employee_id, "since": since},
    )


def supersede_older(conn: Connection, report: dict[str, Any]) -> None:
    """Older reports on the same assignment still awaiting the ticket system: the newest one counts
    (ADR-033), whether it came from the report form or the AI engine."""
    conn.execute(
        text(f"""UPDATE {W}.work_item_reported_updates SET source_sync_status='SUPERSEDED'
                 WHERE organization_id=:o AND workspace_id=:w AND assignment_id=:a AND source_sync_status='AWAITING_SOURCE'
                   AND reported_update_id <> :r AND reported_at <= :at"""),
        {"o": report["organization_id"], "w": report["workspace_id"], "a": report["assignment_id"], "r": report["reported_update_id"], "at": report["reported_at"]},
    )


def chunk_source(conn: Connection, org, ws, chunk_id) -> dict[str, Any] | None:
    """A chunk of this workspace, with its document version and section (to resolve a citation)."""
    rows = _all(
        conn,
        f"""SELECT chunk_id, document_version_id, source_section_id FROM {W}.knowledge_chunks
            WHERE organization_id=:o AND workspace_id=:w AND chunk_id=:c""",
        {"o": org, "w": ws, "c": chunk_id},
    )
    return rows[0] if rows else None


def ai_reply(conn: Connection, org, ws, work_session_id, message_id) -> str | None:
    """The text of one companion reply in this session (what may be read aloud)."""
    rows = _all(
        conn,
        f"SELECT text FROM {W}.work_session_messages WHERE organization_id=:o AND workspace_id=:w AND work_session_id=:s AND message_id=:m AND sender='AI'",
        {"o": org, "w": ws, "s": work_session_id, "m": message_id},
    )
    return rows[0]["text"] if rows else None


# ---------------------------------------------------------------- delegation proposed by the AI engine (ADR-034)
def shift_members(conn: Connection, org, ws, shift_instance_id) -> list[uuid.UUID]:
    return [
        r["employee_id"]
        for r in _all(
            conn,
            f"SELECT employee_id FROM {W}.shift_instance_memberships WHERE organization_id=:o AND workspace_id=:w AND shift_instance_id=:s",
            {"o": org, "w": ws, "s": shift_instance_id},
        )
    ]


def create_proposal(conn: Connection, org, ws, team_id, shift_instance_id, created_by, context: dict[str, Any]) -> dict[str, Any]:
    return dict(
        conn.execute(
            text(
                f"""INSERT INTO {W}.delegation_proposals (organization_id, workspace_id, shift_instance_id, team_id, created_by, status, context_revisions)
                    VALUES (:o, :w, :s, CAST(:t AS uuid), :by, 'PROPOSED', CAST(:ctx AS jsonb)) RETURNING *"""
            ),
            {"o": org, "w": ws, "s": shift_instance_id, "t": str(team_id), "by": created_by, "ctx": json.dumps(context)},
        ).one()._mapping
    )


def add_proposal_item(conn: Connection, org, ws, proposal_id, work_item_id, employee_id, reason: str, match_data: dict[str, Any]) -> None:
    conn.execute(
        text(
            f"""INSERT INTO {W}.delegation_proposal_items (organization_id, workspace_id, delegation_proposal_id, work_item_id, recommended_employee_id, recommendation_reason, match_data)
                VALUES (:o, :w, :p, :i, :e, :r, CAST(:m AS jsonb))"""
        ),
        {"o": org, "w": ws, "p": proposal_id, "i": work_item_id, "e": employee_id, "r": reason, "m": json.dumps(match_data)},
    )



# ---------------------------------------------------------------- automatic assignment (ADR-035)
def lock_workspace_assignment(conn: Connection, org, ws) -> None:
    conn.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": f"auto_assign:{org}:{ws}"})


def open_work_counts(conn: Connection, org, ws, employee_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not employee_ids:
        return {}
    rows = _all(
        conn,
        f"""SELECT a.employee_id, count(*) AS n FROM {W}.work_item_assignments a
            JOIN {W}.work_items wi ON wi.organization_id=a.organization_id AND wi.workspace_id=a.workspace_id AND wi.work_item_id=a.work_item_id
            WHERE a.organization_id=:o AND a.workspace_id=:w AND a.employee_id = ANY(:ids)
              AND a.status NOT IN ('CANCELLED', 'COMPLETED') AND wi.status IN ('ACTIVE', 'IN_PROGRESS', 'BLOCKED')
            GROUP BY a.employee_id""",
        {"o": org, "w": ws, "ids": employee_ids},
    )
    counts = {e: 0 for e in employee_ids}
    counts.update({r["employee_id"]: r["n"] for r in rows})
    return counts


def assign_with(conn: Connection, org, ws, work_item_id, employee_id, assigned_by, source: str, match_data: dict[str, Any]) -> dict[str, Any]:
    return dict(
        conn.execute(
            text(
                f"""INSERT INTO {W}.work_item_assignments (organization_id, workspace_id, work_item_id, employee_id, assigned_by_employee_id, assignment_source, status, assigned_at, match_data)
                    VALUES (:o, :w, :i, :e, :by, :src, 'ASSIGNED', now(), CAST(:m AS jsonb)) RETURNING *"""
            ),
            {"o": org, "w": ws, "i": work_item_id, "e": employee_id, "by": assigned_by, "src": source, "m": json.dumps(match_data)},
        ).one()._mapping
    )


def employee_names(conn: Connection, org, ws, ids: list[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not ids:
        return {}
    return {
        r["employee_id"]: r["name"]
        for r in _all(conn, f"SELECT employee_id, first_name || ' ' || last_name AS name FROM {W}.employees WHERE organization_id=:o AND workspace_id=:w AND employee_id = ANY(:ids)", {"o": org, "w": ws, "ids": ids})
    }



def changes_token(conn: Connection, org, ws) -> str:
    """Changes when work, assignments, reports or proposals change in this workspace (screens poll it)."""
    row = conn.execute(
        text(
            f"""SELECT (SELECT max(updated_at) FROM {W}.work_items WHERE organization_id=:o AND workspace_id=:w),
                       (SELECT max(updated_at) FROM {W}.work_item_assignments WHERE organization_id=:o AND workspace_id=:w),
                       (SELECT count(*) FROM {W}.work_item_assignments WHERE organization_id=:o AND workspace_id=:w),
                       (SELECT max(updated_at) FROM {W}.work_item_reported_updates WHERE organization_id=:o AND workspace_id=:w),
                       (SELECT max(updated_at) FROM {W}.delegation_proposals WHERE organization_id=:o AND workspace_id=:w)"""
        ),
        {"o": org, "w": ws},
    ).one()
    return "|".join(str(x) for x in row)


# ---------------------------------------------------------------- companion notices (ADR-036 plan, step 4)
def notice_events_since(conn: Connection, org, ws, recipient, since) -> list[dict[str, Any]]:
    """Notifications addressed to this person since `since` that the companion announces in the chat."""
    return _all(
        conn,
        f"""SELECT event_id, event_type, payload, created_at FROM {W}.outbox_events
            WHERE organization_id=:o AND workspace_id=:w AND recipient_employee_id=:e AND created_at > :since
              AND event_type IN ('work.assigned', 'work.unassigned', 'work.report_needs_review', 'work.reported_done')
            ORDER BY created_at""",
        {"o": org, "w": ws, "e": recipient, "since": since},
    )


def matched_reports_since(conn: Connection, org, ws, employee_id, since) -> list[dict[str, Any]]:
    """This person's reports the ticket system confirmed since `since`."""
    return _all(
        conn,
        f"""SELECT r.reported_update_id, r.source_reconciled_at, wi.external_id, wi.title FROM {W}.work_item_reported_updates r
            JOIN {W}.work_items wi ON wi.organization_id=r.organization_id AND wi.workspace_id=r.workspace_id AND wi.work_item_id=r.work_item_id
            WHERE r.organization_id=:o AND r.workspace_id=:w AND r.employee_id=:e AND r.source_sync_status='MATCHED'
              AND r.source_reconciled_at > :since AND wi.status IN ('COMPLETED', 'CLOSED')
            ORDER BY r.source_reconciled_at""",
        {"o": org, "w": ws, "e": employee_id, "since": since},
    )


def announced(conn: Connection, org, ws, work_session_id, refs: list[str]) -> set[str]:
    if not refs:
        return set()
    rows = _all(
        conn,
        f"""SELECT jsonb_array_elements_text(resource_refs) AS ref FROM {W}.work_session_messages
            WHERE organization_id=:o AND workspace_id=:w AND work_session_id=:s AND provenance='BACKEND_RECORD' AND resource_refs ?| CAST(:refs AS text[])""",
        {"o": org, "w": ws, "s": work_session_id, "refs": refs},
    )
    return {r["ref"] for r in rows}


def scenario_of(conn: Connection, org, ws):
    """The company scenario of this workspace (its terminology names the ticket system)."""
    return conn.execute(text(f"SELECT scenario_id FROM {W}.workspaces WHERE organization_id=:o AND workspace_id=:w"), {"o": org, "w": ws}).scalar()
