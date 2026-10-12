"""The AI engineer's LangGraph graph as the onboarding tutor (ADR-030), against a fake LangGraph API.

The fake saves turns exactly as her `record_turn` node does (contract "engine-1"), so these tests
check the app's side: authorization, caps, driving the graph, idempotency and reading the result.
No real graph or model is called.
"""

import json
import uuid

import httpx
import pytest
from sqlalchemy import text

from app.integrations.langgraph_engine import LangGraphEngine
from app.integrations.tutor import install_test_tutor
from tests.test_demo_slice import code
from tests.test_usage_caps import caps  # noqa: F401 (fixture)
from tests.test_voice import learner_session


class FakeGraph:
    """A LangGraph API that remembers each thread and saves turns like the real graph."""

    def __init__(self, engine):
        self.engine = engine
        self.threads: dict[str, dict] = {}
        self.runs: list[dict] = []
        self.script: list[str] = []  # what the next resume does: teach | check | pause | complete | fail | silent
        self.unreachable = False

    # ---------------------------------------------------------------- what her record_turn writes
    def _save(self, sid: str, learner: dict, reply: dict, cid: str | None, extra: dict | None = None, completed_subtopic: bool = False):
        with self.engine.begin() as c:
            s = c.execute(text("UPDATE workweave.learning_sessions SET revision = revision + 1 WHERE learning_session_id=:s RETURNING organization_id, workspace_id, revision, current_subtopic_id, learning_assignment_id, employee_id"), {"s": sid}).mappings().one()
            env = {"contract_version": "engine-1", "reply": reply, **(extra or {})}
            c.execute(
                text("""INSERT INTO workweave.learning_turns (organization_id, workspace_id, learning_session_id, client_turn_id, input_hash, sequence, input_reference, response_envelope, committed_revision, stage)
                        SELECT :o, :w, :s, :cid, 'h', COALESCE(MAX(sequence), -1) + 1, CAST(:inp AS jsonb), CAST(:env AS jsonb), :rev, 'COMMITTED'
                        FROM workweave.learning_turns WHERE learning_session_id = :s"""),
                {"o": s["organization_id"], "w": s["workspace_id"], "s": sid, "cid": cid or str(uuid.uuid4()), "inp": json.dumps(learner), "env": json.dumps(env), "rev": s["revision"]},
            )
            if not completed_subtopic:  # like record_turn: the first saved reply starts the item
                c.execute(text("UPDATE workweave.employee_learning_progress SET status='IN_PROGRESS', started_at=now() WHERE learning_assignment_id=:la AND subtopic_id=:st AND status='NOT_STARTED'"),
                          {"la": s["learning_assignment_id"], "st": s["current_subtopic_id"]})
            if completed_subtopic:
                c.execute(text("UPDATE workweave.employee_learning_progress SET status='COMPLETED', completed_at=now() WHERE learning_assignment_id=:la AND subtopic_id=:st"),
                          {"la": s["learning_assignment_id"], "st": s["current_subtopic_id"]})

    def citation(self, sid: str) -> dict:
        with self.engine.connect() as c:
            v, sec = c.execute(text("""SELECT ks.document_version_id, ks.section_id FROM workweave.knowledge_sections ks
                                       JOIN workweave.learning_sessions ls ON ls.workspace_id = ks.workspace_id
                                       WHERE ls.learning_session_id=:s AND ks.section_key='h2:1/h3:1'"""), {"s": sid}).one()
        return {"document_version_id": str(v), "section_id": str(sec), "chunk_id": None}

    def _stream(self, tid: str, t: dict, body: dict) -> httpx.Response:
        """A streamed resume: same saves as runs/wait, reported as step events."""
        pending = bool((t["values"].get("learning") or {}).get("pending_question"))
        step = self.script[0] if self.script else "teach"
        if step == "fail":
            self.script.pop(0)
            self.runs.append(body)
            return httpx.Response(200, content=_sse([("updates", {"wait_for_user": {}}), ("error", {"error": "boom"})]), headers={"content-type": "text/event-stream"})
        wait = self.handler(httpx.Request("POST", f"http://graph.test/threads/{tid}/runs/wait", json={**body, "stream_mode": None}))
        assert wait.status_code == 200
        return httpx.Response(200, content=_sse(_steps_for(step, pending)), headers={"content-type": "text/event-stream"})

    # ---------------------------------------------------------------- the API
    def handler(self, req: httpx.Request) -> httpx.Response:
        if self.unreachable:
            raise httpx.ConnectError("down")
        path, body = req.url.path, json.loads(req.content) if req.content else {}
        if req.method == "POST" and path == "/threads":
            self.threads.setdefault(body["thread_id"], {"values": {}, "waiting": False})
            return httpx.Response(200, json={"thread_id": body["thread_id"]})
        tid = path.split("/")[2]
        t = self.threads.get(tid)
        if req.method == "GET" and path.endswith("/state"):
            if not t:
                return httpx.Response(404)
            return httpx.Response(200, json={"values": t["values"], "next": ["wait_for_user"] if t["waiting"] else [], "tasks": [{"interrupts": [{"value": {}}]}] if t["waiting"] else []})
        streamed = path.endswith("/runs/stream")
        assert (streamed or path.endswith("/runs/wait")) and body["assistant_id"] == "ai_adaptive_onboarding"
        if streamed:
            return self._stream(tid, t, body)
        self.runs.append(body)
        cfg = body["config"]["configurable"]
        if "input" in body:  # start: the opening for the current item
            self._save(tid, {}, {"kind": "TEACHING", "text": "What have you done before to find the current procedure?", "strategy": None, "citations": []}, None)
            t["values"], t["waiting"] = {"employee": body["input"]["employee"], "learning": {"current_status": "NOT_STARTED"}}, True
            return httpx.Response(200, json=t["values"])
        msg = body["command"]["resume"]
        learner = {"text": msg["message"], "input_kind": cfg["input_kind"], **({"interrupted_previous_reply": True} if cfg.get("interrupted_previous_reply") else {})}
        step = self.script.pop(0) if self.script else "teach"
        if step == "fail":
            return httpx.Response(500, json={"detail": "boom"})
        if step == "silent":
            return httpx.Response(200, json={"learning": {"current_status": "IN_PROGRESS"}})
        if step == "pause":
            t["values"], t["waiting"] = {"response_analysis": {"recommended_action": "PAUSE"}, "learning": {"current_status": "IN_PROGRESS"}}, False
            return httpx.Response(200, json=t["values"])
        if step == "teach":
            self._save(tid, learner, {"kind": "TEACHING", "text": "Check the controlled registry for the current version.", "strategy": "CONCISE", "citations": [self.citation(tid)]}, cfg["client_turn_id"])
        elif step == "check":
            self._save(tid, learner, {"kind": "CHECK", "text": "Ticket #829 links v3.3. What do you do?", "strategy": None, "citations": []}, cfg["client_turn_id"])
            t["values"] = {**t["values"], "learning": {"current_status": "IN_PROGRESS", "pending_question": "Ticket #829 links v3.3. What do you do?"}}
            t["waiting"] = True
            return httpx.Response(200, json=t["values"])
        elif step == "complete":
            self._save(tid, learner, {"kind": "TEACHING", "text": "", "strategy": None, "citations": []}, cfg["client_turn_id"],
                       extra={"assessment": {"outcome": "CORRECT", "criteria_version": "c1", "evidence": "PASSED"}, "completed_subtopic": {"name": "Find the current procedure"}}, completed_subtopic=True)
            t["values"], t["waiting"] = {"learning": {"current_status": "COMPLETED"}}, False
            return httpx.Response(200, json=t["values"])
        t["waiting"] = True
        return httpx.Response(200, json=t["values"])


def _steps_for(step: str, pending: bool) -> list[tuple[str, dict]]:
    """The step events her graph emits for each scripted outcome (names as in her graph)."""
    first = [("updates", {"wait_for_user": {}})]
    if pending:
        grade = {"complete": "CORRECT", "teach": "INCORRECT"}.get(step, "PARTIAL")
        first.append(("updates", {"evaluate_assessment": {"assessment": {"outcome": grade}}}))
    else:
        first.append(("updates", {"analyze_user_response": {"response_analysis": {"recommended_action": {"check": "ASSESS", "pause": "PAUSE"}.get(step, "TEACH")}}}))
    tail = {
        "teach": [("updates|teaching:x", {"retrieve_knowledge": {}}), ("updates|teaching:x", {"generate_response": {}}), ("updates", {"teaching": {}}), ("updates", {"record_turn": {}})],
        "check": [("updates", {"assessment": {}}), ("updates", {"record_turn": {}})],
        "complete": [("updates", {"progression": {}}), ("updates", {"record_turn": {}})],
        "pause": [],
    }.get(step, [])
    return first + tail


def _sse(events: list[tuple[str, dict]]) -> bytes:
    return "".join(f"event: {e}\ndata: {json.dumps(d)}\n\n" for e, d in [("metadata", {"run_id": "r"}), *events]).encode()


@pytest.fixture()
def graph(engine):
    g = FakeGraph(engine)
    install_test_tutor(LangGraphEngine("http://graph.test", "ai_adaptive_onboarding", client=httpx.Client(transport=httpx.MockTransport(g.handler))))
    yield g
    install_test_tutor(None)


def send(client, view, msg="Which version?", kind="TEXT", cid=None, interrupted=False):
    return client.post(f"/api/onboarding/sessions/{view['learning_session_id']}/turns",
                       json={"client_turn_id": cid or str(uuid.uuid4()), "expected_revision": view["revision"], "text": msg, "input_kind": kind, "interrupted_previous_reply": interrupted})


def test_start_opens_the_conversation_once_with_the_tutors_opening(client, graph):
    v = learner_session(client)
    assert [m["sender"] for m in v["transcript"]] == ["AI"]  # the opening has no learner message
    assert v["transcript"][0]["text"].startswith("What have you done before")
    assert v["tutor"]["status"] == "ok"
    starts = [r for r in graph.runs if "input" in r]
    assert len(starts) == 1 and starts[0]["input"]["employee"]["session_id"] == v["learning_session_id"]
    assert client.post("/api/onboarding/sessions").json()["data"]["transcript"] == v["transcript"]  # resuming doesn't re-open
    assert len([r for r in graph.runs if "input" in r]) == 1
    assert client.get("/api/capabilities").json()["data"]["conversation_engine"] == "AVAILABLE"


def test_a_message_resumes_the_graph_and_the_saved_turn_is_shown(client, engine, graph):
    v = learner_session(client)
    r = send(client, v, "Which version should I follow?", kind="VOICE_TRANSCRIPT", interrupted=True)
    assert r.status_code == 200, r.text
    run = graph.runs[-1]
    assert run["command"] == {"resume": {"message": "Which version should I follow?", "input_kind": "VOICE_TRANSCRIPT"}}
    assert run["config"]["configurable"]["input_kind"] == "VOICE_TRANSCRIPT" and run["config"]["configurable"]["interrupted_previous_reply"] is True
    v2 = r.json()["data"]
    learner_msg, reply = v2["transcript"][-2:]
    assert learner_msg["text"] == "Which version should I follow?" and learner_msg["input_kind"] == "VOICE_TRANSCRIPT"
    assert reply["text"] == "Check the controlled registry for the current version."
    assert reply["citations"][0]["label"].startswith("SOP-001 v3.4") and reply["citations"][0]["excerpt"]["text"]
    assert v2["revision"] > v["revision"]
    with engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM workweave.audit_events WHERE action='learning_turn.recorded' AND workspace_id=(SELECT workspace_id FROM workweave.learning_sessions WHERE learning_session_id=:s)"), {"s": v["learning_session_id"]}).scalar_one() == 1


def test_a_retried_message_returns_the_saved_reply_without_running_the_graph_again(client, graph):
    v = learner_session(client)
    cid = str(uuid.uuid4())
    first = send(client, v, cid=cid).json()["data"]
    runs = len(graph.runs)
    again = send(client, v, cid=cid)  # same ID, stale revision: still the saved answer
    assert again.status_code == 200 and again.json()["data"]["transcript"] == first["transcript"]
    assert len(graph.runs) == runs


def test_an_engine_failure_saves_nothing_and_keeps_the_message(client, engine, graph):
    v = learner_session(client)
    graph.script = ["fail"]
    r = send(client, v)
    assert r.status_code == 503 and code(r) == "DEPENDENCY_UNAVAILABLE" and r.json()["error"]["retryable"]
    assert "still in the box" in r.json()["error"]["message"]
    graph.script = ["silent"]  # finished without saving a reply: never shown as an answer
    assert send(client, v).status_code == 503
    assert len(client.get(f"/api/onboarding/sessions/{v['learning_session_id']}").json()["data"]["transcript"]) == 1


def test_asking_to_stop_pauses_the_session(client, graph):
    v = learner_session(client)
    graph.script = ["pause"]
    r = send(client, v, "Can we stop here for today?")
    assert r.status_code == 200 and r.json()["data"]["status"] == "PAUSED"


def test_a_check_question_is_the_open_question(client, graph):
    v = learner_session(client)
    graph.script = ["check"]
    v2 = send(client, v).json()["data"]
    assert v2["transcript"][-1]["kind"] == "CHECK"
    assert v2["pending_check"]["text"] == "Ticket #829 links v3.3. What do you do?"
    v3 = send(client, v2).json()["data"]  # answered with a teaching reply: no longer open
    assert v3["pending_check"] is None


def test_completion_shows_the_outcome_and_continue_opens_the_next_item(client, graph):
    v = learner_session(client)
    graph.script = ["complete"]
    v2 = send(client, v, "I'd check the registry and escalate the v3.3 link.").json()["data"]
    done = v2["transcript"][-1]
    assert done["kind"] == "COMPLETION" and done["text"] == "Find the current procedure is complete."
    assert done["assessment"]["outcome"] == "CORRECT" and done["assessment"]["note"] == "Counted as evidence for this objective."
    assert v2["awaiting_continue"] is True
    r = send(client, v2)
    assert r.status_code == 409 and "Continue" in r.json()["error"]["message"]
    r = client.post(f"/api/onboarding/sessions/{v['learning_session_id']}/continue", json={"expected_revision": v2["revision"]})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["transcript"][-1]["text"].startswith("What have you done before")  # the next item's opening
    assert len([x for x in graph.runs if "input" in x]) == 2


def test_caps_apply_before_the_graph_runs(client, graph, caps):  # noqa: F811
    caps(PUBLIC_RUN_TUTOR_TURN=1)
    v = learner_session(client)  # the opening uses the one allowed turn
    runs = len(graph.runs)
    r = send(client, v)
    assert r.status_code == 429 and code(r) == "LIMIT_REACHED"
    assert len(graph.runs) == runs


def test_an_unreachable_engine_leaves_the_session_saved_and_says_so(client, graph):
    graph.unreachable = True
    v = learner_session(client)
    assert v["status"] == "ACTIVE" and v["transcript"] == []
    assert v["tutor"]["status"] == "unavailable" and "Reload" in v["tutor"]["message"]
    graph.unreachable = False
    v2 = client.post("/api/onboarding/sessions").json()["data"]  # reload: opens now
    assert len(v2["transcript"]) == 1


def test_continue_needs_the_engine(client):
    v = learner_session(client)
    r = client.post(f"/api/onboarding/sessions/{v['learning_session_id']}/continue", json={"expected_revision": v["revision"]})
    assert r.status_code == 501 and code(r) == "CAPABILITY_UNAVAILABLE"


# ---------------------------------------------------------------- progress while the tutor works
def stream_turn(client, view, msg="Which version?", cid=None):
    r = client.post(f"/api/onboarding/sessions/{view['learning_session_id']}/turns/stream",
                    json={"client_turn_id": cid or str(uuid.uuid4()), "expected_revision": view["revision"], "text": msg, "input_kind": "TEXT"})
    events = []
    if r.headers.get("content-type", "").startswith("text/event-stream"):
        for block in r.text.strip().split("\n\n"):
            lines = dict(line.split(": ", 1) for line in block.splitlines())
            events.append((lines["event"], json.loads(lines["data"])))
    return r, events


def test_progress_is_reported_while_the_tutor_works_then_the_saved_reply(client, graph):
    v = learner_session(client)
    r, events = stream_turn(client, v)
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store, no-transform"  # proxies must not buffer
    labels = [d["label"] for e, d in events if e == "progress"]
    assert labels == ["Understanding your message…", "Finding the right part of the procedure…", "Writing a reply…"]
    kind, done = events[-1]
    assert kind == "done" and done["data"]["transcript"][-1]["text"] == "Check the controlled registry for the current version."
    assert done["request_id"]


def test_answering_a_check_question_reports_grading(client, graph):
    v = learner_session(client)
    graph.script = ["check"]
    v2 = send(client, v)
    graph.script = ["complete"]
    _, events = stream_turn(client, v2.json()["data"], "I'd check the registry first.")
    assert [d["label"] for e, d in events if e == "progress"] == ["Checking your answer…", "Recording your progress…"]
    assert events[-1][0] == "done" and events[-1][1]["data"]["awaiting_continue"] is True


def test_a_failure_while_streaming_is_an_error_event_and_saves_nothing(client, graph):
    v = learner_session(client)
    graph.script = ["fail"]
    r, events = stream_turn(client, v)
    assert events[-1] == ("error", {"request_id": events[-1][1]["request_id"], "error": {"code": "DEPENDENCY_UNAVAILABLE", "message": "The tutor couldn't reply. Nothing was saved; your message is still in the box, so you can try again.", "retryable": True}})
    assert len(client.get(f"/api/onboarding/sessions/{v['learning_session_id']}").json()["data"]["transcript"]) == 1


def test_checks_that_fail_before_the_tutor_starts_are_plain_errors(client, graph, caps):  # noqa: F811
    caps(PUBLIC_RUN_TUTOR_TURN=1)
    v = learner_session(client)  # the opening uses the one allowed turn
    r, _ = stream_turn(client, {**v, "revision": v["revision"] + 5})
    assert r.status_code == 409 and code(r) == "REVISION_CONFLICT"
    r, _ = stream_turn(client, v)
    assert r.status_code == 429 and code(r) == "LIMIT_REACHED"


def test_a_retried_streamed_message_returns_the_saved_reply_at_once(client, graph):
    v = learner_session(client)
    cid = str(uuid.uuid4())
    _, first = stream_turn(client, v, cid=cid)
    runs = len(graph.runs)
    _, again = stream_turn(client, v, cid=cid)
    assert again == [("done", {**again[0][1]})] and again[0][1]["data"]["transcript"] == first[-1][1]["data"]["transcript"]
    assert len(graph.runs) == runs


def test_without_the_engine_the_stream_endpoint_answers_like_turns(client):
    v = learner_session(client)
    r, _ = stream_turn(client, v)
    assert r.status_code == 501 and code(r) == "CAPABILITY_UNAVAILABLE"



def test_resuming_after_a_break_past_a_completed_item_opens_the_next_one(client, graph):
    v = learner_session(client)
    graph.script = ["complete"]
    v2 = send(client, v, "I'd check the registry and escalate the v3.3 link.").json()["data"]
    assert v2["awaiting_continue"] is True
    # A reload without a break keeps the choice with the learner: Continue, no new opening.
    again = client.post("/api/onboarding/sessions").json()["data"]
    assert again["awaiting_continue"] is True and len([r for r in graph.runs if "input" in r]) == 1
    # Take a break, then resume (e.g. from the overview): the position moves to the next item...
    paused = client.post(f"/api/onboarding/sessions/{v['learning_session_id']}/pause", json={"client_turn_id": str(uuid.uuid4()), "expected_revision": v2["revision"]})
    assert paused.status_code == 200 and paused.json()["data"]["status"] == "PAUSED"
    resumed = client.post("/api/onboarding/sessions").json()["data"]
    # ...and the tutor opens it, so the learner can carry on (no missing Continue, no dead end).
    assert resumed["status"] == "ACTIVE" and resumed["awaiting_continue"] is False
    assert len([r for r in graph.runs if "input" in r]) == 2
    assert resumed["transcript"][-1]["text"].startswith("What have you done before")
    assert send(client, resumed).status_code == 200  # and messages work again
