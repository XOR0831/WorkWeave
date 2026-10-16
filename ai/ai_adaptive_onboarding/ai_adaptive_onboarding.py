from dotenv import load_dotenv
from google import genai
from typing_extensions import TypedDict
from typing import  Dict, Annotated, List, Optional, Literal
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from uuid import uuid4

# from langchain.schema import Document  
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig


from langgraph.graph import START, END, StateGraph
from langgraph.graph.state import LastValue
from langgraph.types import Command, Send, interrupt
# from langgraph.checkpoint.memory import InMemorySaver

import asyncio
import hashlib
import json
# import configuration
import operator
import os

load_dotenv()

# Database
db_port = os.getenv("PORT")
db_name = os.getenv("DB_NAME")
db_pass = os.getenv("PASS")
DATABASE_URL = f"postgresql+psycopg://{db_name}:{db_pass}@localhost:{db_port}/{db_name}"

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

# LLM
gemini_api_key = os.getenv("GEMINI_API_KEY")

# Gemini
client = genai.Client(api_key=gemini_api_key)
GEMINI_MODEL = os.getenv("GEMINI_MODEL")
# Grading and feedback on answers decide progress, so they can use a stronger model (owner decision 2026-10-04).
GEMINI_REASONING_MODEL = os.getenv("GEMINI_REASONING_MODEL") or GEMINI_MODEL
GEMINI_REASONING_THINKING = os.getenv("GEMINI_REASONING_THINKING", "low")
EMBEDDING_MODEL = os.getenv("GEMINI_EMBED_MODEL")
EMBEDDING_DIMENSION = int(os.getenv("GEMINI_EMBED_DIM"))

# Schema
class Employee(BaseModel):
    session_id: Optional[str] = Field(
        default=None,
        description="Current onboarding learning session ID"
    )
    employee_id: str = Field(
        description="Employee participating in the onboarding session"
    )
    organization_id: str = Field(
        description="Organization the employee belongs to"
    )
    workspace_id: str = Field(
        description="Workspace where the onboarding session is running"
    )
    learning_assignment_id: Optional[str] = None
    session_status: Optional[Literal["ACTIVE", "PAUSED", "COMPLETED"]] = Field(
        default=None,
        description="Current status of the onboarding session"
    )

class LearningObjective(BaseModel):
    objective_id: str = Field(
        description="Unique learning objective ID"
    )
    description: str = Field(
        description="What the employee is expected to learn"
    )
    assessment_criteria: dict = Field(
        default_factory=dict,
        description="Criteria used to assess the learning objective"
    )
    criteria_version: str = Field(
        description="Version of the assessment criteria"
    )
    required: bool = Field(
        description="Whether this objective is required for progression"
    )
    hint_policy: dict = Field(
        default_factory=dict,
        description="Rules for providing hints during learning or assessment"
    )
    competency_id: Optional[str] = None


class Subtopic(BaseModel):
    subtopic_id: str = Field(
        description="Current curriculum subtopic ID"
    )
    title: str = Field(
        description="Current curriculum subtopic title"
    )
    objectives: list[LearningObjective] = Field(
        default_factory=list,
        description="Learning objectives associated with the subtopic"
    )


class Topic(BaseModel):
    topic_id: str = Field(
        description="Current curriculum topic ID"
    )
    title: str = Field(
        description="Current curriculum topic title"
    )
    subtopics: list[Subtopic] = Field(
        default_factory=list,
        description="Subtopics belonging to the curriculum topic"
    )


class Onboarding(BaseModel):
    curriculum_id: str = Field(
        description="Curriculum assigned to the employee"
    )
    curriculum_title: str = Field(
        description="Name of the assigned curriculum"
    )
    topics: list[Topic] = Field(
        default_factory=list,
        description="Topics included in the onboarding curriculum"
    )
    current_topic_id: Optional[str] = Field(
        default=None,
        description="Topic currently being learned"
    )
    current_subtopic_id: Optional[str] = Field(
        default=None,
        description="Subtopic currently being learned"
    )

class KnowledgeChunk(BaseModel):
    chunk_id: str = Field(
        description="Retrieved knowledge chunk ID"
    )
    content: str = Field(
        description="Approved knowledge content available to the onboarding AI"
    )
    document_code: str = Field(
        description="Source document code"
    )
    document_version_id: str = Field(
        description="Version of the source document"
    )
    section_id: str = Field(
        description="Knowledge section containing the chunk"
    )
    section_key: Optional[str] = Field(
        default=None,
        description="Human-readable source section identifier"
    )
    distance: Optional[float] = Field(
        default=None,
        description="Vector retrieval distance for the chunk"
    )

class LearningState(BaseModel):
    current_topic_id: Optional[str] = None
    current_subtopic_id: Optional[str] = None
    current_status: Optional[Literal["NOT_STARTED", "IN_PROGRESS", "COMPLETED"]] = None
    current_objectives: list[LearningObjective] = Field(
        default_factory=list
    )
    retrieved_knowledge: list[KnowledgeChunk] = Field(
        default_factory=list,
        description="Knowledge retrieved for the current learning interaction"
    )
    pending_question: Optional[str] = Field(
        default=None,
        description="Question currently awaiting an employee response"
    )
    current_strategy: Optional[Literal["CONCISE", "DETAILED", "STEP_BY_STEP", "EXAMPLE", "GUIDED_PRACTICE"]] = Field(
        default=None,
        description="Current teaching strategy"
    )
    
class LearningSignal(BaseModel):
    signal: Literal["CONFUSION", "UNCERTAINTY", "EXAMPLE_REQUEST", "REPEATED_QUESTION", "SELF_REPORTED_FAMILIARITY"]
    evidence: str = Field(
        description="Evidence from the employee response supporting the signal"
    )

class ResponseAnalysis(BaseModel):
    intent: Literal["ANSWER", "QUESTION", "HELP_REQUEST", "PAUSE_REQUEST", "CONTINUE", "OTHER",]
    signals: list[LearningSignal] = Field(
        default_factory=list,
        description="Evidence-based signals detected in the current interaction"
    )
    recommended_action: Literal["TEACH", "ASSESS", "PROGRESS", "CLARIFY", "PAUSE"]
    recommended_strategy: Optional[Literal["CONCISE", "DETAILED", "STEP_BY_STEP", "EXAMPLE", "GUIDED_PRACTICE"]] = None

class AssessmentCriterionResult(BaseModel):
    criterion: str
    met: bool
    evidence: Optional[str] = None

class AssessmentState(BaseModel):
    objective_id: str
    pending_question_id: str
    question: str
    attempt_id: Optional[str] = None
    criteria: dict
    employee_answer: Optional[str] = None
    criterion_results: list[AssessmentCriterionResult] = Field(
        default_factory=list
    )
    outcome: Optional[Literal["CORRECT", "PARTIAL", "INCORRECT", "UNASSESSABLE"]] = None
    evidence: Optional[str] = None
    turn_id: Optional[str] = None
    client_turn_id: Optional[str] = None

class AssessmentEvaluation(BaseModel):
    criterion_results: list[AssessmentCriterionResult]
    outcome: Literal["CORRECT", "PARTIAL", "INCORRECT", "UNASSESSABLE"]
    evidence: str

class UserInputState(BaseModel):
    message: Optional[str] = Field(
        default=None,
        description="Current user utterance or query"
    )
    input_kind: Optional[Literal["TEXT", "VOICE_TRANSCRIPT"]] = Field(
        default=None,
        description="How the current user input was received"
    )

class ConversationState(BaseModel):
    user_message: Optional[str] = Field(
        default=None,
        description="Current user utterance or response"
    )
    assistant_message: Optional[str] = Field(
        default=None,
        description="Current response generated by the onboarding AI"
    )
    input_kind: Optional[Literal["TEXT", "VOICE_TRANSCRIPT"]] = Field(
        default=None,
        description="How the current user input was received"
    )
    is_initial_message: bool = Field(
        default=False,
        description="Whether this is the AI's opening message for the session"
    )

class OnboardingState(BaseModel):
    employee: Employee
    onboarding: Optional[Onboarding] = None
    learning: LearningState = Field(
        default_factory=LearningState
    )
    response_analysis: Optional[ResponseAnalysis] = None
    assessment: Optional[AssessmentState] = None
    conversation: ConversationState = Field(
        default_factory=ConversationState
    )

# Tools
def embed_query(query: str) -> list[float]:
    response = client.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=query,
        config={
            "output_dimensionality": EMBEDDING_DIMENSION
        },
    )

    if not response.embeddings:
        raise ValueError(
            "Gemini did not return an embedding."
        )

    return response.embeddings[0].values

def build_initial_retrieval_query(state: OnboardingState) -> str:
    if state.onboarding is None:
        raise ValueError(
            "Onboarding session has not been initialized."
        )

    if state.learning.current_subtopic_id is None:
        raise ValueError(
            "Current learning context has not been resolved."
        )

    current_topic = None
    current_subtopic = None

    for topic in state.onboarding.topics:
        if topic.topic_id == state.learning.current_topic_id:
            current_topic = topic

            for subtopic in topic.subtopics:
                if (subtopic.subtopic_id == state.learning.current_subtopic_id):
                    current_subtopic = subtopic
                    break
            break

    if current_topic is None or current_subtopic is None:
        raise ValueError(
            "Current topic/subtopic could not be resolved."
        )

    objective_text = "\n".join(objective.description for objective in state.learning.current_objectives)

    return f"""
        Topic: {current_topic.title}
        Subtopic: {current_subtopic.title}

        Learning objectives:
        {objective_text}
    """.strip()

def retrieve_learning_knowledge(state: OnboardingState, query_embedding: list[float]) -> list[KnowledgeChunk]:
    query = text("""
        WITH query_vector AS (
            SELECT CAST(:query_embedding AS public.vector) AS embedding
        )
        SELECT
            c.chunk_id,
            c.content,
            c.chunk_index,
            ks.section_id,
            ks.section_key,
            ks.topic_heading,
            ks.subtopic_heading,
            v.document_version_id,
            v.version,
            d.document_code,
            r.source_id,
            c.embedding <=> q.embedding AS cosine_distance
        FROM workweave.curriculum_source_sections AS css
        JOIN workweave.curriculum_sources AS cs
            ON cs.organization_id = css.organization_id
            AND cs.workspace_id = css.workspace_id
            AND cs.curriculum_source_id = css.curriculum_source_id
            AND cs.curriculum_id = css.curriculum_id
            AND cs.document_version_id = css.document_version_id
        JOIN workweave.knowledge_sections AS ks
            ON ks.organization_id = css.organization_id
            AND ks.workspace_id = css.workspace_id
            AND ks.document_version_id = css.document_version_id
            AND ks.section_id = css.section_id
        JOIN workweave.knowledge_chunks AS c
            ON c.organization_id = ks.organization_id
            AND c.workspace_id = ks.workspace_id
            AND c.document_version_id = ks.document_version_id
            AND c.source_section_id = ks.section_id
        JOIN workweave.knowledge_document_versions AS v
            ON v.organization_id = c.organization_id
            AND v.workspace_id = c.workspace_id
            AND v.document_version_id = c.document_version_id
        JOIN workweave.knowledge_documents AS d
            ON d.organization_id = v.organization_id
            AND d.workspace_id = v.workspace_id
            AND d.document_id = v.document_id
        JOIN workweave.source_records AS r
            ON r.organization_id = c.organization_id
            AND r.workspace_id = c.workspace_id
            AND r.source_id = c.source_id
            AND r.source_id = v.source_id
        CROSS JOIN query_vector AS q
        WHERE css.organization_id = :organization_id
            AND css.workspace_id = :workspace_id
            AND css.subtopic_id = :current_subtopic_id
            AND css.relationship_type = 'TEACHES'
            AND cs.relationship_type = 'TEACHES'
            AND v.approval_status = 'APPROVED'
            AND v.temporal_status = 'CURRENT'
            AND d.current_version_id = v.document_version_id
            AND (v.effective_at IS NULL OR v.effective_at <= NOW())
            AND r.revoked_at IS NULL
            AND (r.retention_until IS NULL OR r.retention_until > NOW())
            AND r.access_partition = 'ORGANIZATION'
            AND c.embedding IS NOT NULL
            AND c.embedding_model = :embedding_model
            AND c.embedding_dimension = :embedding_dimension
            AND public.vector_dims(q.embedding) = :embedding_dimension
        ORDER BY cosine_distance
        LIMIT 6
    """)

    params = {
        "organization_id": state.employee.organization_id,
        "workspace_id": state.employee.workspace_id,
        "current_subtopic_id": state.learning.current_subtopic_id,
        "query_embedding": query_embedding,
        "embedding_model": EMBEDDING_MODEL,
        "embedding_dimension": EMBEDDING_DIMENSION,
    }

    with SessionLocal() as session:
        result = session.execute(query, params)
        rows = result.mappings().all()

    return [
        KnowledgeChunk(
            chunk_id=str(row["chunk_id"]),
            content=row["content"],
            document_code=row["document_code"],
            document_version_id=str(row["document_version_id"]),
            section_id=str(row["section_id"]),
            section_key=row["section_key"],
            distance=float(row["cosine_distance"]),
        )
        for row in rows
    ]

def generate_initial_message(state: OnboardingState) -> str:
    if state.onboarding is None:
        raise ValueError(
            "Onboarding session has not been initialized."
        )

    if state.learning.current_topic_id is None:
        raise ValueError(
            "Current topic has not been resolved."
        )

    if state.learning.current_subtopic_id is None:
        raise ValueError(
            "Current subtopic has not been resolved."
        )

    current_topic = None
    current_subtopic = None

    for topic in state.onboarding.topics:
        if topic.topic_id == state.learning.current_topic_id:
            current_topic = topic

            for subtopic in topic.subtopics:
                if subtopic.subtopic_id == state.learning.current_subtopic_id:
                    current_subtopic = subtopic
                    break

            break

    if current_topic is None or current_subtopic is None:
        raise ValueError(
            "Current topic/subtopic could not be resolved."
        )

    objectives = "\n".join(
        f"- {objective.description}"
        for objective in state.learning.current_objectives
    )

    prompt = f"""
    You are the WorkWeave Adaptive Onboarding AI.

    You are starting a natural onboarding conversation with an employee.

    Current topic:
    {current_topic.title}

    Current subtopic:
    {current_subtopic.title}

    Learning objectives:
    {objectives}

    The employee has not started this learning area yet.

    Your goal for this first message is only to understand the employee's
    existing familiarity or experience before deciding whether to teach,
    assess, clarify, or progress.

    Conversation style:
    - Speak naturally, like a helpful coworker or mentor.
    - Be warm but not overly enthusiastic or formal.
    - Keep the message short.
    - Do not sound like a course instructor, training module, or scripted chatbot.
    - Do not say phrases such as "Today we're focusing on",
    "In this session", "Our learning objective", or "tailor our session".
    - Do not announce the topic or learning objective formally.
    - Do not repeat the learning objective verbatim.
    - Do not mention WorkWeave unless it is naturally necessary.

    Behavior:
    - Give only enough context for the employee to understand what you are asking about.
    - Do not teach or explain the procedure yet.
    - Do not reveal the correct process or answer.
    - Do not provide hints that could influence a later assessment.
    - Do not assess mastery in this message.
    - Do not assume the employee is experienced or inexperienced.
    - Ask exactly one open-ended question about the employee's existing
    experience or familiarity with the current area.
    - Prefer asking about what they have actually done before rather than
    asking them to rate their own skill level.
    - End after that one question.

    Return only the message that should be shown to the employee.
    """

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
    )

    if not response.text:
        raise ValueError(
            "Gemini did not generate an opening message."
        )

    return response.text.strip()

def save_learning_event(state: OnboardingState, *, event_type: str,operation_key: str, event_data: dict, strategy: Optional[str] = None, source_refs: Optional[list] = None, objective_id: Optional[str] = None, session=None) -> OnboardingState:
    if state.employee.session_id is None:
        raise ValueError(
            "Learning session ID is required."
        )

    if state.learning.current_subtopic_id is None:
        raise ValueError(
            "Current subtopic is required."
        )

    if objective_id is None:
        objective_id = (
            state.learning.current_objectives[0].objective_id
            if state.learning.current_objectives
            else None
        )

    event_id = str(uuid4())

    query = text("""
        INSERT INTO workweave.employee_learning_events (
            learning_event_id,
            organization_id,
            workspace_id,
            learning_session_id,
            employee_id,
            topic_id,
            subtopic_id,
            objective_id,
            event_type,
            strategy,
            event_data,
            source_refs,
            operation_key
        )
        VALUES (
            :learning_event_id,
            :organization_id,
            :workspace_id,
            :learning_session_id,
            :employee_id,
            :topic_id,
            :subtopic_id,
            :objective_id,
            :event_type,
            :strategy,
            CAST(:event_data AS jsonb),
            CAST(:source_refs AS jsonb),
            :operation_key
        )
        ON CONFLICT (
            organization_id,
            workspace_id,
            operation_key
        ) DO NOTHING
    """)

    params = {
        "learning_event_id": event_id,
        "organization_id": state.employee.organization_id,
        "workspace_id": state.employee.workspace_id,
        "learning_session_id": state.employee.session_id,
        "employee_id": state.employee.employee_id,
        "topic_id": state.learning.current_topic_id,
        "subtopic_id": state.learning.current_subtopic_id,
        "objective_id": objective_id,"event_type": event_type,
        "strategy": strategy,
        "event_data": json.dumps(event_data),
        "source_refs": json.dumps(source_refs or []),
        "operation_key": operation_key,
    }

    def execute_event(db_session):
        db_session.execute(
            query,
            params,
        )

    if session is not None:
        execute_event(session)
    else:
        with SessionLocal.begin() as db_session:
            execute_event(db_session)

    return state

def persist_learning_turn(state: OnboardingState, session) -> OnboardingState:
    if state.assessment is None:
        raise ValueError(
            "Assessment state is required."
        )

    if not state.assessment.employee_answer:
        raise ValueError(
            "Assessment answer is required."
        )

    if not state.assessment.outcome:
        raise ValueError(
            "Assessment must be evaluated first."
        )

    if state.assessment.turn_id:
        return state

    turn_id = str(uuid4())

    if not state.assessment.client_turn_id:
        state.assessment.client_turn_id = str(uuid4())

    answer = state.assessment.employee_answer

    input_hash = hashlib.sha256(
        answer.encode("utf-8")
    ).hexdigest()

    sequence_query = text("""
        SELECT COALESCE(MAX(sequence), -1) + 1
        FROM workweave.learning_turns
        WHERE organization_id = :organization_id
            AND workspace_id = :workspace_id
            AND learning_session_id = :learning_session_id
    """)

    sequence = session.execute(
        sequence_query,
        {
            "organization_id": (
                state.employee.organization_id
            ),
            "workspace_id": (
                state.employee.workspace_id
            ),
            "learning_session_id": (
                state.employee.session_id
            ),
        },
    ).scalar_one()

    insert_query = text("""
        INSERT INTO workweave.learning_turns (
            turn_id,
            organization_id,
            workspace_id,
            learning_session_id,
            client_turn_id,
            input_hash,
            sequence,
            input_reference,
            response_envelope,
            committed_revision,
            stage
        )
        VALUES (
            :turn_id,
            :organization_id,
            :workspace_id,
            :learning_session_id,
            :client_turn_id,
            :input_hash,
            :sequence,
            CAST(:input_reference AS jsonb),
            CAST(:response_envelope AS jsonb),
            :committed_revision,
            :stage
        )
    """)

    session.execute(
        insert_query,
        {
            "turn_id": turn_id,
            "organization_id": (
                state.employee.organization_id
            ),
            "workspace_id": (
                state.employee.workspace_id
            ),
            "learning_session_id": (
                state.employee.session_id
            ),
            "client_turn_id": (
                state.assessment.client_turn_id
            ),
            "input_hash": input_hash,
            "sequence": sequence,
            "input_reference": json.dumps({
                "input_kind": (
                    state.conversation.input_kind
                    or "TEXT"
                ),
                "text": answer,
            }),
            "response_envelope": json.dumps({
                "objective_id": (
                    state.assessment.objective_id
                ),
                "outcome": (
                    state.assessment.outcome
                ),
                "criterion_results": [
                    result.model_dump()
                    for result
                    in state.assessment.criterion_results
                ],
                "evidence": (
                    state.assessment.evidence
                ),
            }),
            "committed_revision": 1,
            "stage": "COMMITTED",
        },
    )

    state.assessment.turn_id = turn_id

    return state

def persist_assessment_attempt(state: OnboardingState, session) -> OnboardingState:
    if state.assessment is None:
        raise ValueError(
            "Assessment state is required."
        )

    if not state.assessment.outcome:
        raise ValueError(
            "Assessment must be evaluated before persistence."
        )

    if not state.assessment.employee_answer:
        raise ValueError(
            "Assessment answer is required."
        )

    if not state.assessment.turn_id:
        raise ValueError(
            "Learning turn must be persisted first."
        )

    objective = next(
        (
            objective
            for objective in state.learning.current_objectives
            if objective.objective_id
            == state.assessment.objective_id
        ),
        None,
    )

    if objective is None:
        raise ValueError(
            "Assessment objective was not found in the "
            "current learning context."
        )

    attempt_id = str(uuid4())

    query = text("""
        INSERT INTO workweave.learning_assessment_attempts (
            attempt_id,
            organization_id,
            workspace_id,
            turn_id,
            pending_question_id,
            objective_id,
            criteria_version,
            answer_reference,
            criterion_results,
            outcome,
            support_metadata
        )
        VALUES (
            :attempt_id,
            :organization_id,
            :workspace_id,
            :turn_id,
            :pending_question_id,
            :objective_id,
            :criteria_version,
            CAST(:answer_reference AS jsonb),
            CAST(:criterion_results AS jsonb),
            :outcome,
            CAST(:support_metadata AS jsonb)
        )
    """)

    params = {
        "attempt_id": attempt_id,
        "turn_id": state.assessment.turn_id,
        "organization_id": (
            state.employee.organization_id
        ),
        "workspace_id": (
            state.employee.workspace_id
        ),
        "pending_question_id": (
            state.assessment.pending_question_id
        ),
        "objective_id": (
            state.assessment.objective_id
        ),
        "criteria_version": (
            objective.criteria_version
        ),
        "answer_reference": json.dumps({
            "answer": state.assessment.employee_answer,
        }),
        "criterion_results": json.dumps([
            result.model_dump()
            for result
            in state.assessment.criterion_results
        ]),
        "outcome": state.assessment.outcome,
        "support_metadata": json.dumps({
            "question": state.assessment.question,
            "evidence": state.assessment.evidence,
        }),
    }

    session.execute(query, params)

    state.assessment.attempt_id = attempt_id

    return state

def persist_objective_evidence(state: OnboardingState, session) -> OnboardingState:
    if state.assessment is None:
        raise ValueError(
            "Assessment state is required."
        )

    if state.assessment.outcome != "CORRECT":
        raise ValueError(
            "Only a CORRECT assessment can be accepted "
            "as objective evidence."
        )

    if not state.assessment.attempt_id:
        raise ValueError(
            "Assessment attempt must be persisted first."
        )

    objective = next(
        (
            objective
            for objective in state.learning.current_objectives
            if objective.objective_id
            == state.assessment.objective_id
        ),
        None,
    )

    if objective is None:
        raise ValueError(
            "Assessment objective was not found in the "
            "current learning context."
        )

    evidence_id = str(uuid4())

    query = text("""
        INSERT INTO workweave.objective_evidence (
            objective_evidence_id,
            organization_id,
            workspace_id,
            learning_assignment_id,
            objective_id,
            criteria_version,
            attempt_id,
            outcome,
            accepted_at,
            policy_version
        )
        VALUES (
            :objective_evidence_id,
            :organization_id,
            :workspace_id,
            :learning_assignment_id,
            :objective_id,
            :criteria_version,
            :attempt_id,
            :outcome,
            CURRENT_TIMESTAMP,
            :policy_version
        )
    """)

    params = {
        "objective_evidence_id": evidence_id,
        "organization_id": (
            state.employee.organization_id
        ),
        "workspace_id": (
            state.employee.workspace_id
        ),
        "learning_assignment_id": (
            state.employee.learning_assignment_id
        ),
        "objective_id": (
            state.assessment.objective_id
        ),
        "criteria_version": (
            objective.criteria_version
        ),
        "attempt_id": (
            state.assessment.attempt_id
        ),
        # objective_evidence accepts PASSED / NOT_PASSED / UNASSESSABLE; only a CORRECT answer reaches here.
        "outcome": "PASSED",
        "policy_version": "onboarding-v1",
    }

    session.execute(query, params)

    return state

def update_progress_completed(state: OnboardingState, session) -> None:
    if state.assessment is None:
        raise ValueError(
            "Assessment state is required."
        )

    if state.assessment.outcome != "CORRECT":
        raise ValueError(
            "Only a CORRECT assessment can complete "
            "the current subtopic."
        )

    query = text("""
        UPDATE workweave.employee_learning_progress
        SET
            status = 'COMPLETED',
            started_at = COALESCE(started_at, CURRENT_TIMESTAMP),
            completed_at = COALESCE(
                completed_at,
                CURRENT_TIMESTAMP
            ),
            updated_at = CURRENT_TIMESTAMP,
            revision = revision + 1
        WHERE organization_id = :organization_id
          AND workspace_id = :workspace_id
          AND employee_id = :employee_id
          AND learning_assignment_id = :learning_assignment_id
          AND subtopic_id = :subtopic_id
    """)

    params = {
        "organization_id": (
            state.employee.organization_id
        ),
        "workspace_id": (
            state.employee.workspace_id
        ),
        "employee_id": (
            state.employee.employee_id
        ),
        "learning_assignment_id": (
            state.employee.learning_assignment_id
        ),
        "subtopic_id": (
            state.learning.current_subtopic_id
        ),
    }

    result = session.execute(
        query,
        params,
    )

    if result.rowcount == 0:
        raise ValueError(
            "No learning progress row was found "
            "for the current subtopic."
        )

# Graph Flow
def initialize_session(state: OnboardingState) -> OnboardingState:
    employee = state.employee

    if employee.session_id is None:
        raise ValueError(
            "session_id is required for the current existing-session test."
        )

    with SessionLocal() as session:
        session_query = text("""
            SELECT
                ls.learning_session_id,
                ls.status AS session_status,
                ls.learning_assignment_id,
                ls.curriculum_id,
                ls.current_topic_id,
                ls.current_subtopic_id,

                cur.name AS curriculum_title

            FROM workweave.learning_sessions ls

            JOIN workweave.learning_assignments la
                ON la.organization_id = ls.organization_id
                AND la.workspace_id = ls.workspace_id
                AND la.learning_assignment_id = ls.learning_assignment_id
                AND la.employee_id = ls.employee_id
                AND la.curriculum_id = ls.curriculum_id

            JOIN workweave.curricula cur
                ON cur.organization_id = ls.organization_id
                AND cur.workspace_id = ls.workspace_id
                AND cur.curriculum_id = ls.curriculum_id

            WHERE ls.organization_id = :organization_id
                AND ls.workspace_id = :workspace_id
                AND ls.employee_id = :employee_id
                AND ls.learning_session_id = :session_id

                AND ls.status IN ('ACTIVE', 'PAUSED')
                AND la.status = 'ACTIVE'
                AND cur.status = 'PUBLISHED'
        """)

        result = session.execute(
            session_query,
            {
                "organization_id": employee.organization_id,
                "workspace_id": employee.workspace_id,
                "employee_id": employee.employee_id,
                "session_id": employee.session_id,
            }
        )

        session_data = result.mappings().first()

        if not session_data:
            raise ValueError(
                "No valid ACTIVE or PAUSED onboarding session was found."
            )

        curriculum_query = text("""
            SELECT
                ct.topic_id,
                ct.name AS topic_name,
                ct.description AS topic_description,
                ct.order_index AS topic_order,

                cs.subtopic_id,
                cs.name AS subtopic_name,
                cs.description AS subtopic_description,
                cs.order_index AS subtopic_order,

                lo.objective_id,
                lo.description AS objective_description,
                lo.assessment_criteria,
                lo.criteria_version,
                lo.required,
                lo.hint_policy,
                lo.competency_id

            FROM workweave.curriculum_topics ct

            JOIN workweave.curriculum_subtopics cs
                ON cs.organization_id = ct.organization_id
                AND cs.workspace_id = ct.workspace_id
                AND cs.topic_id = ct.topic_id

            LEFT JOIN workweave.learning_objectives lo
                ON lo.organization_id = cs.organization_id
                AND lo.workspace_id = cs.workspace_id
                AND lo.subtopic_id = cs.subtopic_id

            WHERE ct.organization_id = :organization_id
                AND ct.workspace_id = :workspace_id
                AND ct.curriculum_id = :curriculum_id

                AND ct.active = TRUE
                AND cs.active = TRUE

            ORDER BY
                ct.order_index,
                cs.order_index
        """)

        result = session.execute(
            curriculum_query,
            {
                "organization_id": employee.organization_id,
                "workspace_id": employee.workspace_id,
                "curriculum_id": session_data["curriculum_id"],
            }
        )

        curriculum_rows = result.mappings().all()

        if not curriculum_rows:
            raise ValueError(
                "No active topics/subtopics were found for the curriculum."
            )

        topics = {}

        for row in curriculum_rows:

            topic_id = str(row["topic_id"])
            subtopic_id = str(row["subtopic_id"])

            if topic_id not in topics:
                topics[topic_id] = {
                    "topic_id": topic_id,
                    "title": row["topic_name"],
                    "subtopics": {}
                }

            if subtopic_id not in topics[topic_id]["subtopics"]:
                topics[topic_id]["subtopics"][subtopic_id] = {
                    "subtopic_id": subtopic_id,
                    "title": row["subtopic_name"],
                    "objectives": []
                }

            if row["objective_id"] is not None:

                objective = LearningObjective(
                    objective_id=str(row["objective_id"]),
                    description=row["objective_description"],
                    assessment_criteria=(
                        row["assessment_criteria"] or {}
                    ),
                    criteria_version=row["criteria_version"],
                    required=row["required"],
                    hint_policy=row["hint_policy"] or {},
                    competency_id=(
                        str(row["competency_id"])
                        if row["competency_id"] is not None
                        else None
                    ),
                )

                topics[topic_id]["subtopics"][subtopic_id][
                    "objectives"
                ].append(objective)

        curriculum_topics = []

        for topic in topics.values():

            subtopics = [
                Subtopic(**subtopic)
                for subtopic in topic["subtopics"].values()
            ]

            curriculum_topics.append(
                Topic(
                    topic_id=topic["topic_id"],
                    title=topic["title"],
                    subtopics=subtopics,
                )
            )

        # progress_query = text("""
        #     SELECT
        #         progress_id,
        #         subtopic_id,
        #         status,
        #         started_at,
        #         completed_at

        #     FROM workweave.employee_learning_progress

        #     WHERE organization_id = :organization_id
        #         AND workspace_id = :workspace_id
        #         AND employee_id = :employee_id
        #         AND learning_assignment_id = :learning_assignment_id
        # """)

        # result = session.execute(
        #     progress_query,
        #     {
        #         "organization_id": employee.organization_id,
        #         "workspace_id": employee.workspace_id,
        #         "employee_id": employee.employee_id,
        #         "learning_assignment_id": session_data[
        #             "learning_assignment_id"
        #         ],
        #     }
        # )

        # progress_rows = result.mappings().all()

        # progress = {
        #     str(row["subtopic_id"]): row["status"]
        #     for row in progress_rows
        # }

        current_topic_id = (
            str(session_data["current_topic_id"])
            if session_data["current_topic_id"] is not None
            else None
        )

        current_subtopic_id = (
            str(session_data["current_subtopic_id"])
            if session_data["current_subtopic_id"] is not None
            else None
        )

        state.employee.session_id = str(
            session_data["learning_session_id"]
        )

        state.employee.learning_assignment_id = str(
            session_data["learning_assignment_id"]
        )

        state.employee.session_status = session_data[
            "session_status"
        ]

        state.onboarding = Onboarding(
            curriculum_id=str(session_data["curriculum_id"]),
            curriculum_title=session_data["curriculum_title"],
            topics=curriculum_topics,
            current_topic_id=current_topic_id,
            current_subtopic_id=current_subtopic_id,
        )

        return state

def get_current_learning_context(state: OnboardingState):
    if state.onboarding is None:
        raise ValueError(
            "Onboarding session has not been initialized."
        )

    if state.employee.session_id is None:
        raise ValueError(
            "Learning session ID is required."
        )

    with SessionLocal() as session:
        assignment_query = text("""
            SELECT
                learning_assignment_id
            FROM workweave.learning_sessions
            WHERE organization_id = :organization_id
              AND workspace_id = :workspace_id
              AND learning_session_id = :learning_session_id
              AND employee_id = :employee_id
              AND status IN ('ACTIVE', 'PAUSED')
        """)

        assignment = session.execute(
            assignment_query,
            {
                "organization_id": state.employee.organization_id,
                "workspace_id": state.employee.workspace_id,
                "learning_session_id": state.employee.session_id,
                "employee_id": state.employee.employee_id,
            }
        ).mappings().first()

        if assignment is None:
            raise ValueError(
                "No valid learning session was found."
            )

        learning_assignment_id = str(
            assignment["learning_assignment_id"]
        )

        progress_query = text("""
            SELECT
                subtopic_id,
                status,
                started_at,
                completed_at
            FROM workweave.employee_learning_progress
            WHERE organization_id = :organization_id
              AND workspace_id = :workspace_id
              AND employee_id = :employee_id
              AND learning_assignment_id = :learning_assignment_id
        """)

        progress_rows = session.execute(
            progress_query,
            {
                "organization_id": state.employee.organization_id,
                "workspace_id": state.employee.workspace_id,
                "employee_id": state.employee.employee_id,
                "learning_assignment_id": learning_assignment_id,
            }
        ).mappings().all()

        progress_by_subtopic = {
            str(row["subtopic_id"]): row
            for row in progress_rows
        }

        prerequisite_query = text("""
            SELECT
                subtopic_id,
                prerequisite_subtopic_id
            FROM workweave.curriculum_prerequisites
            WHERE organization_id = :organization_id
              AND workspace_id = :workspace_id
        """)

        prerequisite_rows = session.execute(
            prerequisite_query,
            {
                "organization_id": state.employee.organization_id,
                "workspace_id": state.employee.workspace_id,
            }
        ).mappings().all()

        prerequisites = {}

        for row in prerequisite_rows:

            subtopic_id = str(row["subtopic_id"])
            prerequisite_id = str(
                row["prerequisite_subtopic_id"]
            )

            prerequisites.setdefault(
                subtopic_id,
                []
            ).append(prerequisite_id)

    for topic in state.onboarding.topics:
        for subtopic in topic.subtopics:
            progress = progress_by_subtopic.get(subtopic.subtopic_id)

            if (progress and progress["status"] == "IN_PROGRESS"):
                state.learning.current_topic_id = topic.topic_id
                state.learning.current_subtopic_id = subtopic.subtopic_id
                state.learning.current_status = "IN_PROGRESS"
                state.learning.current_objectives = subtopic.objectives

                return state

    for topic in state.onboarding.topics:
        for subtopic in topic.subtopics:
            progress = progress_by_subtopic.get(subtopic.subtopic_id)
            status = (progress["status"] if progress else "NOT_STARTED")

            if status != "NOT_STARTED":
                continue

            required_prerequisites = prerequisites.get(subtopic.subtopic_id, [])
            prerequisites_complete = True

            for prerequisite_id in required_prerequisites:
                prerequisite_progress = (progress_by_subtopic.get(prerequisite_id))

                if (prerequisite_progress is None or prerequisite_progress["status"] != "COMPLETED"):
                    prerequisites_complete = False
                    break

            if prerequisites_complete:
                state.learning.current_topic_id = topic.topic_id
                state.learning.current_subtopic_id = subtopic.subtopic_id
                state.learning.current_status = "NOT_STARTED"
                state.learning.current_objectives = subtopic.objectives

                return state

    state.learning.current_topic_id = None
    state.learning.current_subtopic_id = None
    state.learning.current_status = "COMPLETED"
    state.learning.current_objectives = []

    return state

def initiate_conversation(state: OnboardingState) -> OnboardingState:
    if state.learning.current_status == "COMPLETED":
        return state

    opening_message = generate_initial_message(state)

    state.conversation.user_message = None
    state.conversation.input_kind = None
    state.conversation.assistant_message = opening_message
    state.conversation.is_initial_message = True

    state.learning.retrieved_knowledge = []
    state.learning.pending_question = None
    state.learning.current_strategy = None

    return state

def save_initial_event(state: OnboardingState) -> OnboardingState:
    if not state.conversation.assistant_message:
        raise ValueError(
            "No assistant message exists to save."
        )

    return save_learning_event(
        state,
        event_type="SESSION_STARTED",
        operation_key=(
            f"initial-message:{state.employee.session_id}"
        ),
        event_data={
            "message": state.conversation.assistant_message,
            "input_kind": "AI",
            "is_initial_message": (
                state.conversation.is_initial_message
            ),
        },
        strategy=None,
        source_refs=[],
    )

def wait_for_user(state: OnboardingState) -> OnboardingState:
    user_input = interrupt({
        "message": state.conversation.assistant_message
    })

    if isinstance(user_input, dict):
        message = user_input.get("message")
        input_kind = user_input.get("input_kind", "TEXT")
    else:
        message = str(user_input)
        input_kind = "TEXT"

    if not message:
        raise ValueError(
            "User message is required."
        )

    state.conversation.user_message = message
    state.conversation.input_kind = input_kind
    state.conversation.is_initial_message = False

    return state

def analyze_user_response(state: OnboardingState) -> OnboardingState:
    user_message = state.conversation.user_message

    if not user_message:
        raise ValueError(
            "User message is required for response analysis."
        )

    if state.onboarding is None:
        raise ValueError(
            "Onboarding session has not been initialized."
        )

    current_topic = None
    current_subtopic = None

    for topic in state.onboarding.topics:
        if topic.topic_id == state.learning.current_topic_id:
            current_topic = topic

            for subtopic in topic.subtopics:
                if (
                    subtopic.subtopic_id
                    == state.learning.current_subtopic_id
                ):
                    current_subtopic = subtopic
                    break

            break

    if current_topic is None or current_subtopic is None:
        raise ValueError(
            "Current learning context could not be resolved."
        )

    objectives = "\n".join(
        f"- {objective.description}"
        for objective in state.learning.current_objectives
    )

    prompt = f"""
    You are analyzing an employee's response during adaptive onboarding.

    Current topic:
    {current_topic.title}

    Current subtopic:
    {current_subtopic.title}

    Learning objectives:
    {objectives}

    The AI previously said:
    {state.conversation.assistant_message}

    The employee responded:
    {user_message}

    Analyze only what is supported by the employee's response.

    Intent definitions:
    - ANSWER: responding to the AI's current question.
    - QUESTION: asking a question about the topic.
    - HELP_REQUEST: explicitly asking for explanation, guidance, or help.
    - PAUSE_REQUEST: wants to stop, pause, or take a break.
    - CONTINUE: explicitly wants to continue or move forward.
    - OTHER: none of the above clearly apply.

    Learning signals:
    - CONFUSION: explicitly shows misunderstanding or confusion.
    - UNCERTAINTY: explicitly expresses uncertainty or lack of knowledge.
    - EXAMPLE_REQUEST: asks for an example.
    - REPEATED_QUESTION: repeats a previously asked question.
    - SELF_REPORTED_FAMILIARITY: explicitly describes prior familiarity
    or experience relevant to the current learning area.

    Do not infer personality, intelligence, learning ability, or mental state.
    Do not infer a learning signal without evidence in the response.

    Choose the recommended action:
    - TEACH when the response indicates the employee needs explanation,
    guidance, or instruction.
    - ASSESS when the employee reports relevant familiarity or experience
    and it is appropriate to verify their understanding.
    - PROGRESS only when the system already has accepted assessment evidence
    showing that the required learning objective has been satisfied.
    - Never choose PROGRESS only because the employee says they understand,
    says "yes", says "okay", says "got it", thanks the AI, or indicates that
    an explanation was helpful. These responses are conversational
    acknowledgements, not evidence of mastery.
    - If the employee indicates that the explanation makes sense but has not
    yet demonstrated the required learning objective, choose ASSESS so their
    understanding can be verified.
    - Do not treat self-reported understanding as accepted learning evidence.
    - CLARIFY when the response is ambiguous or insufficient to decide
    what should happen next.
    - PAUSE when the employee explicitly wants to pause or stop.
    If TEACH is recommended, choose the most appropriate teaching strategy.
    Otherwise, recommended_strategy should normally be null.

    Routing priority:

    1. Explicit pause/stop request -> PAUSE
    2. Explicit confusion/help/question -> TEACH
    3. Explanation understood but mastery not yet verified -> ASSESS
    4. Existing accepted assessment evidence satisfies the objective -> PROGRESS
    5. Ambiguous response -> CLARIFY
    """

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config={
            "response_mime_type": "application/json",
            "response_json_schema": ResponseAnalysis.model_json_schema(),
            # Classification needs little reasoning; minimal thinking cut this call from ~9.5s to ~2.3s.
            "thinking_config": {"thinking_level": "minimal"},
        },
    )

    if not response.text:
        raise ValueError(
            "Gemini did not return response analysis."
        )

    analysis = ResponseAnalysis.model_validate_json(
        response.text
    )

    state.response_analysis = analysis

    return state

# SUBGRAPH - TEACHING
def teaching_retrieve_knowledge(state: OnboardingState) -> OnboardingState:

    if state.response_analysis is None:
        raise ValueError(
            "Response analysis is required before teaching."
        )

    if state.response_analysis.recommended_action != "TEACH":
        raise ValueError(
            "Teaching retrieval was called for a non-TEACH action."
        )

    retrieval_query = build_initial_retrieval_query(state)

    if state.conversation.user_message:
        retrieval_query += (
            "\n\nEmployee's current message:\n"
            f"{state.conversation.user_message}"
        )

    query_embedding = embed_query(
        retrieval_query
    )

    retrieved_knowledge = retrieve_learning_knowledge(
        state,
        query_embedding
    )

    if not retrieved_knowledge:
        raise ValueError(
            "No approved knowledge was found for the current learning context."
        )

    state.learning.retrieved_knowledge = retrieved_knowledge
    state.learning.current_strategy = (
        state.response_analysis.recommended_strategy
        or "CONCISE"
    )

    return state

def generate_teaching_response(state: OnboardingState) -> OnboardingState:
    if not state.learning.retrieved_knowledge:
        raise ValueError(
            "Retrieved knowledge is required before generating a teaching response."
        )

    strategy = state.learning.current_strategy or "CONCISE"

    objectives = "\n".join(
        f"- {objective.description}"
        for objective in state.learning.current_objectives
    )

    knowledge_context = "\n\n".join(
        (
            f"Source: {chunk.document_code} "
            f"| Section: {chunk.section_key}\n"
            f"{chunk.content}"
        )
        for chunk in state.learning.retrieved_knowledge
    )

    prompt = f"""
    You are the WorkWeave Adaptive Onboarding AI.

    You are continuing a natural onboarding conversation with an employee.

    Employee's message:
    {state.conversation.user_message}

    Learning objectives:
    {objectives}

    Teaching strategy:
    {strategy}

    Approved knowledge:
    {knowledge_context}

    Your task is to teach the employee using only the approved knowledge above.

    Grounding rules:
    - Do not introduce procedures, facts, requirements, or steps that are not
      supported by the approved knowledge.
    - If the approved knowledge does not contain something needed, say that
      it is not available in the current approved material.
    - Do not treat your own reasoning as an authoritative procedure.
    - Do not expose internal chunk IDs, retrieval scores, or system metadata.

    Teaching behavior:
    - Respond directly to what the employee said.
    - Adapt the explanation to the selected teaching strategy.
    - Keep the tone natural, like a helpful coworker or mentor.
    - Do not mention the teaching strategy by name.
    - Do not mention learning objectives or assessment criteria.
    - Do not overwhelm the employee with unnecessary information.
    - Preserve important warnings, limitations, and escalation instructions
      from the approved knowledge.

    Strategy guidance:
    - CONCISE: explain only the essential idea briefly.
    - DETAILED: provide a fuller explanation with relevant context.
    - STEP_BY_STEP: explain the process in a clear practical sequence.
    - EXAMPLE: teach primarily through a grounded example.
    - GUIDED_PRACTICE: guide the employee through applying the knowledge
      without giving an unsupported answer.

    Source reference:
    - Naturally identify the relevant document and section when useful.
    - Do not fabricate a section or source reference.

    End with exactly one short, natural follow-up question that helps determine
    whether the employee understood the explanation or is ready to apply it.

    Return only the message that should be shown to the employee.
    """

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
    )

    if not response.text:
        raise ValueError(
            "Gemini did not generate a teaching response."
        )

    state.conversation.assistant_message = response.text.strip()
    state.conversation.is_initial_message = False

    return state

def save_teaching_event(state: OnboardingState,) -> OnboardingState:
    if not state.conversation.assistant_message:
        raise ValueError(
            "No teaching response exists to save."
        )

    if not state.learning.retrieved_knowledge:
        raise ValueError(
            "Retrieved knowledge is required "
            "before saving a teaching event."
        )
    
    source_refs = [
        {
            "chunk_id": chunk.chunk_id,
            "document_code": chunk.document_code,
            "document_version_id": (
                chunk.document_version_id
            ),
            "section_id": chunk.section_id,
            "section_key": chunk.section_key,
        }
        for chunk in state.learning.retrieved_knowledge
    ]

    operation_key = (
        f"teaching:"
        f"{state.employee.session_id}:"
        f"{state.learning.current_subtopic_id}:"
        f"{hashlib.sha256((state.conversation.user_message or '').encode()).hexdigest()}"
    )

    return save_learning_event(
        state,
        event_type="EXPLANATION_PROVIDED",
        operation_key=operation_key,
        event_data={
            "message": state.conversation.assistant_message,
            "input_kind": "AI",
        },
        strategy=state.learning.current_strategy,
        source_refs=source_refs,
    )

# Teaching Builder Subgraph
teaching_builder = StateGraph(OnboardingState)
teaching_builder.add_node("retrieve_knowledge", teaching_retrieve_knowledge)
teaching_builder.add_node("generate_response", generate_teaching_response)
teaching_builder.add_node("save_teaching_event", save_teaching_event)

teaching_builder.add_edge(START, "retrieve_knowledge")
teaching_builder.add_edge("retrieve_knowledge", "generate_response")
teaching_builder.add_edge("generate_response", "save_teaching_event")
teaching_builder.add_edge("save_teaching_event", END)

teaching_graph = teaching_builder.compile()

# SUBGRAPH - ASSESSMENT
def generate_assessment_question(state: OnboardingState) -> OnboardingState:
    if not state.learning.current_objectives:
        raise ValueError(
            "No learning objective is available for assessment."
        )
    
    objective = state.learning.current_objectives[0]
    criteria = objective.assessment_criteria

    if not criteria:
        raise ValueError(
            "Assessment criteria are required."
        )

    # Ground the scenario in the approved material for this item (retrieve it if teaching didn't yet).
    if not state.learning.retrieved_knowledge:
        state.learning.retrieved_knowledge = retrieve_learning_knowledge(state, embed_query(build_initial_retrieval_query(state)))
    knowledge_context = "\n\n".join(
        f"Source: {chunk.document_code} | Section: {chunk.section_key}\n{chunk.content}"
        for chunk in state.learning.retrieved_knowledge
    )

    prompt = f"""
    You are the WorkWeave Adaptive Onboarding AI.

    You need to verify whether an employee can apply what they
    have just learned.

    Learning objective:
    {objective.description}

    Assessment criteria:
    {json.dumps(criteria, indent=2)}

    Approved knowledge for this learning area (the employee's workplace, equipment and examples):
    {knowledge_context}

    The AI previously said:
    {state.conversation.assistant_message}

    The employee responded:
    {state.conversation.user_message}

    Generate exactly one natural assessment question.

    Assessment question requirements:
    - Ask exactly one natural application question.
    - Prefer a practical scenario when appropriate.
    - The question must give the employee a reasonable opportunity
    to demonstrate the required checks.
    - Keep the scenario concise and easy to understand on first read.
    - Include only the details necessary to evaluate the learning
    objective.
    - Avoid unnecessarily long setup or unrelated details.
    - Assess understanding through application, not self-report.
    - Do not ask whether they understand or whether the previous
    explanation made sense.
    - Do not ask them to rate their confidence.
    - Do not reveal, list, or directly paraphrase the assessment
    criteria.
    - Do not reveal the correct answer.
    - Do not tell the employee exactly what steps they must perform.
    - Do not mention assessment, scoring, criteria, or evaluation.
    - Keep the conversation natural, like a coworker asking how
    they would handle a situation.

    Hint requirements:
    - Include exactly one short hint after the question.
    - Format it as: "Hint: ..."
    - The hint should reduce cognitive load and help the employee
    identify where to begin.
    - Point only toward the general concept or area they should
    think about.
    - Do not reveal or enumerate the required checks.
    - Do not provide the solution.
    - Do not tell the employee the specific actions they need to take.
    - Keep the hint to one short sentence.
    - Do not provide coaching beyond this single permitted hint.

    Difficulty guidance:
    - Use an onboarding-level scenario, not an expert-level scenario.
    - Test the core learning objective rather than trying to force every detail
    of every assessment criterion into the question.
    - The employee should be able to answer naturally in a few sentences.
    - Do not require a perfectly formatted or exhaustive response.
    - Avoid combining too many edge cases into one scenario.
    - Include enough context for the employee to reason about the situation
    without needing to memorize exact wording from the source.

    Workplace grounding:
    - Set the scenario in the employee's own workplace as described in the approved knowledge:
      use its kinds of equipment, work items and examples.
    - Do not introduce industries, products or systems the approved knowledge doesn't mention.
    - Use only document codes and versions that appear in the approved knowledge; never invent one.

    Return only the question and its hint that should be shown
    to the employee.
    """

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
    )

    if not response.text:
        raise ValueError(
            "Gemini did not generate an assessment question."
        )

    question = response.text.strip()
    state.assessment = AssessmentState(
        objective_id=objective.objective_id,
        pending_question_id=str(uuid4()),
        question=question,
        criteria=criteria
    )
    state.learning.pending_question = question
    state.conversation.assistant_message = question
    state.conversation.is_initial_message = False

    return state

# Assessment Builder Subgraph
assessment_builder = StateGraph(OnboardingState)
assessment_builder.add_node("generate_question", generate_assessment_question)

assessment_builder.add_edge(START, "generate_question")
assessment_builder.add_edge("generate_question", END)
assessment_graph = assessment_builder.compile()

def evaluate_assessment_answer(state: OnboardingState) -> OnboardingState:
    if state.assessment is None:
        raise ValueError(
            "Assessment state is required."
        )

    if not state.learning.pending_question:
        raise ValueError(
            "No pending assessment question exists."
        )

    if not state.conversation.user_message:
        raise ValueError(
            "Employee answer is required."
        )

    criteria = state.assessment.criteria
    required_checks = criteria.get("required_checks", [])
    check_descriptions = criteria.get("check_descriptions", {})

    if not required_checks:
        raise ValueError(
            "No required assessment checks were found."
        )

    prompt = f"""
    You are evaluating an employee's answer during
    WorkWeave Adaptive Onboarding.

    Assessment question:
    {state.assessment.question}

    Employee answer:
    {state.conversation.user_message}

    Required checks:
    {json.dumps(required_checks, indent=2)}

    Check descriptions:
    {json.dumps(check_descriptions, indent=2)}

    Evaluate the employee's answer only against the required
    checks above.

    For every required check:
    - Return the exact criterion name.
    - Set met=true only when the employee's answer provides
      sufficient evidence for that criterion.
    - Set met=false when the criterion is missing, incorrect,
      contradicted, or only implied too weakly.
    - Evidence must briefly explain what in the employee's
      answer supports or fails to support the criterion.
    - Do not give credit based on what the AI previously taught.
    - Do not assume knowledge that the employee did not
      demonstrate.
    - Do not treat confidence or self-reported understanding
      as evidence.

    Evaluation guidance:
    - Evaluate whether the employee demonstrates the core intent of each
    criterion, not whether they reproduce every detail in its description.
    - Use a reasonable onboarding standard, not an expert certification standard.
    - Accept natural language, paraphrases, shorthand, and equivalent actions.
    - Do not require the employee to use exact SOP terminology.
    - Do not require every example or supporting detail mentioned in a criterion
    description to appear in the answer.
    - Mark a criterion as met when the employee's answer clearly demonstrates
    the essential behavior or decision represented by that criterion.
    - Infer obvious implications when they are reasonably clear from the
    employee's answer, but do not invent actions or knowledge they did not
    demonstrate.
    - Minor omissions that do not change the employee's underlying decision
    should not automatically cause a criterion to fail.
    - Only mark a criterion as not met when an important part of its core intent
    is missing, contradicted, or handled incorrectly.
    - Prefer PARTIAL over INCORRECT when the employee demonstrates meaningful
    understanding but misses important parts.
    - Use UNASSESSABLE only when the employee does not make a meaningful attempt
    to answer, asks for the answer, gives an unrelated response, or provides
    too little information to evaluate.

    Determine the overall outcome using these rules:

    CORRECT:
    The employee demonstrates the core learning objective and shows
    sufficient practical understanding to proceed safely and correctly.

    A CORRECT answer does not need to explicitly state every required
    check when some checks are reasonably demonstrated by the employee's
    overall approach or are secondary details that can be reinforced later.

    Minor omissions should not prevent a CORRECT outcome when they do not
    change the correctness or safety of the employee's intended action.

    PARTIAL:
    The employee demonstrates meaningful understanding of the learning
    objective, but misses an important behavior that could materially affect
    the correctness, safety, or reliability of the action.

    INCORRECT:
    The employee's answer demonstrates little or no understanding of the
    core objective, or proposes an action that materially contradicts the
    required behavior.

    UNASSESSABLE:
    The employee does not make a meaningful attempt to answer, asks for the
    answer, gives an unrelated response, or provides too little information
    to reasonably evaluate their understanding.

    Important:
    - Do not mark an answer CORRECT merely because it sounds
      reasonable.
    - Evaluate demonstrated behavior, not inferred intent.
    - Do not invent evidence.
    """

    response = client.models.generate_content(
        model=GEMINI_REASONING_MODEL,
        contents=prompt,
        config={
            "response_mime_type": "application/json",
            "response_json_schema": (
                AssessmentEvaluation.model_json_schema()
            ),
            "thinking_config": {"thinking_level": GEMINI_REASONING_THINKING},
        },
    )

    if not response.text:
        raise ValueError(
            "Gemini did not return an assessment evaluation."
        )

    evaluation = AssessmentEvaluation.model_validate_json(
        response.text
    )

    returned_criteria = [result.criterion for result in evaluation.criterion_results]

    if (
        len(returned_criteria) != len(required_checks)
        or set(returned_criteria) != set(required_checks)
    ):
        raise ValueError(
            "Assessment evaluation did not return exactly "
            "the required criteria."
        )

    state.assessment.employee_answer = (
        state.conversation.user_message
    )
    state.assessment.criterion_results = (
        evaluation.criterion_results
    )
    state.assessment.outcome = evaluation.outcome
    state.assessment.evidence = evaluation.evidence
    state.learning.pending_question = None

    return state

def generate_assessment_reinforcement(state: OnboardingState) -> OnboardingState:
    if state.assessment is None:
        raise ValueError(
            "Assessment state is required."
        )

    if state.assessment.outcome not in (
        "PARTIAL",
        "INCORRECT",
    ):
        raise ValueError(
            "Reinforcement requires a PARTIAL or INCORRECT assessment."
        )

    failed_criteria = [
        result
        for result in state.assessment.criterion_results
        if not result.met
    ]

    if not failed_criteria:
        raise ValueError(
            "No failed assessment criteria were found."
        )

    failed_context = "\n".join(
        (
            f"- {result.criterion}: "
            f"{result.evidence or 'Not demonstrated.'}"
        )
        for result in failed_criteria
    )

    knowledge_context = "\n\n".join(
        (
            f"Source: {chunk.document_code} "
            f"| Section: {chunk.section_key}\n"
            f"{chunk.content}"
        )
        for chunk in state.learning.retrieved_knowledge
    )

    prompt = f"""
    You are the WorkWeave Adaptive Onboarding AI.

    The employee attempted an assessment question but has not
    yet demonstrated all required knowledge.

    Assessment question:
    {state.assessment.question}

    Employee answer:
    {state.assessment.employee_answer}

    Areas that were not demonstrated:
    {failed_context}

    Approved knowledge:
    {knowledge_context}

    Provide targeted reinforcement using only the approved
    knowledge above.

    Behavior:
    - Focus only on the areas the employee missed or got wrong.
    - Do not reteach criteria they already demonstrated.
    - Do not mention internal criterion names.
    - Do not mention scoring, CORRECT, PARTIAL, INCORRECT,
      assessment criteria, or evaluation.
    - Do not tell the employee they failed.
    - Explain naturally like a helpful coworker or mentor.
    - Correct misunderstandings clearly when necessary.
    - Do not introduce information unsupported by the approved
      knowledge.
    - Keep the response concise.
    - End with exactly one short question asking whether the
      explanation is clear.

    Return only the message shown to the employee.
    """

    response = client.models.generate_content(
        model=GEMINI_REASONING_MODEL,
        contents=prompt,
        config={"thinking_config": {"thinking_level": GEMINI_REASONING_THINKING}},
    )

    if not response.text:
        raise ValueError(
            "Gemini did not generate assessment reinforcement."
        )

    state.conversation.assistant_message = (
        response.text.strip()
    )
    state.conversation.user_message = None
    state.conversation.is_initial_message = False
    state.learning.current_strategy = "CONCISE"

    return state

# SUBGRAPH - PROGRESS
def can_complete_current_subtopic(state: OnboardingState) -> bool:
    if state.assessment is None:
        return False

    if state.assessment.outcome != "CORRECT":
        return False

    if not state.learning.current_objectives:
        return False

    assessed_objective_id = state.assessment.objective_id

    required_objective_ids = {
        objective.objective_id
        for objective in state.learning.current_objectives
        if objective.required
    }

    if len(required_objective_ids) != 1:
        return False

    return assessed_objective_id in required_objective_ids

def complete_current_subtopic(state: OnboardingState) -> OnboardingState:
    if not can_complete_current_subtopic(state):
        raise ValueError(
            "Current subtopic does not have sufficient "
            "evidence for completion."
        )
    with SessionLocal.begin() as session:
        persist_learning_turn(state, session)
        persist_assessment_attempt(state, session)
        persist_objective_evidence(state, session)
        update_progress_completed(state, session)

        save_learning_event(
            state=state,
            event_type="SUBTOPIC_COMPLETED",
            objective_id=state.assessment.objective_id,
            event_data={
                "assessment_outcome": (
                    state.assessment.outcome
                ),
                "attempt_id": (
                    state.assessment.attempt_id
                ),
            },
            operation_key=(
                f"subtopic-completed:"
                f"{state.employee.learning_assignment_id}:"
                f"{state.learning.current_subtopic_id}"
            ),
            session=session
        )

    state.learning.current_status = "COMPLETED"

    return state

# Progression Builder Subgraph
progression_builder = StateGraph(OnboardingState)
progression_builder.add_node("complete_current_subtopic", complete_current_subtopic)

progression_builder.add_edge(START, "complete_current_subtopic")
progression_builder.add_edge("complete_current_subtopic", END)
progression_graph = progression_builder.compile()

# ---------------------------------------------------------------- WorkWeave app integration (added 2026-10-04)
# Saves each exchange in the format the WorkWeave app reads, so the app writes no learning rows of its own.
# The app passes its request ID and the learner's input kind in the run config; without them (langgraph
# dev, voice console) an ID is generated, so standalone testing is unchanged.

def _app_config(config: RunnableConfig | None) -> dict:
    return dict((config or {}).get("configurable") or {})


def generate_clarification(state: OnboardingState) -> OnboardingState:
    """CLARIFY: ask one short question to understand an ambiguous reply (no teaching, no assessing)."""
    prompt = f"""
    You are the WorkWeave Adaptive Onboarding AI, talking with an employee like a helpful coworker.

    You previously said:
    {state.conversation.assistant_message}

    The employee replied:
    {state.conversation.user_message}

    Their reply is ambiguous, so it isn't clear what they need next.
    Ask exactly one short, friendly question that helps them say what they mean
    (for example, whether they want an explanation, an example, or to try a question).
    - Do not teach, explain the procedure, give hints, or assess.
    - Do not guess what they meant, and do not comment on how they feel or sound.
    Return only the message shown to the employee.
    """
    response = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
    if not response.text:
        raise ValueError("Gemini did not generate a clarification question.")
    state.conversation.assistant_message = response.text.strip()
    state.conversation.is_initial_message = False
    return state

def record_turn(state: OnboardingState, config: RunnableConfig) -> OnboardingState:
    """One transcript turn per tutor reply (learner input + reply + sources + outcome), the open check
    question as a COMPREHENSION_QUESTION event, and the session's revision/position, in one transaction."""
    cfg = _app_config(config)
    e, a = state.employee, state.assessment
    completed = state.learning.current_status == "COMPLETED"
    # Which learner message this reply answers: none for the opening; the graded answer after evaluation.
    answered = a is not None and a.outcome is not None and a.employee_answer is not None and state.conversation.user_message in (None, a.employee_answer)
    learner = None if state.conversation.is_initial_message else (a.employee_answer if answered else state.conversation.user_message)
    is_check = bool(state.learning.pending_question) and state.conversation.assistant_message == state.learning.pending_question
    taught = (not state.conversation.is_initial_message and not is_check and not completed
              and state.response_analysis is not None and state.response_analysis.recommended_action != "CLARIFY")
    citations, seen = [], set()
    for chunk in (state.learning.retrieved_knowledge if taught or (answered and not completed) else []):
        if chunk.section_id not in seen:
            seen.add(chunk.section_id)
            citations.append({"document_version_id": chunk.document_version_id, "section_id": chunk.section_id, "chunk_id": chunk.chunk_id})
    objective = next((o for o in state.learning.current_objectives if a and o.objective_id == a.objective_id), None)
    envelope = {
        "contract_version": "engine-1",
        "reply": {"kind": "CHECK" if is_check else "TEACHING", "text": "" if completed else (state.conversation.assistant_message or ""),
                  "strategy": state.learning.current_strategy, "citations": citations},
    }
    if answered and objective:
        envelope["assessment"] = {"objective_id": a.objective_id, "outcome": a.outcome, "criteria_version": objective.criteria_version,
                                  "evidence": "PASSED" if a.outcome == "CORRECT" else ("UNASSESSABLE" if a.outcome == "UNASSESSABLE" else "NOT_PASSED"),
                                  "criterion_results": [r.model_dump() for r in a.criterion_results]}
    if completed:
        name = next((s.title for t in (state.onboarding.topics if state.onboarding else []) for s in t.subtopics if s.subtopic_id == state.learning.current_subtopic_id), "This subtopic")
        envelope["completed_subtopic"] = {"subtopic_id": state.learning.current_subtopic_id, "name": name}
    client_turn_id = cfg.get("client_turn_id") or str(uuid4())
    input_kind = cfg.get("input_kind") or state.conversation.input_kind or "TEXT"
    learner_input = {"text": learner, "input_kind": input_kind} if learner else {}
    if learner and cfg.get("interrupted_previous_reply"):
        learner_input["interrupted_previous_reply"] = True
    keys = {"o": e.organization_id, "w": e.workspace_id, "s": e.session_id}
    with SessionLocal.begin() as session:
        revision = session.execute(text("""
            UPDATE workweave.learning_sessions
               SET revision = revision + 1, updated_at = CURRENT_TIMESTAMP,
                   current_topic_id = COALESCE(CAST(:topic AS uuid), current_topic_id),
                   current_subtopic_id = COALESCE(CAST(:sub AS uuid), current_subtopic_id)
             WHERE organization_id = :o AND workspace_id = :w AND learning_session_id = :s
            RETURNING revision"""), {**keys, "topic": state.learning.current_topic_id, "sub": state.learning.current_subtopic_id}).scalar_one()
        if not completed and state.learning.current_subtopic_id and e.learning_assignment_id:
            # First saved reply on an item starts it (the progress row needs started_at before COMPLETED).
            session.execute(text("""
                UPDATE workweave.employee_learning_progress
                   SET status = 'IN_PROGRESS', started_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP, revision = revision + 1
                 WHERE organization_id = :o AND workspace_id = :w AND learning_assignment_id = CAST(:la AS uuid)
                   AND subtopic_id = CAST(:sub AS uuid) AND status = 'NOT_STARTED'"""),
                {**keys, "la": e.learning_assignment_id, "sub": state.learning.current_subtopic_id})
        if completed and a is not None and a.turn_id:
            # The completion step already wrote this turn (persist_learning_turn): add the app's fields to it.
            session.execute(text("""
                UPDATE workweave.learning_turns
                   SET response_envelope = response_envelope || CAST(:env AS jsonb), client_turn_id = CAST(:cid AS uuid),
                       committed_revision = :rev, updated_at = CURRENT_TIMESTAMP, revision = revision + 1
                 WHERE organization_id = :o AND workspace_id = :w AND learning_session_id = :s AND turn_id = CAST(:t AS uuid)"""),
                {**keys, "env": json.dumps(envelope), "cid": client_turn_id, "rev": revision, "t": a.turn_id})
        else:
            session.execute(text("""
                INSERT INTO workweave.learning_turns (organization_id, workspace_id, learning_session_id, client_turn_id, input_hash,
                                                      sequence, input_reference, response_envelope, committed_revision, stage)
                SELECT :o, :w, :s, CAST(:cid AS uuid), :hash, COALESCE(MAX(sequence), -1) + 1, CAST(:inp AS jsonb), CAST(:env AS jsonb), :rev, 'COMMITTED'
                  FROM workweave.learning_turns WHERE organization_id = :o AND workspace_id = :w AND learning_session_id = :s
                ON CONFLICT (organization_id, workspace_id, learning_session_id, client_turn_id) DO NOTHING"""),
                {**keys, "cid": client_turn_id, "hash": hashlib.sha256(json.dumps(learner_input, sort_keys=True).encode()).hexdigest(),
                 "inp": json.dumps(learner_input), "env": json.dumps(envelope), "rev": revision})
        if is_check and a is not None and objective:
            save_learning_event(state, event_type="COMPREHENSION_QUESTION", operation_key=f"check:{a.pending_question_id}", objective_id=a.objective_id,
                                event_data={"question_id": a.pending_question_id, "question_version": 1, "criteria_version": objective.criteria_version,
                                            "text": a.question, "issued_turn_id": client_turn_id}, session=session)
    return state


def route_after_record(state: OnboardingState) -> str:
    return "end" if state.learning.current_status == "COMPLETED" else "wait"


# ROUTING
def route_user_response(state: OnboardingState) -> str:
    if state.learning.pending_question:
        return "assessment_answer"

    return "conversation"

def route_action(state: OnboardingState) -> str:

    if state.response_analysis is None:
        raise ValueError(
            "Response analysis is required before routing."
        )

    action = state.response_analysis.recommended_action
    # Completing a subtopic needs a CORRECT assessment of its required objective; without one, check first.
    if action == "PROGRESS" and not can_complete_current_subtopic(state):
        action = "ASSESS"
    routes = {
        "TEACH": "teaching",
        "ASSESS": "assessment",
        "PROGRESS": "progression",
        "CLARIFY": "clarification",
        "PAUSE": "pause",
    }

    if action not in routes:
        raise ValueError(
            f"Unsupported onboarding action: {action}"
        )

    return routes[action]

def prepare_assessment_teaching(state: OnboardingState) -> OnboardingState:
    if state.assessment is None:
        raise ValueError(
            "Assessment state is required."
        )

    state.response_analysis = ResponseAnalysis(
        intent="HELP_REQUEST",
        signals=[],
        recommended_action="TEACH",
        recommended_strategy="CONCISE",
    )

    return state

def route_assessment_outcome(state: OnboardingState) -> str:
    if state.assessment is None:
        raise ValueError(
            "Assessment state is required."
        )

    outcome = state.assessment.outcome

    if outcome == "CORRECT":
        return "correct"

    if outcome == "PARTIAL":
        return "reinforce"

    if outcome in ("INCORRECT", "UNASSESSABLE"):
        return "teach"

    raise ValueError(
        f"Unsupported assessment outcome: {outcome}"
    )

# Onboarding Builder Graph
onboarding_builder = StateGraph(OnboardingState)

# Nodes
onboarding_builder.add_node("initialize_session", initialize_session)
onboarding_builder.add_node("get_current_learning_context", get_current_learning_context)
onboarding_builder.add_node("initiate_conversation", initiate_conversation)
onboarding_builder.add_node("save_initial_event", save_initial_event)
onboarding_builder.add_node("wait_for_user", wait_for_user)
onboarding_builder.add_node("analyze_user_response", analyze_user_response)
onboarding_builder.add_node("teaching", teaching_graph)
onboarding_builder.add_node("assessment", assessment_graph)
onboarding_builder.add_node("evaluate_assessment", evaluate_assessment_answer)
onboarding_builder.add_node("assessment_reinforcement", generate_assessment_reinforcement)
onboarding_builder.add_node("progression", progression_graph)
onboarding_builder.add_node("prepare_assessment_teaching", prepare_assessment_teaching)
onboarding_builder.add_node("clarification", generate_clarification)
onboarding_builder.add_node("record_turn", record_turn)

# Edges
onboarding_builder.add_edge(START, "initialize_session")
onboarding_builder.add_edge("initialize_session", "get_current_learning_context")
onboarding_builder.add_edge("get_current_learning_context", "initiate_conversation")
onboarding_builder.add_edge("initiate_conversation", "save_initial_event")
onboarding_builder.add_edge("save_initial_event", "record_turn")
onboarding_builder.add_conditional_edges(
    "wait_for_user",
    route_user_response,
    {
        "assessment_answer": "evaluate_assessment",
        "conversation": "analyze_user_response",
    },
)
onboarding_builder.add_conditional_edges(
    "analyze_user_response",
    route_action,
    {
        "teaching": "teaching",
        "assessment": "assessment",
        "progression": "progression",
        "clarification": "clarification",
        "pause": END
    },
)
onboarding_builder.add_edge("teaching", "record_turn")
onboarding_builder.add_edge("assessment", "record_turn")
onboarding_builder.add_conditional_edges(
    "evaluate_assessment",
    route_assessment_outcome,
    {
        "correct": "progression",
        "reinforce": "assessment_reinforcement",
        "teach": "prepare_assessment_teaching"
    },
)
onboarding_builder.add_edge("assessment_reinforcement", "record_turn")
onboarding_builder.add_edge("prepare_assessment_teaching", "teaching")
onboarding_builder.add_edge("progression", "record_turn")
onboarding_builder.add_edge("clarification", "record_turn")
onboarding_builder.add_conditional_edges("record_turn", route_after_record, {"wait": "wait_for_user", "end": END})

# checkpointer = InMemorySaver()

# graph = onboarding_builder.compile(
#     checkpointer=checkpointer
# )
graph = onboarding_builder.compile()

# employee = Employee(
#     session_id="962b85ff-2e18-4e75-bacb-86198e830c05",
#     employee_id="23d464aa-1f89-4bea-9f8c-56a100e58b80",
#     organization_id="e0f0513e-3a43-4ee9-9192-a026fe01d7b1",
#     workspace_id="30bbbc4c-5f01-44c7-94af-82eadae6f758"
# )
# state = OnboardingState(
#     employee=employee
# )

# result = graph.invoke(OnboardingState)

# result = OnboardingState(**result)

# print(result.model_dump_json(indent=2))
# state = initialize_session(state)

# current = get_current_learning_context(state)

# print("TOPIC:")
# print(current["topic"].title)

# print("\nSUBTOPIC:")
# print(current["subtopic"].title)

# print("\nOBJECTIVES:")
# for objective in current["objectives"]:
#     print("-", objective.description)


