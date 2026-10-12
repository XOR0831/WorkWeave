"""The reviewer workspace (ADR-041).

For holders of team-scoped `knowledge:review`. The queue shows, for the teams they review:
- knowledge notes submitted from the Work Companion (decided here);
- Exit KT artifact revisions and successor packages waiting for review (decided in Exit KT, where
  their full context and rules are; ADR-039).
Nobody reviews their own submission. Each decision binds the exact submitted revision.

Approving a note copies that exact revision into memory_records with the audience its author asked
for; it stays a REPORTED observation (approval doesn't make it verified, complete work or change an
SOP). Rejecting needs a reason, which its author sees. The author is notified either way.
"""

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Connection, text

from app.errors import ApiError
from app.repositories import commands, work
from app.services.onboarding import _persona
from app.services.work_commands import _command, _id

W = "workweave"
ACTION = "knowledge:review"


def _rows(conn: Connection, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute(text(sql), params).mappings()]


def _teams(conn: Connection, org, ws, me) -> list[str]:
    teams = work.teams_with(conn, org, ws, me, ACTION)
    if not teams:
        raise ApiError("FORBIDDEN", "The reviewer workspace is for authorized knowledge reviewers.")
    return teams


IN_TEAMS = f"""EXISTS (SELECT 1 FROM {W}.employee_team_memberships m WHERE m.organization_id={{t}}.organization_id AND m.workspace_id={{t}}.workspace_id
                         AND m.employee_id={{t}}.{{col}} AND m.is_active AND m.team_id::text = ANY(:teams))"""


def queue(conn: Connection, token: str | None) -> list[dict[str, Any]]:
    r, me = _persona(conn, token)
    org, ws = r.session["organization_id"], r.session["workspace_id"]
    p = {"o": org, "w": ws, "me": me, "teams": _teams(conn, org, ws, me)}
    out: list[dict[str, Any]] = []
    for d in _rows(conn, f"""SELECT d.*, e.first_name || ' ' || e.last_name AS author FROM {W}.memory_drafts d
                             JOIN {W}.employees e ON e.organization_id=d.organization_id AND e.workspace_id=d.workspace_id AND e.employee_id=d.owner_employee_id
                             WHERE d.organization_id=:o AND d.workspace_id=:w AND d.status='PENDING_REVIEW' AND d.owner_employee_id <> :me
                               AND {IN_TEAMS.format(t='d', col='owner_employee_id')} ORDER BY d.updated_at""", p):
        out.append({"review_id": str(d["draft_id"]), "kind": "MEMORY_DRAFT", "title": "Knowledge note", "submitted_by": d["author"],
                    "revision_label": f"Revision {d['submitted_revision'] or d['revision']}", "content": d["content"],
                    "audience": (d["requested_audience"] or ["TEAM"])[0], "resource_id": str(d["draft_id"]), "href": "/reviews/"})
    for a in _rows(conn, f"""SELECT a.artifact_id, a.title, r.artifact_revision_id, r.version, r.content, r.audience, e.first_name || ' ' || e.last_name AS author
                             FROM {W}.exit_kt_artifacts a
                             JOIN {W}.exit_kt_artifact_revisions r ON r.organization_id=a.organization_id AND r.workspace_id=a.workspace_id AND r.artifact_revision_id=a.current_revision_id
                             JOIN {W}.exit_kt_knowledge_items i ON i.organization_id=a.organization_id AND i.workspace_id=a.workspace_id AND i.kt_item_id=a.kt_item_id
                             JOIN {W}.exit_kt_cases c ON c.organization_id=i.organization_id AND c.workspace_id=i.workspace_id AND c.exit_kt_case_id=i.exit_kt_case_id
                             JOIN {W}.employees e ON e.organization_id=c.organization_id AND e.workspace_id=c.workspace_id AND e.employee_id=c.employee_id
                             WHERE a.organization_id=:o AND a.workspace_id=:w AND r.status='PENDING_REVIEW' AND c.employee_id <> :me
                               AND {IN_TEAMS.format(t='c', col='employee_id')} ORDER BY r.submitted_at""", p):
        out.append({"review_id": str(a["artifact_revision_id"]), "kind": "KT_ARTIFACT", "title": a["title"], "submitted_by": a["author"], "revision_label": f"v{a['version']}",
                    "content": a["content"], "audience": a["audience"], "resource_id": str(a["artifact_id"]), "href": "/exit-kt/?area=knowledge"})
    for k in _rows(conn, f"""SELECT p.package_id, p.revision, p.draft_sections, e.first_name || ' ' || e.last_name AS author, s.first_name || ' ' || s.last_name AS successor
                             FROM {W}.exit_kt_packages p
                             JOIN {W}.exit_kt_cases c ON c.organization_id=p.organization_id AND c.workspace_id=p.workspace_id AND c.exit_kt_case_id=p.exit_kt_case_id
                             JOIN {W}.employees e ON e.organization_id=c.organization_id AND e.workspace_id=c.workspace_id AND e.employee_id=c.employee_id
                             JOIN {W}.employees s ON s.organization_id=p.organization_id AND s.workspace_id=p.workspace_id AND s.employee_id=p.successor_employee_id
                             WHERE p.organization_id=:o AND p.workspace_id=:w AND p.status='PENDING_REVIEW' AND c.employee_id <> :me
                               AND {IN_TEAMS.format(t='c', col='employee_id')}""", p):
        out.append({"review_id": str(k["package_id"]), "kind": "KT_PACKAGE", "title": f"Successor package for {k['successor']}", "submitted_by": k["author"],
                    "revision_label": f"Revision {k['revision']}", "content": "\n".join(f"{x.get('title')}: {x.get('content')}" for x in k["draft_sections"] or []),
                    "audience": "Successor", "resource_id": str(k["package_id"]), "href": "/exit-kt/?area=responsibility"})
    return out


def decide_note(conn: Connection, token: str | None, draft_id: str, decision: str, comment: str, key: str, request_id) -> dict[str, Any]:
    payload = {"draft_id": draft_id, "decision": decision, "comment": comment}

    def run(r: Any, me) -> tuple[dict[str, Any], int]:
        org, ws = r.session["organization_id"], r.session["workspace_id"]
        teams = _teams(conn, org, ws, me)
        rows = _rows(conn, f"SELECT * FROM {W}.memory_drafts WHERE organization_id=:o AND workspace_id=:w AND draft_id=:d FOR UPDATE", {"o": org, "w": ws, "d": _id(draft_id, "note")})
        if not rows:
            raise ApiError("NOT_FOUND", "Note not found.")
        d = rows[0]
        if d["owner_employee_id"] == me:
            raise ApiError("FORBIDDEN", "You can't review your own knowledge note.")
        if not _rows(conn, f"""SELECT 1 FROM {W}.employee_team_memberships WHERE organization_id=:o AND workspace_id=:w AND employee_id=:e AND is_active AND team_id::text = ANY(:t)""",
                     {"o": org, "w": ws, "e": d["owner_employee_id"], "t": teams}):
            raise ApiError("FORBIDDEN", "This note is from a team you don't review.")
        if d["status"] != "PENDING_REVIEW":
            raise ApiError("GUARD_FAILED", "This note isn't waiting for review.")
        if decision == "REJECT" and not comment.strip():
            raise ApiError("MALFORMED_INPUT", "Explain why the note isn't approved; its author sees it.")
        status = "APPROVED" if decision == "APPROVE" else "REJECTED"
        new = _rows(conn, f"""UPDATE {W}.memory_drafts SET status=:s, review_comment=:c, updated_at=now(), revision=revision+1
                              WHERE organization_id=:o AND workspace_id=:w AND draft_id=:d RETURNING *""",
                    {"o": org, "w": ws, "d": d["draft_id"], "s": status, "c": comment.strip() or None})[0]
        if status == "APPROVED":
            conn.execute(text(f"""INSERT INTO {W}.memory_records (organization_id, workspace_id, originating_draft_id, approved_content_revision, content, evidence_type,
                                     source_refs, approved_audience, approved_by, approved_at)
                                  VALUES (:o, :w, :d, :rev, :content, 'REPORTED', CAST(:refs AS jsonb), CAST(:aud AS jsonb), :me, :t)"""),
                         {"o": org, "w": ws, "d": d["draft_id"], "rev": d["submitted_revision"] or d["revision"], "content": d["content"],
                          "refs": json.dumps(d["evidence_refs"] or []), "aud": json.dumps(d["requested_audience"] or ["TEAM"]), "me": me, "t": datetime.now(UTC)})
        work.outbox(conn, org, ws, request_id, d["owner_employee_id"], "memory_draft", d["draft_id"], new["revision"], "knowledge.note_decided", {"status": status})
        commands.audit(conn, org, ws, me, f"memory_draft.{status.lower()}", "memory_draft", d["draft_id"], new["revision"], request_id)
        return {"draft_id": str(d["draft_id"]), "status": status}, new["revision"]

    return _command(conn, token, "memory_draft.decide", key, payload, run)
