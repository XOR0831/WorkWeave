"""The AI engineer's Work Companion graph, reached over the LangGraph API (ADR-034).

Her graph owns the conversation's intelligence: the opening brief, intent analysis, guidance from
approved knowledge (retrieval and embeddings), and interpreting work updates, which it saves itself
as reports in `work_item_reported_updates`. This adapter only drives it and reads back what ran:

- one thread per work session; the thread ID is the work session ID (LangGraph requires a UUID);
- `start` runs her graph from the beginning (the opening brief), `resume` answers `wait_for_user`;
- every run streams step updates (sub-graphs included), so the backend knows which steps ran and
  which approved chunks guidance used, without trusting any free text for that;
- calendar steps stop the run before they start: `proceed` lets it continue once the calendar is
  connected; otherwise `hand_back` puts the backend's fixed reply in place and returns the graph to
  `wait_for_user`.

It never writes business rows and never invents a reply.
"""

import logging
import json
import time
from dataclasses import dataclass, field
from functools import lru_cache
from collections.abc import Callable
from typing import Any, Protocol

import httpx

from app.config import get_settings

_log = logging.getLogger("workweave.engines")


# Called as each graph step finishes (step name, its state update): live progress for the employee.
OnStep = Callable[[str, dict[str, Any]], None] | None


class CompanionEngineError(Exception):
    """The graph couldn't be reached or the run failed; this request saved nothing."""


class CompanionBusy(CompanionEngineError):
    """Another request's run is still going on this thread (LangGraph answers 409)."""


@dataclass
class Thread:
    exists: bool
    waiting: bool  # paused at wait_for_user, ready for the employee's message
    next: list[str]
    values: dict[str, Any]


@dataclass
class Trace:
    """What one run did: the steps that finished, in order, and the state it ended in."""

    steps: list[str] = field(default_factory=list)
    retrieved: list[dict[str, Any]] = field(default_factory=list)  # guidance chunks, as the graph saw them
    thread: Thread | None = None

    @property
    def stopped_before(self) -> str | None:
        """The step the run stopped in front of (interrupt_before), unless it is waiting for the employee."""
        if not self.thread or self.thread.waiting:
            return None
        return self.thread.next[0] if self.thread.next else None


class CompanionEngine(Protocol):
    provider: str

    def thread(self, thread_id: str) -> Thread: ...

    def start(self, thread_id: str, employee: dict[str, str], work_session_id: str, stop_before: list[str]) -> Trace: ...

    def resume(self, thread_id: str, text: str, input_kind: str, client_turn_id: str, stop_before: list[str], on_step: OnStep = None) -> Trace: ...

    def hand_back(self, thread_id: str, conversation: dict[str, Any], message: str) -> Trace: ...

    def wait_idle(self, thread_id: str, timeout_s: float = 90.0) -> None: ...

    def proceed(self, thread_id: str, on_step: OnStep = None) -> Trace: ...


class LangGraphCompanion:
    provider = "langgraph"
    # A reply that only the backend wrote goes in as if her clarify step had produced it; that step's
    # outgoing edge returns the graph to wait_for_user.
    HAND_BACK_AS = "clarify_request"

    def __init__(self, url: str, assistant: str, client: httpx.Client | None = None, timeout_s: float = 120.0):
        self.url = url.rstrip("/")
        self.assistant = assistant
        self._client = client or httpx.Client(timeout=httpx.Timeout(timeout_s, connect=5.0))

    def _call(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        try:
            r = self._client.request(method, f"{self.url}{path}", json=body)
        except httpx.HTTPError as e:
            _log.warning("the work assistant: couldn't be reached.")  # the reason stays in the server log
            raise CompanionEngineError("The work assistant couldn't do that because an error was encountered.") from e
        if r.status_code == 404 and method == "GET":
            return None
        if r.status_code == 409:
            raise CompanionBusy("The work assistant is still working on the previous message.")
        if r.status_code >= 400:
            _log.warning("the work assistant: returned an error (%s).", r.status_code)  # the reason stays in the server log
            raise CompanionEngineError("The work assistant couldn't do that because an error was encountered.")
        try:
            return r.json()
        except ValueError as e:
            _log.warning("the work assistant: returned an unreadable response.")  # the reason stays in the server log
            raise CompanionEngineError("The work assistant couldn't do that because an error was encountered.") from e

    def thread(self, thread_id: str) -> Thread:
        st = self._call("GET", f"/threads/{thread_id}/state")
        if not st or not st.get("values"):
            return Thread(False, False, [], {})
        nxt = list(st.get("next") or [])
        interrupted = any(t.get("interrupts") for t in st.get("tasks") or [])
        return Thread(True, "wait_for_user" in nxt and interrupted, nxt, st.get("values") or {})

    def _stream(self, thread_id: str, payload: dict[str, Any], on_step: OnStep = None) -> Trace:
        self._call("POST", "/threads", {"thread_id": thread_id, "if_exists": "do_nothing"})
        body = {"assistant_id": self.assistant, "multitask_strategy": "reject", "stream_mode": ["updates"], "stream_subgraphs": True, **payload}
        trace = Trace()
        try:
            with self._client.stream("POST", f"{self.url}/threads/{thread_id}/runs/stream", json=body) as r:
                if r.status_code == 409:
                    raise CompanionBusy("The work assistant is still working on the previous message.")
                if r.status_code >= 400:
                    _log.warning("the work assistant: returned an error (%s).", r.status_code)  # the reason stays in the server log
                    raise CompanionEngineError("The work assistant couldn't do that because an error was encountered.")
                event = ""
                for line in r.iter_lines():
                    if line.startswith("event:"):
                        event = line[6:].strip()
                    elif line.startswith("data:") and event:
                        if event == "error":
                            _log.warning("the work assistant: stopped with an error.")  # the reason stays in the server log
                            raise CompanionEngineError("The work assistant couldn't do that because an error was encountered.")
                        if event.split("|", 1)[0] != "updates":
                            continue
                        try:
                            data = json.loads(line[5:])
                        except ValueError:
                            continue
                        for step, update in data.items() if isinstance(data, dict) else ():
                            if step.startswith("__"):
                                continue
                            trace.steps.append(step)
                            if on_step:
                                on_step(step, update if isinstance(update, dict) else {})
                            if step == "retrieve_relevant_chunks" and isinstance(update, dict):
                                trace.retrieved = [c for c in update.get("retrieved_knowledge") or [] if isinstance(c, dict)]
        except httpx.HTTPError as e:
            _log.warning("the work assistant: couldn't be reached.")  # the reason stays in the server log
            raise CompanionEngineError("The work assistant couldn't do that because an error was encountered.") from e
        trace.thread = self.thread(thread_id)
        return trace

    def start(self, thread_id: str, employee: dict[str, str], work_session_id: str, stop_before: list[str]) -> Trace:
        payload: dict[str, Any] = {"input": {"employee": employee, "session": {"work_session_id": work_session_id}}}
        if stop_before:
            payload["interrupt_before"] = stop_before
        return self._stream(thread_id, payload)

    def resume(self, thread_id: str, text: str, input_kind: str, client_turn_id: str, stop_before: list[str], on_step: OnStep = None) -> Trace:
        payload: dict[str, Any] = {
            "command": {"resume": {"message": text, "input_kind": input_kind}},
            "config": {"configurable": {"client_turn_id": client_turn_id, "input_kind": input_kind}},
        }
        if stop_before:
            payload["interrupt_before"] = stop_before
        return self._stream(thread_id, payload, on_step)

    def wait_idle(self, thread_id: str, timeout_s: float = 90.0) -> None:
        """Waits while another request's run is going on this thread (e.g. two page loads opening the
        same session); raises CompanionBusy if it is still running after timeout_s."""
        deadline = time.monotonic() + timeout_s
        while True:
            t = self._call("GET", f"/threads/{thread_id}")
            if not t or t.get("status") != "busy":
                return
            if time.monotonic() > deadline:
                raise CompanionBusy("The work assistant is still working on the previous message.")
            time.sleep(0.5)

    def proceed(self, thread_id: str, on_step: OnStep = None) -> Trace:
        """Lets a run that stopped in front of a calendar step carry on (the calendar is connected)."""
        return self._stream(thread_id, {"input": None}, on_step)

    def hand_back(self, thread_id: str, conversation: dict[str, Any], message: str) -> Trace:
        values = {"conversation": {**conversation, "assistant_message": message, "is_opening_brief": False}}
        self._call("POST", f"/threads/{thread_id}/state", {"values": values, "as_node": self.HAND_BACK_AS})
        return self._stream(thread_id, {"input": None})


_installed: CompanionEngine | None = None


def install_test_companion(engine: CompanionEngine | None) -> None:
    """Install (or, with None, remove) a deterministic engine. Test environment only."""
    global _installed
    if get_settings().workweave_env != "test":
        raise RuntimeError("A test companion engine can only be installed when WORKWEAVE_ENV=test.")
    _installed = engine


def get_companion() -> CompanionEngine | None:
    """The AI engineer's graph when COMPANION_ENGINE=langgraph and LANGGRAPH_COMPANION_URL are set
    (a test engine in the test environment); None means the assistant isn't connected."""
    s = get_settings()
    if _installed is not None and s.workweave_env == "test":
        return _installed
    if s.companion_engine == "langgraph" and s.langgraph_companion_url:
        return _langgraph(s.langgraph_companion_url, s.langgraph_companion_assistant)
    return None


@lru_cache
def _langgraph(url: str, assistant: str) -> LangGraphCompanion:
    return LangGraphCompanion(url, assistant)
