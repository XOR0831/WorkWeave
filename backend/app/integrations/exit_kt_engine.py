"""The Exit KT graph (docs/32, ADR-044), reached over the LangGraph API on port 5681.

Read-only by design: the graph returns proposals (discovery, interview questions, artifact drafts,
successor recommendations, answers) and the backend validates and stores what it accepts. The
copilot keeps one thread per case and person; the other jobs run on their own threads so one never
blocks another (LangGraph rejects a second run on a busy thread).
"""

import logging
import uuid
from functools import lru_cache
from typing import Any, Protocol

import httpx

from app.config import get_settings

_log = logging.getLogger("workweave.engines")

THREADS = uuid.UUID("3c9b7e21-5d4a-4f6b-8e2c-1a7d9f0b6c42")


class ExitKtEngineError(Exception):
    """The graph couldn't be reached or the run failed; nothing was saved."""


class ExitKtEngine(Protocol):
    provider: str

    def run(self, request: dict[str, Any]) -> dict[str, Any]: ...


def thread_id(case_id: str, employee_id: str, operation: str = "ASK", interview_id: str | None = None) -> str:
    suffix = "" if operation == "ASK" else f":{operation}:{interview_id or ''}"
    return str(uuid.uuid5(THREADS, f"{case_id}:{employee_id}{suffix}"))


class LangGraphExitKt:
    provider = "langgraph"

    def __init__(self, url: str, assistant: str, client: httpx.Client | None = None, timeout_s: float = 180.0):
        self.url, self.assistant = url.rstrip("/"), assistant
        self._client = client or httpx.Client(timeout=httpx.Timeout(timeout_s, connect=5.0))

    def run(self, request: dict[str, Any]) -> dict[str, Any]:
        tid = thread_id(request["exit_kt_case_id"], request["employee_id"], request["operation"], request.get("interview_id"))
        try:
            self._client.post(f"{self.url}/threads", json={"thread_id": tid, "if_exists": "do_nothing"}).raise_for_status()
            r = self._client.post(f"{self.url}/threads/{tid}/runs/wait", json={"assistant_id": self.assistant, "input": {"request": request}, "multitask_strategy": "reject"})
        except httpx.HTTPError as e:
            _log.warning("the knowledge-transfer assistant: couldn't be reached.")  # the reason stays in the server log
            raise ExitKtEngineError("The knowledge-transfer assistant couldn't do that because an error was encountered.") from e
        if r.status_code == 409:
            raise ExitKtEngineError("The knowledge-transfer assistant is still working on your previous request.")
        if r.status_code >= 400:
            _log.warning("the knowledge-transfer assistant: returned an error (%s).", r.status_code)  # the reason stays in the server log
            raise ExitKtEngineError("The knowledge-transfer assistant couldn't do that because an error was encountered.")
        try:
            values = r.json()
        except ValueError as e:
            _log.warning("the knowledge-transfer assistant: returned an unreadable response.")  # the reason stays in the server log
            raise ExitKtEngineError("The knowledge-transfer assistant couldn't do that because an error was encountered.") from e
        result = values.get("result") if isinstance(values, dict) else None
        if not isinstance(result, dict):
            _log.warning("the knowledge-transfer assistant: finished without a result.")  # the reason stays in the server log
            raise ExitKtEngineError("The knowledge-transfer assistant couldn't do that because an error was encountered.")
        return result


@lru_cache
def engine() -> ExitKtEngine | None:
    s = get_settings()
    if s.exit_kt_engine != "langgraph" or not s.langgraph_exit_kt_url:
        return None
    return LangGraphExitKt(s.langgraph_exit_kt_url, s.langgraph_exit_kt_assistant)
