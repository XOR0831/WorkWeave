"""The Shift Handover graph in the workspace (docs/31, ADR-043).

Only for shift leads (handover.Ctx). The graph runs outside any database transaction and only
proposes. Before anything is stored, every record it cites is checked against this handover's own
records (the team's tickets and their updates, the handover's items, the team's publications,
approved knowledge in this workspace); anything else is dropped.

- Gap check (outgoing lead): suggestions are stored as PENDING, marked as from the AI engine, with
  their evidence; the previous check's unreviewed ones are replaced. Clarification questions
  go into the lead's copilot conversation. The lead accepts or ignores each one as before.
- Draft (outgoing lead): proposed section text for the editor; nothing is stored until the lead saves.
- Copilot (any lead): the lead's message and the answer are stored in their private conversation.
  A proposed edit is only applied if the lead applies it (an ordinary section edit).
Nothing here publishes, completes, acknowledges or approves anything.
"""

import json
import uuid as _uuid
from typing import Any

from sqlalchemy import Connection, text

from app.db import transaction
from app.errors import ApiError
from app.integrations import handover_engine
from app.repositories import commands, work
from app.repositories import handover as repo
from app.services import handover, usage
from app.services.work_commands import _command

W = "workweave"
NOT_CONNECTED = "The handover companion isn't connected right now. The handover itself, its items and publications come from the database."
SOURCE_ROW_TYPE = {"WORK_ITEM": "TICKET", "WORK_EVENT": "WORK_EVENT", "REPORTED_UPDATE": "WORK_EVENT", "KNOWLEDGE_CHUNK": "DOCUMENT"}


def available() -> bool:
    return handover_engine.engine() is not None


def _engine():
    e = handover_engine.engine()
    if not e:
        raise ApiError("CAPABILITY_UNAVAILABLE", NOT_CONNECTED)
    return e


def _run(request: dict[str, Any]) -> dict[str, Any]:
    try:
        out = _engine().run(request)
    except handover_engine.HandoverEngineError as e:
        raise ApiError("DEPENDENCY_UNAVAILABLE", f"{e} Nothing was changed; try again.") from None
    if out.get("status") == "FORBIDDEN":
        raise ApiError("FORBIDDEN", (out.get("warnings") or ["Shift Handover is for shift leads."])[0])
    if out.get("status") == "FAILED":
        raise ApiError("GUARD_FAILED", (out.get("warnings") or ["The handover assistant couldn't do that."])[0])
    return out


def _request(c: handover.Ctx, h: dict[str, Any], operation: str, **extra: Any) -> dict[str, Any]:
    return {"organization_id": str(c.org), "workspace_id": str(c.ws), "handover_id": str(h["handover_id"]), "employee_id": str(c.me), "operation": operation, **extra}


def _handover(c: handover.Ctx) -> dict[str, Any]:
    h = c.handover()
    if not h:
        raise ApiError("GUARD_FAILED", "There's no handover for the shift in progress yet.")
    return h


# ---------------------------------------------------------------- checking what the graph cites
def _allowed(conn: Connection, c: handover.Ctx) -> dict[str, set[str]]:
    """IDs this handover may cite, by type (the backend's own view of the handover's records)."""
    p = {"o": c.org, "w": c.ws}
    tickets = {str(x["work_item_id"]) for x in work.visible_items(conn, c.org, c.ws, [c.team])}
    items = {str(x["handover_item_id"]) for x in repo.items(conn, c.org, c.ws, [o["shift_instance_id"] for o in c.occurrences])}
    rows = lambda sql: {str(r[0]) for r in conn.execute(text(sql), {**p, "ids": list(tickets)}).all()} if tickets else set()  # noqa: E731
    pubs = {str(x["publication_id"]) for x in repo.publications(conn, c.org, c.ws, [h["handover_id"] for h in repo.team_handovers(conn, c.org, c.ws, [o["shift_instance_id"] for o in c.occurrences])])}
    return {
        "WORK_ITEM": tickets,
        "HANDOVER_ITEM": items,
        "WORK_EVENT": rows(f"SELECT work_event_id FROM {W}.work_events WHERE organization_id=:o AND workspace_id=:w AND work_item_id::text = ANY(:ids)"),
        "REPORTED_UPDATE": rows(f"SELECT reported_update_id FROM {W}.work_item_reported_updates WHERE organization_id=:o AND workspace_id=:w AND work_item_id::text = ANY(:ids)"),
        "PUBLICATION": pubs,
    }


def _chunk_ok(conn: Connection, c: handover.Ctx, chunk_id: str) -> bool:
    try:
        cid = _uuid.UUID(chunk_id)
    except ValueError:
        return False
    return bool(conn.execute(text(f"""SELECT 1 FROM {W}.knowledge_chunks k JOIN {W}.knowledge_documents d ON d.organization_id=k.organization_id AND d.workspace_id=k.workspace_id
                                       AND d.current_version_id=k.document_version_id
                                       JOIN {W}.knowledge_document_versions v ON v.organization_id=k.organization_id AND v.workspace_id=k.workspace_id AND v.document_version_id=k.document_version_id
                                       WHERE k.organization_id=:o AND k.workspace_id=:w AND k.chunk_id=:c AND v.approval_status='APPROVED' AND v.temporal_status='CURRENT'"""),
                             {"o": c.org, "w": c.ws, "c": cid}).first())


def _citations(conn: Connection, c: handover.Ctx, allowed: dict[str, set[str]], cites: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for x in cites or []:
        kind, sid = x.get("source_type"), str(x.get("source_id") or "")
        ok = _chunk_ok(conn, c, sid) if kind == "KNOWLEDGE_CHUNK" else sid in allowed.get(kind, set())
        if ok:
            out.append({"source_type": kind, "source_id": sid, "label": str(x.get("label") or "")[:200]})
    return out


# ---------------------------------------------------------------- gap check
def check(token: str | None, key: str, request_id) -> dict[str, Any]:
    with transaction() as conn:
        c = handover.Ctx(conn, token)
        c.require_lead()
        h = _handover(c)
        if commands.find_receipt(conn, c.org, c.ws, c.me, "handover.ai_check", key):
            return _command(conn, token, "handover.ai_check", key, {"handover_id": str(h["handover_id"])}, lambda r, me: ({}, 1))
        usage.charge(conn, "TUTOR_TURN", c.ws, c.session)  # an assistant message (demo caps); refused → nothing runs
        req = _request(c, h, "CHECK")
    out = _run(req)  # outside the transaction

    with transaction() as conn:
        def run(r: Any, me) -> tuple[dict[str, Any], int]:
            c = handover.Ctx(conn, token)
            c.require_lead()
            h = c.handover(lock=True)
            allowed = _allowed(conn, c)
            # The previous check's unreviewed suggestions are replaced by this one.
            conn.execute(text(f"""UPDATE {W}.handover_suggestions SET status='IGNORED', reviewed_by_employee_id=:me, reviewed_at=now(), updated_at=now(), revision=revision+1,
                                     suggested_data = suggested_data || '{{"replaced_by_new_check": true}}'::jsonb
                                  WHERE organization_id=:o AND workspace_id=:w AND handover_id=:h AND status='PENDING' AND suggested_data->>'origin' = 'AI_ENGINE'"""),
                         {"o": c.org, "w": c.ws, "h": h["handover_id"], "me": me})
            stored = 0
            for s in out.get("suggestions") or []:
                hid, wid = s.get("handover_item_id"), s.get("work_item_id")
                if (hid and hid not in allowed["HANDOVER_ITEM"]) or (wid and wid not in allowed["WORK_ITEM"]):
                    continue
                cites = _citations(conn, c, allowed, s.get("citations"))
                if not cites:
                    continue  # nothing verifiable behind it
                data = {"origin": "AI_ENGINE", "title": s.get("title"), "proposed_note": s.get("proposed_note"), "section": s.get("section_name"), "work_item_id": wid,
                        "evidence_type": s.get("evidence_type"), "model": out.get("model"), "prompt_version": out.get("prompt_version")}
                sid = conn.execute(text(f"""INSERT INTO {W}.handover_suggestions (organization_id, workspace_id, handover_id, handover_item_id, suggestion_type, suggested_data, reason, source_refs, context_revisions)
                                            VALUES (:o, :w, :h, :i, :t, CAST(:d AS jsonb), :r, CAST(:refs AS jsonb), CAST(:ctx AS jsonb)) RETURNING suggestion_id"""),
                                   {"o": c.org, "w": c.ws, "h": h["handover_id"], "i": _uuid.UUID(hid) if hid else None, "t": s["suggestion_type"], "d": json.dumps(data),
                                    "r": (s.get("reason") or "")[:1000], "refs": json.dumps(cites), "ctx": json.dumps({"handover_revision": h["revision"]})}).scalar_one()
                for x in cites:  # evidence rows, attached to the item if the lead accepts it
                    if x["source_type"] in SOURCE_ROW_TYPE:
                        conn.execute(text(f"""INSERT INTO {W}.handover_item_sources (organization_id, workspace_id, suggestion_id, source_type, external_id, source_reference, extracted_data, detected_by_ai)
                                              VALUES (:o, :w, :s, :t, :e, :ref, CAST(:x AS jsonb), true)"""),
                                     {"o": c.org, "w": c.ws, "s": sid, "t": SOURCE_ROW_TYPE[x["source_type"]], "e": x["label"].split(" · ")[0][:100] if x["source_type"] == "WORK_ITEM" else None,
                                      "ref": x["source_id"], "x": json.dumps({"cited_as": x["source_type"], "label": x["label"]})})
                stored += 1
            # All of a check's questions go in one message, as a bulleted list (owner, 2026-10-11).
            asked, cites = [], []
            for q in out.get("questions") or []:
                t = " ".join((q.get("question") or "").split())
                if t and t.lower() not in {a.lower() for a in asked}:
                    asked.append(t)
                    cites += [x for x in _citations(conn, c, allowed, q.get("citations")) if (x["source_type"], x["source_id"]) not in {(y["source_type"], y["source_id"]) for y in cites}]
            if asked:
                body = asked[0] if len(asked) == 1 else "Questions from the gap check:\n" + "\n".join(f"- {a}" for a in asked)
                _add_message(conn, c, h, "AI", "QUESTION", body, cites, [], None, out.get("model"))
            if not stored and not asked:
                _add_message(conn, c, h, "SYSTEM", "MESSAGE", "Gap check: nothing to add. The records don't show missing, outdated or duplicate items.", [], [], None, out.get("model"))
            commands.audit(conn, c.org, c.ws, me, "shift_handover.ai_check", "shift_handover", h["handover_id"], h["revision"], request_id)
            return handover.view(c), h["revision"]

        return _command(conn, token, "handover.ai_check", key, {"handover_id": req["handover_id"]}, run)


# ---------------------------------------------------------------- section drafts (never stored)
def draft(token: str | None, section_ids: list[str]) -> dict[str, Any]:
    with transaction() as conn:
        c = handover.Ctx(conn, token)
        c.require_lead()
        h = _handover(c)
        usage.charge(conn, "TUTOR_TURN", c.ws, c.session)  # an assistant message (demo caps); refused → nothing runs
        req = _request(c, h, "DRAFT", section_ids=section_ids)
    out = _run(req)
    with transaction() as conn:
        c = handover.Ctx(conn, token)
        allowed = _allowed(conn, c)
        known = {str(s["section_id"]) for s in repo.sections(conn, c.org, c.ws, h["template_version_id"])}
        drafts = [{"section_id": d["section_id"], "section_name": d.get("section_name") or "", "content": d.get("content") or "", "unknowns": d.get("unknowns") or [],
                   "citations": _citations(conn, c, allowed, d.get("citations"))} for d in out.get("drafts") or [] if d.get("section_id") in known]
    return {"drafts": drafts, "warnings": out.get("warnings") or []}


# ---------------------------------------------------------------- copilot
def _add_message(conn: Connection, c: handover.Ctx, h: dict[str, Any], sender: str, kind: str, content: str, citations, unknowns, proposed_edit, model) -> None:
    if not content.strip():
        return
    # clock_timestamp(): a question and its answer, saved together, keep their order.
    conn.execute(text(f"""INSERT INTO {W}.handover_copilot_messages (organization_id, workspace_id, handover_id, employee_id, sender, kind, content, citations, unknowns, proposed_edit, model, created_at)
                          VALUES (:o, :w, :h, :e, :s, :k, :t, CAST(:c AS jsonb), CAST(:u AS jsonb), CAST(:p AS jsonb), :m, clock_timestamp())"""),
                 {"o": c.org, "w": c.ws, "h": h["handover_id"], "e": c.me, "s": sender, "k": kind, "t": content.strip()[:8000], "c": json.dumps(citations or []),
                  "u": json.dumps(unknowns or []), "p": json.dumps(proposed_edit) if proposed_edit else None, "m": model})


def ask(token: str | None, message: str, key: str, request_id) -> dict[str, Any]:
    with transaction() as conn:
        c = handover.Ctx(conn, token)
        h = _handover(c)
        if commands.find_receipt(conn, c.org, c.ws, c.me, "handover.copilot", key):
            return _command(conn, token, "handover.copilot", key, {"message": message}, lambda r, me: ({}, 1))
        usage.charge(conn, "TUTOR_TURN", c.ws, c.session)  # an assistant message (demo caps); refused → nothing runs
        req = _request(c, h, "ASK", message=message.strip() or None)
    out = _run(req)
    answer = out.get("answer") or {}

    with transaction() as conn:
        def run(r: Any, me) -> tuple[dict[str, Any], int]:
            c = handover.Ctx(conn, token)
            h = _handover(c)
            allowed = _allowed(conn, c)
            edit = answer.get("proposed_edit")
            if not (c.is_lead and edit and edit.get("section_id") in {str(s["section_id"]) for s in repo.sections(conn, c.org, c.ws, h["template_version_id"])}):
                edit = None
            if message.strip():
                _add_message(conn, c, h, "LEAD", "MESSAGE", message, [], [], None, None)
            _add_message(conn, c, h, "AI", "MESSAGE" if message.strip() else "BRIEF", answer.get("text") or "I couldn't answer that from the records.",
                         _citations(conn, c, allowed, answer.get("citations")), answer.get("unknowns") or [], edit, out.get("model"))
            return handover.view(c), h["revision"]

        return _command(conn, token, "handover.copilot", key, {"message": message}, run)


def messages(conn: Connection, c: handover.Ctx, h: dict[str, Any] | None) -> list[dict[str, Any]]:
    """The lead's own copilot conversation, oldest first (never another lead's)."""
    rows = [] if not h else [dict(r) for r in conn.execute(
        text(f"""SELECT * FROM {W}.handover_copilot_messages WHERE organization_id=:o AND workspace_id=:w AND handover_id=:h AND employee_id=:e ORDER BY created_at, message_id"""),
        {"o": c.org, "w": c.ws, "h": h["handover_id"], "e": c.me}).mappings()]
    out = []
    for m in rows:
        out.append({
            "message_id": str(m["message_id"]),
            "sender": {"LEAD": "EMPLOYEE", "AI": "AI", "SYSTEM": "SYSTEM"}[m["sender"]],
            "text": m["content"] + ("\n\nNot in the records: " + "; ".join(m["unknowns"]) if m["unknowns"] else ""),
            "citations": [{"citation_id": f"{m['message_id']}-{i}", "label": x["label"] or x["source_type"].replace("_", " ").lower(),
                           "excerpt": {"source_id": x["source_id"], "document_version_id": "", "heading_path": [x["label"]], "text": x["label"], "evidence_type": "OBSERVED"}}
                          for i, x in enumerate(m["citations"])],
            "provenance": "EMPLOYEE_INPUT" if m["sender"] == "LEAD" else "HANDOVER_ENGINE" if m["sender"] == "AI" else "BACKEND_RECORD",
            **({"proposed_edit": m["proposed_edit"]} if m["proposed_edit"] else {}),
            **({"kind": m["kind"]} if m["kind"] != "MESSAGE" else {}),
        })
    if not out and not available():
        out.append({"message_id": "copilot-not-connected", "sender": "SYSTEM", "text": NOT_CONNECTED, "citations": [], "provenance": "BACKEND_RECORD"})
    return out
