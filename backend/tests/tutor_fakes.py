"""Deterministic tutor engine for tests only (never importable from the app package).

It returns queued results in order and records every context it receives. During each call it
asserts that no database connection of this test database is idle inside a transaction, which
proves the backend doesn't hold a transaction open across the engine call.
"""

import uuid
from collections.abc import Callable
from typing import Any

from sqlalchemy import Engine, text

from app.integrations.tutor import TutorContext, TutorResult

Step = TutorResult | Exception | Callable[[TutorContext], TutorResult]


class ScriptedTutor:
    provider = "test-scripted"
    graph_version = "test-scripted-1"

    def __init__(self, engine: Engine):
        self.engine = engine
        self.queue: list[Step] = []
        self.contexts: list[TutorContext] = []
        self.texts: list[str] = []

    def then(self, *steps: Step) -> "ScriptedTutor":
        self.queue.extend(steps)
        return self

    def open_session(self, ctx: TutorContext) -> TutorResult:
        return TutorResult("ok", provider=self.provider)

    def pause(self, ctx: TutorContext) -> TutorResult:
        return TutorResult("ok", provider=self.provider)

    def process_turn(self, ctx: TutorContext, text_: str, input_kind: str) -> TutorResult:
        with self.engine.connect() as c:
            open_txns = c.execute(
                text("SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() AND state = 'idle in transaction' AND pid <> pg_backend_pid()")
            ).scalar_one()
        assert open_txns == 0, "a database transaction was held open during the engine call"
        self.contexts.append(ctx)
        self.texts.append(text_)
        step = self.queue.pop(0)
        if isinstance(step, Exception):
            raise step
        return step(ctx) if callable(step) else step


def ok(output: dict[str, Any]) -> TutorResult:
    return TutorResult("ok", provider=ScriptedTutor.provider, output=output)


def cite(version_id, section_id=None, chunk_id=None) -> dict[str, Any]:
    return {"document_version_id": str(version_id), "section_id": str(section_id) if section_id else None, "chunk_id": str(chunk_id) if chunk_id else None}


def teaching(citations: list[dict[str, Any]], check: dict[str, Any] | None = None, **extra: Any) -> dict[str, Any]:
    out: dict[str, Any] = {
        "contract_version": "proposed-1",
        "reply": {"kind": "TEACHING", "text": "Use the current approved procedure version, and say what you don't know.", "strategy": "CONCISE", "citations": citations},
        "event": "EXPLANATION_PROVIDED",
        "metadata": {"model_id": "scripted", "prompt_version": "test-1"},
    }
    if check:
        out["new_check"] = check
    out.update(extra)
    return out


def check_for(objective_id, criteria_version: str, question_id: uuid.UUID | None = None) -> dict[str, Any]:
    return {"question_id": str(question_id or uuid.uuid4()), "question_version": "1", "objective_id": str(objective_id), "criteria_version": criteria_version,
            "text": "Two procedure versions disagree. Which one do you follow, and what do you do about the gap?"}


def answer(question_id, objective_id, criteria_version: str, outcome: str, met: dict[str, bool], hints_used: int = 0, kind: str = "FEEDBACK") -> dict[str, Any]:
    return {
        "contract_version": "proposed-1",
        "reply": {"kind": kind, "text": "Here's how your answer compares with the procedure.", "citations": []},
        "assessment": {"question_id": str(question_id), "objective_id": str(objective_id), "criteria_version": criteria_version, "outcome": outcome,
                       "criterion_results": [{"check": k, "met": v} for k, v in met.items()], "hints_used": hints_used},
        "metadata": {"model_id": "scripted"},
    }
