"""Shift Handover queries (blueprint 04/07, ADR-019/022). Every query is scoped to one workspace."""

import json
import uuid
from typing import Any

from sqlalchemy import Connection, text

W = "workweave"


def _all(conn: Connection, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    return [dict(r._mapping) for r in conn.execute(text(sql), params)]


def _one(conn: Connection, sql: str, params: dict[str, Any]) -> dict[str, Any] | None:
    rows = _all(conn, sql, params)
    return rows[0] if rows else None


# ---------------------------------------------------------------- shifts
def team_occurrences(conn: Connection, org, ws, team_id) -> list[dict[str, Any]]:
    """The team's shift occurrences in time order, with their lead and members."""
    return _all(
        conn,
        f"""SELECT si.shift_instance_id, si.status, si.scheduled_start_at, si.scheduled_end_at, si.shift_lead_employee_id, sh.name, sh.timezone,
                   COALESCE(array_agg(m.employee_id) FILTER (WHERE m.employee_id IS NOT NULL), '{{}}') AS member_ids
            FROM {W}.shift_instances si
            JOIN {W}.shifts sh ON sh.organization_id=si.organization_id AND sh.workspace_id=si.workspace_id AND sh.shift_id=si.shift_id
            LEFT JOIN {W}.shift_instance_memberships m ON m.organization_id=si.organization_id AND m.workspace_id=si.workspace_id AND m.shift_instance_id=si.shift_instance_id
            WHERE si.organization_id=:o AND si.workspace_id=:w AND sh.team_id=CAST(:t AS uuid) AND si.status <> 'CANCELLED'
            GROUP BY si.shift_instance_id, sh.name, sh.timezone
            ORDER BY si.scheduled_start_at""",
        {"o": org, "w": ws, "t": str(team_id)},
    )


# ---------------------------------------------------------------- templates
def team_template(conn: Connection, org, ws, team_id) -> dict[str, Any] | None:
    return _one(
        conn,
        f"""SELECT * FROM {W}.handover_templates WHERE organization_id=:o AND workspace_id=:w AND is_active
              AND (team_id = CAST(:t AS uuid) OR team_id IS NULL) ORDER BY (team_id IS NULL), is_default DESC LIMIT 1""",
        {"o": org, "w": ws, "t": str(team_id)},
    )


def template_version(conn: Connection, org, ws, template_version_id) -> dict[str, Any] | None:
    return _one(conn, f"SELECT * FROM {W}.handover_template_versions WHERE organization_id=:o AND workspace_id=:w AND template_version_id=:v", {"o": org, "w": ws, "v": template_version_id})


def latest_version(conn: Connection, org, ws, template_id) -> dict[str, Any] | None:
    return _one(conn, f"SELECT * FROM {W}.handover_template_versions WHERE organization_id=:o AND workspace_id=:w AND template_id=:t ORDER BY version DESC LIMIT 1", {"o": org, "w": ws, "t": template_id})


def sections(conn: Connection, org, ws, template_version_id) -> list[dict[str, Any]]:
    return _all(conn, f"SELECT * FROM {W}.handover_template_sections WHERE organization_id=:o AND workspace_id=:w AND template_version_id=:v ORDER BY order_index", {"o": org, "w": ws, "v": template_version_id})


def add_version(conn: Connection, org, ws, template_id, version: int) -> dict[str, Any]:
    return dict(conn.execute(text(f"""INSERT INTO {W}.handover_template_versions (organization_id, workspace_id, template_id, version, published_at)
                                      VALUES (:o, :w, :t, :v, now()) RETURNING *"""), {"o": org, "w": ws, "t": template_id, "v": version}).one()._mapping)


def add_section(conn: Connection, org, ws, template_version_id, name: str, order_index: int, required: bool) -> dict[str, Any]:
    return dict(conn.execute(text(f"""INSERT INTO {W}.handover_template_sections (organization_id, workspace_id, template_version_id, name, order_index, is_required)
                                      VALUES (:o, :w, :v, :n, :i, :r) RETURNING *"""), {"o": org, "w": ws, "v": template_version_id, "n": name, "i": order_index, "r": required}).one()._mapping)


# ---------------------------------------------------------------- handovers
def handover_from(conn: Connection, org, ws, source_shift_instance_id, lock: bool = False) -> dict[str, Any] | None:
    return _one(
        conn,
        f"""SELECT * FROM {W}.shift_handovers WHERE organization_id=:o AND workspace_id=:w AND source_shift_instance_id=:s
            ORDER BY created_at DESC LIMIT 1""" + (" FOR UPDATE" if lock else ""),
        {"o": org, "w": ws, "s": source_shift_instance_id},
    )


def handover(conn: Connection, org, ws, handover_id, lock: bool = False) -> dict[str, Any] | None:
    return _one(conn, f"SELECT * FROM {W}.shift_handovers WHERE organization_id=:o AND workspace_id=:w AND handover_id=:h" + (" FOR UPDATE" if lock else ""), {"o": org, "w": ws, "h": handover_id})


def create_handover(conn: Connection, org, ws, source, target, template_version_id, created_by, draft: list[dict[str, Any]]) -> dict[str, Any]:
    return dict(
        conn.execute(
            text(f"""INSERT INTO {W}.shift_handovers (organization_id, workspace_id, source_shift_instance_id, target_shift_instance_id, template_version_id, status,
                         created_by_employee_id, context_as_of, draft_sections)
                     VALUES (:o, :w, :s, :t, :v, 'DRAFT', :by, now(), CAST(:d AS jsonb)) RETURNING *"""),
            {"o": org, "w": ws, "s": source, "t": target, "v": template_version_id, "by": created_by, "d": json.dumps(draft)},
        ).one()._mapping
    )


def update_handover(conn: Connection, h: dict[str, Any], **fields: Any) -> dict[str, Any]:
    sets, params = [], {"o": h["organization_id"], "w": h["workspace_id"], "h": h["handover_id"]}
    for k, v in fields.items():
        if k == "draft_sections":
            sets.append("draft_sections = CAST(:draft_sections AS jsonb)")
            params[k] = json.dumps(v)
        else:
            sets.append(f"{k} = :{k}")
            params[k] = v
    return dict(conn.execute(text(f"UPDATE {W}.shift_handovers SET {', '.join(sets)} WHERE organization_id=:o AND workspace_id=:w AND handover_id=:h RETURNING *"), params).one()._mapping)


def team_handovers(conn: Connection, org, ws, shift_ids: list[uuid.UUID]) -> list[dict[str, Any]]:
    if not shift_ids:
        return []
    return _all(conn, f"SELECT * FROM {W}.shift_handovers WHERE organization_id=:o AND workspace_id=:w AND source_shift_instance_id = ANY(:ids)", {"o": org, "w": ws, "ids": shift_ids})


# ---------------------------------------------------------------- publications
def publications(conn: Connection, org, ws, handover_ids: list[uuid.UUID]) -> list[dict[str, Any]]:
    if not handover_ids:
        return []
    return _all(conn, f"SELECT * FROM {W}.handover_publications WHERE organization_id=:o AND workspace_id=:w AND handover_id = ANY(:ids) ORDER BY published_at", {"o": org, "w": ws, "ids": handover_ids})


def publication(conn: Connection, org, ws, publication_id) -> dict[str, Any] | None:
    return _one(conn, f"SELECT * FROM {W}.handover_publications WHERE organization_id=:o AND workspace_id=:w AND publication_id=:p", {"o": org, "w": ws, "p": publication_id})


def add_publication(conn: Connection, h: dict[str, Any], number: int, scope: dict[str, Any], section_content: list[dict[str, Any]], published_by) -> dict[str, Any]:
    return dict(
        conn.execute(
            text(f"""INSERT INTO {W}.handover_publications (organization_id, workspace_id, handover_id, publication_number, content_revision, scope_snapshot,
                         template_version_id, section_content, source_revisions, published_by, published_at)
                     VALUES (:o, :w, :h, :n, :rev, CAST(:scope AS jsonb), :v, CAST(:sc AS jsonb), '{{}}'::jsonb, :by, clock_timestamp()) RETURNING *"""),
            {"o": h["organization_id"], "w": h["workspace_id"], "h": h["handover_id"], "n": number, "rev": h["revision"], "scope": json.dumps(scope),
             "v": h["template_version_id"], "sc": json.dumps(section_content), "by": published_by},
        ).one()._mapping
    )


def entries(conn: Connection, org, ws, publication_ids: list[uuid.UUID]) -> list[dict[str, Any]]:
    if not publication_ids:
        return []
    return _all(conn, f"SELECT * FROM {W}.handover_entries WHERE organization_id=:o AND workspace_id=:w AND publication_id = ANY(:ids)", {"o": org, "w": ws, "ids": publication_ids})


def add_entry(conn: Connection, pub: dict[str, Any], item: dict[str, Any], work_status: str, refs: list[str]) -> None:
    conn.execute(
        text(f"""INSERT INTO {W}.handover_entries (organization_id, workspace_id, publication_id, handover_item_id, section_id, snapshot_work_status,
                     snapshot_acknowledgement_status, snapshot_description, snapshot_source_refs)
                 VALUES (:o, :w, :p, :i, :s, :ws_, :ack, :d, CAST(:refs AS jsonb))"""),
        {"o": pub["organization_id"], "w": pub["workspace_id"], "p": pub["publication_id"], "i": item["handover_item_id"], "s": item["section_id"],
         "ws_": work_status, "ack": item["acknowledgement_status"], "d": item["description"], "refs": json.dumps(refs)},
    )


def receipts(conn: Connection, org, ws, publication_ids: list[uuid.UUID]) -> list[dict[str, Any]]:
    if not publication_ids:
        return []
    return _all(conn, f"SELECT * FROM {W}.handover_receipts WHERE organization_id=:o AND workspace_id=:w AND publication_id = ANY(:ids) ORDER BY received_at", {"o": org, "w": ws, "ids": publication_ids})


def add_receipt(conn: Connection, pub: dict[str, Any], shift_instance_id, employee_id) -> bool:
    r = conn.execute(
        text(f"""INSERT INTO {W}.handover_receipts (organization_id, workspace_id, publication_id, recipient_shift_instance_id, recipient_employee_id, received_at)
                 VALUES (:o, :w, :p, :s, :e, now()) ON CONFLICT (organization_id, workspace_id, publication_id, recipient_employee_id) DO NOTHING RETURNING receipt_id"""),
        {"o": pub["organization_id"], "w": pub["workspace_id"], "p": pub["publication_id"], "s": shift_instance_id, "e": employee_id},
    ).first()
    return r is not None


# ---------------------------------------------------------------- persistent items
def items(conn: Connection, org, ws, shift_ids: list[uuid.UUID]) -> list[dict[str, Any]]:
    """Persistent items that originated in, or are owned by, these shifts; with the linked ticket."""
    if not shift_ids:
        return []
    return _all(
        conn,
        f"""SELECT hi.*, wi.external_id, wi.status AS ticket_status,
                   (SELECT s.source_type FROM {W}.handover_item_sources s WHERE s.organization_id=hi.organization_id AND s.workspace_id=hi.workspace_id
                      AND s.handover_item_id=hi.handover_item_id ORDER BY s.created_at LIMIT 1) AS source_type,
                   (SELECT s.external_id FROM {W}.handover_item_sources s WHERE s.organization_id=hi.organization_id AND s.workspace_id=hi.workspace_id
                      AND s.handover_item_id=hi.handover_item_id ORDER BY s.created_at LIMIT 1) AS source_external_id
            FROM {W}.handover_items hi
            LEFT JOIN {W}.work_items wi ON wi.organization_id=hi.organization_id AND wi.workspace_id=hi.workspace_id AND wi.work_item_id=hi.work_item_id
            WHERE hi.organization_id=:o AND hi.workspace_id=:w
              AND (hi.originating_shift_instance_id = ANY(:ids) OR hi.current_owner_shift_instance_id = ANY(:ids))
            ORDER BY hi.created_at""",
        {"o": org, "w": ws, "ids": shift_ids},
    )


def item(conn: Connection, org, ws, handover_item_id, lock: bool = False) -> dict[str, Any] | None:
    return _one(conn, f"SELECT * FROM {W}.handover_items WHERE organization_id=:o AND workspace_id=:w AND handover_item_id=:i" + (" FOR UPDATE" if lock else ""), {"o": org, "w": ws, "i": handover_item_id})


def items_for_work(conn: Connection, org, ws, work_item_id) -> list[dict[str, Any]]:
    return _all(conn, f"SELECT * FROM {W}.handover_items WHERE organization_id=:o AND workspace_id=:w AND work_item_id=:i FOR UPDATE", {"o": org, "w": ws, "i": work_item_id})


def create_item(conn: Connection, org, ws, title: str, description: str, origin_shift, owner_shift, employee_id, section_id, work_item_id=None) -> dict[str, Any]:
    return dict(
        conn.execute(
            text(f"""INSERT INTO {W}.handover_items (organization_id, workspace_id, work_item_id, title, description, originating_shift_instance_id, originating_employee_id,
                         current_owner_shift_instance_id, work_status, acknowledgement_status, section_id)
                     VALUES (:o, :w, :wi, :t, :d, :os, :e, :ow, 'ACTIVE', 'NOT_REQUIRED', :s) RETURNING *"""),
            {"o": org, "w": ws, "wi": work_item_id, "t": title, "d": description, "os": origin_shift, "e": employee_id, "ow": owner_shift, "s": section_id},
        ).one()._mapping
    )


def update_item(conn: Connection, it: dict[str, Any], **fields: Any) -> dict[str, Any]:
    sets = ", ".join(f"{k} = :{k}" for k in fields)
    return dict(
        conn.execute(text(f"UPDATE {W}.handover_items SET {sets} WHERE organization_id=:o AND workspace_id=:w AND handover_item_id=:i RETURNING *"),
                     {**fields, "o": it["organization_id"], "w": it["workspace_id"], "i": it["handover_item_id"]}).one()._mapping
    )


def add_item_event(conn: Connection, it: dict[str, Any], event_type: str, employee_id, shift_instance_id, previous: str | None, new: str | None, details: dict[str, Any], cycle_id=None) -> None:
    conn.execute(
        text(f"""INSERT INTO {W}.handover_item_events (organization_id, workspace_id, handover_item_id, employee_id, shift_instance_id, event_type, previous_status,
                     new_status, details, completion_cycle_id)
                 VALUES (:o, :w, :i, :e, :s, :t, :p, :n, CAST(:d AS jsonb), :c)"""),
        {"o": it["organization_id"], "w": it["workspace_id"], "i": it["handover_item_id"], "e": employee_id, "s": shift_instance_id, "t": event_type,
         "p": previous, "n": new, "d": json.dumps(details), "c": cycle_id},
    )


def item_events(conn: Connection, org, ws, item_ids: list[uuid.UUID]) -> list[dict[str, Any]]:
    if not item_ids:
        return []
    return _all(conn, f"SELECT * FROM {W}.handover_item_events WHERE organization_id=:o AND workspace_id=:w AND handover_item_id = ANY(:ids) ORDER BY created_at", {"o": org, "w": ws, "ids": item_ids})


def link_source(conn: Connection, org, ws, suggestion_id, handover_item_id) -> None:
    conn.execute(text(f"UPDATE {W}.handover_item_sources SET handover_item_id=:i WHERE organization_id=:o AND workspace_id=:w AND suggestion_id=:s AND handover_item_id IS NULL"),
                 {"o": org, "w": ws, "s": suggestion_id, "i": handover_item_id})


# ---------------------------------------------------------------- suggestions
def suggestions(conn: Connection, org, ws, handover_id) -> list[dict[str, Any]]:
    return _all(
        conn,
        f"""SELECT sg.*,
                   (SELECT s.source_type FROM {W}.handover_item_sources s WHERE s.organization_id=sg.organization_id AND s.workspace_id=sg.workspace_id AND s.suggestion_id=sg.suggestion_id LIMIT 1) AS source_type,
                   (SELECT s.external_id FROM {W}.handover_item_sources s WHERE s.organization_id=sg.organization_id AND s.workspace_id=sg.workspace_id AND s.suggestion_id=sg.suggestion_id LIMIT 1) AS source_external_id
            FROM {W}.handover_suggestions sg WHERE sg.organization_id=:o AND sg.workspace_id=:w AND sg.handover_id=:h ORDER BY sg.created_at""",
        {"o": org, "w": ws, "h": handover_id},
    )


def suggestion(conn: Connection, org, ws, suggestion_id, lock: bool = False) -> dict[str, Any] | None:
    return _one(conn, f"SELECT * FROM {W}.handover_suggestions WHERE organization_id=:o AND workspace_id=:w AND suggestion_id=:s" + (" FOR UPDATE" if lock else ""), {"o": org, "w": ws, "s": suggestion_id})


def review_suggestion(conn: Connection, sg: dict[str, Any], status: str, reviewer) -> None:
    conn.execute(text(f"""UPDATE {W}.handover_suggestions SET status=:st, reviewed_by_employee_id=:r, reviewed_at=now()
                          WHERE organization_id=:o AND workspace_id=:w AND suggestion_id=:s"""),
                 {"st": status, "r": reviewer, "o": sg["organization_id"], "w": sg["workspace_id"], "s": sg["suggestion_id"]})


# ---------------------------------------------------------------- completion cycles and acknowledgements
def cycles(conn: Connection, org, ws, item_ids: list[uuid.UUID]) -> list[dict[str, Any]]:
    if not item_ids:
        return []
    return _all(
        conn,
        f"""SELECT c.*, a.acknowledgement_id, a.requested_from_shift_instance_id, a.comment, a.status AS ack_status
            FROM {W}.handover_completion_cycles c
            LEFT JOIN {W}.handover_acknowledgements a ON a.organization_id=c.organization_id AND a.workspace_id=c.workspace_id AND a.completion_cycle_id=c.completion_cycle_id
            WHERE c.organization_id=:o AND c.workspace_id=:w AND c.handover_item_id = ANY(:ids) ORDER BY c.created_at""",
        {"o": org, "w": ws, "ids": item_ids},
    )


def cycle(conn: Connection, org, ws, cycle_id, lock: bool = False) -> dict[str, Any] | None:
    return _one(
        conn,
        f"""SELECT c.*, a.acknowledgement_id, a.requested_from_shift_instance_id, a.status AS ack_status, a.revision AS ack_revision
            FROM {W}.handover_completion_cycles c
            LEFT JOIN {W}.handover_acknowledgements a ON a.organization_id=c.organization_id AND a.workspace_id=c.workspace_id AND a.completion_cycle_id=c.completion_cycle_id
            WHERE c.organization_id=:o AND c.workspace_id=:w AND c.completion_cycle_id=:c""" + (" FOR UPDATE OF c" if lock else ""),
        {"o": org, "w": ws, "c": cycle_id},
    )


def open_cycle(conn: Connection, it: dict[str, Any], shift_instance_id, confirmed_by, event_id) -> dict[str, Any]:
    return dict(
        conn.execute(
            text(f"""INSERT INTO {W}.handover_completion_cycles (organization_id, workspace_id, handover_item_id, completed_in_shift_instance_id, confirmed_by_employee_id,
                         completion_event_id, status)
                     VALUES (:o, :w, :i, :s, :by, :e, 'PENDING') RETURNING *"""),
            {"o": it["organization_id"], "w": it["workspace_id"], "i": it["handover_item_id"], "s": shift_instance_id, "by": confirmed_by, "e": event_id},
        ).one()._mapping
    )


def request_ack(conn: Connection, it: dict[str, Any], cycle_id, from_shift, from_employee) -> None:
    conn.execute(
        text(f"""INSERT INTO {W}.handover_acknowledgements (organization_id, workspace_id, handover_item_id, completion_cycle_id, requested_from_shift_instance_id,
                     requested_from_employee_id, status, requested_at)
                 VALUES (:o, :w, :i, :c, :s, :e, 'PENDING', now())"""),
        {"o": it["organization_id"], "w": it["workspace_id"], "i": it["handover_item_id"], "c": cycle_id, "s": from_shift, "e": from_employee},
    )


def set_cycle(conn: Connection, c: dict[str, Any], status: str) -> None:
    conn.execute(text(f"UPDATE {W}.handover_completion_cycles SET status=:s WHERE organization_id=:o AND workspace_id=:w AND completion_cycle_id=:c"),
                 {"s": status, "o": c["organization_id"], "w": c["workspace_id"], "c": c["completion_cycle_id"]})


def respond_ack(conn: Connection, c: dict[str, Any], status: str, comment: str | None) -> None:
    conn.execute(
        text(f"""UPDATE {W}.handover_acknowledgements SET status=:s, comment=:m, responded_at=now()
                 WHERE organization_id=:o AND workspace_id=:w AND acknowledgement_id=:a"""),
        {"s": status, "m": comment, "o": c["organization_id"], "w": c["workspace_id"], "a": c["acknowledgement_id"]},
    )
