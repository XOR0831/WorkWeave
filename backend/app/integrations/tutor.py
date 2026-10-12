"""Tutor engine port (PROPOSED; blueprint/14-ai-engineer-integration-contract.md).

The AI engineer owns the onboarding LangGraph (Teaching, Assessment, Progression subgraphs),
prompts, model calls and checkpoints. The backend owns identity, assignment, durable writes,
revisions and idempotency, and calls the engine through this port.

CONTRACT STATUS: `proposed-1` is the application side's proposal. It has NOT been signed off by
the AI engineer (blueprint/14 requires both to pin a version before swapping implementations).
Until it is, only NotConnectedTutor is ever configured; a deterministic engine can be installed
in the test environment only (`install_test_tutor`), never in development or release.

Everything the engine returns is untrusted input: the backend validates the schema here and every
ID, citation, question and assessment against server-side state before anything is stored. The
engine has no authority to complete subtopics; a proposed outcome is evidence only after the
backend's deterministic policy accepts it.
"""

import uuid
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.config import get_settings

# Typed statuses from the integration contract.
Status = Literal["ok", "insufficient_evidence", "unsupported_capability", "invalid_output", "unavailable", "timeout"]

CONTRACT_VERSION = "proposed-1"


# ---------------------------------------------------------------- engine input (server-established)
@dataclass(frozen=True)
class ObjectiveContext:
    objective_id: str
    description: str
    criteria_version: str
    required: bool
    required_checks: list[str]


@dataclass(frozen=True)
class PendingQuestion:
    question_id: str
    question_version: str
    objective_id: str
    criteria_version: str
    text: str
    issued_turn_id: str


@dataclass(frozen=True)
class TutorContext:
    """Server-established context. Identifiers are scope, never model-granted authority."""

    organization_id: str
    workspace_id: str
    learning_session_id: str
    thread_id: str
    employee_id: str
    curriculum_id: str
    current_subtopic_id: str | None
    permitted_document_version_ids: list[str] = field(default_factory=list)
    objectives: list[ObjectiveContext] = field(default_factory=list)
    pending_question: PendingQuestion | None = None
    # Bounded committed conversation (blueprint/17 starting budget: last 12 messages).
    recent_messages: list[dict[str, str]] = field(default_factory=list)
    # The learner cut off the previous spoken reply (tap, Space or voice); they may not have heard all of it.
    previous_reply_interrupted: bool = False
    contract_version: str = CONTRACT_VERSION


# ---------------------------------------------------------------- engine output (untrusted; validated)
class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CitationRef(_Strict):
    """A permitted source: exact document version plus a section and/or chunk of that version."""

    document_version_id: uuid.UUID
    section_id: uuid.UUID | None = None
    chunk_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _needs_a_location(self) -> "CitationRef":
        if self.section_id is None and self.chunk_id is None:
            raise ValueError("a citation needs a section_id or chunk_id")
        return self


class Reply(_Strict):
    kind: Literal["TEACHING", "EXAMPLE", "HINT", "CHECK", "FEEDBACK"]
    text: str = Field(min_length=1, max_length=4000)
    strategy: Literal["CONCISE", "DETAILED", "EXAMPLE", "ANALOGY", "STEP_BY_STEP", "GUIDED_PRACTICE", "REPHRASE", "REINFORCEMENT"] | None = None
    citations: list[CitationRef] = Field(default_factory=list, max_length=8)


class NewCheck(_Strict):
    """A comprehension question issued in this reply; it becomes the pending question once committed."""

    question_id: uuid.UUID
    question_version: str = Field(min_length=1, max_length=40)
    objective_id: uuid.UUID
    criteria_version: str = Field(min_length=1, max_length=80)
    text: str = Field(min_length=1, max_length=1000)


class CriterionResult(_Strict):
    check: str = Field(min_length=1, max_length=120)
    met: bool
    answer_span: tuple[int, int] | None = None


class Assessment(_Strict):
    """A proposed, criterion-level evaluation of the learner's answer to the pending question."""

    question_id: uuid.UUID
    objective_id: uuid.UUID
    criteria_version: str = Field(min_length=1, max_length=80)
    outcome: Literal["CORRECT", "PARTIAL", "INCORRECT", "UNASSESSABLE"]
    criterion_results: list[CriterionResult] = Field(default_factory=list, max_length=20)
    hints_used: int = Field(default=0, ge=0, le=50)


class TurnOutput(_Strict):
    contract_version: Literal["proposed-1"]
    reply: Reply
    event: Literal["EXPLANATION_PROVIDED", "CLARIFICATION_REQUESTED", "QUESTION_ASKED", "EXAMPLE_REQUESTED", "HINT_PROVIDED", "REINFORCEMENT"] | None = None
    new_check: NewCheck | None = None
    assessment: Assessment | None = None
    # Provider/model/prompt metadata, stored with the reply. Never consulted for progress.
    metadata: dict[str, str] = Field(default_factory=dict, max_length=12)


@dataclass(frozen=True)
class TutorResult:
    status: Status
    message: str = ""
    provider: str = ""
    # Present only with status "ok": the raw engine output, validated by the backend before use.
    output: dict[str, Any] | None = None
    messages: list[dict[str, Any]] = field(default_factory=list)


class TutorEngine(Protocol):
    provider: str
    graph_version: str

    def open_session(self, ctx: TutorContext) -> TutorResult: ...

    def process_turn(self, ctx: TutorContext, text: str, input_kind: str) -> TutorResult: ...

    def pause(self, ctx: TutorContext) -> TutorResult: ...


NOT_CONNECTED = "The tutor isn't connected yet. Sessions, position and breaks are saved; messages can't be answered until the tutor integration is installed."


class NotConnectedTutor:
    provider = "none"
    graph_version = "not-connected"

    def open_session(self, ctx: TutorContext) -> TutorResult:
        return TutorResult("unavailable", message=NOT_CONNECTED, provider=self.provider)

    def process_turn(self, ctx: TutorContext, text: str, input_kind: str) -> TutorResult:
        return TutorResult("unavailable", message=NOT_CONNECTED, provider=self.provider)

    def pause(self, ctx: TutorContext) -> TutorResult:
        # A break is still recorded deterministically by the backend.
        return TutorResult("unavailable", message=NOT_CONNECTED, provider=self.provider)


_installed: TutorEngine | None = None


def install_test_tutor(engine: TutorEngine | None) -> None:
    """Install (or, with None, remove) a deterministic engine. Test environment only.

    Raises outside WORKWEAVE_ENV=test, so development and release builds can only ever run
    NotConnectedTutor until a reviewed provider is integrated.
    """
    global _installed
    if get_settings().workweave_env != "test":
        raise RuntimeError("A test tutor engine can only be installed when WORKWEAVE_ENV=test.")
    _installed = engine


def get_tutor() -> TutorEngine:
    """The configured engine: a test engine (test env only), the AI engineer's LangGraph graph when
    TUTOR_ENGINE=langgraph and LANGGRAPH_URL are set (ADR-030), otherwise NotConnectedTutor."""
    s = get_settings()
    if _installed is not None and s.workweave_env == "test":
        return _installed
    if s.tutor_engine == "langgraph" and s.langgraph_url:
        return _langgraph(s.langgraph_url, s.langgraph_assistant)
    return _not_connected()


@lru_cache
def _langgraph(url: str, assistant: str) -> TutorEngine:
    from app.integrations.langgraph_engine import LangGraphEngine

    return LangGraphEngine(url, assistant)


@lru_cache
def _not_connected() -> TutorEngine:
    return NotConnectedTutor()
