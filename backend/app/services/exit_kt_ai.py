"""The Exit KT graph in the case workspace (docs/32, ADR-044).

The graph runs outside any database transaction and only proposes. Before anything is stored, every
record it cites is checked against this case's own records (its responsibilities, transfers,
knowledge items and findings; the tickets and updates of the person handing over; approved
documents; the team's competency evidence; this interview's answers; the approved package; approved
knowledge in this workspace). Anything else is dropped.

- Discovery (employee or manager): the inventory is kept on the case until the next run; new
  findings, plan items (PROPOSED checklist items) and new knowledge areas are stored as AI proposals;
  every knowledge item's deterministic risk is refreshed.
- Interview (employee): within a consent the employee gives first; private to them.
- Draft from interview (employee): a private draft revision, never submitted by itself.
- Successor recommendation (manager): recommended owner and reason on the transfer; never the owner.
- Copilot (employee, manager, successor): a private conversation per case and person.
Nothing here approves, publishes, completes, receives or transfers anything.
"""

import json
import uuid as _uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Connection, text

from app.db import transaction
from app.errors import ApiError
from app.integrations import exit_kt_engine
from app.repositories import commands, exit_kt as repo, work
from app.services import exit_kt, usage
from app.services.handover_ai import _chunk_ok
from app.services.work_commands import _command, _id

W = "workweave"
NOT_CONNECTED = "The knowledge-transfer assistant isn't connected right now. The case, its items and approvals come from the database; you can still work on them by hand."
SOURCE_ROW = {"WORK_ITEM": "TICKET", "WORK_EVENT": "WORK_HISTORY", "DOCUMENT_VERSION": "DOCUMENT"}
NOTICE = "kt-interview-v1"


def available() -> bool:
    return exit_kt_engine.engine() is not None


def _run(request: dict[str, Any]) -> dict[str, Any]:
    e = exit_kt_engine.engine()
    if not e:
        raise ApiError("CAPABILITY_UNAVAILABLE", NOT_CONNECTED)
    try:
        out = e.run(request)
    except exit_kt_engine.ExitKtEngineError as err:
        raise ApiError("DEPENDENCY_UNAVAILABLE", f"{err} Nothing was changed; try again.") from None
    if out.get("status") == "FORBIDDEN":
        raise ApiError("FORBIDDEN", (out.get("warnings") or ["You aren't part of this knowledge-transfer case."])[0])
    if out.get("status") == "FAILED":
        raise ApiError("GUARD_FAILED", (out.get("warnings") or ["The knowledge-transfer assistant couldn't do that."])[0])
    return out


def _request(c: exit_kt.Ctx, operation: str, **extra: Any) -> dict[str, Any]:
    return {"organization_id": str(c.org), "workspace_id": str(c.ws), "exit_kt_case_id": str(c.case["exit_kt_case_id"]), "employee_id": str(c.me), "operation": operation, **extra}


def _ctx(conn: Connection, token, need: str) -> exit_kt.Ctx:
    c = exit_kt.Ctx(conn, token)
    if not c.case:
        raise ApiError("FORBIDDEN", "You aren't part of an Exit KT case in this workspace.")
    if need == "SUBJECT" and c.role != "SUBJECT":
        raise ApiError("FORBIDDEN", "Only the employee does this for their own knowledge transfer.")
    if need == "MANAGER" and not (c.can_review or c.can_manage):
        raise ApiError("FORBIDDEN", "This is for the manager running the knowledge transfer.")
    if need == "DISCOVER" and not (c.role == "SUBJECT" or c.can_review or c.can_manage):
        raise ApiError("FORBIDDEN", "Discovery is for the employee and the manager.")
    return c


# ---------------------------------------------------------------- checking what the graph cites
def _allowed(conn: Connection, c: exit_kt.Ctx, interview_id=None) -> dict[str, set[str]]:
    p = {"o": c.org, "w": c.ws, "c": c.case["exit_kt_case_id"], "e": c.case["employee_id"]}
    ids = lambda sql, extra=None: {str(r[0]) for r in conn.execute(text(sql), {**p, **(extra or {})}).all()}  # noqa: E731
    teams = repo.employee_teams(conn, c.org, c.ws, c.case["employee_id"])
    return {
        "RESPONSIBILITY": ids(f"""SELECT responsibility_id FROM {W}.responsibilities WHERE organization_id=:o AND workspace_id=:w AND (owner_employee_id=:e OR responsibility_id IN
                                  (SELECT responsibility_id FROM {W}.responsibility_transfers WHERE organization_id=:o AND workspace_id=:w AND exit_kt_case_id=:c))"""),
        "TRANSFER": ids(f"SELECT transfer_id FROM {W}.responsibility_transfers WHERE organization_id=:o AND workspace_id=:w AND exit_kt_case_id=:c"),
        "KNOWLEDGE_ITEM": ids(f"SELECT kt_item_id FROM {W}.exit_kt_knowledge_items WHERE organization_id=:o AND workspace_id=:w AND exit_kt_case_id=:c"),
        "FINDING": ids(f"SELECT finding_id FROM {W}.exit_kt_findings WHERE organization_id=:o AND workspace_id=:w AND exit_kt_case_id=:c"),
        "WORK_ITEM": ids(f"""SELECT work_item_id FROM {W}.work_item_assignments WHERE organization_id=:o AND workspace_id=:w AND employee_id=:e
                             UNION SELECT work_item_id FROM {W}.work_events WHERE organization_id=:o AND workspace_id=:w AND employee_id=:e
                             UNION SELECT work_item_id FROM {W}.work_item_assignments WHERE organization_id=:o AND workspace_id=:w AND employee_id IN
                               (SELECT employee_id FROM {W}.employee_team_memberships WHERE organization_id=:o AND workspace_id=:w AND is_active AND team_id::text = ANY(:t))""",
                         {"t": teams}),
        "WORK_EVENT": ids(f"SELECT work_event_id FROM {W}.work_events WHERE organization_id=:o AND workspace_id=:w AND employee_id=:e"),
        "DOCUMENT_VERSION": ids(f"SELECT document_version_id FROM {W}.knowledge_document_versions WHERE organization_id=:o AND workspace_id=:w AND approval_status='APPROVED'"),
        "COMPETENCY_EVIDENCE": ids(f"""SELECT evidence_id FROM {W}.employee_competency_evidence WHERE organization_id=:o AND workspace_id=:w AND employee_id IN
                                       (SELECT employee_id FROM {W}.employee_team_memberships WHERE organization_id=:o AND workspace_id=:w AND is_active AND team_id::text = ANY(:t))""",
                                   {"t": teams}),
        "INTERVIEW_MESSAGE": ids(f"SELECT message_id FROM {W}.exit_kt_interview_messages WHERE organization_id=:o AND workspace_id=:w AND interview_id=:i",
                                 {"i": interview_id}) if interview_id else set(),
        "PACKAGE_VERSION": ids(f"""SELECT v.package_version_id FROM {W}.exit_kt_package_versions v JOIN {W}.exit_kt_packages pk ON pk.organization_id=v.organization_id
                                   AND pk.workspace_id=v.workspace_id AND pk.package_id=v.package_id WHERE pk.organization_id=:o AND pk.workspace_id=:w AND pk.exit_kt_case_id=:c"""),
        "ARTIFACT_REVISION": ids(f"""SELECT kp.artifact_revision_id FROM {W}.knowledge_promotions kp WHERE kp.organization_id=:o AND kp.workspace_id=:w"""),
    }


def _citations(conn: Connection, c: exit_kt.Ctx, allowed: dict[str, set[str]], cites) -> list[dict[str, Any]]:
    out = []
    for x in cites or []:
        kind, sid = x.get("source_type"), str(x.get("source_id") or "")
        if (_chunk_ok(conn, c, sid) if kind == "KNOWLEDGE_CHUNK" else sid in allowed.get(kind, set())):
            out.append({"source_type": kind, "source_id": sid, "label": str(x.get("label") or "")[:200]})
    return out


def _message(conn: Connection, c: exit_kt.Ctx, sender: str, content: str, citations=None, unknowns=None, model=None) -> None:
    if content.strip():
        conn.execute(text(f"""INSERT INTO {W}.exit_kt_copilot_messages (organization_id, workspace_id, exit_kt_case_id, employee_id, sender, content, citations, unknowns, model, created_at)
                              VALUES (:o, :w, :c, :e, :s, :t, CAST(:ci AS jsonb), CAST(:u AS jsonb), :m, clock_timestamp())"""),
                     {"o": c.org, "w": c.ws, "c": c.case["exit_kt_case_id"], "e": c.me, "s": sender, "t": content.strip()[:8000],
                      "ci": json.dumps(citations or []), "u": json.dumps(unknowns or []), "m": model})


# ---------------------------------------------------------------- discovery
def discover(token: str | None, key: str, request_id) -> dict[str, Any]:
    with transaction() as conn:
        c = _ctx(conn, token, "DISCOVER")
        if commands.find_receipt(conn, c.org, c.ws, c.me, "exit_kt.discover", key):
            return _command(conn, token, "exit_kt.discover", key, {}, lambda r, me: ({}, 1))
        usage.charge(conn, "TUTOR_TURN", c.ws, c.session)  # an assistant message (demo caps); refused → nothing runs
        req = _request(c, "DISCOVER")
    out = _run(req)  # outside the transaction
    d = out.get("discovery") or {}

    with transaction() as conn:
        def run(r: Any, me) -> tuple[dict[str, Any], int]:
            c = exit_kt.Ctx(conn, token, lock=True)
            allowed = _allowed(conn, c)
            cid = c.case["exit_kt_case_id"]
            now = datetime.now(UTC)
            ok = lambda xs: _citations(conn, c, allowed, xs)  # noqa: E731
            # Deterministic risk, refreshed on every knowledge item it scored.
            for risk in d.get("risks") or []:
                if risk.get("area_type") == "KNOWLEDGE_ITEM" and risk.get("area_id") in allowed["KNOWLEDGE_ITEM"]:
                    it = repo.get(conn, "exit_kt_knowledge_items", c.org, c.ws, _uuid.UUID(risk["area_id"]), lock=True)
                    repo.update(conn, "exit_kt_knowledge_items", it, risk_level=risk["level"], risk_score=risk["score"], risk_factors=risk["factors"])
            # New knowledge areas the records show.
            for area in d.get("new_areas") or []:
                cites = ok(area.get("citations"))
                if not cites:
                    continue
                risk = area.get("risk") or {}
                it = repo.insert(conn, "exit_kt_knowledge_items", c.org, c.ws, exit_kt_case_id=cid, title=area["title"][:200], description=area.get("description") or None,
                                 documentation_status="NEEDS_REVIEW", kt_status="NOT_STARTED", risk_level=risk.get("level") or "MEDIUM", origin="AI_ENGINE",
                                 risk_score=risk.get("score"), risk_factors=risk.get("factors") or [])
                for x in cites:
                    if x["source_type"] in SOURCE_ROW:
                        repo.insert(conn, "exit_kt_sources", c.org, c.ws, kt_item_id=it["kt_item_id"], source_type=SOURCE_ROW[x["source_type"]], source_reference=x["source_id"],
                                    relevance_data={"origin": "AI_ENGINE", "label": x["label"]})
            # New findings, open for review.
            for f in d.get("findings") or []:
                cites = ok(f.get("citations"))
                kid = f.get("kt_item_id") if f.get("kt_item_id") in allowed["KNOWLEDGE_ITEM"] else None
                if cites:
                    repo.insert(conn, "exit_kt_findings", c.org, c.ws, exit_kt_case_id=cid, kt_item_id=_uuid.UUID(kid) if kid else None, finding_type=f["finding_type"],
                                description=f["description"][:1000], evidence_refs=cites, status="OPEN", origin="AI_ENGINE")
            # The plan: proposed checklist items (the previous run's unreviewed ones are replaced).
            conn.execute(text(f"""UPDATE {W}.kt_checklist_items SET proposal_status='DECLINED', updated_at=now(), revision=revision+1
                                  WHERE organization_id=:o AND workspace_id=:w AND exit_kt_case_id=:c AND origin='AI_ENGINE' AND proposal_status='PROPOSED'"""),
                         {"o": c.org, "w": c.ws, "c": cid})
            for x in d.get("plan") or []:
                kid = x.get("kt_item_id") if x.get("kt_item_id") in allowed["KNOWLEDGE_ITEM"] else None
                rid = x.get("responsibility_id") if x.get("responsibility_id") in allowed["RESPONSIBILITY"] else None
                repo.insert(conn, "kt_checklist_items", c.org, c.ws, exit_kt_case_id=cid, knowledge_item_id=_uuid.UUID(kid) if kid else None,
                            responsibility_id=_uuid.UUID(rid) if rid else None, required=False, status="OPEN", title=x["title"][:300], method=x["method"],
                            priority=x.get("priority"), completion_criteria=x.get("completion_criteria"), origin="AI_ENGINE", proposal_status="PROPOSED",
                            evidence_sources=ok(x.get("citations")))
            # The inventory itself, kept on the case until the next run (citations re-checked).
            kept = {
                "overview": d.get("overview") or "",
                "responsibilities": [{**x, "citations": ok(x.get("citations"))} for x in d.get("responsibilities") or []
                                     if x.get("ownership") == "INFERRED" or x.get("responsibility_id") in allowed["RESPONSIBILITY"]],
                "expertise": [{**x, "citations": ok(x.get("citations"))} for x in d.get("expertise") or [] if ok(x.get("citations"))],
                "changes": [{**x, "citations": ok(x.get("citations"))} for x in d.get("changes") or [] if ok(x.get("citations"))],
                "documents": [x for x in d.get("documents") or [] if x.get("document_version_id") in allowed["DOCUMENT_VERSION"]],
                "open_work": [x for x in d.get("open_work") or [] if x.get("work_item_id") in allowed["WORK_ITEM"]],
                "risks": d.get("risks") or [],
                "risk_explanations": [{**x, "citations": ok(x.get("citations"))} for x in d.get("risk_explanations") or []],
                "unknowns": d.get("unknowns") or [],
                "model": out.get("model"), "prompt_version": out.get("prompt_version"), "discovered_at": now.isoformat(), "discovered_by": str(me),
            }
            repo.update(conn, "exit_kt_cases", c.case, discovery=kept, status="IN_PROGRESS" if c.case["status"] == "DISCOVERY" else c.case["status"])
            commands.audit(conn, c.org, c.ws, me, "exit_kt_case.discovered", "exit_kt_case", cid, c.case["revision"] + 1, request_id)
            return exit_kt.view(exit_kt.Ctx(conn, token)), c.case["revision"] + 1

        return _command(conn, token, "exit_kt.discover", key, {}, run)


# ---------------------------------------------------------------- plan items (the manager decides)
def decide_plan_item(conn: Connection, token, item_id: str, decision: str, required: bool, key: str, expected_revision, request_id):
    def body(c: exit_kt.Ctx):
        c.manager("Only the authorized manager accepts plan items.")
        x = repo.get(conn, "kt_checklist_items", c.org, c.ws, _id(item_id, "plan item"), lock=True)
        if not x or x["exit_kt_case_id"] != c.case["exit_kt_case_id"]:
            raise ApiError("NOT_FOUND", "Plan item not found.")
        if x["proposal_status"] != "PROPOSED":
            raise ApiError("GUARD_FAILED", "This plan item was already decided.")
        repo.update(conn, "kt_checklist_items", x, proposal_status="ACCEPTED" if decision == "ACCEPT" else "DECLINED", required=bool(required) if decision == "ACCEPT" else False)
        return f"kt_plan_item.{decision.lower()}ed", "kt_checklist_item", x["checklist_item_id"]

    return exit_kt._run(conn, token, "exit_kt.plan_item", key, {"item_id": item_id, "decision": decision, "required": required}, expected_revision, request_id, body)


# ---------------------------------------------------------------- targeted interview (the employee's own, with consent)
def start_interview(token: str | None, kt_item_id: str, consent: bool, key: str, request_id) -> dict[str, Any]:
    if not consent:
        raise ApiError("MALFORMED_INPUT", "Accept the purpose, audience and retention notice to start.")
    if not available():  # no consent or interview is recorded for an interview that can't run
        raise ApiError("CAPABILITY_UNAVAILABLE", NOT_CONNECTED)
    with transaction() as conn:
        c = _ctx(conn, token, "SUBJECT")
        item = repo.get(conn, "exit_kt_knowledge_items", c.org, c.ws, _id(kt_item_id, "knowledge area"))
        if not item or item["exit_kt_case_id"] != c.case["exit_kt_case_id"]:
            raise ApiError("NOT_FOUND", "Knowledge area not found.")
        iv = conn.execute(text(f"""SELECT * FROM {W}.exit_kt_interviews WHERE organization_id=:o AND workspace_id=:w AND kt_item_id=:k AND employee_id=:e
                                   AND status IN ('ACTIVE', 'PAUSED') ORDER BY started_at DESC LIMIT 1"""), {"o": c.org, "w": c.ws, "k": item["kt_item_id"], "e": c.me}).mappings().first()
        if iv:  # resume
            return exit_kt.view(c)
        consent_row = repo.insert(conn, "consent_sessions", c.org, c.ws, purpose="EXIT_KT_INTERVIEW", owner_employee_id=c.me, notice_version=NOTICE, accepted_at=datetime.now(UTC),
                                  requested_audience=["PRIVATE"], raw_retention={"until_case_complete": True})
        iv = repo.insert(conn, "exit_kt_interviews", c.org, c.ws, kt_item_id=item["kt_item_id"], employee_id=c.me, consent_session_id=consent_row["consent_session_id"],
                         status="ACTIVE", started_at=datetime.now(UTC))
        repo.update(conn, "exit_kt_knowledge_items", item, kt_status="INTERVIEW_IN_PROGRESS")
        commands.audit(conn, c.org, c.ws, c.me, "exit_kt_interview.started", "exit_kt_interview", iv["interview_id"], 1, request_id)
        usage.charge(conn, "TUTOR_TURN", c.ws, c.session)  # an assistant message (demo caps); refused → nothing runs
        req = _request(c, "INTERVIEW", kt_item_id=str(item["kt_item_id"]), interview_id=str(iv["interview_id"]))
    return _interview_turn(token, req, None)


def answer_interview(token: str | None, interview_id: str, answer: str, request_id) -> dict[str, Any]:
    if not answer.strip():
        raise ApiError("MALFORMED_INPUT", "Write an answer first.")
    with transaction() as conn:
        c = _ctx(conn, token, "SUBJECT")
        iv = repo.get(conn, "exit_kt_interviews", c.org, c.ws, _id(interview_id, "interview"))
        if not iv or iv["employee_id"] != c.me or iv["status"] not in ("ACTIVE", "PAUSED"):
            raise ApiError("NOT_FOUND", "Interview not found.")
        usage.charge(conn, "TUTOR_TURN", c.ws, c.session)  # an assistant message (demo caps); refused → nothing runs
        req = _request(c, "INTERVIEW", kt_item_id=str(iv["kt_item_id"]), interview_id=interview_id)
    return _interview_turn(token, req, answer.strip())


def _interview_turn(token, req: dict[str, Any], answer: str | None) -> dict[str, Any]:
    if answer:  # the answer is kept even if the assistant is down
        with transaction() as conn:
            c = _ctx(conn, token, "SUBJECT")
            repo.insert(conn, "exit_kt_interview_messages", c.org, c.ws, interview_id=_uuid.UUID(req["interview_id"]), sender_type="EMPLOYEE", content=answer[:4000])
    out = _run(req)
    turn = out.get("interview") or {}
    with transaction() as conn:
        c = _ctx(conn, token, "SUBJECT")
        iid = _uuid.UUID(req["interview_id"])
        if turn.get("question"):
            repo.insert(conn, "exit_kt_interview_messages", c.org, c.ws, interview_id=iid, sender_type="AI", message_type="QUESTION", content=turn["question"][:2000],
                        metadata={"model": out.get("model"), "prompt_version": out.get("prompt_version")})
        else:
            repo.insert(conn, "exit_kt_interview_messages", c.org, c.ws, interview_id=iid, sender_type="AI", message_type="READY",
                        content="That covers it. Draft the artifact from this interview, then review and correct it before you submit.", metadata={"model": out.get("model")})
        return exit_kt.view(c)


def draft_from_interview(token: str | None, interview_id: str, request_id) -> dict[str, Any]:
    with transaction() as conn:
        c = _ctx(conn, token, "SUBJECT")
        iv = repo.get(conn, "exit_kt_interviews", c.org, c.ws, _id(interview_id, "interview"))
        if not iv or iv["employee_id"] != c.me:
            raise ApiError("NOT_FOUND", "Interview not found.")
        usage.charge(conn, "TUTOR_TURN", c.ws, c.session)  # an assistant message (demo caps); refused → nothing runs
        req = _request(c, "DRAFT_ARTIFACT", kt_item_id=str(iv["kt_item_id"]), interview_id=interview_id)
    out = _run(req)
    a = out.get("artifact")
    if not a:
        raise ApiError("GUARD_FAILED", (out.get("warnings") or ["Nothing in the interview or records supports a draft yet."])[0])
    with transaction() as conn:
        c = exit_kt.Ctx(conn, token, lock=True)
        allowed = _allowed(conn, c, iv["interview_id"])
        cites = _citations(conn, c, allowed, a.get("citations"))
        item = repo.get(conn, "exit_kt_knowledge_items", c.org, c.ws, iv["kt_item_id"], lock=True)
        art = next(iter(repo.artifacts(conn, c.org, c.ws, [item["kt_item_id"]])), None)
        if art:
            cur = repo.get(conn, "exit_kt_artifact_revisions", c.org, c.ws, art["current_revision_id"], lock=True)
            if cur["status"] == "DRAFT":
                repo.update(conn, "exit_kt_artifact_revisions", cur, content=a["content"], source_refs=cites)
            else:
                rev = repo.insert(conn, "exit_kt_artifact_revisions", c.org, c.ws, artifact_id=art["artifact_id"], version=cur["version"] + 1, content=a["content"], status="DRAFT", source_refs=cites)
                repo.update(conn, "exit_kt_artifacts", art, current_revision_id=rev["artifact_revision_id"])
        else:
            art = repo.insert(conn, "exit_kt_artifacts", c.org, c.ws, kt_item_id=item["kt_item_id"], artifact_type=a["artifact_type"], title=a["title"][:200], generated_from_interview_id=iv["interview_id"])
            rev = repo.insert(conn, "exit_kt_artifact_revisions", c.org, c.ws, artifact_id=art["artifact_id"], version=1, content=a["content"], status="DRAFT", source_refs=cites)
            repo.update(conn, "exit_kt_artifacts", art, current_revision_id=rev["artifact_revision_id"])
        repo.update(conn, "exit_kt_knowledge_items", item, kt_status="DRAFT_CREATED")
        repo.update(conn, "exit_kt_interviews", repo.get(conn, "exit_kt_interviews", c.org, c.ws, iv["interview_id"], lock=True), status="COMPLETED", completed_at=datetime.now(UTC))
        bumped = repo.update(conn, "exit_kt_cases", c.case)
        commands.audit(conn, c.org, c.ws, c.me, "exit_kt_artifact.drafted_from_interview", "exit_kt_artifact", art["artifact_id"], bumped["revision"], request_id)
        return exit_kt.view(exit_kt.Ctx(conn, token))


# ---------------------------------------------------------------- successor recommendation (the manager confirms elsewhere)
def recommend(token: str | None, key: str, request_id) -> dict[str, Any]:
    with transaction() as conn:
        c = _ctx(conn, token, "MANAGER")
        if commands.find_receipt(conn, c.org, c.ws, c.me, "exit_kt.recommend", key):
            return _command(conn, token, "exit_kt.recommend", key, {}, lambda r, me: ({}, 1))
        usage.charge(conn, "TUTOR_TURN", c.ws, c.session)  # an assistant message (demo caps); refused → nothing runs
        req = _request(c, "RECOMMEND_SUCCESSOR")
    out = _run(req)

    with transaction() as conn:
        def run(r: Any, me) -> tuple[dict[str, Any], int]:
            c = exit_kt.Ctx(conn, token, lock=True)
            allowed = _allowed(conn, c)
            team = {str(m) for m in conn.execute(text(f"""SELECT employee_id FROM {W}.employee_team_memberships WHERE organization_id=:o AND workspace_id=:w AND is_active
                                                         AND team_id::text = ANY(:t)"""), {"o": c.org, "w": c.ws, "t": repo.employee_teams(conn, c.org, c.ws, c.case["employee_id"])}).scalars()}
            for x in out.get("recommendations") or []:
                rid, who = x.get("responsibility_id"), x.get("recommended_employee_id")
                if rid not in allowed["RESPONSIBILITY"] or who not in team or who == str(c.case["employee_id"]):
                    continue
                data = {"origin": "AI_ENGINE", "factors": x.get("factors") or {}, "citations": _citations(conn, c, allowed, x.get("citations")), "model": out.get("model")}
                t = next((t for t in repo.of_case(conn, "responsibility_transfers", c.org, c.ws, c.case["exit_kt_case_id"]) if str(t["responsibility_id"]) == rid), None)
                if t and t["status"] == "TRANSFERRED":
                    continue
                if t:
                    repo.update(conn, "responsibility_transfers", repo.get(conn, "responsibility_transfers", c.org, c.ws, t["transfer_id"], lock=True), recommended_owner_employee_id=_uuid.UUID(who),
                                recommendation_reason=(x.get("reason") or "")[:600], recommendation_data=data, status="PROPOSED" if t["status"] == "DISCOVERED" else t["status"])
                else:
                    resp = repo.get(conn, "responsibilities", c.org, c.ws, _uuid.UUID(rid))
                    effective = datetime.combine(c.case["final_working_date"], datetime.min.time(), UTC) if c.case.get("final_working_date") else datetime.now(UTC) + timedelta(days=7)
                    repo.insert(conn, "responsibility_transfers", c.org, c.ws, exit_kt_case_id=c.case["exit_kt_case_id"], responsibility_id=resp["responsibility_id"],
                                current_owner_employee_id=resp["owner_employee_id"], recommended_owner_employee_id=_uuid.UUID(who), recommendation_reason=(x.get("reason") or "")[:600],
                                recommendation_data=data, status="PROPOSED", effective_at=effective, expected_owner_revision=resp["ownership_revision"])
            bumped = repo.update(conn, "exit_kt_cases", c.case)
            commands.audit(conn, c.org, c.ws, me, "responsibility_transfer.recommended", "exit_kt_case", c.case["exit_kt_case_id"], bumped["revision"], request_id)
            return exit_kt.view(exit_kt.Ctx(conn, token)), bumped["revision"]

        return _command(conn, token, "exit_kt.recommend", key, {}, run)


# ---------------------------------------------------------------- copilot
def ask(token: str | None, message: str, key: str, request_id) -> dict[str, Any]:
    """A question, or (empty message) the opening brief the chat starts with (owner, 2026-10-11)."""
    key = key or str(_uuid.uuid4())  # a question without a key is never a replay of another
    with transaction() as conn:
        c = exit_kt.Ctx(conn, token)
        if not c.case:
            raise ApiError("FORBIDDEN", "You aren't part of an Exit KT case in this workspace.")
        if c.role == "SUCCESSOR" and not (repo.package(conn, c.org, c.ws, c.case["exit_kt_case_id"]) or {}).get("current_approved_version_id"):
            raise ApiError("GUARD_FAILED", "There's no approved package to ask about yet.")
        if commands.find_receipt(conn, c.org, c.ws, c.me, "exit_kt.ask", key):
            return _command(conn, token, "exit_kt.ask", key, {"message": message}, lambda r, me: ({}, 1))
        usage.charge(conn, "TUTOR_TURN", c.ws, c.session)  # an assistant message (demo caps); refused → nothing runs
        req = _request(c, "ASK", message=message.strip() or None)
    out = _run(req)
    a = out.get("answer") or {}

    with transaction() as conn:
        def run(r: Any, me) -> tuple[dict[str, Any], int]:
            c = exit_kt.Ctx(conn, token)
            allowed = _allowed(conn, c)
            if message.strip():
                _message(conn, c, "PERSON", message)
            _message(conn, c, "AI", a.get("text") or "I couldn't answer that from the records.", _citations(conn, c, allowed, a.get("citations")), a.get("unknowns"), out.get("model"))
            return exit_kt.view(c), 1

        return _command(conn, token, "exit_kt.ask", key, {"message": message}, run)


def messages(conn: Connection, c: exit_kt.Ctx) -> list[dict[str, Any]]:
    """This person's own copilot conversation on the case, oldest first."""
    rows = [dict(r) for r in conn.execute(text(f"""SELECT * FROM {W}.exit_kt_copilot_messages WHERE organization_id=:o AND workspace_id=:w AND exit_kt_case_id=:c AND employee_id=:e
                                                 ORDER BY created_at, message_id"""), {"o": c.org, "w": c.ws, "c": c.case["exit_kt_case_id"], "e": c.me}).mappings()]
    out = [{"message_id": str(m["message_id"]), "sender": {"PERSON": "EMPLOYEE", "AI": "AI", "SYSTEM": "SYSTEM"}[m["sender"]],
            "text": m["content"] + ("\n\nNot in the records: " + "; ".join(m["unknowns"]) if m["unknowns"] else ""),
            "citations": [{"citation_id": f"{m['message_id']}-{i}", "label": x["label"] or x["source_type"].replace("_", " ").lower(),
                           "excerpt": {"source_id": x["source_id"], "document_version_id": "", "heading_path": [x["label"]], "text": x["label"], "evidence_type": "OBSERVED"}}
                          for i, x in enumerate(m["citations"])],
            "provenance": "EMPLOYEE_INPUT" if m["sender"] == "PERSON" else "KT_ENGINE" if m["sender"] == "AI" else "BACKEND_RECORD"} for m in rows]
    if not out and not available():
        out.append({"message_id": "kt-not-connected", "sender": "SYSTEM", "text": NOT_CONNECTED, "citations": [], "provenance": "BACKEND_RECORD"})
    return out


def interview_messages(conn: Connection, c: exit_kt.Ctx, interview_id) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute(text(f"""SELECT * FROM {W}.exit_kt_interview_messages WHERE organization_id=:o AND workspace_id=:w AND interview_id=:i
                                                 ORDER BY created_at, message_id"""), {"o": c.org, "w": c.ws, "i": interview_id}).mappings()]
