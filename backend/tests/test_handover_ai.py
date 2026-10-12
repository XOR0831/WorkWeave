"""The Shift Handover graph in the workspace (docs/31, ADR-043), with a stand-in engine."""

import uuid

import pytest
from sqlalchemy import text

from app.integrations import handover_engine
from tests.test_companion_commands import count, fresh
from tests.test_demo_slice import code, pick
from tests.test_handover import H, k, open_handover


class Engine:
    provider = "test"

    def __init__(self):
        self.requests, self.replies, self.error = [], {}, None

    def run(self, request):
        self.requests.append(request)
        if self.error:
            raise handover_engine.HandoverEngineError("The handover assistant couldn't be reached.")
        reply = self.replies[request["operation"]]
        return reply(request) if callable(reply) else reply


@pytest.fixture()
def engine_(monkeypatch):
    e = Engine()
    monkeypatch.setattr(handover_engine, "engine", lambda: e)
    return e


def ticket(engine, ws, ext="829"):
    with engine.connect() as c:
        return str(c.execute(text("SELECT work_item_id FROM workweave.work_items WHERE workspace_id=:w AND external_id LIKE :e"), {"w": ws, "e": f"%{ext}"}).scalar_one())


def test_the_gap_check_stores_only_verifiable_suggestions_and_asks_questions(client, engine, engine_):
    ws = fresh(client, "Alex")
    w = open_handover(client)
    assert w["can_check"] and w["copilot_available"]
    t829 = ticket(engine, ws)
    good = {"suggestion_type": "STALE_INFORMATION", "work_item_id": t829, "title": "#829 has a newer update", "proposed_note": "Bolts on order.", "reason": "Jamie reported it.",
            "evidence_type": "REPORTED", "citations": [{"source_type": "WORK_ITEM", "source_id": t829, "label": "Ticket #829 · Machine #14"}]}
    invented = {**good, "work_item_id": str(uuid.uuid4()), "title": "Invented ticket"}
    uncited = {**good, "title": "No evidence", "citations": [{"source_type": "WORK_EVENT", "source_id": str(uuid.uuid4()), "label": "?"}]}
    engine_.replies["CHECK"] = {"status": "OK", "model": "gemini-test", "suggestions": [good, invented, uncited],
                                "questions": [{"gap": "BLOCKER_MISSING", "question": "What's blocking #829?", "citations": [{"source_type": "WORK_ITEM", "source_id": t829, "label": "Ticket #829"}]},
                                              {"gap": "OWNER_MISSING", "question": "Who owns  #829 next?", "citations": [{"source_type": "WORK_ITEM", "source_id": t829, "label": "Ticket #829"}]},
                                              {"gap": "BLOCKER_MISSING", "question": "what's blocking #829?", "citations": []}]}
    r = client.post(f"/api/handovers/{w['handover_id']}/gap-check", json={"idempotency_key": k()}, headers=H)
    assert r.status_code == 200, r.text
    v = r.json()["data"]
    ai = [s for s in v["suggestions"] if s.get("origin") == "AI_ENGINE"]
    assert [s["title"] for s in ai] == ["#829 has a newer update"] and ai[0]["evidence_type"] == "REPORTED" and ai[0]["proposed"] == "Bolts on order."
    qs = [m for m in v["copilot"] if m.get("kind") == "QUESTION"]  # one message, bulleted; repeats and repeated sources dropped
    assert len(qs) == 1 and qs[0]["text"] == "Questions from the gap check:\n- What's blocking #829?\n- Who owns #829 next?"
    assert [x["label"] for x in qs[0]["citations"]] == ["Ticket #829"]
    assert engine_.requests[0]["operation"] == "CHECK" and engine_.requests[0]["employee_id"] == next(p["employee_id"] for p in client.get("/api/personas").json()["data"] if p["first_name"] == "Alex")
    # A new check replaces the previous check's unreviewed suggestions.
    client.post(f"/api/handovers/{w['handover_id']}/gap-check", json={"idempotency_key": k()}, headers=H)
    assert count(engine, ws, "SELECT count(*) FROM workweave.handover_suggestions WHERE workspace_id=:w AND status='PENDING' AND suggested_data->>'origin'='AI_ENGINE'") == 1


def test_accepting_an_ai_missing_item_links_its_ticket_and_evidence(client, engine, engine_):
    ws = fresh(client, "Alex")
    w = open_handover(client)
    t910 = ticket(engine, ws, "910")
    engine_.replies["CHECK"] = {"status": "OK", "suggestions": [{"suggestion_type": "MISSING_ITEM", "work_item_id": t910, "title": "Ticket #910 due tonight", "proposed_note": "Due during Evening.",
                                                                  "reason": "Due in the next shift.", "section_name": "Scheduled Activities", "evidence_type": "OBSERVED",
                                                                  "citations": [{"source_type": "WORK_ITEM", "source_id": t910, "label": "Ticket #910 · Pump check"}]}], "questions": []}
    w = client.post(f"/api/handovers/{w['handover_id']}/gap-check", json={"idempotency_key": k()}, headers=H).json()["data"]
    s = next(x for x in w["suggestions"] if x.get("origin") == "AI_ENGINE")
    w = client.post(f"/api/handover-suggestions/{s['suggestion_id']}/accept", json={"idempotency_key": k(), "expected_revision": w["revision"], "handover_id": w["handover_id"]}, headers=H).json()["data"]
    item = next(i for i in w["items"] if i["title"] == "Ticket #910 due tonight")
    assert item["work_item_id"] == t910 and item["description"] == "Due during Evening." and item["section_id"] == next(x["section_id"] for x in w["sections"] if x["name"] == "Scheduled Activities")
    assert count(engine, ws, "SELECT count(*) FROM workweave.handover_item_sources WHERE workspace_id=:w AND detected_by_ai AND handover_item_id IS NOT NULL") == 1


def test_the_copilot_keeps_each_leads_conversation_and_only_offers_edits_to_the_outgoing_lead(client, engine, engine_):
    ws = fresh(client, "Alex")
    w = open_handover(client)
    summary = next(x["section_id"] for x in w["sections"] if x["name"] == "Shift Summary")
    t829 = ticket(engine, ws)
    engine_.replies["ASK"] = lambda req: {"status": "OK", "model": "gemini-test", "answer": {
        "text": "#829 is still in progress.", "unknowns": ["the torque value"], "proposed_edit": {"section_id": summary, "content": "#829 continues."},
        "citations": [{"source_type": "WORK_ITEM", "source_id": t829, "label": "Ticket #829"}, {"source_type": "PUBLICATION", "source_id": str(uuid.uuid4()), "label": "fake"}]}}
    v = client.post(f"/api/handovers/{w['handover_id']}/copilot", json={"idempotency_key": k(), "text": "What about #829?"}, headers=H).json()["data"]
    lead, ai = v["copilot"][-2:]
    assert lead["sender"] == "EMPLOYEE" and lead["text"] == "What about #829?"
    assert ai["sender"] == "AI" and ai["provenance"] == "HANDOVER_ENGINE" and [c["label"] for c in ai["citations"]] == ["Ticket #829"]
    assert ai["proposed_edit"] == {"section_id": summary, "content": "#829 continues."} and "Not in the records: the torque value" in ai["text"]
    assert next(d for d in v["draft_sections"] if d["section_id"] == summary)["content"] != "#829 continues."  # never applied by itself
    pick(client, "Dana")  # the incoming lead: own conversation, and no edits offered
    d = client.post(f"/api/handovers/{w['handover_id']}/copilot", json={"idempotency_key": k(), "text": ""}, headers=H).json()["data"]
    assert len(d["copilot"]) == 1 and d["copilot"][0]["kind"] == "BRIEF" and "proposed_edit" not in d["copilot"][0]
    assert engine_.requests[-1]["message"] is None
    pick(client, "Jamie")
    assert code(client.post(f"/api/handovers/{w['handover_id']}/copilot", json={"idempotency_key": k(), "text": "hi"}, headers=H)) == "FORBIDDEN"


def test_drafts_are_returned_not_stored_and_engine_failures_change_nothing(client, engine, engine_):
    ws = fresh(client, "Alex")
    w = open_handover(client)
    summary = next(x["section_id"] for x in w["sections"] if x["name"] == "Shift Summary")
    engine_.replies["DRAFT"] = {"status": "OK", "drafts": [{"section_id": summary, "section_name": "Shift Summary", "content": "- #829 continues.", "unknowns": [], "citations": []},
                                                            {"section_id": str(uuid.uuid4()), "content": "x"}]}
    r = client.post(f"/api/handovers/{w['handover_id']}/section-drafts", json={"section_ids": [summary]}, headers=H)
    assert r.status_code == 200 and [d["section_id"] for d in r.json()["data"]["drafts"]] == [summary]
    assert open_handover(client)["revision"] == w["revision"]  # nothing stored
    engine_.error = True
    before = count(engine, ws, "SELECT count(*) FROM workweave.handover_copilot_messages WHERE workspace_id=:w")
    r = client.post(f"/api/handovers/{w['handover_id']}/copilot", json={"idempotency_key": k(), "text": "x"}, headers=H)
    assert r.status_code == 503 and count(engine, ws, "SELECT count(*) FROM workweave.handover_copilot_messages WHERE workspace_id=:w") == before
    pick(client, "Dana")
    engine_.error = False
    assert code(client.post(f"/api/handovers/{w['handover_id']}/gap-check", json={"idempotency_key": k()}, headers=H)) == "FORBIDDEN"  # outgoing lead only
