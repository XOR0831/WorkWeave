"""The Exit KT graph in the case workspace (docs/32, ADR-044), with a stand-in engine."""

import uuid

import pytest
from sqlalchemy import text

from app.integrations import exit_kt_engine
from tests.test_companion_commands import count, fresh
from tests.test_demo_slice import code, pick
from tests.test_exit_kt import H, case, item, k, ok, post


class Engine:
    provider = "test"

    def __init__(self):
        self.requests, self.replies, self.error = [], {}, False

    def run(self, request):
        self.requests.append(request)
        if self.error:
            raise exit_kt_engine.ExitKtEngineError("The knowledge-transfer assistant couldn't be reached.")
        reply = self.replies[request["operation"]]
        return reply(request) if callable(reply) else reply


@pytest.fixture()
def engine_(monkeypatch):
    e = Engine()
    monkeypatch.setattr(exit_kt_engine, "engine", lambda: e)
    return e


def ticket(engine, ws, ext):
    with engine.connect() as c:
        return str(c.execute(text("SELECT work_item_id FROM workweave.work_items WHERE workspace_id=:w AND external_id=:e"), {"w": ws, "e": ext}).scalar_one())


def risk(area_type, area_id, level="HIGH", score=7):
    return {"area_type": area_type, "area_id": area_id, "title": "x", "score": score, "level": level,
            "factors": [{"factor": "SOLE_OWNER", "weight": 3, "established": True, "note": "Only they appear", "sources": []}]}


def test_discovery_stores_only_verifiable_proposals_and_the_inventory(client, engine, engine_):
    ws = fresh(client, "Morgan")
    c = case(client)
    t458 = ticket(engine, ws, "Ticket #458")
    resp = c["responsibilities"][0]
    kti = item(c, "Evidence-based escalation practice")["kt_item_id"]
    cite = [{"source_type": "WORK_ITEM", "source_id": t458, "label": "Ticket #458 · Machine #14 dust alarm"}]
    fake = [{"source_type": "WORK_ITEM", "source_id": str(uuid.uuid4()), "label": "made up"}]
    engine_.replies["DISCOVER"] = {"status": "OK", "model": "gemini-test", "discovery": {
        "overview": "Alex maintains Machine #14.",
        "responsibilities": [{"responsibility_id": resp["responsibility_id"], "title": resp["title"], "ownership": "CONFIRMED", "note": "", "citations": []}],
        "expertise": [{"text": "Cleared a dust alarm.", "evidence_type": "OBSERVED", "citations": cite}, {"text": "Invented.", "evidence_type": "OBSERVED", "citations": fake}],
        "risks": [risk("KNOWLEDGE_ITEM", kti)], "documents": [], "changes": [], "open_work": [], "risk_explanations": [], "unknowns": ["No decision log."],
        "findings": [{"finding_type": "SOLE_KNOWLEDGE_HOLDER", "kt_item_id": kti, "description": "Only Alex handles dust alarms.", "citations": cite},
                     {"finding_type": "PROCESS_DISCREPANCY", "description": "Made up.", "citations": fake}],
        "plan": [{"title": "Walk through the dust alarm case", "method": "HISTORICAL_CASE_REVIEW", "priority": 1, "completion_criteria": "Successor explains the steps.",
                  "kt_item_id": kti, "citations": cite}],
        "new_areas": [{"title": "Machine #14 alarm handling", "description": "Recurring alarms.", "citations": cite, "risk": risk("KNOWLEDGE_ITEM", "new", "MEDIUM", 4)},
                      {"title": "Ghost area", "description": "x", "citations": fake}]}}
    r = client.post("/api/exit-kt/discovery", json={"idempotency_key": k()}, headers=H)
    assert r.status_code == 200, r.text
    v = r.json()["data"]
    assert v["discovery"]["overview"] == "Alex maintains Machine #14." and [x["text"] for x in v["discovery"]["expertise"]] == ["Cleared a dust alarm."]
    assert item(v, "Evidence-based escalation practice")["risk_level"] == "HIGH" and item(v, "Evidence-based escalation practice")["risk_factors"][0]["factor"] == "SOLE_OWNER"
    new = item(v, "Machine #14 alarm handling")
    assert new["origin"] == "AI_ENGINE" and new["risk_level"] == "MEDIUM" and not any(i["title"] == "Ghost area" for i in v["knowledge_items"])
    ai_findings = [f for f in v["findings"] if f["origin"] == "AI_ENGINE"]
    assert [f["description"] for f in ai_findings] == ["Only Alex handles dust alarms."] and ai_findings[0]["evidence"] == ["Ticket #458 · Machine #14 dust alarm"]
    plan = [x for x in v["checklist"] if x["origin"] == "AI_ENGINE"]
    assert plan[0]["proposal_status"] == "PROPOSED" and plan[0]["method"] == "HISTORICAL_CASE_REVIEW" and not plan[0]["required"]
    # The manager accepts it; only then does it count for completion.
    v = ok(post(client, f"plan/{plan[0]['checklist_item_id']}/accept", v, required=True))
    assert next(x for x in v["checklist"] if x["checklist_item_id"] == plan[0]["checklist_item_id"])["proposal_status"] == "ACCEPTED"
    pick(client, "Jamie")  # the successor never sees the discovery or findings
    j = case(client)
    assert "discovery" not in j and j["findings"] == []


def test_a_consented_interview_ends_in_a_private_draft(client, engine, engine_):
    ws = fresh(client, "Alex")
    c = case(client)
    kti = item(c, "Evidence-based escalation practice")["kt_item_id"]
    turns = iter([{"status": "OK", "interview": {"question": "Which details do you include when you ask for missing evidence?", "ready_for_artifact": False}},
                  {"status": "OK", "interview": {"question": None, "ready_for_artifact": True}}])
    engine_.replies["INTERVIEW"] = lambda req: next(turns)
    assert code(client.post(f"/api/exit-kt/knowledge-items/{kti}/interview", json={"idempotency_key": k(), "consent": False}, headers=H)) == "MALFORMED_INPUT"
    v = client.post(f"/api/exit-kt/knowledge-items/{kti}/interview", json={"idempotency_key": k(), "consent": True}, headers=H).json()["data"]
    iv = v["interviews"][0]
    assert iv["consent_accepted"] and iv["messages"][-1]["content"].startswith("Which details")
    assert count(engine, ws, "SELECT count(*) FROM workweave.consent_sessions WHERE workspace_id=:w AND purpose='EXIT_KT_INTERVIEW'") == 1
    v = client.post(f"/api/exit-kt/interviews/{iv['interview_id']}/messages", json={"text": "The work item, the source version, and that the cause is still unknown."}, headers=H).json()["data"]
    answer_id = next(m["message_id"] for m in v["interviews"][0]["messages"] if m["sender_type"] == "EMPLOYEE")
    engine_.replies["DRAFT_ARTIFACT"] = {"status": "OK", "artifact": {"artifact_type": "CHECKLIST", "title": "Requesting missing evidence", "content": "- Include the work item and source version. (reported)",
                                                                   "unknowns": [], "citations": [{"source_type": "INTERVIEW_MESSAGE", "source_id": answer_id, "label": "Interview answer"}]}}
    v = client.post(f"/api/exit-kt/interviews/{iv['interview_id']}/draft", headers=H).json()["data"]
    art = next(a for a in v["artifacts"] if a["kt_item_id"] == kti)
    assert art["revisions"][-1]["status"] == "DRAFT" and art["revisions"][-1]["content"].startswith("- Include the work item")
    pick(client, "Morgan")  # drafts and interviews stay private until submitted
    m = case(client)
    assert m["interviews"] == [] and not any(a["kt_item_id"] == kti and a["revisions"][-1]["status"] == "DRAFT" for a in m["artifacts"])


def test_recommendations_only_name_team_members_and_never_transfer(client, engine, engine_):
    ws = fresh(client, "Morgan")
    c = case(client)
    people = {p["first_name"]: p["employee_id"] for p in client.get("/api/personas").json()["data"]}
    resp = next(r for r in c["responsibilities"] if r["title"].startswith("Recurring"))
    engine_.replies["RECOMMEND_SUCCESSOR"] = {"status": "OK", "recommendations": [
        {"responsibility_id": resp["responsibility_id"], "recommended_employee_id": people["Jamie"], "reason": "Jamie has validated evidence and no open work.", "factors": {}, "citations": []},
        {"responsibility_id": resp["responsibility_id"], "recommended_employee_id": str(uuid.uuid4()), "reason": "Stranger.", "factors": {}, "citations": []}]}
    v = client.post("/api/exit-kt/recommendations", json={"idempotency_key": k()}, headers=H).json()["data"]
    t = next(x for x in v["transfers"] if x["responsibility_id"] == resp["responsibility_id"])
    assert t["recommended_owner_employee_id"] == people["Jamie"] and t["status"] == "PROPOSED" and "final_owner_employee_id" not in t
    assert next(r for r in v["responsibilities"] if r["responsibility_id"] == resp["responsibility_id"])["owner_employee_id"] == people["Alex"]  # unchanged
    pick(client, "Alex")
    assert code(client.post("/api/exit-kt/recommendations", json={"idempotency_key": k()}, headers=H)) == "FORBIDDEN"


def test_the_copilot_keeps_each_persons_conversation_and_failures_change_nothing(client, engine, engine_):
    ws = fresh(client, "Alex")
    engine_.replies["ASK"] = {"status": "OK", "model": "gemini-test", "answer": {"text": "You own Machine #14 maintenance.", "unknowns": [],
                                                                               "citations": [{"source_type": "RESPONSIBILITY", "source_id": str(uuid.uuid4()), "label": "fake"}]}}
    v = client.post("/api/exit-kt/copilot", json={"idempotency_key": k(), "text": "What do I own?"}, headers=H).json()["data"]
    assert [m["sender"] for m in v["copilot"]] == ["EMPLOYEE", "AI"] and v["copilot"][1]["citations"] == []  # invented citation dropped
    pick(client, "Jamie")  # no approved package yet in this run
    assert code(client.post("/api/exit-kt/package/questions", json={"text": "What am I taking over?"}, headers=H)) == "GUARD_FAILED"
    pick(client, "Alex")
    engine_.error = True
    before = count(engine, ws, "SELECT count(*) FROM workweave.exit_kt_copilot_messages WHERE workspace_id=:w")
    assert client.post("/api/exit-kt/copilot", json={"idempotency_key": k(), "text": "x"}, headers=H).status_code == 503
    assert count(engine, ws, "SELECT count(*) FROM workweave.exit_kt_copilot_messages WHERE workspace_id=:w") == before
