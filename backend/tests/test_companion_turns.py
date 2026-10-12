"""Work Companion conversation through the AI engine (ADR-034), with a deterministic stand-in graph.

The stand-in behaves like the AI engineer's graph where the backend depends on it: it opens with a
brief, waits for the employee, reports which steps ran (and the chunks guidance retrieved), saves
work updates itself as reports, runs or stops before calendar steps, and ends after a pause.
Which step "runs" is scripted by the test message; the real graph decides with Gemini.
"""

import json
import uuid

import httpx
import pytest
from sqlalchemy import text

from app.integrations.companion_engine import LangGraphCompanion, Thread, Trace, install_test_companion
from app.services.companion_turns import CALENDAR_CONNECT, CALENDAR_DOWN, CALENDAR_OFF
from tests.test_companion_commands import _assigned_story, count, item, tool
from tests.test_demo_slice import code

H = {"X-WorkWeave-Client": "web"}


class FakeCompanion:
    provider = "fake"

    def __init__(self, engine):
        self.db = engine
        self.threads: dict[str, dict] = {}
        self.calls: list[str] = []
        self.fail = False

    def _t(self, tid: str) -> Thread:
        t = self.threads.get(tid)
        if not t:
            return Thread(False, False, [], {})
        return Thread(True, t["next"] == ["wait_for_user"] and t["waiting"], list(t["next"]), {"conversation": dict(t["conversation"]), "response_analysis": t.get("analysis"), "session": {}, "delegation": t.get("delegation") or {}, "assignment_question": t.get("assignment_question") or {}, "app_action": t.get("app_action")})

    def thread(self, thread_id: str) -> Thread:
        return self._t(thread_id)

    def start(self, thread_id, employee, work_session_id, stop_before):
        self.calls.append("start")
        uuid.UUID(thread_id)  # LangGraph answers 422 to a thread ID that isn't a UUID
        if self.fail:
            from app.integrations.companion_engine import CompanionEngineError

            raise CompanionEngineError("down")
        self.threads[thread_id] = {"employee": employee, "session": work_session_id, "next": ["wait_for_user"], "waiting": True,
                                   "conversation": {"assistant_message": "Brief: your top priority is Ticket #829.", "user_message": None}}
        if self.busy_once:
            from app.integrations.companion_engine import CompanionBusy

            self.busy_once = False
            raise CompanionBusy("409")  # the other request's run produced the brief above
        return Trace(steps=["initialize_companion", "load_work_context", "determine_priorities", "generate_opening_brief"], thread=self._t(thread_id))

    def resume(self, thread_id, text_, input_kind, client_turn_id, stop_before, on_step=None):
        self.calls.append("resume")
        if self.fail:
            from app.integrations.companion_engine import CompanionEngineError

            raise CompanionEngineError("down")
        t = self.threads[thread_id]
        t["conversation"] = {"assistant_message": "", "user_message": text_}
        trace = Trace(steps=["wait_for_user", "analyze_user_response"])
        pending = {"calendar": "calendar_inquiry", "schedule": "schedule_work", "yes, schedule": "handle_schedule_approval"}
        step = next((v for k, v in pending.items() if text_.startswith(k)), None)
        if step:
            assert step in stop_before  # the app always checks the calendar connection first
            t.update(next=[step], waiting=False, analysis={"intent": "CALENDAR_INQUIRY", "recommended_action": "CALENDAR", "referenced_work_item_id": None})
        elif text_.startswith("guide"):
            chunks = text_.split()[1:]
            trace.retrieved = [{"chunk_id": c, "document_id": "x", "title": "t", "content": "c", "similarity": 0.9} for c in chunks]
            trace.steps += ["resolve_work_item", "retrieve_relevant_chunks", "generate_work_guidance", "work_guidance"]
            t["conversation"]["assistant_message"] = "Use the controlled registry to confirm the current version."
            t["analysis"] = {"intent": "WORK_QUESTION", "recommended_action": "GUIDE", "referenced_work_item_id": self.ref}
        elif text_.startswith("done"):
            self._save_report(t, "COMPLETED")
            trace.steps += ["interpret_work_update", "persist_reported_update", "work_update", "refresh_after_work_update"]
            t["conversation"]["assistant_message"] = "Recorded that you reported this as COMPLETED; the ticket system hasn't shown it yet."
        elif text_.startswith("delegate"):
            # As her delegation subgraph would: the shift in progress and the suggested hand-overs.
            t["delegation"] = dict(self.delegation)
            trace.steps += ["load_shift_team", "propose_delegation", "generate_delegation_response", "delegate_work"]
            t["conversation"]["assistant_message"] = "I've prepared a delegation proposal. Review it in the work area and confirm to assign."
        elif text_.startswith("why"):
            t["assignment_question"] = {"work_item_id": self.ref}
            trace.steps += ["load_assignment_options", "select_assignment", "generate_assignment_explanation", "explain_assignment"]
            t["conversation"]["assistant_message"] = "WorkWeave assigned it to you by its competency rule."
        elif text_.startswith("act "):
            # As her request_app_action step: the action named as JSON in the test message.
            t["app_action"] = json.loads(text_[4:])
            trace.steps += ["request_app_action"]
            t["conversation"]["assistant_message"] = "On it…"
        elif text_.startswith("confirm"):
            trace.steps += ["confirm_delegation"]
            t["conversation"]["assistant_message"] = "Confirming the delegation proposal…"
        elif text_.startswith("pause"):
            t.update(next=[], waiting=False)
            trace.steps += ["pause_companion"]
            t["conversation"]["assistant_message"] = "Got it. I'll pause here."
        else:
            trace.steps += ["focus_work"]
            t["conversation"]["assistant_message"] = "Let's start with Ticket #829."
            t["analysis"] = {"intent": "START_WORK", "recommended_action": "FOCUS", "referenced_work_item_id": self.ref}
        trace.thread = self._t(thread_id)
        for step in trace.steps:  # as the real stream reports each finished step
            if on_step:
                on_step(step, {"response_analysis": t.get("analysis") or {}} if step == "analyze_user_response" else {})
        return trace

    busy_once = False  # the next start finds another request's run already going

    CALENDAR = {
        "calendar_inquiry": (["calendar_inquiry"], "You have a team briefing at 3:00 PM today."),
        "schedule_work": (["load_employee_shift", "calculate_free_slots", "generate_schedule_proposal", "schedule_work"], "Proposed: Ticket #829 at 1:00 PM for 30 minutes. Do you approve?"),
        "handle_schedule_approval": (["handle_schedule_approval", "create_approved_calendar_events"], "Successfully added 1 scheduled task(s) to your Google Calendar."),
    }

    def proceed(self, thread_id, on_step=None):
        self.calls.append("proceed")
        t = self.threads[thread_id]
        steps, message = self.CALENDAR[t["next"][0]]
        t.update(next=["wait_for_user"], waiting=True)
        t["conversation"]["assistant_message"] = message
        return Trace(steps=steps, thread=self._t(thread_id))

    def wait_idle(self, thread_id, timeout_s=90.0):
        self.calls.append("wait_idle")

    def hand_back(self, thread_id, conversation, message):
        self.calls.append("hand_back")
        t = self.threads[thread_id]
        t.update(next=["wait_for_user"], waiting=True, conversation={**conversation, "assistant_message": message})
        return Trace(thread=self._t(thread_id))

    ref: str | None = None
    delegation: dict = {}

    def _save_report(self, t: dict, status: str) -> None:
        """As her persist_reported_update does: straight into the reports table."""
        e = t["employee"]
        with self.db.begin() as c:
            a = c.execute(text("""SELECT assignment_id, work_item_id FROM workweave.work_item_assignments WHERE workspace_id=:w AND employee_id=:e
                                  AND status IN ('ASSIGNED','ACCEPTED','IN_PROGRESS') AND work_item_id=:i"""), {"w": e["workspace_id"], "e": e["employee_id"], "i": self.ref}).one()
            c.execute(text("""INSERT INTO workweave.work_item_reported_updates (organization_id, workspace_id, assignment_id, work_item_id, employee_id, work_session_id,
                                  reported_status, description, source_status_at_report, source_sync_status, update_type)
                              VALUES (:o, :w, :a, :i, :e, :s, :rs, 'Finished the inspection.', 'IN_PROGRESS', 'AWAITING_SOURCE', 'STATUS_CHANGE')"""),
                      {"o": e["organization_id"], "w": e["workspace_id"], "a": a.assignment_id, "i": a.work_item_id, "e": e["employee_id"], "s": t["session"], "rs": status})


@pytest.fixture()
def fake(engine):
    f = FakeCompanion(engine)
    install_test_companion(f)
    yield f
    install_test_companion(None)


def open_session(client) -> dict:
    r = client.post("/api/work-sessions", headers=H)
    assert r.status_code == 200, r.text
    return r.json()["data"]


def send(client, v: dict, msg: str, cid: str | None = None):
    return client.post(f"/api/work-sessions/{v['work_session_id']}/messages", json={"client_turn_id": cid or str(uuid.uuid4()), "expected_revision": v["revision"], "text": msg}, headers=H)


def test_the_opening_brief_is_saved_once(client, engine, fake):
    _assigned_story(client, engine)
    v = open_session(client)
    again = open_session(client)  # a reload, or a second tab
    assert again["work_session_id"] == v["work_session_id"]
    assert [m["sender"] for m in again["transcript"]] == ["AI"] and again["transcript"][0]["provenance"] == "WORK_ENGINE"
    assert again["assistant"]["status"] == "ok" and again["canvas"] == {"view": "BRIEFING"}
    assert [c for c in fake.calls if c != "wait_idle"] == ["start"]


def test_two_page_loads_opening_at_once_both_get_the_brief(client, engine, fake):
    ws = _assigned_story(client, engine)
    fake.busy_once = True  # this load's start collides with the other load's run
    v = open_session(client)
    assert v["assistant"]["status"] == "ok" and [m["text"] for m in v["transcript"]] == ["Brief: your top priority is Ticket #829."]
    assert open_session(client)["transcript"] == v["transcript"]
    assert count(engine, ws, "SELECT count(*) FROM workweave.work_session_messages WHERE workspace_id=:w") == 1  # saved once


def test_a_focus_reply_selects_the_item_and_a_retry_does_not_run_twice(client, engine, fake):
    _assigned_story(client, engine)
    fake.ref = item(client, "Ticket #829")["work_item_id"]
    v = open_session(client)
    cid = str(uuid.uuid4())
    r = send(client, v, "yes, let's start", cid)
    assert r.status_code == 200, r.text
    out = r.json()["data"]
    assert [m["sender"] for m in out["transcript"]] == ["AI", "EMPLOYEE", "AI"]
    assert out["transcript"][-1]["ui_action"] == "SHOW_WORK_ITEMS" and out["canvas"] == {"view": "WORK_ITEMS", "selected_id": fake.ref}
    again = send(client, v, "yes, let's start", cid)  # the same message sent again
    assert again.status_code == 200 and len(again.json()["data"]["transcript"]) == 3
    assert fake.calls.count("resume") == 1
    stale = send(client, v, "another")
    assert stale.status_code == 409 and code(stale) == "REVISION_CONFLICT"


def test_guidance_cites_only_this_workspaces_approved_chunks(client, engine, fake):
    ws = _assigned_story(client, engine)
    fake.ref = item(client, "Ticket #829")["work_item_id"]
    with engine.connect() as c:
        mine = c.execute(text("SELECT chunk_id FROM workweave.knowledge_chunks WHERE workspace_id=:w AND embedding IS NOT NULL ORDER BY chunk_index LIMIT 1"), {"w": ws}).scalar_one()
        other = c.execute(text("SELECT chunk_id FROM workweave.knowledge_chunks WHERE workspace_id<>:w LIMIT 1"), {"w": ws}).scalar_one()
    v = open_session(client)
    out = send(client, v, f"guide {mine} {other} not-a-uuid").json()["data"]
    reply = out["transcript"][-1]
    assert reply["ui_action"] == "SHOW_GUIDANCE" and out["canvas"] == {"view": "GUIDANCE", "guidance_id": reply["message_id"]}
    assert len(reply["citations"]) == 1 and reply["citations"][0]["label"].startswith("SOP-001 v3.4")  # the other workspace's chunk is dropped
    g = client.get(f"/api/work-sessions/{v['work_session_id']}/guidance/{reply['message_id']}").json()["data"]
    assert g["answer_status"] == "ANSWERED" and g["question"].startswith("guide") and g["related_work_item_id"] == fake.ref
    assert g["citations"][0]["excerpt"]["text"]


def test_a_report_the_engine_saved_gets_the_ticket_system_bookkeeping(client, engine, fake):
    ws = _assigned_story(client, engine)
    t = item(client, "Ticket #829")
    fake.ref = t["work_item_id"]
    client.post(f"/api/work-items/{t['work_item_id']}/reports", json={"idempotency_key": str(uuid.uuid4()), "expected_revision": t["revision"], "reported_status": "BLOCKED", "description": "Waiting for a part."}, headers=H)
    v = open_session(client)
    out = send(client, v, "done with 829").json()["data"]
    assert out["transcript"][-1]["ui_action"] == "SHOW_WORK_UPDATES" and out["canvas"] == {"view": "WORK_UPDATES"}
    with engine.connect() as c:
        states = c.execute(text("SELECT reported_status, source_sync_status FROM workweave.work_item_reported_updates WHERE workspace_id=:w ORDER BY reported_at"), {"w": ws}).all()
    assert [tuple(x) for x in states] == [("BLOCKED", "SUPERSEDED"), ("COMPLETED", "AWAITING_SOURCE")]
    assert count(engine, ws, "SELECT count(*) FROM workweave.outbox_events WHERE workspace_id=:w AND event_type='work.reported_done'") == 1  # Alex, the lead on shift
    assert count(engine, ws, "SELECT count(*) FROM workweave.audit_events WHERE workspace_id=:w AND action='work_report.status_change'") == 1
    shown = item(client, "Ticket #829")
    assert shown["status"] == "IN_PROGRESS" and shown["report"]["reported_status"] == "DONE" and shown["report"]["sync_status"] == "AWAITING_SOURCE"
    assert client.get("/api/work-state").json()["data"]["awaiting_sync_count"] == 1
    assert tool(client, shown, "COMPLETED", "Resolved.").status_code == 200  # the real status, in the ticket system
    assert item(client, "Ticket #829")["report"]["sync_status"] == "MATCHED"  # her COMPLETED matches the ticket's COMPLETED


@pytest.fixture()
def calendar(monkeypatch):
    from app.integrations import calendar_service

    state = {"now": "CONNECTED"}
    monkeypatch.setattr(calendar_service, "status", lambda: state["now"])
    return state


def test_calendar_and_scheduling_run_in_the_graph_when_connected_and_stay_in_the_chat(client, engine, fake, calendar):
    ws = _assigned_story(client, engine)
    v = open_session(client)
    v = send(client, v, "calendar today?").json()["data"]
    assert v["transcript"][-1]["text"].startswith("You have a team briefing") and v["transcript"][-1]["ui_action"] == "NO_VIEW_CHANGE"
    assert v["transcript"][-1]["provenance"] == "WORK_ENGINE" and "calendar_connect" not in v
    v = send(client, v, "schedule my tickets").json()["data"]
    out = send(client, v, "yes, schedule it").json()["data"]
    assert out["transcript"][-1]["text"].startswith("Successfully added") and out["canvas"] == {"view": "BRIEFING"}
    assert fake.calls.count("proceed") == 3 and "hand_back" not in fake.calls
    with engine.connect() as c:
        actions = c.execute(text("SELECT action FROM workweave.audit_events WHERE workspace_id=:w AND action LIKE 'work_schedule.%' ORDER BY created_at"), {"w": ws}).scalars().all()
    assert actions == ["work_schedule.requested", "work_schedule.events_created"]  # what happened, never the calendar's contents


def test_without_a_google_sign_in_the_reply_offers_to_connect_and_the_question_can_be_asked_again(client, engine, fake, calendar):
    _assigned_story(client, engine)
    calendar["now"] = "NOT_CONNECTED"
    v = open_session(client)
    v = send(client, v, "calendar today?").json()["data"]
    last = v["transcript"][-1]
    assert last["text"] == CALENDAR_CONNECT and last["provenance"] == "BACKEND_RECORD"
    assert v["calendar_connect"] == {"connect_url": "http://127.0.0.1:8001/auth/google", "retry_text": "calendar today?"}
    assert fake.calls[-1] == "hand_back" and "proceed" not in fake.calls and fake.thread(v["work_session_id"]).waiting
    assert client.get("/api/calendar/status").json()["data"] == {"enabled": True, "connected": False, "reachable": True}
    calendar["now"] = "CONNECTED"  # the employee signed in from the button
    assert client.get("/api/calendar/status").json()["data"]["connected"] is True
    again = send(client, v, "calendar today?").json()["data"]
    assert again["transcript"][-1]["text"].startswith("You have a team briefing") and "calendar_connect" not in again


def test_an_unreachable_calendar_service_gets_a_plain_reply(client, engine, fake, calendar):
    _assigned_story(client, engine)
    calendar["now"] = "UNREACHABLE"
    v = send(client, open_session(client), "calendar today?").json()["data"]
    assert v["transcript"][-1]["text"] == CALENDAR_DOWN and "calendar_connect" not in v


def test_with_calendar_switched_off_the_app_answers_and_the_graph_waits_again(client, engine, fake, calendar, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "companion_calendar", False)
    _assigned_story(client, engine)
    v = open_session(client)
    out = send(client, v, "calendar today?").json()["data"]
    assert out["transcript"][-1]["text"] == CALENDAR_OFF and out["transcript"][-1]["ui_action"] == "NO_VIEW_CHANGE"
    assert fake.calls[-1] == "hand_back" and fake.thread(v["work_session_id"]).waiting
    assert client.get("/api/calendar/status").json()["data"] == {"enabled": False, "connected": False}


def test_after_a_pause_the_next_message_starts_a_fresh_brief(client, engine, fake):
    _assigned_story(client, engine)
    fake.ref = item(client, "Ticket #829")["work_item_id"]
    v = open_session(client)
    v = send(client, v, "pause please").json()["data"]
    out = send(client, v, "back, let's go").json()["data"]
    assert [m["text"][:5] for m in out["transcript"] if m["sender"] == "AI"] == ["Brief", "Got i", "Brief", "Let's"]
    assert [c for c in fake.calls if c != "wait_idle"] == ["start", "resume", "start", "resume"]


def test_an_engine_failure_saves_nothing(client, engine, fake):
    ws = _assigned_story(client, engine)
    v = open_session(client)
    fake.fail = True
    r = send(client, v, "hello")
    assert r.status_code == 503 and code(r) == "DEPENDENCY_UNAVAILABLE"
    assert count(engine, ws, "SELECT count(*) FROM workweave.work_session_messages WHERE workspace_id=:w") == 1  # just the brief


def test_the_conversation_is_private_to_its_employee(client, engine, fake):
    from tests.test_demo_slice import pick

    _assigned_story(client, engine)
    v = open_session(client)
    pick(client, "Alex")  # the lead monitors work, not the member's conversation
    assert client.get(f"/api/work-sessions/{v['work_session_id']}").status_code == 404


def test_the_langgraph_adapter_reads_steps_and_guidance_chunks_from_the_stream():
    events = [
        ("metadata", {"run_id": "r"}),
        ("updates", {"wait_for_user": {"conversation": {}}}),
        ("updates", {"analyze_user_response": {"response_analysis": {"recommended_action": "GUIDE"}}}),
        ("updates|work_guidance:abc", {"retrieve_relevant_chunks": {"retrieved_knowledge": [{"chunk_id": "c1"}, "junk"]}}),
        ("updates", {"work_guidance": {"conversation": {}}}),
        ("updates", {"__interrupt__": [{"value": {"message": "hi"}}]}),
    ]
    body = "".join(f"event: {e}\ndata: {json.dumps(d)}\n\n" for e, d in events)
    state = {"values": {"conversation": {"assistant_message": "hi"}}, "next": ["wait_for_user"], "tasks": [{"name": "wait_for_user", "interrupts": [{"value": {}}]}]}
    seen: list[tuple[str, str]] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append((req.method, req.url.path))
        if req.url.path.endswith("/runs/stream"):
            sent = json.loads(req.content)
            assert sent["interrupt_before"] == ["calendar_inquiry"] and sent["command"]["resume"]["message"] == "how?"
            return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})
        if req.url.path.endswith("/state"):
            return httpx.Response(200, json=state)
        return httpx.Response(200, json={})

    g = LangGraphCompanion("http://graph.test", "ai_work_companion", client=httpx.Client(transport=httpx.MockTransport(handler)))
    trace = g.resume("t1", "how?", "TEXT", "cid", ["calendar_inquiry"])
    assert trace.steps == ["wait_for_user", "analyze_user_response", "retrieve_relevant_chunks", "work_guidance"]
    assert trace.retrieved == [{"chunk_id": "c1"}] and trace.thread.waiting and trace.stopped_before is None


# ---------------------------------------------------------------- read-aloud of companion replies
def test_companion_replies_are_read_aloud_only_for_their_employee(client, other_client, engine, fake):
    from app.services.voice import audio_cache
    from tests.test_demo_slice import pick
    from tests.test_voice import FakeVoice
    from app.integrations.voice import install_test_voice

    voice = FakeVoice()
    install_test_voice(voice)
    audio_cache.clear()
    try:
        _assigned_story(client, engine)
        fake.ref = item(client, "Ticket #829")["work_item_id"]
        v = send(client, open_session(client), "yes, let's start").json()["data"]
        brief, mine, reply = v["transcript"]
        base = f"/api/work-sessions/{v['work_session_id']}/voice/speech"
        r = client.get(f"{base}/{brief['message_id']}/stream")
        assert r.status_code == 200 and r.headers["x-sample-rate"] == "24000" and r.content == b"\x01\x00\x02\x00\x03\x00"
        assert voice.spoken == [brief["text"]]
        assert client.get(f"{base}/{brief['message_id']}/stream").content == r.content and len(voice.spoken) == 1  # replay from the cache
        assert client.get(f"{base}/{reply['message_id']}").headers["content-type"] == "audio/wav"
        assert client.get(f"{base}/{mine['message_id']}/stream").status_code == 404  # never the employee's own words
        assert client.get(f"{base}/not-a-message/stream").status_code == 422
        pick(client, "Alex")  # the lead can't hear a member's conversation
        assert client.get(f"{base}/{reply['message_id']}/stream").status_code == 404
        assert other_client.get(f"{base}/{reply['message_id']}/stream").status_code in (401, 404)
        install_test_voice(None)
    finally:
        install_test_voice(None)
        audio_cache.clear()


def test_the_adapter_waits_while_another_run_is_busy(monkeypatch):
    import app.integrations.companion_engine as ce

    states = iter(["busy", "busy", "interrupted"])
    monkeypatch.setattr(ce.time, "sleep", lambda s: None)
    g = LangGraphCompanion("http://graph.test", "ai_work_companion", client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"status": next(states)}))))
    g.wait_idle("t1")
    assert next(states, "done") == "done"  # polled until the other run finished
    stuck = LangGraphCompanion("http://graph.test", "ai_work_companion", client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"status": "busy"}))))
    with pytest.raises(ce.CompanionBusy):
        stuck.wait_idle("t1", timeout_s=0)


@pytest.mark.parametrize(("answer", "expected"), [(200, "CONNECTED"), (401, "NOT_CONNECTED"), (502, "UNREACHABLE"), (None, "UNREACHABLE")])
def test_the_calendar_check_reads_a_one_minute_window(answer, expected):
    from app.integrations import calendar_service

    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path == "/calendar/availability" and "start" in req.url.params and "end" in req.url.params
        if answer is None:
            raise httpx.ConnectError("down")
        return httpx.Response(answer, json={})

    calendar_service.install_test_client(httpx.Client(transport=httpx.MockTransport(handler)))
    try:
        assert calendar_service.status() == expected
    finally:
        calendar_service.install_test_client(None)



# ---------------------------------------------------------------- delegation from the conversation
def _lead_shift(engine, ws: str, lead: str) -> str:
    with engine.connect() as c:
        return str(c.execute(text("""SELECT shift_instance_id FROM workweave.shift_instances WHERE workspace_id=:w AND shift_lead_employee_id=:e
                                      AND scheduled_start_at <= now() AND scheduled_end_at > now() AND status NOT IN ('CANCELLED','COMPLETED')"""), {"w": ws, "e": lead}).scalar_one())


def test_the_shift_lead_hands_a_ticket_to_a_teammate_on_the_same_shift_after_confirming(client, engine, fake):
    from tests.test_companion_commands import emp
    from tests.test_demo_slice import pick

    ws = _assigned_story(client, engine)  # Alex holds #910, Jamie #829
    pick(client, "Alex")
    alex, sam, jamie, priya = (emp(engine, ws, n) for n in ("Alex", "Sam", "Jamie", "Priya"))
    t910, t829 = item(client, "Ticket #910")["work_item_id"], item(client, "Ticket #829")["work_item_id"]
    fake.delegation = {"shift_instance_id": _lead_shift(engine, ws, alex), "proposal": [
        {"work_item_id": t910, "employee_id": sam, "reason": "Asked to hand #910 to Sam."},
        {"work_item_id": t829, "employee_id": jamie, "reason": "Already Jamie's."},
        {"work_item_id": t910, "employee_id": priya, "reason": "Duplicate."},
    ]}
    out = send(client, open_session(client), "delegate 910 to Sam").json()["data"]
    reply, note = out["transcript"][-2], out["transcript"][-1]
    assert reply["ui_action"] == "SHOW_DELEGATION_PROPOSAL" and out["canvas"]["view"] == "DELEGATION_PROPOSAL"
    assert note["sender"] == "SYSTEM" and "Ticket #829 (already with that person)" in note["text"] and "Ticket #910 (suggested twice" in note["text"]
    pid = out["canvas"]["proposal_id"]
    p = client.get(f"/api/delegation-proposals/{pid}").json()["data"]
    assert p["origin"] == "AI_ENGINE" and p["status"] == "PROPOSED" and [(i["work_item_id"], i["recommended_employee_id"]) for i in p["items"]] == [(t910, sam)]
    assert set(p["candidate_ids"]) == {sam, jamie, alex}  # people on Alex's shift, Alex included
    assert item(client, "Ticket #910")["assignee_id"] == alex  # nothing changes before confirming
    off_shift = client.patch(f"/api/delegation-proposals/{pid}", json={"idempotency_key": str(uuid.uuid4()), "expected_revision": p["revision"], "work_item_id": t910, "final_employee_id": priya}, headers=H)
    assert off_shift.status_code == 409 and code(off_shift) == "GUARD_FAILED"
    done = client.post(f"/api/delegation-proposals/{pid}/confirm", json={"idempotency_key": str(uuid.uuid4()), "expected_revision": p["revision"]}, headers=H)
    assert done.status_code == 200, done.text
    assert item(client, "Ticket #910")["assignee_id"] == sam
    with engine.connect() as c:
        states = dict(c.execute(text("SELECT employee_id::text, status FROM workweave.work_item_assignments WHERE workspace_id=:w AND work_item_id=:i"), {"w": ws, "i": t910}).all())
    assert states == {alex: "CANCELLED", sam: "ASSIGNED"}
    assert count(engine, ws, "SELECT count(*) FROM workweave.audit_events WHERE workspace_id=:w AND action='work_item_assignment.handed_over'") == 1
    assert count(engine, ws, "SELECT count(*) FROM workweave.outbox_events WHERE workspace_id=:w AND event_type='work.assigned' AND recipient_employee_id=CAST(:s AS uuid)".replace(":s", f"'{sam}'")) == 1


def test_a_member_who_isnt_the_shift_lead_gets_no_proposal(client, engine, fake):
    from tests.test_companion_commands import emp

    ws = _assigned_story(client, engine)  # Jamie is a member, not the lead
    fake.delegation = {"shift_instance_id": _lead_shift(engine, ws, emp(engine, ws, "Alex")), "proposal": [
        {"work_item_id": item(client, "Ticket #829")["work_item_id"], "employee_id": emp(engine, ws, "Sam"), "reason": "x"}]}
    out = send(client, open_session(client), "delegate 829 to Sam").json()["data"]
    assert out["transcript"][-1]["text"].startswith("I couldn't prepare that delegation proposal: only the lead of the shift in progress")
    assert out["transcript"][-1]["provenance"] == "BACKEND_RECORD" and out["canvas"] == {"view": "BRIEFING"}
    assert count(engine, ws, "SELECT count(*) FROM workweave.delegation_proposals WHERE workspace_id=:w AND context_revisions->>'origin'='AI_ENGINE'") == 0



def test_a_why_question_opens_the_ticket_it_was_about(client, engine, fake):
    _assigned_story(client, engine)  # Jamie holds #829
    fake.ref = item(client, "Ticket #829")["work_item_id"]
    out = send(client, open_session(client), "why did I get 829?").json()["data"]
    assert out["transcript"][-1]["ui_action"] == "SHOW_WORK_ITEMS" and out["canvas"] == {"view": "WORK_ITEMS", "selected_id": fake.ref}
    fake.ref = str(uuid.uuid4())  # a ticket this employee can't see is never opened
    out = send(client, out, "why about that one?").json()["data"]
    assert out["canvas"] == {"view": "WORK_ITEMS"}



def test_the_lead_moves_a_teammates_ticket_and_confirms_it_in_the_chat(client, engine, fake):
    from tests.test_companion_commands import emp
    from tests.test_demo_slice import pick

    ws = _assigned_story(client, engine)  # Jamie holds #829
    pick(client, "Alex")
    alex, sam, jamie = (emp(engine, ws, n) for n in ("Alex", "Sam", "Jamie"))
    t829 = item(client, "Ticket #829")["work_item_id"]
    fake.delegation = {"shift_instance_id": _lead_shift(engine, ws, alex), "proposal": [{"work_item_id": t829, "employee_id": sam, "reason": "Asked to move #829 to Sam."}]}
    v = send(client, open_session(client), "delegate 829 from Jamie to Sam").json()["data"]
    pid = v["canvas"]["proposal_id"]
    assert item(client, "Ticket #829")["assignee_id"] == jamie  # nothing changes before confirming
    out = send(client, v, "confirm").json()["data"]
    last = out["transcript"][-1]
    assert last["text"].startswith("Confirmed. Ticket #829 is now with Sam Kim") and last["provenance"] == "BACKEND_RECORD"
    assert out["canvas"] == {"view": "DELEGATION_PROPOSAL", "proposal_id": pid}
    assert client.get(f"/api/delegation-proposals/{pid}").json()["data"]["status"] == "CONFIRMED"
    with engine.connect() as c:
        states = dict(c.execute(text("SELECT employee_id::text, status FROM workweave.work_item_assignments WHERE workspace_id=:w AND work_item_id=:i"), {"w": ws, "i": t829}).all())
    assert (states[jamie], states[sam]) == ("CANCELLED", "ASSIGNED")  # (the pack also has an older cancelled one)
    assert count(engine, ws, "SELECT count(*) FROM workweave.outbox_events WHERE workspace_id=:w AND event_type='work.unassigned' AND recipient_employee_id=CAST(:j AS uuid)".replace(":j", f"'{jamie}'")) == 1
    pick(client, "Sam")  # the new holder sees it in their own lists right away
    assert item(client, "Ticket #829")["assignee_id"] == sam
    pick(client, "Alex")
    again = send(client, out, "confirm").json()["data"]  # nothing pending any more
    assert again["transcript"][-1]["text"].startswith("I couldn't confirm it: This proposal is already confirmed")


def test_confirm_in_the_chat_needs_a_proposal_just_shown(client, engine, fake):
    from tests.test_demo_slice import pick

    _assigned_story(client, engine)
    pick(client, "Alex")
    out = send(client, open_session(client), "confirm").json()["data"]
    assert out["transcript"][-1]["text"].startswith("There's no delegation proposal waiting for your confirmation")



def test_the_lead_can_take_a_ticket_themself_from_the_chat(client, engine, fake):
    from tests.test_companion_commands import emp
    from tests.test_demo_slice import pick

    ws = _assigned_story(client, engine)  # Jamie holds #829
    pick(client, "Alex")
    alex = emp(engine, ws, "Alex")
    t829 = item(client, "Ticket #829")["work_item_id"]
    fake.delegation = {"shift_instance_id": _lead_shift(engine, ws, alex), "proposal": [{"work_item_id": t829, "employee_id": alex, "reason": "Assign it to me."}]}
    v = send(client, open_session(client), "delegate 829 to me").json()["data"]
    assert v["canvas"]["view"] == "DELEGATION_PROPOSAL"
    out = send(client, v, "confirm").json()["data"]
    assert out["transcript"][-1]["text"].startswith("Confirmed. Ticket #829 is now with Alex Rivera")
    assert item(client, "Ticket #829")["assignee_id"] == alex



def test_the_stream_shows_progress_then_the_saved_reply(client, engine, fake):
    _assigned_story(client, engine)
    fake.ref = item(client, "Ticket #829")["work_item_id"]
    v = open_session(client)
    r = client.post(f"/api/work-sessions/{v['work_session_id']}/messages/stream", json={"client_turn_id": str(uuid.uuid4()), "expected_revision": v["revision"], "text": "guide me"}, headers=H)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    events = [(b.split("\n")[0][7:], json.loads(b.split("\n")[1][6:])) for b in r.text.strip().split("\n\n")]
    labels = [d["label"] for e, d in events if e == "progress"]
    assert labels[0] == "Understanding your message…" and "Writing guidance from the procedure…" in labels
    done = events[-1]
    assert done[0] == "done" and done[1]["data"]["transcript"][-1]["ui_action"] == "SHOW_GUIDANCE"


def test_the_stream_reports_a_failure_as_an_error_event(client, engine, fake):
    _assigned_story(client, engine)
    v = open_session(client)
    fake.fail = True
    r = client.post(f"/api/work-sessions/{v['work_session_id']}/messages/stream", json={"client_turn_id": str(uuid.uuid4()), "expected_revision": v["revision"], "text": "hello"}, headers=H)
    last = r.text.strip().split("\n\n")[-1]
    assert last.startswith("event: error") and "DEPENDENCY_UNAVAILABLE" in last


# ---------------------------------------------------------------- the companion speaks first
def test_people_hear_about_changes_to_their_work_in_the_chat(client, engine, fake):
    from tests.test_companion_commands import emp
    from tests.test_demo_slice import pick

    ws = _assigned_story(client, engine)  # Jamie holds #829
    jamie_view = open_session(client)  # both sessions are open before the change
    pick(client, "Sam")
    sam_view = open_session(client)
    pick(client, "Alex")
    t = item(client, "Ticket #829")
    moved = client.post(f"/api/work-items/{t['work_item_id']}/assignee", json={"idempotency_key": str(uuid.uuid4()), "expected_revision": t["revision"], "employee_id": emp(engine, ws, "Sam")}, headers=H)
    assert moved.status_code == 200, moved.text
    pick(client, "Sam")
    sam = open_session(client)  # the page re-reads when the team's work changes
    assert sam["transcript"][-1]["text"].startswith("Ticket #829 was assigned to you.") and sam["transcript"][-1]["provenance"] == "BACKEND_RECORD"
    assert open_session(client)["transcript"] == sam["transcript"]  # announced once
    pick(client, "Jamie")
    jamie = open_session(client)
    assert jamie["transcript"][-1]["text"].startswith("One of your tickets was moved to someone else")
    assert jamie_view and sam_view



# ---------------------------------------------------------------- app actions from the chat
def act(client, v, **action):
    return send(client, v, "act " + json.dumps(action)).json()["data"]


def test_views_filters_and_voice_settings_by_chat(client, engine, fake):
    _assigned_story(client, engine)
    v = open_session(client)
    v = act(client, v, action="SHOW_WORK_ITEMS", status_filter=["BLOCKED"])
    assert v["canvas"] == {"view": "WORK_ITEMS", "filters": {"status": ["BLOCKED"]}} and v["transcript"][-1]["text"] == "Here are your blocked tickets."
    v = act(client, v, action="SHOW_WORK_UPDATES")
    assert v["canvas"] == {"view": "WORK_UPDATES"}
    v = act(client, v, action="SHOW_BRIEFING")
    assert v["canvas"] == {"view": "BRIEFING"}
    v = act(client, v, action="READ_ALOUD_OFF")
    assert v["transcript"][-1]["client_action"] == "READ_ALOUD_OFF"
    v = act(client, v, action="NONE")
    assert v["transcript"][-1]["text"].startswith("I can't do that from the chat yet")


def test_open_in_the_ticket_system_and_accept_by_chat(client, engine, fake):
    ws = _assigned_story(client, engine)  # Jamie holds #829; #910 is Alex's
    v = act(client, open_session(client), action="OPEN_TICKET_SYSTEM", work_item_reference="829")
    t829 = item(client, "Ticket #829")["work_item_id"]
    last = v["transcript"][-1]
    assert last["link"] == {"label": "Open in the ticket system", "href": f"/companion/tool/?item={t829}"} and v["canvas"] == {"view": "WORK_ITEMS", "selected_id": t829}
    v = act(client, v, action="OPEN_TICKET_SYSTEM", work_item_reference="Ticket #910")
    assert v["transcript"][-1]["text"].startswith("I couldn't find Ticket #910")  # not Jamie's: not hers to see
    v = act(client, v, action="ACCEPT_ASSIGNMENT", work_item_reference="#829")
    assert v["transcript"][-1]["text"] == "Got it: Ticket #829 is yours."
    with engine.connect() as c:
        assert c.execute(text("SELECT status FROM workweave.work_item_assignments WHERE workspace_id=:w AND work_item_id=:i AND status <> 'CANCELLED'"), {"w": ws, "i": t829}).scalar_one() == "ACCEPTED"
    v = act(client, v, action="ACCEPT_ASSIGNMENT", work_item_reference="829")
    assert v["transcript"][-1]["text"] == "You've already taken Ticket #829."


def test_the_lead_changes_or_cancels_a_proposal_by_chat(client, engine, fake):
    from tests.test_companion_commands import emp
    from tests.test_demo_slice import pick

    ws = _assigned_story(client, engine)
    pick(client, "Alex")
    alex, sam, jamie = (emp(engine, ws, n) for n in ("Alex", "Sam", "Jamie"))
    fake.delegation = {"shift_instance_id": _lead_shift(engine, ws, alex), "proposal": [{"work_item_id": item(client, "Ticket #910")["work_item_id"], "employee_id": sam, "reason": "x"}]}
    v = send(client, open_session(client), "delegate 910 to Sam").json()["data"]
    pid = v["canvas"]["proposal_id"]
    v = act(client, v, action="CHANGE_PROPOSAL_PERSON", person_name="Jamie")
    assert v["transcript"][-1]["text"] == 'Changed: Ticket #910 now goes to Jamie Chen. Say "confirm" to assign it.'
    p = client.get(f"/api/delegation-proposals/{pid}").json()["data"]
    assert p["status"] == "EDITED" and p["items"][0]["final_employee_id"] == jamie and p["items"][0]["recommended_employee_id"] == sam
    v = act(client, v, action="REJECT_PROPOSAL", reason="Not needed")
    assert v["transcript"][-1]["text"] == "Cancelled. Nothing was assigned."
    assert client.get(f"/api/delegation-proposals/{pid}").json()["data"]["status"] == "REJECTED"
    v = act(client, v, action="REJECT_PROPOSAL")
    assert v["transcript"][-1]["text"].startswith("I couldn't do that: This proposal is already rejected")


def test_knowledge_notes_by_chat(client, engine, fake):
    ws = _assigned_story(client, engine)
    v = act(client, open_session(client), action="SAVE_NOTE", note_text="Check the mounting bolts first.")
    assert v["transcript"][-1]["text"].startswith('Saved as a private draft note: "Check the mounting bolts first."')
    v = act(client, v, action="SUBMIT_NOTE")
    assert v["transcript"][-1]["text"].startswith("That note is private")
    v = act(client, v, action="SAVE_NOTE", note_text="Calibrate before the vibration test.", note_audience="TEAM")
    v = act(client, v, action="SUBMIT_NOTE")
    assert v["transcript"][-1]["text"] == "Submitted your note for review."
    with engine.connect() as c:
        states = c.execute(text("SELECT content, status FROM workweave.memory_drafts WHERE workspace_id=:w ORDER BY created_at"), {"w": ws}).all()
    assert [tuple(x) for x in states] == [("Check the mounting bolts first.", "DRAFT"), ("Calibrate before the vibration test.", "PENDING_REVIEW")]
