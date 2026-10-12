"""Voice for the handover copilot and Exit KT (ADR-045): the same transport, only the person's own replies."""

import pytest

from app.integrations.voice import install_test_voice
from app.services.voice import audio_cache
from tests.test_companion_commands import fresh
from tests.test_demo_slice import code, pick
from tests.test_exit_kt import case, item
from tests.test_exit_kt_ai import engine_ as kt_engine  # noqa: F401
from tests.test_handover import H, k, open_handover
from tests.test_handover_ai import engine_ as handover_engine_  # noqa: F401
from tests.test_voice import FakeVoice


@pytest.fixture()
def voice():
    v = FakeVoice()
    install_test_voice(v)
    audio_cache.clear()
    yield v
    install_test_voice(None)
    audio_cache.clear()


def test_handover_voice_is_for_leads_and_reads_only_their_own_copilot_answers(client, voice, handover_engine_):  # noqa: F811
    fresh(client, "Alex")
    w = open_handover(client)
    r = client.post("/api/handover/voice/listen", json={"mode": "HANDS_FREE"}, headers=H)
    assert r.status_code == 200 and r.json()["data"]["token"] == "fake-token" and voice.modes == ["HANDS_FREE"]
    handover_engine_.replies["ASK"] = {"status": "OK", "model": "gemini-test", "answer": {"text": "#829 is still in progress.", "unknowns": ["the torque value"], "citations": []}}
    v = client.post(f"/api/handovers/{w['handover_id']}/copilot", json={"idempotency_key": k(), "text": "What about #829?"}, headers=H).json()["data"]
    mine, ai = v["copilot"][-2:]
    base = "/api/handover/voice/speech"
    s = client.get(f"{base}/{ai['message_id']}/stream")
    assert s.status_code == 200 and s.headers["x-sample-rate"] == "24000" and voice.spoken == [ai["text"]]  # read exactly as shown
    assert client.get(f"{base}/{ai['message_id']}/stream").content == s.content and len(voice.spoken) == 1  # replay from the cache
    assert client.get(f"{base}/{mine['message_id']}/stream").status_code == 404  # never the lead's own words
    assert client.get(f"{base}/not-a-message/stream").status_code == 422
    pick(client, "Dana")  # another lead can't hear this conversation
    assert client.get(f"{base}/{ai['message_id']}/stream").status_code == 404
    pick(client, "Jamie")  # members don't get handover voice at all
    assert code(client.post("/api/handover/voice/listen", json={"mode": "TAP"}, headers=H)) == "FORBIDDEN"
    install_test_voice(None)
    pick(client, "Alex")
    assert code(client.post("/api/handover/voice/listen", json={"mode": "TAP"}, headers=H)) == "CAPABILITY_UNAVAILABLE"


def test_exit_kt_voice_reads_the_persons_own_copilot_answers_and_interview_questions(client, voice, kt_engine):  # noqa: F811
    fresh(client, "Alex")
    assert client.post("/api/exit-kt/voice/listen", json={"mode": "TAP"}, headers=H).status_code == 200
    kt_engine.replies["ASK"] = {"status": "OK", "model": "gemini-test", "answer": {"text": "You own Machine #14 maintenance.", "unknowns": [], "citations": []}}
    v = client.post("/api/exit-kt/copilot", json={"idempotency_key": k(), "text": "What do I own?"}, headers=H).json()["data"]
    mine, ai = v["copilot"]
    base = "/api/exit-kt/voice/speech"
    assert client.get(f"{base}/{ai['message_id']}/stream").status_code == 200 and voice.spoken == ["You own Machine #14 maintenance."]
    assert client.get(f"{base}/{mine['message_id']}/stream").status_code == 404

    kti = item(case(client), "Evidence-based escalation practice")["kt_item_id"]
    kt_engine.replies["INTERVIEW"] = {"status": "OK", "interview": {"question": "Which details do you include?", "ready_for_artifact": False}}
    iv = client.post(f"/api/exit-kt/knowledge-items/{kti}/interview", json={"idempotency_key": k(), "consent": True}, headers=H).json()["data"]["interviews"][0]
    question = iv["messages"][-1]
    assert client.get(f"{base}/{question['message_id']}/stream").status_code == 200 and voice.spoken[-1] == "Which details do you include?"

    pick(client, "Morgan")  # the manager is on the case but hears neither Alex's conversation nor the private interview
    assert client.post("/api/exit-kt/voice/listen", json={"mode": "TAP"}, headers=H).status_code == 200
    assert client.get(f"{base}/{ai['message_id']}/stream").status_code == 404
    assert client.get(f"{base}/{question['message_id']}/stream").status_code == 404


def test_handover_and_exit_kt_assistants_count_against_the_demo_cap(client, engine, handover_engine_, kt_engine):  # noqa: F811
    from sqlalchemy import text

    with engine.begin() as c:
        c.execute(text("DELETE FROM workweave.demo_usage"))
        c.execute(text("UPDATE workweave.demo_usage_limits SET daily_limit = 0"))
        c.execute(text("UPDATE workweave.demo_usage_limits SET daily_limit = 2 WHERE tier='PUBLIC' AND scope_type='RUN' AND usage_kind='TUTOR_TURN'"))
    try:
        fresh(client, "Alex")
        w = open_handover(client)
        handover_engine_.replies["ASK"] = {"status": "OK", "model": "m", "answer": {"text": "ok", "unknowns": [], "citations": []}}
        kt_engine.replies["ASK"] = {"status": "OK", "model": "m", "answer": {"text": "ok", "unknowns": [], "citations": []}}
        assert client.post(f"/api/handovers/{w['handover_id']}/copilot", json={"idempotency_key": k(), "text": "hi"}, headers=H).status_code == 200
        assert client.post("/api/exit-kt/copilot", json={"idempotency_key": k(), "text": "hi"}, headers=H).status_code == 200
        r = client.post(f"/api/handovers/{w['handover_id']}/copilot", json={"idempotency_key": k(), "text": "again"}, headers=H)
        assert r.status_code == 429 and r.json()["error"]["limit"]["kind"] == "TUTOR_TURN"
        assert len(handover_engine_.requests) == 1  # refused before the assistant ran
    finally:
        with engine.begin() as c:
            c.execute(text("DELETE FROM workweave.demo_usage"))
            c.execute(text("UPDATE workweave.demo_usage_limits SET daily_limit = 0"))
