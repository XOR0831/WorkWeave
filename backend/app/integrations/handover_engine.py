"""The Shift Handover graph (docs/31, ADR-043), reached over the LangGraph API on port 5680.

Read-only by design: the graph returns proposals (gap-check suggestions and questions, section
drafts, copilot answers) and the backend validates and stores what it accepts. The copilot has one
thread per handover and lead (a UUID derived from both), so it remembers the conversation.
"""

import logging
import uuid
from functools import lru_cache
from typing import Any, Protocol

import httpx

from app.config import get_settings

_log = logging.getLogger("workweave.engines")

THREADS = uuid.UUID("6a1d3c8e-3f5b-4c1e-9d1a-0b8f2c4e7a10")  # namespace for handover thread IDs


class HandoverEngineError(Exception):
    """The graph couldn't be reached or the run failed; nothing was saved."""


class HandoverEngine(Protocol):
    provider: str

    def run(self, request: dict[str, Any]) -> dict[str, Any]: ...


def thread_id(handover_id: str, employee_id: str, operation: str = "ASK") -> str:
    """The copilot keeps one conversation thread per handover and lead. The gap check and drafts get
    their own threads (they need no memory), so they can run while the other is still working; LangGraph
    rejects a second run on a busy thread."""
    suffix = "" if operation == "ASK" else f":{operation}"
    return str(uuid.uuid5(THREADS, f"{handover_id}:{employee_id}{suffix}"))


class LangGraphHandover:
    provider = "langgraph"

    def __init__(self, url: str, assistant: str, client: httpx.Client | None = None, timeout_s: float = 120.0):
        self.url, self.assistant = url.rstrip("/"), assistant
        self._client = client or httpx.Client(timeout=httpx.Timeout(timeout_s, connect=5.0))

    def run(self, request: dict[str, Any]) -> dict[str, Any]:
        """One run with the backend-established request; returns the graph's `result`."""
        tid = thread_id(request["handover_id"], request["employee_id"], request["operation"])
        try:
            self._client.post(f"{self.url}/threads", json={"thread_id": tid, "if_exists": "do_nothing"}).raise_for_status()
            r = self._client.post(f"{self.url}/threads/{tid}/runs/wait",
                                  json={"assistant_id": self.assistant, "input": {"request": request}, "multitask_strategy": "reject"})
        except httpx.HTTPError as e:
            _log.warning("the handover assistant: couldn't be reached.")  # the reason stays in the server log
            raise HandoverEngineError("The handover assistant couldn't do that because an error was encountered.") from e
        if r.status_code == 409:
            raise HandoverEngineError("The handover assistant is still working on your previous request.")
        if r.status_code >= 400:
            _log.warning("the handover assistant: returned an error (%s).", r.status_code)  # the reason stays in the server log
            raise HandoverEngineError("The handover assistant couldn't do that because an error was encountered.")
        try:
            values = r.json()
        except ValueError as e:
            _log.warning("the handover assistant: returned an unreadable response.")  # the reason stays in the server log
            raise HandoverEngineError("The handover assistant couldn't do that because an error was encountered.") from e
        result = values.get("result") if isinstance(values, dict) else None
        if not isinstance(result, dict):
            _log.warning("the handover assistant: finished without a result.")  # the reason stays in the server log
            raise HandoverEngineError("The handover assistant couldn't do that because an error was encountered.")
        return result


@lru_cache
def engine() -> HandoverEngine | None:
    s = get_settings()
    if s.handover_engine != "langgraph" or not s.langgraph_handover_url:
        return None
    return LangGraphHandover(s.langgraph_handover_url, s.langgraph_handover_assistant)
