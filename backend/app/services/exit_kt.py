"""Exit Knowledge Transfer from the database (owner decisions 2026-10-10, ADR-039).

Who (per case):
- SUBJECT: the employee leaving or changing roles. Only they author, edit and submit their KT
  artifacts and assemble/submit the successor package; their drafts stay private until submitted.
- Reviewer side: the case's knowledge reviewer and holders of knowledge:review or
  responsibility:transfer for the employee's team. knowledge:review decides artifacts and packages
  and promotes approved knowledge; responsibility:transfer edits successors, reviews the effective
  time, confirms transfers, records checklist exceptions and completes the case. Nobody approves
  their own knowledge.
- SUCCESSOR: the package's named successor (or a proposed new owner). They see approved package
  versions only and confirm receipt of the exact version they read.

Separate actions (CLAUDE.md): package receipt, knowledge approval, promotion, ownership transfer and
closing a knowledge gap never imply each other.
- Promotion makes an approved artifact revision a new organizational document version, marked
  "waiting for indexing" (the AI engineer's ingestion indexes it later; until then it isn't in AI
  retrieval). Existing SOP versions are never overwritten.
- A permanent transfer needs an approved package, the successor's receipt of that exact version,
  the effective time reached (or reviewed), and an unchanged ownership revision.

Not connected yet (AI layer): knowledge discovery, the guided interview, drafting from an
interview and package Q&A answer CAPABILITY_UNAVAILABLE; the manual path covers each.

Every command commits its change, the case revision, receipt, audit and notifications together
(work_commands._command), checked against the case revision the user saw.
"""

from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import Connection

from app.errors import ApiError
from app.repositories import commands, exit_kt as repo, work
from app.services.onboarding import _persona
from app.services.work_commands import _check_revision, _command, _id

TZ = ZoneInfo("Asia/Manila")
NOT_CONNECTED = {
    "discovery": "Knowledge discovery isn't connected yet. The inventory and findings shown are the scenario's records; you can still add knowledge areas yourself.",
    "interview": "The guided interview isn't connected yet. Write the artifact yourself instead; it stays private until you submit it.",
    "draft": "Drafting from an interview isn't connected yet. Write the artifact yourself; it stays private until you submit it.",
    "qa": "Package questions aren't connected yet. Read the approved package; ask the reviewer about anything it doesn't cover.",
    "case": "Opening another case isn't connected in this demo yet; the scenario's case is shown.",
}
PACKAGE_STATUS = {"DRAFT": "DRAFT", "PENDING_REVIEW": "SUBMITTED", "APPROVED": "APPROVED", "REVISION_REQUIRED": "REJECTED"}
GENERATED_SECTIONS = ("Approved knowledge", "Excluded")
SOURCE_LABEL = {"APPROVED_EXCERPT": "Approved excerpt", "INTERVIEW": "Consented interview (private)", "DOCUMENT": "Document", "WORK_EVENT": "Work event", "TICKET": "Ticket", "EMAIL": "Email", "MANUAL": "Entered by hand"}


# ---------------------------------------------------------------- context
class Ctx:
    def __init__(self, conn: Connection, token: str | None, lock: bool = False):
        r, me = _persona(conn, token)
        self.conn, self.me, self.session = conn, me, r.session
        self.org, self.ws = r.session["organization_id"], r.session["workspace_id"]
        self.case: dict[str, Any] | None = None
        self.role = "NONE"
        for c in repo.cases(conn, self.org, self.ws):
            role = self._role(c)
            if role != "NONE":
                self.case, self.role = c, role
                break
        self.can_review = self.can_manage = False
        if self.case:
            teams = set(repo.employee_teams(conn, self.org, self.ws, self.case["employee_id"]))
            mine = self.case["employee_id"] == me
            self.can_review = not mine and bool(teams & set(work.teams_with(conn, self.org, self.ws, me, "knowledge:review")))
            self.can_manage = not mine and bool(teams & set(work.teams_with(conn, self.org, self.ws, me, "responsibility:transfer")))
            if self.role == "NONE" and (self.can_review or self.can_manage):
                self.role = "REVIEWER"
            if lock:
                self.case = {**self.case, **repo.get(conn, "exit_kt_cases", self.org, self.ws, self.case["exit_kt_case_id"], lock=True)}

    def _role(self, c: dict[str, Any]) -> str:
        me = self.me
        if c["employee_id"] == me:
            return "SUBJECT"
        if me in (c["reviewer_employee_id"], c["initiated_by_employee_id"]):
            return "REVIEWER"
        teams = set(repo.employee_teams(self.conn, self.org, self.ws, c["employee_id"]))
        if teams & (set(work.teams_with(self.conn, self.org, self.ws, me, "knowledge:review")) | set(work.teams_with(self.conn, self.org, self.ws, me, "responsibility:transfer"))):
            return "REVIEWER"
        if me == c["successor_employee_id"] or me in c["proposed_owners"]:
            return "SUCCESSOR"
        return "NONE"

    def require(self, roles: tuple[str, ...], message: str) -> dict[str, Any]:
        if not self.case or self.role not in roles:
            raise ApiError("FORBIDDEN", message)
        return self.case

    def reviewer(self, message: str) -> dict[str, Any]:
        if not self.case or not self.can_review:
            raise ApiError("FORBIDDEN", message)
        return self.case

    def manager(self, message: str) -> dict[str, Any]:
        if not self.case or not self.can_manage:
            raise ApiError("FORBIDDEN", message)
        return self.case


def _iso(v) -> str | None:
    return v.isoformat() if v else None


def _effective(t: dict[str, Any], now: datetime) -> tuple[str, bool]:
    if not t["effective_at"]:
        return "Not set", False
    if t["effective_at"] <= now:
        return f"Reached ({t['effective_at'].astimezone(TZ):%d %b %H:%M})", True
    return f"{t['effective_at'].astimezone(TZ):%d %b %H:%M} (future)", False


# ---------------------------------------------------------------- the view
def view(c: Ctx) -> dict[str, Any] | None:
    from app.services import exit_kt_ai  # exit_kt_ai uses this module

    if not c.case:
        return None
    conn, org, ws, case, now = c.conn, c.org, c.ws, c.case, datetime.now(UTC)
    cid = case["exit_kt_case_id"]
    subject, successor = c.role == "SUBJECT", c.role == "SUCCESSOR"
    items = repo.items(conn, org, ws, cid)
    item_ids = [i["kt_item_id"] for i in items]
    srcs = repo.sources(conn, org, ws, item_ids)
    arts = repo.artifacts(conn, org, ws, item_ids)
    revs = repo.revisions(conn, org, ws, [a["artifact_id"] for a in arts])
    promos = {p["artifact_revision_id"]: p for p in repo.promotions(conn, org, ws, [r["artifact_revision_id"] for r in revs])}

    def linked(item_id) -> str | None:
        for s in srcs:
            if s["kt_item_id"] == item_id and s["source_type"] == "DOCUMENT":
                dv = repo.document_version(conn, org, ws, s["source_reference"])
                if dv:
                    label = f"{dv['document_code']} v{dv['version']}"
                    return label if dv["temporal_status"] == "CURRENT" else f"{label} (current: v{dv['current_version']})" if dv["current_version"] else f"{label} (superseded)"
        return None

    artifacts = []
    for a in arts:
        mine = [r for r in revs if r["artifact_id"] == a["artifact_id"] and (subject or r["status"] != "DRAFT")]  # drafts stay private
        if not mine:
            continue
        current = a["current_revision_id"] if subject else mine[-1]["artifact_revision_id"]
        promo = next((promos[r["artifact_revision_id"]] for r in mine if r["artifact_revision_id"] in promos), None)
        artifacts.append({
            "artifact_id": str(a["artifact_id"]),
            "kt_item_id": str(a["kt_item_id"]),
            "artifact_type": a["artifact_type"],
            "title": a["title"],
            "current_revision_id": str(current),
            "revisions": [
                {"artifact_revision_id": str(r["artifact_revision_id"]), "version": r["version"], "content": r["content"], "status": r["status"], "audience": r["audience"],
                 **({"review_comment": r["review_comment"]} if r["review_comment"] else {}), **({"reviewed_by": str(r["reviewed_by_id"])} if r["reviewed_by_id"] else {})}
                for r in mine
            ],
            **({"promotion": {"document_version_label": f"{promo['document_code']} v{promo['version']}", "index_status": promo["index_status"]}} if promo else {}),
        })

    findings = repo.of_case(conn, "exit_kt_findings", org, ws, cid)
    records = repo.source_records(conn, org, ws, [x for f in findings for x in f["evidence_refs"] if not isinstance(x, dict)])
    transfers = repo.of_case(conn, "responsibility_transfers", org, ws, cid)
    pkg = repo.package(conn, org, ws, cid)
    checklist = repo.of_case(conn, "kt_checklist_items", org, ws, cid)
    resp_ids = [t["responsibility_id"] for t in transfers] + (repo.package_responsibilities(conn, org, ws, pkg["package_id"]) if pkg else []) + [x["responsibility_id"] for x in checklist if x["responsibility_id"]]
    resps = repo.responsibilities(conn, org, ws, resp_ids, case["employee_id"])
    titles = {r["responsibility_id"]: r["title"] for r in resps} | {i["kt_item_id"]: i["title"] for i in items}
    versions = repo.package_versions(conn, org, ws, pkg["package_id"]) if pkg else []
    rcpts = repo.receipts(conn, org, ws, [v["package_version_id"] for v in versions])
    interviews = repo.interviews(conn, org, ws, item_ids) if subject else []  # private to the employee
    msgs = repo.interview_messages(conn, org, ws, [i["interview_id"] for i in interviews])
    open_work = repo.open_work_of(conn, org, ws, case["employee_id"])
    return {
        "exit_kt_case_id": str(cid),
        "employee_id": str(case["employee_id"]),
        "case_kind": case["case_kind"],
        **({"final_working_date": case["final_working_date"].isoformat()} if case["final_working_date"] else {}),
        "status": case["status"],
        "reviewer_employee_id": str(case["reviewer_employee_id"]) if case["reviewer_employee_id"] else "",
        "revision": case["revision"],
        "knowledge_items": [] if successor else [
            {"kt_item_id": str(i["kt_item_id"]), "title": i["title"], "description": i["description"] or "", "documentation_status": i["documentation_status"], "kt_status": i["kt_status"],
             "risk_level": i["risk_level"],
             "origin": "AI_ENGINE" if i.get("origin") == "AI_ENGINE" else "MANUAL" if any(s["kt_item_id"] == i["kt_item_id"] and s["source_type"] == "EMPLOYEE_ADDED" for s in srcs) else "SYNTHETIC_SEED",
             **({"risk_score": i["risk_score"], "risk_factors": i["risk_factors"]} if i.get("risk_score") is not None else {}),
             **({"linked_source": ls} if (ls := linked(i["kt_item_id"])) else {}),
             **({"artifact_id": str(a["artifact_id"])} if (a := next((x for x in arts if x["kt_item_id"] == i["kt_item_id"]), None)) and any(y["artifact_id"] == str(a["artifact_id"]) for y in artifacts) else {})}
            for i in items
        ],
        "findings": [] if successor else [
            {"finding_id": str(f["finding_id"]), **({"kt_item_id": str(f["kt_item_id"])} if f["kt_item_id"] else {}), "finding_type": f["finding_type"], "description": f["description"],
             "evidence": [x.get("label") or x.get("source_type", "").replace("_", " ").lower() for x in f["evidence_refs"] if isinstance(x, dict)]  # AI findings cite records
                         + [f"{SOURCE_LABEL.get(records[str(x)]['source_type'], 'Source')} ({records[str(x)]['evidence_type'].lower()})" for x in f["evidence_refs"] if not isinstance(x, dict) and str(x) in records],
             "status": f["status"], "origin": "AI_ENGINE" if f.get("origin") == "AI_ENGINE" else "SYNTHETIC_SEED", **({"review_reason": f["review_reason"]} if f["review_reason"] else {})}
            for f in findings
        ],
        "interviews": [
            {"interview_id": str(i["interview_id"]), "kt_item_id": str(i["kt_item_id"]), "status": "IN_PROGRESS" if i["status"] == "ACTIVE" else i["status"] if i["status"] != "CANCELLED" else "PAUSED",
             "consent_accepted": True, "script_prompts": [],
             "messages": [{"message_id": str(m["message_id"]), "sender_type": m["sender_type"], "content": m["content"], "provenance": "EMPLOYEE_INPUT" if m["sender_type"] == "EMPLOYEE" else "SCRIPTED_FIXTURE" if m.get("message_type") == "SCRIPTED_FIXTURE" else "KT_ENGINE"}
                          for m in msgs if m["interview_id"] == i["interview_id"]]}
            for i in interviews
        ],
        "artifacts": [] if successor else artifacts,
        "responsibilities": [{"responsibility_id": str(r["responsibility_id"]), "responsibility_type": r["responsibility_type"], "title": r["title"], "owner_employee_id": str(r["owner_employee_id"]),
                              "ownership_revision": r["ownership_revision"]} for r in resps],
        "transfers": [
            {"transfer_id": str(t["transfer_id"]), "responsibility_id": str(t["responsibility_id"]), "current_owner_employee_id": str(t["current_owner_employee_id"]),
             **({"recommended_owner_employee_id": str(t["recommended_owner_employee_id"])} if t["recommended_owner_employee_id"] else {}),
             **({"final_owner_employee_id": str(t["final_owner_employee_id"])} if t["final_owner_employee_id"] else {}),
             **({"recommendation_reason": t["recommendation_reason"]} if t["recommendation_reason"] else {}),
             "status": t["status"], "effective_label": _effective(t, now)[0], "effective_reached": _effective(t, now)[1], "expected_owner_revision": t["expected_owner_revision"], "origin": "SYNTHETIC_SEED"}
            for t in transfers
        ],
        "package": {
            "package_id": str(pkg["package_id"]) if pkg else "",
            "successor_employee_id": str(pkg["successor_employee_id"]) if pkg else "",
            "status": PACKAGE_STATUS[pkg["status"]] if pkg else "DRAFT",
            "draft_sections": [] if successor or not pkg else pkg["draft_sections"],  # the successor reads approved versions only
            "versions": [{"package_version_id": str(v["package_version_id"]), "content_revision": v["content_revision"], "sections": v["sections"], "approved_by": str(v["approved_by"])} for v in versions],
            **({"current_approved_version_id": str(pkg["current_approved_version_id"])} if pkg and pkg["current_approved_version_id"] else {}),
            "receipts": [{"package_version_id": str(x["package_version_id"]), "employee_id": str(x["successor_employee_id"])} for x in rcpts],
            "revision": pkg["revision"] if pkg else 1,
            **({"review_comment": pkg["review_comment"]} if pkg and pkg["review_comment"] else {}),
        },
        "checklist": [
            {"checklist_item_id": str(x["checklist_item_id"]),
             "label": x.get("title") or (f"{titles.get(x['knowledge_item_id'], 'Knowledge area')} documented and approved" if x["knowledge_item_id"] else f"{titles.get(x['responsibility_id'], 'Responsibility')} transferred or explicitly retained"),
             "required": x["required"], "status": x["status"], "evidence_refs": [str(e) for e in x["evidence_refs"] if e != "exception"], **({"exception_reason": x["exception_reason"]} if x["exception_reason"] else {}),
             # docs/32: the knowledge-transfer plan lives on the checklist; the AI's items wait for the manager.
             **({k: x[k] for k in ("method", "priority", "completion_criteria") if x.get(k) is not None}),
             "origin": x.get("origin") or "SCENARIO", "proposal_status": x.get("proposal_status") or "ACCEPTED",
             **({"evidence_sources": x["evidence_sources"]} if x.get("evidence_sources") else {})}
            for x in checklist if (x.get("proposal_status") or "ACCEPTED") != "DECLINED"
        ],
        "open_work_note": f"{', '.join(open_work)} {'stays' if len(open_work) == 1 else 'stay'} open. Completing KT doesn't close or reassign {'it' if len(open_work) == 1 else 'them'}; the shift lead does that." if open_work else "",
        "successor_prompts": [],
        # docs/32: this person's own conversation with the knowledge-transfer assistant.
        "successor_qa": exit_kt_ai.messages(conn, c) if successor else [],
        "copilot": [] if successor else exit_kt_ai.messages(conn, c),
        "kt_available": exit_kt_ai.available(),
        **({"discovery": case["discovery"]} if case.get("discovery") and not successor else {}),
        "can_manage": c.can_manage, "can_review": c.can_review,
    }


def get_case(conn: Connection, token: str | None) -> dict[str, Any] | None:
    return view(Ctx(conn, token))


# ---------------------------------------------------------------- commands
def _run(conn: Connection, token: str | None, name: str, key: str, payload: dict[str, Any], expected_revision: int | None, request_id, body) -> dict[str, Any]:
    """One case command: locks the case, checks the revision the user saw, runs `body(ctx)` (which
    returns the audit action and resource), bumps the case revision and audits, all in one transaction."""

    def run(r: Any, me) -> tuple[dict[str, Any], int]:
        c = Ctx(conn, token, lock=True)
        if not c.case:
            raise ApiError("FORBIDDEN", "You aren't part of an Exit KT case in this workspace.")
        _check_revision(c.case["revision"], expected_revision, "case")
        action, rtype, rid = body(c)
        bumped = repo.update(conn, "exit_kt_cases", c.case)
        c.case = {**c.case, **bumped}
        commands.audit(conn, c.org, c.ws, me, action, rtype, rid, bumped["revision"], request_id)
        return view(c), bumped["revision"]

    return _command(conn, token, name, key, {**payload, "expected_revision": expected_revision}, run)


def _notify(c: Ctx, who, rtype: str, rid, event: str, request_id, payload: dict[str, Any] | None = None) -> None:
    if who and who != c.me:
        work.outbox(c.conn, c.org, c.ws, request_id, who, rtype, rid, c.case["revision"] + 1, event, payload or {})


def _item(c: Ctx, kt_item_id: str, lock: bool = True) -> dict[str, Any]:
    it = repo.get(c.conn, "exit_kt_knowledge_items", c.org, c.ws, _id(kt_item_id, "knowledge area"), lock)
    if not it or it["exit_kt_case_id"] != c.case["exit_kt_case_id"]:
        raise ApiError("NOT_FOUND", "Knowledge area not found.")
    return it


def _artifact(c: Ctx, artifact_id: str) -> dict[str, Any]:
    a = repo.get(c.conn, "exit_kt_artifacts", c.org, c.ws, _id(artifact_id, "artifact"), lock=True)
    if not a:
        raise ApiError("NOT_FOUND", "Artifact not found.")
    _item(c, str(a["kt_item_id"]), lock=False)
    return a


def _current_revision(c: Ctx, a: dict[str, Any], revision_id: str | None = None) -> dict[str, Any]:
    cur = repo.get(c.conn, "exit_kt_artifact_revisions", c.org, c.ws, a["current_revision_id"], lock=True)
    if revision_id is not None and (not cur or str(cur["artifact_revision_id"]) != revision_id):
        raise ApiError("REVISION_CONFLICT", "This must target the artifact's current revision. The content has changed; reload and review it again.")
    return cur


EDITORS = ("SUBJECT", "REVIEWER")


def add_knowledge_item(conn, token, title: str, description: str, key: str, expected_revision, request_id):
    def body(c: Ctx):
        c.require(EDITORS, "Only the employee or the reviewer side can add knowledge areas.")
        if not title.strip():
            raise ApiError("MALFORMED_INPUT", "Give the knowledge area a title.")
        it = repo.insert(conn, "exit_kt_knowledge_items", c.org, c.ws, exit_kt_case_id=c.case["exit_kt_case_id"], title=title.strip(), description=description.strip() or None,
                         documentation_status="MISSING", kt_status="INTERVIEW_REQUIRED", risk_level="MEDIUM")
        repo.insert(conn, "exit_kt_sources", c.org, c.ws, kt_item_id=it["kt_item_id"], source_type="EMPLOYEE_ADDED", source_reference=str(c.me), relevance_data={"added_by": str(c.me)})
        return "exit_kt_knowledge_item.added", "exit_kt_knowledge_item", it["kt_item_id"]

    return _run(conn, token, "exit_kt.add_item", key, {"title": title, "description": description}, expected_revision, request_id, body)


def link_existing(conn, token, kt_item_id: str, key: str, expected_revision, request_id):
    """A person confirms an area is already covered by an approved current document (no interview)."""

    def body(c: Ctx):
        c.require(EDITORS, "Only the employee or the reviewer side can verify existing knowledge.")
        it = _item(c, kt_item_id)
        doc = next((s for s in repo.sources(conn, c.org, c.ws, [it["kt_item_id"]]) if s["source_type"] == "DOCUMENT"), None)
        dv = repo.document_version(conn, c.org, c.ws, doc["source_reference"]) if doc else None
        if it["documentation_status"] != "DOCUMENTED" or not dv or not dv["current_version_id"]:
            raise ApiError("GUARD_FAILED", "Only an area documented by an approved, current document can skip the interview.")
        repo.update(conn, "exit_kt_knowledge_items", it, kt_status="COMPLETE")
        return "exit_kt_knowledge_item.linked_existing", "exit_kt_knowledge_item", it["kt_item_id"]

    return _run(conn, token, "exit_kt.link_existing", key, {"kt_item_id": kt_item_id}, expected_revision, request_id, body)


def review_finding(conn, token, finding_id: str, decision: str, reason: str, key: str, expected_revision, request_id):
    def body(c: Ctx):
        c.require(EDITORS, "Only the employee or the reviewer side can review findings.")
        f = repo.get(conn, "exit_kt_findings", c.org, c.ws, _id(finding_id, "finding"), lock=True)
        if not f or f["exit_kt_case_id"] != c.case["exit_kt_case_id"]:
            raise ApiError("NOT_FOUND", "Finding not found.")
        if not reason.strip():
            raise ApiError("MALFORMED_INPUT", "Give a reason or evidence for this decision.")
        status = {"CONFIRM": "CONFIRMED", "DISMISS": "DISMISSED", "RESOLVE": "RESOLVED"}[decision]
        repo.update(conn, "exit_kt_findings", f, status=status, review_reason=reason.strip(), reviewed_by=c.me, reviewed_at=datetime.now(UTC))
        return f"exit_kt_finding.{status.lower()}", "exit_kt_finding", f["finding_id"]

    return _run(conn, token, "exit_kt.review_finding", key, {"finding_id": finding_id, "decision": decision, "reason": reason}, expected_revision, request_id, body)


def create_case(conn, token, employee_id: str, case_kind: str, final_working_date, key: str, request_id):
    """The manager (responsibility:transfer for the employee's team) opens a case (docs/32). They're its
    knowledge reviewer when they also hold knowledge:review. One open case per employee."""
    payload = {"employee_id": employee_id, "case_kind": case_kind, "final_working_date": str(final_working_date) if final_working_date else None}

    def run(r: Any, me) -> tuple[dict[str, Any], int]:
        org, ws = r.session["organization_id"], r.session["workspace_id"]
        emp = repo.active_employee(conn, org, ws, _id(employee_id, "employee"))
        if not emp:
            raise ApiError("NOT_FOUND", "That person isn't an active employee in this workspace.")
        if emp["employee_id"] == me:
            raise ApiError("FORBIDDEN", "You can't open a knowledge-transfer case for yourself; your manager does.")
        teams = set(repo.employee_teams(conn, org, ws, emp["employee_id"]))
        if not teams & set(work.teams_with(conn, org, ws, me, "responsibility:transfer")):
            raise ApiError("FORBIDDEN", "Opening a case needs the responsibility-transfer permission for this person's team.")
        if case_kind == "DEPARTURE" and not final_working_date:
            raise ApiError("MALFORMED_INPUT", "A departure needs a final working date.")
        if any(x["employee_id"] == emp["employee_id"] and x["status"] != "COMPLETE" for x in repo.cases(conn, org, ws)):
            raise ApiError("GUARD_FAILED", "This person already has an open knowledge-transfer case.")
        reviewer = me if teams & set(work.teams_with(conn, org, ws, me, "knowledge:review")) else None
        case = repo.insert(conn, "exit_kt_cases", org, ws, employee_id=emp["employee_id"], case_kind=case_kind, final_working_date=final_working_date if case_kind == "DEPARTURE" else None,
                           status="DISCOVERY", initiated_by_employee_id=me, reviewer_employee_id=reviewer, started_at=datetime.now(UTC))
        work.outbox(conn, org, ws, request_id, emp["employee_id"], "exit_kt_case", case["exit_kt_case_id"], 1, "exit_kt.case_opened", {"case_kind": case_kind})
        commands.audit(conn, org, ws, me, "exit_kt_case.opened", "exit_kt_case", case["exit_kt_case_id"], 1, request_id)
        return view(Ctx(conn, token)), 1

    return _command(conn, token, "exit_kt.create_case", key, payload, run)


def assign_successor(conn, token, successor_id: str, key: str, expected_revision, request_id):
    """The manager names the package's successor. It never transfers ownership: each transfer still
    needs the approved package, the successor's receipt and the effective time (ADR-039)."""

    def body(c: Ctx):
        c.manager("Only the authorized manager assigns the successor.")
        who = repo.active_employee(conn, c.org, c.ws, _id(successor_id, "employee"))
        if not who:
            raise ApiError("NOT_FOUND", "That person isn't an active employee in this workspace.")
        if who["employee_id"] == c.case["employee_id"]:
            raise ApiError("MALFORMED_INPUT", "The successor can't be the person handing over.")
        p = repo.package(conn, c.org, c.ws, c.case["exit_kt_case_id"], lock=True)
        if p and p["status"] == "PENDING_REVIEW":
            raise ApiError("GUARD_FAILED", "The package is waiting for review; decide it before changing the successor.")
        effective = datetime.combine(c.case["final_working_date"], datetime.min.time(), UTC) if c.case.get("final_working_date") else datetime.now(UTC)
        if p:
            if p["successor_employee_id"] == who["employee_id"]:
                raise ApiError("GUARD_FAILED", f"{who['first_name']} is already the successor.")
            # A new successor reads a newly approved version; earlier approvals and receipts stay as history.
            repo.update(conn, "exit_kt_packages", p, successor_employee_id=who["employee_id"], status="DRAFT" if p["status"] == "APPROVED" else p["status"])
        else:
            p = repo.insert(conn, "exit_kt_packages", c.org, c.ws, exit_kt_case_id=c.case["exit_kt_case_id"], successor_employee_id=who["employee_id"], effective_at=effective,
                            draft_sections=[{"title": "Responsibilities", "content": "; ".join(r["title"] for r in repo.responsibilities(conn, c.org, c.ws, [], c.case["employee_id"])) or "None listed yet."}])
        _notify(c, who["employee_id"], "exit_kt_package", p["package_id"], "exit_kt.successor_assigned", request_id)
        return "exit_kt_package.successor_assigned", "exit_kt_package", p["package_id"]

    return _run(conn, token, "exit_kt.assign_successor", key, {"successor_id": successor_id}, expected_revision, request_id, body)


def not_connected(conn, token, what: str) -> None:
    c = Ctx(conn, token)
    if what != "case":
        c.require(("SUBJECT", "REVIEWER", "SUCCESSOR"), "You aren't part of an Exit KT case in this workspace.")
    raise ApiError("CAPABILITY_UNAVAILABLE", NOT_CONNECTED[what])


def create_artifact(conn, token, kt_item_id: str, title: str, content: str, key: str, expected_revision, request_id):
    def body(c: Ctx):
        c.require(("SUBJECT",), "Only the employee can author their KT artifact.")
        if not title.strip() or not content.strip():
            raise ApiError("MALFORMED_INPUT", "Add a title and content.")
        it = _item(c, kt_item_id)
        if repo.artifacts(conn, c.org, c.ws, [it["kt_item_id"]]):
            raise ApiError("GUARD_FAILED", "This knowledge area already has an artifact; edit it instead.")
        a = repo.insert(conn, "exit_kt_artifacts", c.org, c.ws, kt_item_id=it["kt_item_id"], artifact_type="PROCEDURE", title=title.strip())
        r = repo.insert(conn, "exit_kt_artifact_revisions", c.org, c.ws, artifact_id=a["artifact_id"], version=1, content=content.strip(), status="DRAFT")
        repo.update(conn, "exit_kt_artifacts", a, current_revision_id=r["artifact_revision_id"])
        repo.update(conn, "exit_kt_knowledge_items", it, kt_status="DRAFT_CREATED")
        return "exit_kt_artifact.created", "exit_kt_artifact", a["artifact_id"]

    return _run(conn, token, "exit_kt.create_artifact", key, {"kt_item_id": kt_item_id, "title": title, "content": content}, expected_revision, request_id, body)


def edit_artifact(conn, token, artifact_id: str, content: str, key: str, expected_revision, request_id):
    def body(c: Ctx):
        c.require(("SUBJECT",), "Only the employee can edit their draft.")
        if not content.strip():
            raise ApiError("MALFORMED_INPUT", "The artifact can't be empty.")
        a = _artifact(c, artifact_id)
        cur = _current_revision(c, a)
        if cur["status"] == "DRAFT":
            repo.update(conn, "exit_kt_artifact_revisions", cur, content=content.strip())
        else:  # submitted or reviewed revisions are immutable: a change starts a new private draft
            r = repo.insert(conn, "exit_kt_artifact_revisions", c.org, c.ws, artifact_id=a["artifact_id"], version=cur["version"] + 1, content=content.strip(), status="DRAFT")
            repo.update(conn, "exit_kt_artifacts", a, current_revision_id=r["artifact_revision_id"])
            repo.update(conn, "exit_kt_knowledge_items", _item(c, str(a["kt_item_id"])), kt_status="DRAFT_CREATED")
        return "exit_kt_artifact.edited", "exit_kt_artifact", a["artifact_id"]

    return _run(conn, token, "exit_kt.edit_artifact", key, {"artifact_id": artifact_id, "content": content}, expected_revision, request_id, body)


def submit_artifact(conn, token, artifact_id: str, revision_id: str, audience: str, key: str, expected_revision, request_id):
    """The employee reviews and submits the exact revision for knowledge approval."""

    def body(c: Ctx):
        c.require(("SUBJECT",), "Only the employee can submit their artifact.")
        a = _artifact(c, artifact_id)
        cur = _current_revision(c, a, revision_id)
        if cur["status"] != "DRAFT":
            raise ApiError("REVISION_CONFLICT", "Only the current draft revision can be submitted.")
        reviewer = c.case["reviewer_employee_id"]
        if not reviewer:
            raise ApiError("GUARD_FAILED", "This case has no knowledge reviewer yet.")
        now = datetime.now(UTC)
        repo.update(conn, "exit_kt_artifact_revisions", cur, status="PENDING_REVIEW", audience=audience, submitted_at=now, employee_reviewed_by=c.me, employee_reviewed_at=now)
        repo.insert(conn, "knowledge_approvals", c.org, c.ws, artifact_revision_id=cur["artifact_revision_id"], reviewer_employee_id=reviewer, status="PENDING")
        repo.update(conn, "exit_kt_knowledge_items", _item(c, str(a["kt_item_id"])), kt_status="PENDING_REVIEW")
        _notify(c, reviewer, "exit_kt_artifact", a["artifact_id"], "exit_kt.review_requested", request_id, {"version": cur["version"]})
        return "exit_kt_artifact.submitted", "exit_kt_artifact_revision", cur["artifact_revision_id"]

    return _run(conn, token, "exit_kt.submit_artifact", key, {"artifact_id": artifact_id, "revision_id": revision_id, "audience": audience}, expected_revision, request_id, body)


def decide_artifact(conn, token, artifact_id: str, revision_id: str, decision: str, comment: str, key: str, expected_revision, request_id):
    def body(c: Ctx):
        c.reviewer("Only an authorized knowledge reviewer can decide, and nobody approves their own knowledge.")
        a = _artifact(c, artifact_id)
        cur = _current_revision(c, a, revision_id)
        if cur["status"] != "PENDING_REVIEW":
            raise ApiError("REVISION_CONFLICT", "This decision must target the exact submitted revision. It was already reviewed or replaced.")
        if decision != "APPROVE" and not comment.strip():
            raise ApiError("MALFORMED_INPUT", "Add a comment explaining what needs to change.")
        status = {"APPROVE": "APPROVED", "REJECT": "REJECTED", "REQUEST_REVISION": "REVISION_REQUIRED"}[decision]
        now = datetime.now(UTC)
        repo.update(conn, "exit_kt_artifact_revisions", cur, status=status)
        appr = repo.approval(conn, c.org, c.ws, cur["artifact_revision_id"], c.me)
        fields = {"status": status, "review_comment": comment.strip() or None, "reviewed_at": now, "context_revisions": {"case_revision": c.case["revision"]}}
        if appr:
            repo.update(conn, "knowledge_approvals", appr, **fields)
        else:
            repo.insert(conn, "knowledge_approvals", c.org, c.ws, artifact_revision_id=cur["artifact_revision_id"], reviewer_employee_id=c.me, **fields)
        repo.update(conn, "exit_kt_knowledge_items", _item(c, str(a["kt_item_id"])), kt_status="PENDING_REVIEW" if decision == "APPROVE" else "DRAFT_CREATED")
        _notify(c, c.case["employee_id"], "exit_kt_artifact", a["artifact_id"], "exit_kt.review_decided", request_id, {"version": cur["version"], "status": status})
        return f"knowledge_approval.{status.lower()}", "exit_kt_artifact_revision", cur["artifact_revision_id"]

    return _run(conn, token, "exit_kt.decide_artifact", key, {"artifact_id": artifact_id, "revision_id": revision_id, "decision": decision, "comment": comment}, expected_revision, request_id, body)


def promote_artifact(conn, token, artifact_id: str, revision_id: str, key: str, expected_revision, request_id):
    """Approved knowledge becomes a new organizational document version, waiting for indexing."""

    def body(c: Ctx):
        c.reviewer("Only an authorized knowledge reviewer can promote approved knowledge.")
        a = _artifact(c, artifact_id)
        cur = _current_revision(c, a, revision_id)
        if repo.promotions(conn, c.org, c.ws, [cur["artifact_revision_id"]]):
            raise ApiError("GUARD_FAILED", "This revision is already promoted.")
        if cur["status"] != "APPROVED":
            raise ApiError("GUARD_FAILED", "Only the current approved revision can be promoted.")
        now = datetime.now(UTC)
        n = len([d for d in repo._all(conn, f"SELECT 1 FROM {repo.W}.knowledge_documents WHERE organization_id=:o AND workspace_id=:w AND document_type='KT_ARTIFACT'", {"o": c.org, "w": c.ws})]) + 1
        doc = repo.insert(conn, "knowledge_documents", c.org, c.ws, document_code=f"KT-{n:03d}", title=a["title"], document_type="KT_ARTIFACT")
        dv = repo.insert(conn, "knowledge_document_versions", c.org, c.ws, document_id=doc["document_id"], version="1", content=cur["content"], approval_status="APPROVED",
                         temporal_status="CURRENT", effective_at=now, approved_by_employee_id=c.me, approved_at=now)
        repo.update(conn, "knowledge_documents", doc, current_version_id=dv["document_version_id"])
        repo.insert(conn, "knowledge_promotions", c.org, c.ws, artifact_revision_id=cur["artifact_revision_id"], document_version_id=dv["document_version_id"], approved_by=c.me, promoted_at=now, index_status="PENDING")
        repo.update(conn, "exit_kt_knowledge_items", _item(c, str(a["kt_item_id"])), kt_status="COMPLETE", documentation_status="DOCUMENTED")
        return "knowledge_promotion.created", "knowledge_document_version", dv["document_version_id"]

    return _run(conn, token, "exit_kt.promote", key, {"artifact_id": artifact_id, "revision_id": revision_id}, expected_revision, request_id, body)


def _transfer(c: Ctx, transfer_id: str) -> dict[str, Any]:
    t = repo.get(c.conn, "responsibility_transfers", c.org, c.ws, _id(transfer_id, "transfer"), lock=True)
    if not t or t["exit_kt_case_id"] != c.case["exit_kt_case_id"]:
        raise ApiError("NOT_FOUND", "Transfer not found.")
    return t


def edit_transfer(conn, token, transfer_id: str, final_owner: str, key: str, expected_revision, request_id):
    def body(c: Ctx):
        c.manager("Only the authorized manager can edit successor selections.")
        t = _transfer(c, transfer_id)
        if t["status"] == "TRANSFERRED":
            raise ApiError("GUARD_FAILED", "This responsibility was already transferred.")
        owner = _id(final_owner, "employee")
        if owner == t["current_owner_employee_id"]:
            raise ApiError("MALFORMED_INPUT", "Choose someone other than the current owner, or leave it with them.")
        if not repo.active_employee(conn, c.org, c.ws, owner):
            raise ApiError("NOT_FOUND", "That person isn't an active employee in this workspace.")
        repo.update(conn, "responsibility_transfers", t, final_owner_employee_id=owner, status="EDITED")
        return "responsibility_transfer.edited", "responsibility_transfer", t["transfer_id"]

    return _run(conn, token, "exit_kt.edit_transfer", key, {"transfer_id": transfer_id, "final_owner": final_owner}, expected_revision, request_id, body)


def review_effective_time(conn, token, transfer_id: str, key: str, expected_revision, request_id):
    def body(c: Ctx):
        c.manager("Only the authorized manager can review the effective time.")
        t = _transfer(c, transfer_id)
        if t["status"] == "TRANSFERRED":
            raise ApiError("GUARD_FAILED", "This responsibility was already transferred.")
        repo.update(conn, "responsibility_transfers", t, effective_at=datetime.now(UTC))
        return "responsibility_transfer.effective_time_reviewed", "responsibility_transfer", t["transfer_id"]

    return _run(conn, token, "exit_kt.effective_time", key, {"transfer_id": transfer_id}, expected_revision, request_id, body)


def _package(c: Ctx) -> dict[str, Any]:
    p = repo.package(c.conn, c.org, c.ws, c.case["exit_kt_case_id"], lock=True)
    if not p:
        raise ApiError("NOT_FOUND", "This case has no successor package.")
    return p


def assemble_package(conn, token, key: str, expected_revision, request_id):
    """Rebuilds the draft from approved, promoted knowledge; anything else is listed as excluded."""

    def body(c: Ctx):
        c.require(("SUBJECT",), "Only the employee can assemble their successor package.")
        p = _package(c)
        if p["status"] == "PENDING_REVIEW":
            raise ApiError("GUARD_FAILED", "The package is waiting for review; it can't change until it's decided.")
        items = repo.items(conn, c.org, c.ws, c.case["exit_kt_case_id"])
        arts = repo.artifacts(conn, c.org, c.ws, [i["kt_item_id"] for i in items])
        revs = repo.revisions(conn, c.org, c.ws, [a["artifact_id"] for a in arts])
        promos = {x["artifact_revision_id"]: x for x in repo.promotions(conn, c.org, c.ws, [r["artifact_revision_id"] for r in revs])}
        approved, excluded = [], []
        for a in arts:
            promo = next((promos[r["artifact_revision_id"]] for r in revs if r["artifact_id"] == a["artifact_id"] and r["artifact_revision_id"] in promos), None)
            (approved if promo else excluded).append((a, promo))
        base = [s for s in p["draft_sections"] if s.get("title") not in GENERATED_SECTIONS]
        sections = base + [{"title": "Approved knowledge", "content": "; ".join(f"{a['title']} ({x['document_code']} v{x['version']})" for a, x in approved) or "None approved yet.", "evidence_type": "OBSERVED"}]
        if excluded:
            sections.append({"title": "Excluded", "content": f"{'; '.join(a['title'] for a, _ in excluded)}: not approved, so not shared with the successor.", "evidence_type": "UNKNOWN"})
        repo.update(conn, "exit_kt_packages", p, draft_sections=sections, status="DRAFT", review_comment=None,
                    context_revisions={"artifact_revisions": [str(x["artifact_revision_id"]) for _, x in approved]})
        return "exit_kt_package.assembled", "exit_kt_package", p["package_id"]

    return _run(conn, token, "exit_kt.assemble", key, {}, expected_revision, request_id, body)


def submit_package(conn, token, key: str, expected_revision, request_id):
    def body(c: Ctx):
        c.require(("SUBJECT",), "Only the employee can submit their package.")
        p = _package(c)
        if p["status"] not in ("DRAFT", "REVISION_REQUIRED"):
            raise ApiError("GUARD_FAILED", "This package is already submitted or approved. Assemble it again to change it.")
        repo.update(conn, "exit_kt_packages", p, status="PENDING_REVIEW")
        _notify(c, c.case["reviewer_employee_id"], "exit_kt_package", p["package_id"], "exit_kt.package_review_requested", request_id)
        return "exit_kt_package.submitted", "exit_kt_package", p["package_id"]

    return _run(conn, token, "exit_kt.submit_package", key, {}, expected_revision, request_id, body)


def decide_package(conn, token, decision: str, comment: str, key: str, expected_revision, request_id):
    def body(c: Ctx):
        c.reviewer("Only an authorized reviewer can decide on the package, and the employee can't approve their own.")
        p = _package(c)
        if p["status"] != "PENDING_REVIEW":
            raise ApiError("GUARD_FAILED", "Only a submitted package can be reviewed.")
        if decision == "REJECT":
            if not comment.strip():
                raise ApiError("MALFORMED_INPUT", "Explain what needs to change.")
            repo.update(conn, "exit_kt_packages", p, status="REVISION_REQUIRED", review_comment=comment.strip())
            _notify(c, c.case["employee_id"], "exit_kt_package", p["package_id"], "exit_kt.package_returned", request_id)
            return "exit_kt_package.returned", "exit_kt_package", p["package_id"]
        v = repo.insert(conn, "exit_kt_package_versions", c.org, c.ws, package_id=p["package_id"], content_revision=p["revision"], sections=p["draft_sections"],
                        artifact_revision_refs=(p["context_revisions"] or {}).get("artifact_revisions", []), source_revisions={"case_revision": c.case["revision"]},
                        approved_by=c.me, approved_at=datetime.now(UTC))
        repo.update(conn, "exit_kt_packages", p, status="APPROVED", current_approved_version_id=v["package_version_id"], review_comment=None)
        _notify(c, p["successor_employee_id"], "exit_kt_package", p["package_id"], "exit_kt.package_approved", request_id)
        return "exit_kt_package.approved", "exit_kt_package_version", v["package_version_id"]

    return _run(conn, token, "exit_kt.decide_package", key, {"decision": decision, "comment": comment}, expected_revision, request_id, body)


def receive_package(conn, token, version_id: str, key: str, request_id):
    """The successor confirms they read this exact approved version (not an ownership transfer)."""

    def body(c: Ctx):
        p = _package(c)
        if p["successor_employee_id"] != c.me:
            raise ApiError("FORBIDDEN", "Only the named successor can confirm receipt.")
        if str(p["current_approved_version_id"]) != version_id:
            raise ApiError("REVISION_CONFLICT", "A newer approved version exists. Read it before confirming receipt.")
        repo.add_receipt(conn, c.org, c.ws, p["current_approved_version_id"], c.me)
        _notify(c, c.case["reviewer_employee_id"], "exit_kt_package", p["package_id"], "exit_kt.package_received", request_id)
        return "successor_receipt.recorded", "exit_kt_package_version", p["current_approved_version_id"]

    return _run(conn, token, "exit_kt.receive", key, {"version_id": version_id}, None, request_id, body)


def confirm_transfer(conn, token, transfer_id: str, key: str, expected_revision, request_id):
    def body(c: Ctx):
        c.manager("Only the authorized manager can confirm a responsibility transfer.")
        t = _transfer(c, transfer_id)
        if t["status"] == "TRANSFERRED":
            raise ApiError("GUARD_FAILED", "This responsibility was already transferred.")
        r = repo.get(conn, "responsibilities", c.org, c.ws, t["responsibility_id"], lock=True)
        if r["ownership_revision"] != t["expected_owner_revision"] or r["owner_employee_id"] != t["current_owner_employee_id"]:
            raise ApiError("REVISION_CONFLICT", "Ownership changed since this transfer was prepared. Reload and review again; the owner is unchanged.")
        owner = t["final_owner_employee_id"] or t["recommended_owner_employee_id"]
        p = repo.package(conn, c.org, c.ws, c.case["exit_kt_case_id"])
        blockers = []
        if not owner:
            blockers.append("no successor selected")
        if not p or not p["current_approved_version_id"]:
            blockers.append("no approved successor package")
        elif not any(x["successor_employee_id"] == owner for x in repo.receipts(conn, c.org, c.ws, [p["current_approved_version_id"]])):
            blockers.append("the successor hasn't confirmed receipt of the current approved package")
        if owner and p and owner != p["successor_employee_id"]:
            blockers.append("the package is addressed to a different successor")
        if not _effective(t, datetime.now(UTC))[1]:
            blockers.append("the effective time hasn't been reached or reviewed")
        if blockers:
            raise ApiError("GUARD_FAILED", f"Ownership is unchanged: {'; '.join(blockers)}.")
        repo.update(conn, "responsibilities", r, owner_employee_id=owner, ownership_revision=r["ownership_revision"] + 1)
        repo.update(conn, "responsibility_transfers", t, status="TRANSFERRED", final_owner_employee_id=owner, approved_by_employee_id=c.me, completed_at=datetime.now(UTC))
        _notify(c, owner, "responsibility", r["responsibility_id"], "exit_kt.responsibility_transferred", request_id)
        return "responsibility_transfer.transferred", "responsibility_transfer", t["transfer_id"]

    return _run(conn, token, "exit_kt.confirm_transfer", key, {"transfer_id": transfer_id}, expected_revision, request_id, body)


def _checklist_item(c: Ctx, item_id: str) -> dict[str, Any]:
    x = repo.get(c.conn, "kt_checklist_items", c.org, c.ws, _id(item_id, "checklist item"), lock=True)
    if not x or x["exit_kt_case_id"] != c.case["exit_kt_case_id"]:
        raise ApiError("NOT_FOUND", "Checklist item not found.")
    if x["status"] == "RESOLVED":
        raise ApiError("GUARD_FAILED", "This checklist item is already resolved.")
    return x


def resolve_checklist(conn, token, item_id: str, evidence_ref: str, key: str, expected_revision, request_id):
    """Resolved only by reviewed evidence for that item: its promoted knowledge or its completed
    transfer. A receipt or a conversation alone doesn't qualify."""

    def body(c: Ctx):
        c.require(EDITORS, "Only the employee or the reviewer side can resolve checklist items.")
        x = _checklist_item(c, item_id)
        kind, _, ref = evidence_ref.partition(":")
        ok = False
        if kind == "promotion" and x["knowledge_item_id"]:
            a = repo.get(conn, "exit_kt_artifacts", c.org, c.ws, _id(ref, "artifact"))
            revs = repo.revisions(conn, c.org, c.ws, [a["artifact_id"]]) if a and a["kt_item_id"] == x["knowledge_item_id"] else []
            ok = bool(repo.promotions(conn, c.org, c.ws, [r["artifact_revision_id"] for r in revs]))
        elif kind == "transfer" and x["responsibility_id"]:
            t = repo.get(conn, "responsibility_transfers", c.org, c.ws, _id(ref, "transfer"))
            ok = bool(t and t["responsibility_id"] == x["responsibility_id"] and t["status"] == "TRANSFERRED")
        if not ok:
            raise ApiError("GUARD_FAILED", "Choose reviewed evidence for this item: its promoted knowledge or its completed transfer. A receipt or a conversation alone doesn't resolve it.")
        repo.update(conn, "kt_checklist_items", x, status="RESOLVED", evidence_refs=[evidence_ref], reviewed_by=c.me, resolved_at=datetime.now(UTC))
        return "kt_checklist_item.resolved", "kt_checklist_item", x["checklist_item_id"]

    return _run(conn, token, "exit_kt.resolve_checklist", key, {"item_id": item_id, "evidence_ref": evidence_ref}, expected_revision, request_id, body)


def checklist_exception(conn, token, item_id: str, reason: str, key: str, expected_revision, request_id):
    def body(c: Ctx):
        c.manager("Only the authorized manager can record an exception.")
        x = _checklist_item(c, item_id)
        if not reason.strip():
            raise ApiError("MALFORMED_INPUT", "Explain the exception; it's disclosed on the case.")
        repo.update(conn, "kt_checklist_items", x, status="RESOLVED", exception_reason=reason.strip(), evidence_refs=["exception"], reviewed_by=c.me, resolved_at=datetime.now(UTC))
        return "kt_checklist_item.exception_recorded", "kt_checklist_item", x["checklist_item_id"]

    return _run(conn, token, "exit_kt.checklist_exception", key, {"item_id": item_id, "reason": reason}, expected_revision, request_id, body)


def complete_case(conn, token, key: str, expected_revision, request_id):
    def body(c: Ctx):
        c.manager("Only the authorized manager can complete the case.")
        if c.case["status"] == "COMPLETE":
            raise ApiError("GUARD_FAILED", "This case is already complete.")
        items = {i["kt_item_id"]: i["title"] for i in repo.items(conn, c.org, c.ws, c.case["exit_kt_case_id"])}
        open_ = [x for x in repo.of_case(conn, "kt_checklist_items", c.org, c.ws, c.case["exit_kt_case_id"])
                 if x["required"] and x["status"] != "RESOLVED" and (x.get("proposal_status") or "ACCEPTED") == "ACCEPTED"]
        if open_:
            raise ApiError("GUARD_FAILED", f"{len(open_)} required checklist item{'s are' if len(open_) > 1 else ' is'} still open"
                           f"{': ' + '; '.join(items[x['knowledge_item_id']] for x in open_ if x['knowledge_item_id'] in items) if any(x['knowledge_item_id'] in items for x in open_) else ''}.")
        c.case = {**c.case, **repo.update(conn, "exit_kt_cases", c.case, status="COMPLETE", completed_at=datetime.now(UTC))}
        return "exit_kt_case.completed", "exit_kt_case", c.case["exit_kt_case_id"]

    return _run(conn, token, "exit_kt.complete", key, {}, expected_revision, request_id, body)
