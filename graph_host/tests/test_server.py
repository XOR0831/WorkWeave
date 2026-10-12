"""The graph host answers the LangGraph API calls the backend adapters make (ADR-052)."""

import json
import textwrap

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from typing_extensions import TypedDict

import server


class S(TypedDict, total=False):
    opening: str
    message: str
    reply: str
    result: dict


def chat_graph():
    """Opens, waits for the person (like her wait_for_user), replies."""
    def open_(s: S) -> S:
        return {"opening": "hello"}

    def wait_for_user(s: S) -> S:
        got = interrupt({"waiting": True})
        return {"message": got["message"]}

    def reply(s: S) -> S:
        if s["message"] == "boom":
            raise RuntimeError("secret detail")
        return {"reply": f"you said {s['message']}"}

    b = StateGraph(S)
    b.add_node("open", open_)
    b.add_node("wait_for_user", wait_for_user)
    b.add_node("reply", reply)
    b.add_edge(START, "open")
    b.add_edge("open", "wait_for_user")
    b.add_edge("wait_for_user", "reply")
    b.add_edge("reply", END)
    return b.compile()


def task_graph():
    b = StateGraph(S)
    b.add_node("work", lambda s: {"result": {"ok": True, "echo": s.get("message")}})
    b.add_edge(START, "work")
    b.add_edge("work", END)
    return b.compile()


@pytest.fixture
def client():
    host = server.Host({"chat": chat_graph(), "task": task_graph()}, InMemorySaver())
    with TestClient(server.create_app(lambda: (host, None))) as c:
        c.host = host
        yield c


def sse(text: str) -> list[tuple[str, object]]:
    out, event = [], ""
    for line in text.splitlines():
        if line.startswith("event:"):
            event = line[6:].strip()
        elif line.startswith("data:"):
            out.append((event, json.loads(line[5:])))
    return out


def test_stream_pauses_at_the_interrupt_and_resumes_with_a_command(client):
    assert client.post("/threads", json={"thread_id": "t1", "if_exists": "do_nothing"}).json() == {"thread_id": "t1"}
    r = client.post("/threads/t1/runs/stream", json={"assistant_id": "chat", "input": {}, "stream_mode": ["updates"], "stream_subgraphs": True, "multitask_strategy": "reject"})
    events = sse(r.text)
    steps = [k for e, d in events if e == "updates" for k in d]
    assert steps[:2] == ["open", "__interrupt__"]
    st = client.get("/threads/t1/state").json()
    assert st["next"] == ["wait_for_user"] and st["tasks"][0]["interrupts"][0]["value"] == {"waiting": True}
    assert st["values"]["opening"] == "hello"
    r = client.post("/threads/t1/runs/stream", json={"assistant_id": "chat", "command": {"resume": {"message": "hi"}}, "config": {"configurable": {"client_turn_id": "c1"}}})
    assert any(e == "updates" and "reply" in d for e, d in sse(r.text))
    assert client.get("/threads/t1/state").json()["values"]["reply"] == "you said hi"


def test_a_failed_run_reports_an_error_without_its_details(client):
    client.post("/threads/runs-err/runs/stream", json={"assistant_id": "chat", "input": {}})
    r = client.post("/threads/runs-err/runs/stream", json={"assistant_id": "chat", "command": {"resume": {"message": "boom"}}})
    errors = [d for e, d in sse(r.text) if e == "error"]
    assert errors == [{"error": "RuntimeError"}] and "secret detail" not in r.text
    assert client.get("/threads/runs-err").json()["status"] == "idle"  # the lock is released


def test_wait_returns_the_thread_values(client):
    r = client.post("/threads/w1/runs/wait", json={"assistant_id": "task", "input": {"message": "x"}, "multitask_strategy": "reject"})
    assert r.json()["result"] == {"ok": True, "echo": "x"}


def test_a_busy_thread_rejects_a_second_run(client):
    lock = client.host.lock("b1")
    lock.acquire()
    try:
        assert client.get("/threads/b1").json()["status"] == "busy"
        assert client.post("/threads/b1/runs/wait", json={"assistant_id": "task", "input": {}}).status_code == 409
        assert client.post("/threads/b1/runs/stream", json={"assistant_id": "task", "input": {}}).status_code == 409
    finally:
        lock.release()
    assert client.get("/threads/b1").json()["status"] == "idle"


def test_state_update_as_a_node_and_unknown_threads(client):
    assert client.get("/threads/nobody/state").json() == {"values": {}, "next": [], "tasks": []}
    client.post("/threads/u1/runs/stream", json={"assistant_id": "chat", "input": {}})
    r = client.post("/threads/u1/state", json={"values": {"message": "handed back"}, "as_node": "wait_for_user"})
    assert r.status_code == 200
    assert client.get("/threads/u1/state").json()["next"] == ["reply"]
    assert client.post("/threads/nobody/state", json={"values": {}}).status_code == 404


def test_each_assistant_keeps_its_own_threads_and_unknown_assistants_are_unavailable(client):
    client.post("/threads/same/runs/wait", json={"assistant_id": "task", "input": {"message": "a"}})
    client.post("/threads/same/runs/stream", json={"assistant_id": "chat", "input": {}})
    keys = {c.config["configurable"]["thread_id"] for c in client.host.checkpointer.list(None)}
    assert {"task:same", "chat:same"} <= keys
    assert client.post("/threads/x/runs/wait", json={"assistant_id": "nope", "input": {}}).status_code == 503
    client.delete("/threads/same")
    assert not {c.config["configurable"]["thread_id"] for c in client.host.checkpointer.list(None)} & {"task:same", "chat:same"}


def test_graphs_load_from_files_with_their_database_pointed_at_the_given_url(tmp_path, monkeypatch):
    d = tmp_path / "ai_work_companion"
    d.mkdir()
    (d / "ai_work_companion.py").write_text(textwrap.dedent("""
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from langgraph.graph import StateGraph, START, END
        from typing_extensions import TypedDict
        engine = create_engine("postgresql+psycopg://u:p@localhost:5432/x")
        SessionLocal = sessionmaker(bind=engine)
        class S(TypedDict, total=False):
            a: int
        b = StateGraph(S)
        b.add_node("n", lambda s: {"a": 1})
        b.add_edge(START, "n"); b.add_edge("n", END)
        graph = b.compile()
    """))
    (tmp_path / "ai_shift_handover").mkdir()
    (tmp_path / "ai_shift_handover" / "ai_shift_handover.py").write_text("raise RuntimeError('broken graph')\n")
    monkeypatch.setattr(server, "AI_DIR", tmp_path)
    url = "postgresql+psycopg://app:pw@/workweave?host=/cloudsql/p:r:i"  # engines connect lazily
    graphs = server.load_graphs(url)
    assert set(graphs) == {"ai_work_companion"}  # the broken and missing ones are left out
    import sys
    mod = sys.modules["ai_work_companion"]
    assert mod.engine.url.query["host"] == "/cloudsql/p:r:i" and mod.engine.pool.size() == 1 and mod.SessionLocal.kw["bind"] is mod.engine
