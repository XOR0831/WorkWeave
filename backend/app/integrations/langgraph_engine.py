"""The AI engineer's onboarding graph, reached over the LangGraph API (ADR-030).

Her graph is the system of record for learning data: it saves each exchange as a learning turn in the
app's format (`record_turn`, contract "engine-1"), plus events, evidence and progress. This adapter
only drives it: open a conversation, resume it with the learner's message, or start the next item.
It never writes learning rows and never invents a reply.

Locally the graph runs in `langgraph dev`; the same calls work against any LangGraph API server.
One thread per learning session: the thread ID is the learning session ID.
"""

import logging
import json
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import httpx

from app.integrations.tutor import TutorContext, TutorResult

_log = logging.getLogger("workweave.engines")


class EngineError(Exception):
    """The graph couldn't be reached or the run failed; nothing was saved by this request."""


@dataclass
class ThreadState:
    exists: bool
    waiting: bool  # paused at wait_for_user, ready for the learner's message
    values: dict[str, Any]


class LangGraphEngine:
    provider = "langgraph"

    def __init__(self, url: str, assistant: str, client: httpx.Client | None = None, timeout_s: float = 120.0):
        self.url = url.rstrip("/")
        self.assistant = assistant
        self.graph_version = f"langgraph:{assistant}"
        self._client = client or httpx.Client(timeout=httpx.Timeout(timeout_s, connect=5.0))

    # ------------------------------------------------------------ TutorEngine protocol (no-ops here)
    def open_session(self, ctx: TutorContext) -> TutorResult:
        return TutorResult("ok", provider=self.provider)

    def process_turn(self, ctx: TutorContext, text: str, input_kind: str) -> TutorResult:  # pragma: no cover - not used
        raise NotImplementedError("LangGraph turns go through app.services.engine_turns.")

    def pause(self, ctx: TutorContext) -> TutorResult:
        return TutorResult("ok", provider=self.provider)

    # ------------------------------------------------------------ LangGraph API
    def _call(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        try:
            r = self._client.request(method, f"{self.url}{path}", json=body)
        except httpx.HTTPError as e:
            _log.warning("the tutor: couldn't be reached.")  # the reason stays in the server log
            raise EngineError("The tutor couldn't do that because an error was encountered.") from e
        if r.status_code == 404 and method == "GET":
            return None
        if r.status_code == 409:
            raise EngineError("The tutor is still working on the previous message.")
        if r.status_code >= 400:
            _log.warning("the tutor: returned an error (%s).", r.status_code)  # the reason stays in the server log
            raise EngineError("The tutor couldn't do that because an error was encountered.")
        try:
            return r.json()
        except ValueError as e:
            _log.warning("the tutor: returned an unreadable response.")  # the reason stays in the server log
            raise EngineError("The tutor couldn't do that because an error was encountered.") from e

    def state(self, thread_id: str) -> ThreadState:
        st = self._call("GET", f"/threads/{thread_id}/state")
        if not st or not st.get("values"):
            return ThreadState(False, False, {})
        nxt = st.get("next") or []
        interrupted = any(t.get("interrupts") for t in st.get("tasks") or [])
        return ThreadState(True, "wait_for_user" in nxt and interrupted, st.get("values") or {})

    def _run(self, thread_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self._call("POST", "/threads", {"thread_id": thread_id, "if_exists": "do_nothing"})
        out = self._call("POST", f"/threads/{thread_id}/runs/wait", {"assistant_id": self.assistant, "multitask_strategy": "reject", **payload})
        if isinstance(out, dict) and out.get("__error__"):
            _log.warning("the tutor: stopped with an error.")  # the reason stays in the server log
            raise EngineError("The tutor couldn't do that because an error was encountered.")
        return out if isinstance(out, dict) else {}

    def start(self, thread_id: str, employee: dict[str, str]) -> dict[str, Any]:
        """Run from the start: opening message for the current (or next) item, saved by the graph."""
        return self._run(thread_id, {"input": {"employee": employee}, "config": {"configurable": {}}})

    @staticmethod
    def _resume_payload(text: str, input_kind: str, client_turn_id: str, interrupted: bool) -> dict[str, Any]:
        configurable = {"client_turn_id": client_turn_id, "input_kind": input_kind, "interrupted_previous_reply": interrupted}
        return {"command": {"resume": {"message": text, "input_kind": input_kind}}, "config": {"configurable": configurable}}

    def resume(self, thread_id: str, text: str, input_kind: str, client_turn_id: str, interrupted: bool) -> dict[str, Any]:
        """The learner's message; the graph saves the turn under client_turn_id."""
        return self._run(thread_id, self._resume_payload(text, input_kind, client_turn_id, interrupted))

    def resume_stream(self, thread_id: str, text: str, input_kind: str, client_turn_id: str, interrupted: bool) -> Iterator[tuple[str, dict[str, Any]]]:
        """Like resume(), but yields (step name, its state update) as each graph step finishes,
        including steps inside sub-graphs. Raises EngineError if the run fails."""
        self._call("POST", "/threads", {"thread_id": thread_id, "if_exists": "do_nothing"})
        body = {"assistant_id": self.assistant, "multitask_strategy": "reject", "stream_mode": ["updates"], "stream_subgraphs": True,
                **self._resume_payload(text, input_kind, client_turn_id, interrupted)}
        try:
            with self._client.stream("POST", f"{self.url}/threads/{thread_id}/runs/stream", json=body) as r:
                if r.status_code == 409:
                    raise EngineError("The tutor is still working on the previous message.")
                if r.status_code >= 400:
                    _log.warning("the tutor: returned an error (%s).", r.status_code)  # the reason stays in the server log
                    raise EngineError("The tutor couldn't do that because an error was encountered.")
                event = ""
                for line in r.iter_lines():
                    if line.startswith("event:"):
                        event = line[6:].strip()
                    elif line.startswith("data:") and event:
                        if event == "error":
                            _log.warning("the tutor: stopped with an error.")  # the reason stays in the server log
                            raise EngineError("The tutor couldn't do that because an error was encountered.")
                        if event.split("|", 1)[0] != "updates":
                            continue
                        try:
                            data = json.loads(line[5:])
                        except ValueError:
                            continue
                        for step, update in (data or {}).items() if isinstance(data, dict) else ():
                            yield step, update if isinstance(update, dict) else {}
        except httpx.HTTPError as e:
            _log.warning("the tutor: couldn't be reached.")  # the reason stays in the server log
            raise EngineError("The tutor couldn't do that because an error was encountered.") from e
