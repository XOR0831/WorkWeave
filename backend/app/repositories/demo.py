"""Scoped SQL for the demo catalog, visitor workspaces and sessions.

Every visitor query filters by (organization_id, workspace_id). Catalog reads return READY
rows only; baseline (pack) workspaces are read but never written by visitor commands.
"""

import json
import uuid
from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy import Connection, text

W = "workweave"


def ready_catalog(conn: Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        text(
            f"""
            SELECT c.scenario_id, c.company_key, c.pack_version, c.content_hash, c.presentation,
                   c.organization_id, c.workspace_id, o.name AS company_name, o.industry
            FROM {W}.scenario_catalog c
            JOIN {W}.organizations o ON o.organization_id = c.organization_id
            WHERE c.status = 'READY' AND c.synthetic
            ORDER BY COALESCE((c.presentation->>'catalog_order')::int, 1000), c.company_key
            """
        )
    )
    return [dict(r._mapping) for r in rows]


def ready_scenario(conn: Connection, scenario_id: uuid.UUID) -> dict[str, Any] | None:
    return next((s for s in ready_catalog(conn) if s["scenario_id"] == scenario_id), None)


def baseline_identity_digest_rows(conn: Connection, org: uuid.UUID, ws: uuid.UUID) -> list[Any]:
    """Canonical baseline identity rows hashed at activation and re-checked before copying."""
    q = lambda sql: [tuple(r) for r in conn.execute(text(sql), {"o": org, "w": ws})]  # noqa: E731
    return [
        q(f"SELECT department_id::text, name FROM {W}.departments WHERE organization_id=:o AND workspace_id=:w ORDER BY 1"),
        q(f"SELECT team_id::text, department_id::text, name FROM {W}.teams WHERE organization_id=:o AND workspace_id=:w ORDER BY 1"),
        q(f"SELECT role_id::text, name FROM {W}.roles WHERE organization_id=:o AND workspace_id=:w ORDER BY 1"),
        q(f"SELECT employee_id::text, role_id::text, first_name, last_name, employment_status FROM {W}.employees WHERE organization_id=:o AND workspace_id=:w ORDER BY 1"),
        q(f"SELECT employee_id::text, team_id::text, team_role, is_active FROM {W}.employee_team_memberships WHERE organization_id=:o AND workspace_id=:w ORDER BY 1, 2"),
        q(f"SELECT actor_id::text, action, resource_scope::text FROM {W}.permission_grants WHERE organization_id=:o AND workspace_id=:w ORDER BY 1, 2, 3"),
    ]


def has_showcase(conn: Connection) -> bool:
    """Migration 0011 (featured personas) may not be applied yet on an older database."""
    return bool(conn.execute(text(f"""SELECT 1 FROM information_schema.columns WHERE table_schema='{W}'
                                      AND table_name='scenario_personas' AND column_name='showcase'""")).first())


def scenario_personas(conn: Connection, scenario_id: uuid.UUID) -> list[dict[str, Any]]:
    extra = ", featured, showcase" if has_showcase(conn) else ""
    rows = conn.execute(
        text(f"SELECT baseline_employee_id, display_order, scenario_note{extra} FROM {W}.scenario_personas WHERE scenario_id=:s ORDER BY display_order"),
        {"s": scenario_id},
    )
    return [dict(r._mapping) for r in rows]


# ---------------------------------------------------------------- materialization
def visitor_run_proof_enabled(conn: Connection) -> bool:
    """Whether migration 0004 (demo_visitor_runs) is applied; before it, runs carry no proof row."""
    return conn.execute(text(f"SELECT to_regclass('{W}.demo_visitor_runs') IS NOT NULL")).scalar_one()


def materialize_identity(conn: Connection, scenario: dict[str, Any], expires_at: datetime) -> tuple[uuid.UUID, uuid.UUID, dict[str, uuid.UUID]]:
    """Copy the pack's identity records into a new organization/workspace for one visitor.

    Copies departments, teams, roles, employees, memberships and permission grants, and returns
    the old→new ID map so later steps (materialize_learning) keep references consistent.
    """
    src = {"o": scenario["organization_id"], "w": scenario["workspace_id"]}
    org, ws = uuid.uuid4(), uuid.uuid4()
    ids: dict[str, uuid.UUID] = {}

    def remap(old: Any) -> uuid.UUID | None:
        if old is None:
            return None
        key = str(old)
        if key not in ids:
            ids[key] = uuid.uuid4()
        return ids[key]

    def rows(sql: str) -> list[dict[str, Any]]:
        return [dict(r._mapping) for r in conn.execute(text(sql), src)]

    # company_key stays NULL on copies: the public key selects catalog content only.
    conn.execute(
        text(f"INSERT INTO {W}.organizations (organization_id, name, industry) SELECT :n, name, industry FROM {W}.organizations WHERE organization_id=:o"),
        {"n": org, "o": src["o"]},
    )
    conn.execute(
        text(
            f"""INSERT INTO {W}.workspaces (workspace_id, organization_id, kind, pack_version, content_hash, expires_at)
                VALUES (:w, :o, 'DEMO', :pv, :h, :exp)"""
        ),
        {"w": ws, "o": org, "pv": scenario["pack_version"], "h": scenario["content_hash"], "exp": expires_at},
    )
    if visitor_run_proof_enabled(conn):
        # Durable proof that this workspace is a visitor run (migration 0004); cleanup requires it.
        conn.execute(
            text(f"INSERT INTO {W}.demo_visitor_runs (organization_id, workspace_id, scenario_id, pack_version, proof_source) VALUES (:o, :w, :s, :pv, 'MATERIALIZATION')"),
            {"o": org, "w": ws, "s": scenario["scenario_id"], "pv": scenario["pack_version"]},
        )
    scope = {"o": org, "w": ws}
    for r in rows(f"SELECT department_id, name, description FROM {W}.departments WHERE organization_id=:o AND workspace_id=:w"):
        conn.execute(text(f"INSERT INTO {W}.departments (department_id, organization_id, workspace_id, name, description) VALUES (:id, :o, :w, :n, :d)"), {**scope, "id": remap(r["department_id"]), "n": r["name"], "d": r["description"]})
    for r in rows(f"SELECT team_id, department_id, name, description FROM {W}.teams WHERE organization_id=:o AND workspace_id=:w"):
        conn.execute(text(f"INSERT INTO {W}.teams (team_id, organization_id, workspace_id, department_id, name, description) VALUES (:id, :o, :w, :dep, :n, :d)"), {**scope, "id": remap(r["team_id"]), "dep": remap(r["department_id"]), "n": r["name"], "d": r["description"]})
    for r in rows(f"SELECT role_id, name, description FROM {W}.roles WHERE organization_id=:o AND workspace_id=:w"):
        conn.execute(text(f"INSERT INTO {W}.roles (role_id, organization_id, workspace_id, name, description) VALUES (:id, :o, :w, :n, :d)"), {**scope, "id": remap(r["role_id"]), "n": r["name"], "d": r["description"]})
    for r in rows(f"SELECT * FROM {W}.employees WHERE organization_id=:o AND workspace_id=:w"):
        conn.execute(
            text(
                f"""INSERT INTO {W}.employees (employee_id, organization_id, workspace_id, role_id, first_name, last_name, email,
                        employment_status, hire_date, final_working_date, preferred_language, baseline_employee_id)
                    VALUES (:id, :o, :w, :role, :fn, :ln, :email, :st, :hd, :fwd, :lang, :base)"""
            ),
            {**scope, "id": remap(r["employee_id"]), "role": remap(r["role_id"]), "fn": r["first_name"], "ln": r["last_name"], "email": r["email"], "st": r["employment_status"], "hd": r["hire_date"], "fwd": r["final_working_date"], "lang": r["preferred_language"], "base": r["employee_id"]},
        )
    for r in rows(f"SELECT * FROM {W}.employee_team_memberships WHERE organization_id=:o AND workspace_id=:w"):
        conn.execute(
            text(
                f"""INSERT INTO {W}.employee_team_memberships (membership_id, organization_id, workspace_id, employee_id, team_id, team_role, start_date, end_date, is_active)
                    VALUES (:id, :o, :w, :e, :t, :tr, :sd, :ed, :a)"""
            ),
            {**scope, "id": uuid.uuid4(), "e": remap(r["employee_id"]), "t": remap(r["team_id"]), "tr": r["team_role"], "sd": r["start_date"], "ed": r["end_date"], "a": r["is_active"]},
        )
    for r in rows(f"SELECT * FROM {W}.permission_grants WHERE organization_id=:o AND workspace_id=:w"):
        rs = dict(r["resource_scope"] or {})
        for k in ("team_id", "department_id", "employee_id"):
            if rs.get(k):
                rs[k] = str(remap(rs[k]))
        conn.execute(
            text(
                f"""INSERT INTO {W}.permission_grants (grant_id, organization_id, workspace_id, actor_id, resource_scope, action, valid_from, valid_until, granted_by)
                    VALUES (:id, :o, :w, :a, CAST(:rs AS jsonb), :act, :vf, :vu, :gb)"""
            ),
            {**scope, "id": uuid.uuid4(), "a": remap(r["actor_id"]), "rs": json.dumps(rs), "act": r["action"], "vf": r["valid_from"], "vu": r["valid_until"], "gb": remap(r["granted_by"])},
        )
    return org, ws, ids


def count_scope(conn: Connection, org: uuid.UUID, ws: uuid.UUID, table: str) -> int:
    assert table in {"employees", "permission_grants", "employee_team_memberships", "teams", "roles", "departments"}
    return conn.execute(text(f"SELECT count(*) FROM {W}.{table} WHERE organization_id=:o AND workspace_id=:w"), {"o": org, "w": ws}).scalar_one()


# ---------------------------------------------------------------- sessions
def insert_session(conn: Connection, org: uuid.UUID, ws: uuid.UUID, scenario: dict[str, Any], token_hash: str, expires_at: datetime, access_code_id: uuid.UUID | None = None) -> uuid.UUID:
    sid = uuid.uuid4()
    conn.execute(
        text(
            f"""INSERT INTO {W}.demo_visitor_sessions (demo_visitor_session_id, organization_id, workspace_id, scenario_id, pack_version, token_hash, expires_at, access_code_id)
                VALUES (:id, :o, :w, :s, :pv, :th, :exp, :ac)"""
        ),
        {"id": sid, "o": org, "w": ws, "s": scenario["scenario_id"], "pv": scenario["pack_version"], "th": token_hash, "exp": expires_at, "ac": access_code_id},
    )
    return sid


def session_by_token_hash(conn: Connection, token_hash: str) -> dict[str, Any] | None:
    """The session plus the actual kind of the workspace it is attached to (defence in depth)."""
    r = conn.execute(
        text(
            f"""SELECT s.*, w.kind AS attached_workspace_kind
                FROM {W}.demo_visitor_sessions s
                JOIN {W}.workspaces w ON w.organization_id = s.organization_id AND w.workspace_id = s.workspace_id
                WHERE s.token_hash = :t"""
        ),
        {"t": token_hash},
    ).first()
    return dict(r._mapping) if r else None


def set_session_status(conn: Connection, s: dict[str, Any], status: str) -> None:
    conn.execute(
        text(f"UPDATE {W}.demo_visitor_sessions SET status=:st, updated_at=now(), revision=revision+1 WHERE demo_visitor_session_id=:id AND organization_id=:o AND workspace_id=:w"),
        {"st": status, "id": s["demo_visitor_session_id"], "o": s["organization_id"], "w": s["workspace_id"]},
    )


def set_active_persona(conn: Connection, s: dict[str, Any], employee_id: uuid.UUID) -> int:
    return conn.execute(
        text(
            f"""UPDATE {W}.demo_visitor_sessions SET active_employee_id=:e, updated_at=now(), revision=revision+1
                WHERE demo_visitor_session_id=:id AND organization_id=:o AND workspace_id=:w AND status='ACTIVE'
                RETURNING revision"""
        ),
        {"e": employee_id, "id": s["demo_visitor_session_id"], "o": s["organization_id"], "w": s["workspace_id"]},
    ).scalar_one()


def personas(conn: Connection, s: dict[str, Any]) -> list[dict[str, Any]]:
    """The pack's personas inside this visitor workspace, in pack order, with their grants."""
    if has_showcase(conn):  # featured personas and their showcase (migration 0011)
        showcase, showcase_group = "sp.featured, sp.showcase,", ", sp.featured, sp.showcase"
    else:
        showcase, showcase_group = "false AS featured, '{}'::jsonb AS showcase,", ""
    rows = conn.execute(
        text(
            f"""
            SELECT e.employee_id, e.first_name, e.last_name, e.employment_status, r.name AS role_name,
                   t.name AS team_name, m.team_role, sp.scenario_note, sp.display_order, {showcase}
                   -- curriculum:read counts only when explicitly workspace-scoped, matching the API check.
                   COALESCE(array_agg(DISTINCT g.action) FILTER (
                       WHERE g.action IS NOT NULL
                         AND (g.action <> 'curriculum:read'
                              OR (g.resource_scope->>'scope' = 'WORKSPACE' AND NOT g.resource_scope ?| ARRAY['team_id', 'department_id', 'employee_id']))
                   ), '{{}}') AS actions
            FROM {W}.employees e
            JOIN {W}.scenario_personas sp ON sp.baseline_employee_id = e.baseline_employee_id AND sp.scenario_id = :s
            LEFT JOIN {W}.roles r ON r.organization_id = e.organization_id AND r.workspace_id = e.workspace_id AND r.role_id = e.role_id
            LEFT JOIN {W}.employee_team_memberships m ON m.organization_id = e.organization_id AND m.workspace_id = e.workspace_id
                 AND m.employee_id = e.employee_id AND m.is_active
            LEFT JOIN {W}.teams t ON t.organization_id = m.organization_id AND t.workspace_id = m.workspace_id AND t.team_id = m.team_id
            LEFT JOIN {W}.permission_grants g ON g.organization_id = e.organization_id AND g.workspace_id = e.workspace_id
                 AND g.actor_id = e.employee_id AND (g.valid_until IS NULL OR g.valid_until > now())
            WHERE e.organization_id = :o AND e.workspace_id = :w
            GROUP BY e.employee_id, r.name, t.name, m.team_role, sp.scenario_note, sp.display_order{showcase_group}
            ORDER BY sp.display_order
            """
        ),
        {"s": s["scenario_id"], "o": s["organization_id"], "w": s["workspace_id"]},
    )
    return [dict(r._mapping) for r in rows]


def audit(conn: Connection, org: uuid.UUID, ws: uuid.UUID, action: str, resource_id: uuid.UUID, revision: int, request_id: uuid.UUID, actor: uuid.UUID | None = None) -> None:
    conn.execute(
        text(
            f"""INSERT INTO {W}.audit_events (organization_id, workspace_id, actor_id, action, resource_type, resource_id, resource_revision, result, request_id)
                VALUES (:o, :w, :a, :act, 'demo_visitor_session', :rid, :rev, 'COMMITTED', :req)"""
        ),
        {"o": org, "w": ws, "a": actor, "act": action, "rid": resource_id, "rev": revision, "req": request_id},
    )


# ---------------------------------------------------------------- onboarding (curriculum + progress)
def materialize_learning(conn: Connection, scenario: dict[str, Any], org: uuid.UUID, ws: uuid.UUID, ids: dict[str, uuid.UUID]) -> None:
    """Copy curricula, learning paths, objectives, assignments and progress into the visitor copy.

    All topics are copied, including document-bound ones from SOP ingestion (product owner,
    2026-10-04: SOP-001 v3.4's ingested topics are the testing sample, via Machine Fundamentals 1.1).
    A document-bound topic's foreign key to curriculum_sources is satisfied when
    materialize_knowledge copies the sources later in the same transaction (deferred constraint).
    """
    src = {"o": scenario["organization_id"], "w": scenario["workspace_id"]}
    scope = {"o": org, "w": ws}

    def remap(old: Any) -> uuid.UUID | None:
        if old is None:
            return None
        key = str(old)
        if key not in ids:
            ids[key] = uuid.uuid4()
        return ids[key]

    def rows(sql: str) -> list[dict[str, Any]]:
        return [dict(r._mapping) for r in conn.execute(text(sql), src)]

    def insert(table: str, values: dict[str, Any], casts: dict[str, str] | None = None) -> None:
        cols = ", ".join(values)
        params = ", ".join(f"CAST(:{k} AS {casts[k]})" if casts and k in casts else f":{k}" for k in values)
        conn.execute(text(f"INSERT INTO {W}.{table} ({cols}) VALUES ({params})"), values)

    base = {"organization_id": org, "workspace_id": ws}
    for r in rows(f"SELECT * FROM {W}.competencies WHERE organization_id=:o AND workspace_id=:w"):
        insert("competencies", {**base, "competency_id": remap(r["competency_id"]), "code": r["code"], "name": r["name"], "description": r["description"], "category": r["category"]})
    for r in rows(f"SELECT * FROM {W}.curricula WHERE organization_id=:o AND workspace_id=:w"):
        insert("curricula", {**base, "curriculum_id": remap(r["curriculum_id"]), "name": r["name"], "description": r["description"], "version": r["version"], "status": r["status"], "published_at": r["published_at"], "completion_policy_version": r["completion_policy_version"]})
    conn.execute(text(f"SET CONSTRAINTS {W}.curriculum_topics_document_version_fk DEFERRED"))
    topics = rows(f"SELECT * FROM {W}.curriculum_topics WHERE organization_id=:o AND workspace_id=:w")
    for r in topics:
        insert("curriculum_topics", {**base, "topic_id": remap(r["topic_id"]), "curriculum_id": remap(r["curriculum_id"]), "name": r["name"], "description": r["description"],
                                     "order_index": r["order_index"], "active": r["active"], "document_version_id": remap(r["document_version_id"])})
    topic_ids = {str(t["topic_id"]) for t in topics}
    subtopics = [r for r in rows(f"SELECT * FROM {W}.curriculum_subtopics WHERE organization_id=:o AND workspace_id=:w") if str(r["topic_id"]) in topic_ids]
    for r in subtopics:
        insert("curriculum_subtopics", {**base, "subtopic_id": remap(r["subtopic_id"]), "topic_id": remap(r["topic_id"]), "name": r["name"], "description": r["description"], "order_index": r["order_index"], "active": r["active"]})
    sub_ids = {str(x["subtopic_id"]) for x in subtopics}
    for r in rows(f"SELECT * FROM {W}.learning_objectives WHERE organization_id=:o AND workspace_id=:w"):
        if str(r["subtopic_id"]) in sub_ids:
            insert(
                "learning_objectives",
                {**base, "objective_id": remap(r["objective_id"]), "subtopic_id": remap(r["subtopic_id"]), "description": r["description"], "assessment_criteria": json.dumps(r["assessment_criteria"]), "criteria_version": r["criteria_version"], "required": r["required"], "hint_policy": json.dumps(r["hint_policy"]), "competency_id": remap(r["competency_id"])},
                {"assessment_criteria": "jsonb", "hint_policy": "jsonb"},
            )
    for r in rows(f"SELECT * FROM {W}.curriculum_prerequisites WHERE organization_id=:o AND workspace_id=:w"):
        if str(r["subtopic_id"]) in sub_ids and str(r["prerequisite_subtopic_id"]) in sub_ids:
            insert("curriculum_prerequisites", {**base, "prerequisite_id": remap(r["prerequisite_id"]), "subtopic_id": remap(r["subtopic_id"]), "prerequisite_subtopic_id": remap(r["prerequisite_subtopic_id"])})
    for r in rows(f"SELECT * FROM {W}.curriculum_assignments WHERE organization_id=:o AND workspace_id=:w"):
        insert("curriculum_assignments", {**base, "assignment_id": remap(r["assignment_id"]), "curriculum_id": remap(r["curriculum_id"]), "employee_id": remap(r["employee_id"]), "role_id": remap(r["role_id"]), "assigned_at": r["assigned_at"], "assigned_by_employee_id": remap(r["assigned_by_employee_id"]), "status": r["status"]})
    for r in rows(f"SELECT * FROM {W}.learning_assignments WHERE organization_id=:o AND workspace_id=:w"):
        insert("learning_assignments", {**base, "learning_assignment_id": remap(r["learning_assignment_id"]), "employee_id": remap(r["employee_id"]), "curriculum_id": remap(r["curriculum_id"]), "originating_assignment_id": remap(r["originating_assignment_id"]), "assignment_kind": r["assignment_kind"], "status": r["status"]})
    for r in rows(f"SELECT * FROM {W}.employee_learning_progress WHERE organization_id=:o AND workspace_id=:w"):
        if str(r["subtopic_id"]) in sub_ids:
            insert("employee_learning_progress", {**base, "progress_id": remap(r["progress_id"]), "employee_id": remap(r["employee_id"]), "learning_assignment_id": remap(r["learning_assignment_id"]), "subtopic_id": remap(r["subtopic_id"]), "status": r["status"], "started_at": r["started_at"], "completed_at": r["completed_at"]})


# Work Companion data, copied in dependency order (delegation proposals are copied because they are
# part of the scenario and link open work to its team; their screens come with the delegation slice).
WORK_TABLES = (
    "shifts",
    "shift_instances",
    "shift_instance_memberships",
    "work_items",
    "work_item_competency_requirements",
    "delegation_proposals",
    "delegation_proposal_items",
    "work_item_assignments",
    "work_events",
    # Delegation rechecks: declared availability and validated competency evidence (scenario baseline).
    "employee_availability",
    "employee_competency_evidence",
)
RECORD_TIMES = {"created_at", "updated_at"}


SHIFT_TABLES = {"shifts", "shift_instances", "shift_instance_memberships"}
# Shift Handover, copied after the work it refers to, with its times moved like the shifts. These
# tables keep IDs inside JSON (draft sections, sources, suggested data), which are remapped too.
HANDOVER_TABLES = (
    "handover_templates",
    "handover_template_versions",
    "handover_template_sections",
    "shift_handovers",
    "handover_publications",
    "handover_items",
    "handover_entries",
    "handover_suggestions",
    "handover_item_sources",
    "handover_completion_cycles",
    "handover_item_events",
    "handover_acknowledgements",
    "handover_receipts",
)


# Exit KT (ADR-039), copied after work and handovers with times moved like the work. Interviews,
# their messages and consent sessions are consent-bound and never cloned into a visitor run (an
# interview starts empty in each demo); approvals, promotions, package versions and receipts start
# empty too. IDs inside JSON or text references are remapped when their row was copied and dropped
# otherwise, so nothing in the copy points at a baseline row.
EXIT_KT_TABLES = (
    "exit_kt_cases",
    "exit_kt_knowledge_items",
    "exit_kt_sources",
    "exit_kt_findings",
    "exit_kt_artifacts",
    "exit_kt_artifact_revisions",
    "responsibilities",
    "responsibility_transfers",
    "exit_kt_packages",
    "exit_kt_package_responsibilities",
    "kt_checklist_items",
)
NOT_COPIED_REFS = {"generated_from_interview_id"}


def work_anchors(conn: Connection, org: uuid.UUID, ws: uuid.UUID) -> tuple[datetime | None, datetime | None]:
    """(work "now", shift "now") of the pack's scenario.

    Seeds place work relative to the seeding time but shifts by clock day, with one marked ACTIVE,
    so each keeps its own anchor: work moves with the seeding time (tickets stay "due in 2 h"), and
    shifts move so the ACTIVE one is half-way through when a demo starts."""
    seeded = conn.execute(
        text(f"""SELECT max(created_at) FROM {W}.work_items WHERE organization_id=:o AND workspace_id=:w AND coalesce(metadata->>'historical_only', 'false') <> 'true'"""),
        {"o": org, "w": ws},
    ).scalar()
    active = conn.execute(
        text(f"""SELECT scheduled_start_at, scheduled_end_at FROM {W}.shift_instances WHERE organization_id=:o AND workspace_id=:w AND status='ACTIVE'
                 ORDER BY scheduled_start_at LIMIT 1"""),
        {"o": org, "w": ws},
    ).first()
    shift_now = active.scheduled_start_at + (active.scheduled_end_at - active.scheduled_start_at) / 2 if active else seeded
    return seeded, shift_now


def materialize_work(conn: Connection, scenario: dict[str, Any], org: uuid.UUID, ws: uuid.UUID, ids: dict[str, uuid.UUID], now: datetime) -> None:
    """Copy shifts, work items, assignments, work updates, delegation proposals, the Shift Handover
    (templates, handovers, publications, persistent items and their history) and the Exit KT case
    (see EXIT_KT_TABLES) into the visitor copy.

    Scenario times move so every fresh demo tells the same story as "today" (see work_anchors): open
    tickets due in hours, the ACTIVE shift in progress, history in the past.
    Record times (created_at/updated_at) are the copy time. IDs are remapped like the other copies;
    JSON values are copied as they are, except IDs inside handover JSON, which are remapped.
    """
    src = {"o": scenario["organization_id"], "w": scenario["workspace_id"]}
    work_now, shift_now = work_anchors(conn, scenario["organization_id"], scenario["workspace_id"])
    work_delta = (now - work_now) if work_now else timedelta(0)
    shift_delta = (now - shift_now) if shift_now else work_delta

    def remap(old: uuid.UUID) -> uuid.UUID:
        key = str(old)
        if key not in ids:
            ids[key] = uuid.uuid4()
        return ids[key]

    def remap_json(val: Any) -> Any:
        """IDs inside JSON values of the handover tables (strings that are UUIDs)."""
        if isinstance(val, dict):
            return {k: remap_json(v) for k, v in val.items()}
        if isinstance(val, list):
            return [remap_json(v) for v in val]
        if isinstance(val, str):
            try:
                return str(remap(uuid.UUID(val)))
            except ValueError:
                return val
        return val

    def known_json(val: Any) -> Any:
        """Exit KT JSON: IDs of copied rows are remapped; IDs of rows that weren't copied are dropped."""
        if isinstance(val, dict):
            return {k: known_json(v) for k, v in val.items()}
        if isinstance(val, list):
            return [x for x in (known_json(v) for v in val) if x is not _DROP]
        if isinstance(val, str):
            try:
                key = str(uuid.UUID(val))
            except ValueError:
                return val
            return str(ids[key]) if key in ids else _DROP
        return val

    # Handover and Exit KT rows refer to each other both ways (a handover and its current publication,
    # an artifact and its current revision).
    conn.execute(text("SET CONSTRAINTS ALL DEFERRED"))
    for table in WORK_TABLES + HANDOVER_TABLES + EXIT_KT_TABLES:
        shift = shift_delta if table in SHIFT_TABLES or table in HANDOVER_TABLES else work_delta
        kt = table in EXIT_KT_TABLES
        for r in [dict(x._mapping) for x in conn.execute(text(f"SELECT * FROM {W}.{table} WHERE organization_id=:o AND workspace_id=:w"), src)]:
            if kt and col_ref_dropped(r, ids):
                continue
            values: dict[str, Any] = {}
            casts: dict[str, str] = {}
            for col, val in r.items():
                if kt and col in NOT_COPIED_REFS:
                    values[col] = None
                elif kt and isinstance(val, (dict, list)):
                    values[col] = json.dumps(known_json(val))
                    casts[col] = "jsonb"
                elif kt and col == "source_reference":
                    values[col] = known_json(val)
                elif col == "organization_id":
                    values[col] = org
                elif col == "workspace_id":
                    values[col] = ws
                elif col in RECORD_TIMES:
                    values[col] = now
                elif isinstance(val, uuid.UUID):
                    values[col] = remap(val)
                elif isinstance(val, datetime):
                    values[col] = val + shift
                elif isinstance(val, date):  # e.g. shift_date: the scenario day moves with its times
                    values[col] = (datetime.combine(val, time(12)) + shift).date()
                elif isinstance(val, (dict, list)):
                    values[col] = json.dumps(remap_json(val) if table in HANDOVER_TABLES else val)
                    casts[col] = "jsonb"
                elif table in HANDOVER_TABLES and isinstance(val, str) and col == "source_reference":
                    values[col] = remap_json(val)  # a source row ID kept as text
                else:
                    values[col] = val
            cols = ", ".join(values)
            params = ", ".join(f"CAST(:{k} AS {casts[k]})" if k in casts else f":{k}" for k in values)
            conn.execute(text(f"INSERT INTO {W}.{table} ({cols}) VALUES ({params})"), values)


_DROP = object()


def col_ref_dropped(r: dict[str, Any], ids: dict[str, uuid.UUID]) -> bool:
    """An Exit KT source whose text reference names a row that wasn't copied is left out."""
    ref = r.get("source_reference")
    if not isinstance(ref, str):
        return False
    try:
        return str(uuid.UUID(ref)) not in ids
    except ValueError:
        return False


def learner_assignment(conn: Connection, org: uuid.UUID, ws: uuid.UUID, employee_id: uuid.UUID) -> dict[str, Any] | None:
    r = conn.execute(
        text(
            f"""SELECT la.learning_assignment_id, la.status, c.curriculum_id, c.name, c.version
                FROM {W}.learning_assignments la
                JOIN {W}.curricula c ON c.organization_id = la.organization_id AND c.workspace_id = la.workspace_id AND c.curriculum_id = la.curriculum_id
                WHERE la.organization_id = :o AND la.workspace_id = :w AND la.employee_id = :e AND la.status <> 'CANCELLED'
                ORDER BY (la.status = 'ACTIVE') DESC, la.assignment_kind = 'INITIAL' DESC, c.version DESC
                LIMIT 1"""
        ),
        {"o": org, "w": ws, "e": employee_id},
    ).first()
    return dict(r._mapping) if r else None


def learning_path(conn: Connection, org: uuid.UUID, ws: uuid.UUID, curriculum_id: uuid.UUID, learning_assignment_id: uuid.UUID) -> list[dict[str, Any]]:
    """Active topics/subtopics in order, each with its objective text, progress and prerequisites."""
    rows = conn.execute(
        text(
            f"""
            SELECT t.topic_id, t.name AS topic_name, t.order_index AS topic_order,
                   s.subtopic_id, s.name, s.order_index,
                   (SELECT lo.description FROM {W}.learning_objectives lo
                     WHERE lo.organization_id = s.organization_id AND lo.workspace_id = s.workspace_id AND lo.subtopic_id = s.subtopic_id
                     ORDER BY lo.required DESC LIMIT 1) AS objective,
                   -- Optional subtopic: it has objectives but none is required (e.g. v3.4 Reference aids).
                   NOT EXISTS (SELECT 1 FROM {W}.learning_objectives lo
                                WHERE lo.organization_id = s.organization_id AND lo.workspace_id = s.workspace_id AND lo.subtopic_id = s.subtopic_id AND lo.required)
                     AND EXISTS (SELECT 1 FROM {W}.learning_objectives lo
                                WHERE lo.organization_id = s.organization_id AND lo.workspace_id = s.workspace_id AND lo.subtopic_id = s.subtopic_id) AS optional,
                   COALESCE(p.status, 'NOT_STARTED') AS status,
                   GREATEST(p.started_at, p.completed_at) AS progress_at,
                   COALESCE(array_agg(pr.prerequisite_subtopic_id) FILTER (WHERE pr.prerequisite_subtopic_id IS NOT NULL), '{{}}') AS prerequisites
            FROM {W}.curriculum_topics t
            JOIN {W}.curriculum_subtopics s ON s.organization_id = t.organization_id AND s.workspace_id = t.workspace_id AND s.topic_id = t.topic_id
            LEFT JOIN {W}.employee_learning_progress p ON p.organization_id = s.organization_id AND p.workspace_id = s.workspace_id
                 AND p.learning_assignment_id = :la AND p.subtopic_id = s.subtopic_id
            LEFT JOIN {W}.curriculum_prerequisites pr ON pr.organization_id = s.organization_id AND pr.workspace_id = s.workspace_id AND pr.subtopic_id = s.subtopic_id
            WHERE t.organization_id = :o AND t.workspace_id = :w AND t.curriculum_id = :c AND t.active AND s.active
            GROUP BY t.topic_id, s.subtopic_id, p.status, p.started_at, p.completed_at
            ORDER BY t.order_index, s.order_index
            """
        ),
        {"o": org, "w": ws, "c": curriculum_id, "la": learning_assignment_id},
    )
    return [dict(r._mapping) for r in rows]


def supervision_teams(conn: Connection, org: uuid.UUID, ws: uuid.UUID, employee_id: uuid.UUID) -> list[str]:
    """Team IDs this employee may supervise onboarding for (explicit learning:supervise grants only)."""
    rows = conn.execute(
        text(
            f"""SELECT DISTINCT resource_scope->>'team_id' FROM {W}.permission_grants
                WHERE organization_id = :o AND workspace_id = :w AND actor_id = :e AND action = 'learning:supervise'
                  AND valid_from <= now() AND (valid_until IS NULL OR valid_until > now())
                  AND resource_scope ? 'team_id'"""
        ),
        {"o": org, "w": ws, "e": employee_id},
    )
    return [r[0] for r in rows]


def team_learners(conn: Connection, org: uuid.UUID, ws: uuid.UUID, team_ids: list[str], exclude: uuid.UUID) -> list[dict[str, Any]]:
    rows = conn.execute(
        text(
            f"""SELECT DISTINCT e.employee_id, e.first_name, e.last_name
                FROM {W}.employee_team_memberships m
                JOIN {W}.employees e ON e.organization_id = m.organization_id AND e.workspace_id = m.workspace_id AND e.employee_id = m.employee_id
                WHERE m.organization_id = :o AND m.workspace_id = :w AND m.is_active AND m.team_id::text = ANY(:t) AND e.employee_id <> :x
                ORDER BY e.first_name, e.last_name"""
        ),
        {"o": org, "w": ws, "t": team_ids, "x": exclude},
    )
    return [dict(r._mapping) for r in rows]


# ---------------------------------------------------------------- curriculum source documents
def materialize_knowledge(conn: Connection, scenario: dict[str, Any], org: uuid.UUID, ws: uuid.UUID, ids: dict[str, uuid.UUID]) -> None:
    """Copy curriculum source documents, their typed section links and retrieval chunks.

    Documents come from the copied curricula's `curriculum_sources` (preferred, typed path) and
    from legacy `knowledge_mappings` of copied entities. Every version of a linked document is
    copied (history and current pointer intact) with its source record. For versions that are
    approved, current, the document's current pointer and from an unrevoked source, the parsed
    `knowledge_sections`, the typed `curriculum_source_sections` of copied subtopics and every
    chunk with its embedding are copied too. All IDs are remapped; nothing in the visitor copy
    references a baseline row. Fails closed if such a version has a chunk without an embedding.
    """
    src = {"o": scenario["organization_id"], "w": scenario["workspace_id"]}
    base = {"organization_id": org, "workspace_id": ws}

    def rows(sql: str, extra: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        return [dict(r._mapping) for r in conn.execute(text(sql), {**src, **(extra or {})})]

    def remap(old: Any) -> uuid.UUID | None:
        if old is None:
            return None
        key = str(old)
        if key not in ids:
            ids[key] = uuid.uuid4()
        return ids[key]

    mappings = [m for m in rows(f"SELECT * FROM {W}.knowledge_mappings WHERE organization_id=:o AND workspace_id=:w") if str(m["entity_id"]) in ids]
    sources = [c for c in rows(f"SELECT * FROM {W}.curriculum_sources WHERE organization_id=:o AND workspace_id=:w") if str(c["curriculum_id"]) in ids]
    doc_ids = sorted({str(m["document_id"]) for m in mappings} | {str(c["document_id"]) for c in sources})
    if not doc_ids:
        return
    docs = rows(f"SELECT * FROM {W}.knowledge_documents WHERE organization_id=:o AND workspace_id=:w AND document_id::text = ANY(:d)", {"d": doc_ids})
    versions = rows(f"SELECT * FROM {W}.knowledge_document_versions WHERE organization_id=:o AND workspace_id=:w AND document_id::text = ANY(:d)", {"d": doc_ids})
    source_ids = sorted({str(v["source_id"]) for v in versions if v["source_id"]})
    records = rows(f"SELECT * FROM {W}.source_records WHERE organization_id=:o AND workspace_id=:w AND source_id::text = ANY(:s)", {"s": source_ids})
    for r in records:
        if r["consent_session_id"] is not None:
            # Consent-bound sources (interviews, captures) must never be cloned into a demo copy.
            raise RuntimeError(f"Source {r['source_id']} is consent-bound and can't be copied into a visitor run.")
        conn.execute(
            text(
                f"""INSERT INTO {W}.source_records (source_id, organization_id, workspace_id, source_type, storage_object, checksum, owner_employee_id,
                        retention_until, revoked_at, evidence_type, access_partition, metadata)
                    VALUES (:id, :organization_id, :workspace_id, :t, :so, :ck, :own, :ret, :rev, :ev, :ap, CAST(:md AS jsonb))"""
            ),
            {**base, "id": remap(r["source_id"]), "t": r["source_type"], "so": r["storage_object"], "ck": r["checksum"], "own": remap(r["owner_employee_id"]), "ret": r["retention_until"], "rev": r["revoked_at"], "ev": r["evidence_type"], "ap": r["access_partition"], "md": json.dumps(r["metadata"])},
        )
    for d in docs:
        conn.execute(
            text(f"INSERT INTO {W}.knowledge_documents (document_id, organization_id, workspace_id, document_code, title, document_type) VALUES (:id, :organization_id, :workspace_id, :c, :t, :ty)"),
            {**base, "id": remap(d["document_id"]), "c": d["document_code"], "t": d["title"], "ty": d["document_type"]},
        )
    for v in versions:
        conn.execute(
            text(
                f"""INSERT INTO {W}.knowledge_document_versions (document_version_id, organization_id, workspace_id, document_id, version, content, source_id,
                        approval_status, temporal_status, effective_at, approved_by_employee_id, approved_at)
                    VALUES (:id, :organization_id, :workspace_id, :d, :v, :c, :s, :ap, :ts, :ef, :ab, :at)"""
            ),
            {**base, "id": remap(v["document_version_id"]), "d": remap(v["document_id"]), "v": v["version"], "c": v["content"], "s": remap(v["source_id"]), "ap": v["approval_status"], "ts": v["temporal_status"], "ef": v["effective_at"], "ab": remap(v["approved_by_employee_id"]), "at": v["approved_at"]},
        )
    for d in docs:
        if d["current_version_id"]:
            conn.execute(
                text(f"UPDATE {W}.knowledge_documents SET current_version_id=:v WHERE organization_id=:organization_id AND workspace_id=:workspace_id AND document_id=:id"),
                {**base, "id": remap(d["document_id"]), "v": remap(d["current_version_id"])},
            )
    for m in mappings:
        conn.execute(
            text(
                f"""INSERT INTO {W}.knowledge_mappings (mapping_id, organization_id, workspace_id, document_id, document_version_id, section_ref, entity_type, entity_id, relationship_type)
                    VALUES (:id, :organization_id, :workspace_id, :d, :v, :sr, :et, :e, :rt)"""
            ),
            {**base, "id": remap(m["mapping_id"]), "d": remap(m["document_id"]), "v": remap(m["document_version_id"]), "sr": m["section_ref"], "et": m["entity_type"], "e": remap(m["entity_id"]), "rt": m["relationship_type"]},
        )
    for c in sources:
        conn.execute(
            text(
                f"""INSERT INTO {W}.curriculum_sources (curriculum_source_id, organization_id, workspace_id, curriculum_id, document_id, document_version_id, relationship_type)
                    VALUES (:id, :organization_id, :workspace_id, :c, :d, :v, :rt)"""
            ),
            {**base, "id": remap(c["curriculum_source_id"]), "c": remap(c["curriculum_id"]), "d": remap(c["document_id"]), "v": remap(c["document_version_id"]), "rt": c["relationship_type"]},
        )

    # Retrieval material: only approved, current, unrevoked versions linked through curriculum_sources.
    revoked = {str(r["source_id"]) for r in records if r["revoked_at"] is not None}
    current_ptr = {str(d["current_version_id"]) for d in docs if d["current_version_id"]}
    linked = {str(c["document_version_id"]) for c in sources}
    live = [
        v for v in versions
        if str(v["document_version_id"]) in linked and v["approval_status"] == "APPROVED" and v["temporal_status"] == "CURRENT"
        and str(v["document_version_id"]) in current_ptr and str(v["source_id"]) not in revoked
    ]
    live_ids = [str(v["document_version_id"]) for v in live]
    if not live_ids:
        return
    sections = rows(f"SELECT * FROM {W}.knowledge_sections WHERE organization_id=:o AND workspace_id=:w AND document_version_id::text = ANY(:v)", {"v": live_ids})
    for x in sections:
        conn.execute(
            text(
                f"""INSERT INTO {W}.knowledge_sections (section_id, organization_id, workspace_id, document_version_id, section_key, topic_heading, subtopic_heading, topic_order_index, subtopic_order_index)
                    VALUES (:id, :organization_id, :workspace_id, :v, :k, :th, :sh, :to, :so)"""
            ),
            {**base, "id": remap(x["section_id"]), "v": remap(x["document_version_id"]), "k": x["section_key"], "th": x["topic_heading"], "sh": x["subtopic_heading"], "to": x["topic_order_index"], "so": x["subtopic_order_index"]},
        )
    copied_sources = {str(c["curriculum_source_id"]) for c in sources}
    links = rows(f"SELECT * FROM {W}.curriculum_source_sections WHERE organization_id=:o AND workspace_id=:w AND document_version_id::text = ANY(:v)", {"v": live_ids})
    for k in links:
        # Only links whose curriculum source, topic and subtopic were copied (the reviewed learner path).
        if str(k["curriculum_source_id"]) in copied_sources and str(k["topic_id"]) in ids and str(k["subtopic_id"]) in ids:
            conn.execute(
                text(
                    f"""INSERT INTO {W}.curriculum_source_sections (curriculum_source_section_id, organization_id, workspace_id, curriculum_source_id, curriculum_id,
                            document_version_id, section_id, topic_id, subtopic_id, relationship_type)
                        VALUES (:id, :organization_id, :workspace_id, :cs, :c, :v, :sec, :t, :st, :rt)"""
                ),
                {**base, "id": remap(k["curriculum_source_section_id"]), "cs": remap(k["curriculum_source_id"]), "c": remap(k["curriculum_id"]), "v": remap(k["document_version_id"]), "sec": remap(k["section_id"]), "t": remap(k["topic_id"]), "st": remap(k["subtopic_id"]), "rt": k["relationship_type"]},
            )
    chunks = rows(f"SELECT chunk_id, parent_chunk_id, embedding IS NOT NULL AS embedded FROM {W}.knowledge_chunks WHERE organization_id=:o AND workspace_id=:w AND document_version_id::text = ANY(:v)", {"v": live_ids})
    if any(not ch["embedded"] for ch in chunks):
        raise RuntimeError("A current source version has chunks without embeddings; refusing to create a run with an incomplete index.")
    for ch in chunks:
        remap(ch["chunk_id"])
    # Copy chunks in SQL so vectors are copied exactly (no client-side re-encoding). Parents first:
    # approved chunks can't be re-parented after insert (protect_approved_chunk).
    conn.execute(text("CREATE TEMP TABLE IF NOT EXISTS ww_id_map (old uuid PRIMARY KEY, new uuid NOT NULL) ON COMMIT DROP"))
    conn.execute(text("TRUNCATE ww_id_map"))
    conn.execute(text("INSERT INTO ww_id_map (old, new) VALUES (:old, :new)"), [{"old": k, "new": v} for k, v in ids.items()])
    done: set[str] = set()
    pending = {str(ch["chunk_id"]): (str(ch["parent_chunk_id"]) if ch["parent_chunk_id"] else None) for ch in chunks}
    while pending:
        ready = [c for c, parent in pending.items() if parent is None or parent in done]
        if not ready:
            raise RuntimeError("Chunk parent references form a cycle or point outside the copied version.")
        conn.execute(
            text(
                f"""INSERT INTO {W}.knowledge_chunks (chunk_id, organization_id, workspace_id, document_version_id, source_id, parent_chunk_id, section_path, heading,
                        content, chunk_index, source_span, embedding, embedding_model, embedding_dimension, index_generation, metadata, source_section_id)
                    SELECT m.new, :organization_id, :workspace_id, mv.new, ms.new, mp.new, c.section_path, c.heading,
                           c.content, c.chunk_index, c.source_span, c.embedding, c.embedding_model, c.embedding_dimension, c.index_generation, c.metadata, msec.new
                    FROM {W}.knowledge_chunks c
                    JOIN ww_id_map m ON m.old = c.chunk_id
                    JOIN ww_id_map mv ON mv.old = c.document_version_id
                    JOIN ww_id_map ms ON ms.old = c.source_id
                    LEFT JOIN ww_id_map mp ON mp.old = c.parent_chunk_id
                    LEFT JOIN ww_id_map msec ON msec.old = c.source_section_id
                    WHERE c.organization_id = :o AND c.workspace_id = :w AND c.chunk_id::text = ANY(:batch)"""
            ),
            {**base, **src, "batch": ready},
        )
        done.update(ready)
        for c in ready:
            pending.pop(c)


def legacy_source_versions(conn: Connection, org: uuid.UUID, ws: uuid.UUID, subtopic_ids: list[uuid.UUID]) -> list[dict[str, Any]]:
    """Fallback source path: legacy knowledge_mappings → approved, current, unrevoked version."""
    rows = conn.execute(
        text(
            f"""SELECT DISTINCT v.document_version_id, v.document_id, d.document_code, d.title, v.version, v.approval_status,
                       v.temporal_status, d.document_type, v.effective_at, e.first_name || ' ' || e.last_name AS approved_by
                FROM {W}.knowledge_mappings m
                JOIN {W}.knowledge_document_versions v ON v.organization_id = m.organization_id AND v.workspace_id = m.workspace_id AND v.document_version_id = m.document_version_id
                JOIN {W}.knowledge_documents d ON d.organization_id = v.organization_id AND d.workspace_id = v.workspace_id AND d.document_id = v.document_id
                JOIN {W}.source_records r ON r.organization_id = v.organization_id AND r.workspace_id = v.workspace_id AND r.source_id = v.source_id
                LEFT JOIN {W}.employees e ON e.organization_id = v.organization_id AND e.workspace_id = v.workspace_id AND e.employee_id = v.approved_by_employee_id
                WHERE m.organization_id = :o AND m.workspace_id = :w AND m.entity_type = 'CURRICULUM_SUBTOPIC'
                  AND m.entity_id = ANY(:s) AND m.relationship_type = 'TEACHES'
                  AND v.approval_status = 'APPROVED' AND v.temporal_status = 'CURRENT'
                  AND d.current_version_id = v.document_version_id AND r.revoked_at IS NULL
                ORDER BY d.document_code, v.version"""
        ),
        {"o": org, "w": ws, "s": subtopic_ids},
    )
    return [dict(r._mapping) for r in rows]


def typed_source_versions(conn: Connection, org: uuid.UUID, ws: uuid.UUID, subtopic_ids: list[uuid.UUID]) -> list[dict[str, Any]]:
    """Preferred source path: curriculum_source_sections → curriculum_sources → current approved version."""
    rows = conn.execute(
        text(
            f"""SELECT DISTINCT v.document_version_id, v.document_id, d.document_code, d.title, v.version, v.approval_status,
                       v.temporal_status, d.document_type, v.effective_at, e.first_name || ' ' || e.last_name AS approved_by
                FROM {W}.curriculum_source_sections css
                JOIN {W}.curriculum_sources cs ON cs.organization_id = css.organization_id AND cs.workspace_id = css.workspace_id
                     AND cs.curriculum_source_id = css.curriculum_source_id AND cs.document_version_id = css.document_version_id
                JOIN {W}.knowledge_document_versions v ON v.organization_id = cs.organization_id AND v.workspace_id = cs.workspace_id
                     AND v.document_version_id = cs.document_version_id
                JOIN {W}.knowledge_documents d ON d.organization_id = v.organization_id AND d.workspace_id = v.workspace_id AND d.document_id = v.document_id
                JOIN {W}.source_records r ON r.organization_id = v.organization_id AND r.workspace_id = v.workspace_id AND r.source_id = v.source_id
                LEFT JOIN {W}.employees e ON e.organization_id = v.organization_id AND e.workspace_id = v.workspace_id AND e.employee_id = v.approved_by_employee_id
                WHERE css.organization_id = :o AND css.workspace_id = :w AND css.subtopic_id = ANY(:s)
                  AND css.relationship_type = 'TEACHES' AND cs.relationship_type = 'TEACHES'
                  AND v.approval_status = 'APPROVED' AND v.temporal_status = 'CURRENT'
                  AND d.current_version_id = v.document_version_id AND r.revoked_at IS NULL
                ORDER BY d.document_code, v.version"""
        ),
        {"o": org, "w": ws, "s": subtopic_ids},
    )
    return [dict(r._mapping) for r in rows]


def has_typed_links(conn: Connection, org: uuid.UUID, ws: uuid.UUID, subtopic_ids: list[uuid.UUID]) -> bool:
    return bool(
        conn.execute(
            text(f"SELECT EXISTS (SELECT 1 FROM {W}.curriculum_source_sections WHERE organization_id=:o AND workspace_id=:w AND subtopic_id = ANY(:s))"),
            {"o": org, "w": ws, "s": subtopic_ids},
        ).scalar_one()
    )


def subtopic_sections(conn: Connection, org: uuid.UUID, ws: uuid.UUID, subtopic_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[dict[str, Any]]]:
    """Each subtopic's typed teaching sections in current, approved, unrevoked versions."""
    rows = conn.execute(
        text(
            f"""SELECT css.subtopic_id, ks.section_id, ks.section_key, ks.topic_heading, ks.subtopic_heading, v.version, d.document_code
                FROM {W}.curriculum_source_sections css
                JOIN {W}.knowledge_sections ks ON ks.organization_id = css.organization_id AND ks.workspace_id = css.workspace_id
                     AND ks.document_version_id = css.document_version_id AND ks.section_id = css.section_id
                JOIN {W}.knowledge_document_versions v ON v.organization_id = ks.organization_id AND v.workspace_id = ks.workspace_id
                     AND v.document_version_id = ks.document_version_id
                JOIN {W}.knowledge_documents d ON d.organization_id = v.organization_id AND d.workspace_id = v.workspace_id AND d.document_id = v.document_id
                JOIN {W}.source_records r ON r.organization_id = v.organization_id AND r.workspace_id = v.workspace_id AND r.source_id = v.source_id
                WHERE css.organization_id = :o AND css.workspace_id = :w AND css.subtopic_id = ANY(:s) AND css.relationship_type = 'TEACHES'
                  AND v.approval_status = 'APPROVED' AND v.temporal_status = 'CURRENT' AND d.current_version_id = v.document_version_id
                  AND r.revoked_at IS NULL
                ORDER BY ks.topic_order_index, ks.subtopic_order_index"""
        ),
        {"o": org, "w": ws, "s": subtopic_ids},
    )
    out: dict[uuid.UUID, list[dict[str, Any]]] = {}
    for r in rows:
        out.setdefault(r.subtopic_id, []).append(dict(r._mapping))
    return out


def teaching_chunks(conn: Connection, org: uuid.UUID, ws: uuid.UUID, subtopic_id: uuid.UUID) -> list[dict[str, Any]]:
    """Retrieval candidates for one subtopic: embedded chunks of its typed sections, current guidance only.

    Guards: same organization/workspace, TEACHES link, approved + current version that is the
    document's current pointer, unrevoked source, embedding present. Superseded versions (e.g.
    SOP-001 v3.3) can never be returned as current guidance.
    """
    rows = conn.execute(
        text(
            f"""SELECT c.chunk_id, c.document_version_id, c.source_section_id, c.chunk_index, c.heading, c.embedding_model, c.embedding_dimension
                FROM {W}.curriculum_source_sections css
                JOIN {W}.knowledge_chunks c ON c.organization_id = css.organization_id AND c.workspace_id = css.workspace_id
                     AND c.document_version_id = css.document_version_id AND c.source_section_id = css.section_id
                JOIN {W}.knowledge_document_versions v ON v.organization_id = c.organization_id AND v.workspace_id = c.workspace_id
                     AND v.document_version_id = c.document_version_id
                JOIN {W}.knowledge_documents d ON d.organization_id = v.organization_id AND d.workspace_id = v.workspace_id AND d.document_id = v.document_id
                JOIN {W}.source_records r ON r.organization_id = c.organization_id AND r.workspace_id = c.workspace_id AND r.source_id = c.source_id
                WHERE css.organization_id = :o AND css.workspace_id = :w AND css.subtopic_id = :s AND css.relationship_type = 'TEACHES'
                  AND v.approval_status = 'APPROVED' AND v.temporal_status = 'CURRENT' AND d.current_version_id = v.document_version_id
                  AND r.revoked_at IS NULL AND c.embedding IS NOT NULL
                ORDER BY c.chunk_index"""
        ),
        {"o": org, "w": ws, "s": subtopic_id},
    )
    return [dict(r._mapping) for r in rows]
