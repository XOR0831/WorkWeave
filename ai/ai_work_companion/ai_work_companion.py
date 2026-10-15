from datetime import datetime, time, timezone, timedelta
from dotenv import load_dotenv
from google import genai
from typing_extensions import TypedDict
from typing import  Dict, Annotated, List, Optional, Literal
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from uuid import uuid4
from zoneinfo import ZoneInfo

# from langchain.schema import Document  
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from langgraph.graph import START, END, StateGraph
from langgraph.graph.state import LastValue
from langgraph.types import Command, Send, interrupt
from langgraph.checkpoint.memory import InMemorySaver

import asyncio
import hashlib
import json
# import configuration
import operator
import os
import requests

load_dotenv(override=True)

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

llm_chat = ChatGoogleGenerativeAI(
    model=GEMINI_MODEL,
    api_key=gemini_api_key
)

DEFAULT_TASK_DURATION_MINUTES = 30

# Schema
class Employee(BaseModel):
    employee_id: str = Field(
        description="Employee using the Work Companion"
    )
    organization_id: str = Field(
        description="Organization the employee belongs to"
    )
    workspace_id: str = Field(
        description="Workspace where the employee is working"
    )

class EmployeeWorkState(BaseModel):
    work_context_key: Optional[str] = None
    workload_state: Optional[str] = None
    momentum_state: Optional[str] = None
    assistance_need: Optional[str] = None
    active_work_count: int = 0
    blocked_work_count: int = 0
    overdue_work_count: int = 0

class EmployeeShift(BaseModel):
    shift_instance_id: str
    shift_name: str
    timezone: str
    scheduled_start_at: datetime
    scheduled_end_at: datetime
    status: str

class CalendarInquiryRange(BaseModel):
    start: datetime
    end: datetime

class CalendarBusyPeriod(BaseModel):
    start: datetime
    end: datetime

class AvailableTimeSlot(BaseModel):
    start: datetime
    end: datetime
    duration_minutes: int

class ScheduledTask(BaseModel):
    work_item_id: str
    event_type: Literal["TASK", "FOCUS", "CUSTOM"] = "TASK"
    title: str
    start: datetime
    end: datetime
    duration_minutes: int

class ScheduleProposal(BaseModel):
    tasks: list[ScheduledTask] = Field(default_factory=list)
    unscheduled_work_item_ids: list[str] = Field(default_factory=list)
    total_scheduled_minutes: int = 0

class SchedulingContext(BaseModel):
    employee_email: str | None = None
    shifts: list[EmployeeShift] = Field(default_factory=list)
    busy_periods: list[CalendarBusyPeriod] = Field(default_factory=list)
    available_slots: list[AvailableTimeSlot] = Field(default_factory=list)
    error: str | None = None
    proposal: ScheduleProposal = Field(default_factory=ScheduleProposal)
    approval_status: str = "not_requested"
    response: str | None = None

class ScheduleApprovalDecision(BaseModel):
    decision: Literal["APPROVE", "REJECT", "MODIFY", "UNCLEAR"]
    requested_start: datetime | None = None
    requested_end: datetime | None = None
    requested_title: str | None = None

class KnowledgeScopeSelection(BaseModel):
    document_id: Optional[str] = None
    document_code: Optional[str] = None
    title: Optional[str] = None
    topic: Optional[str] = None
    subtopic: Optional[str] = None

class RetrievedKnowledgeChunk(BaseModel):
    chunk_id: str
    document_id: str
    document_code: Optional[str] = None
    title: str
    topic: Optional[str] = None
    subtopic: Optional[str] = None
    content: str
    similarity: float

class WorkItem(BaseModel):
    work_item_id: str = Field(
        description="Unique ID of the work item"
    )
    external_id: Optional[str] = Field(
        default=None,
        description="Source-system reference, such as a ticket number"
    )
    work_type: Literal["TASK", "TICKET", "INCIDENT", "ACTIVITY", "HANDOVER", "OTHER"] = Field(
        description="Type of work assigned to the employee"
    )
    title: str = Field(
        description="Short title of the work item"
    )
    description: Optional[str] = Field(
        default=None,
        description="Additional details about the work item"
    )
    status: str = Field(
        description="Current status of the work item"
    )
    priority: Optional[str] = Field(
        default=None,
        description="Source-system priority, if available"
    )
    due_at: Optional[str] = Field(
        default=None,
        description="Deadline or target completion time"
    )
    sla_due_at: Optional[str] = Field(
        default=None,
        description="SLA deadline for the work item, if applicable"
    )
    is_carryover: bool = Field(
        default=False,
        description="Whether this work item carried over from previous work"
    )
    is_blocked: bool = Field(
        default=False,
        description="Whether progress is currently blocked"
    )
    blocker: Optional[str] = Field(
        default=None,
        description="Reason the work item is blocked"
    )
    reported_status: Optional[str] = Field(
        default=None,
        description=(
            "Latest employee-reported status awaiting source reconciliation"
        ),
    )
    source_sync_status: Optional[Literal["AWAITING_SOURCE", "MATCHED", "NEEDS_REVIEW"]] = None
    blocker_source: Optional[Literal["EMPLOYEE_REPORTED", "SOURCE_CONFIRMED"]] = None

class PriorityItem(BaseModel):
    work_item_id: str = Field(
        description="Work item being prioritized"
    )
    rank: int = Field(
        description="Recommended order in which the employee should address the item"
    )
    reason: str = Field(
        description="Why WorkWeave assigned this priority"
    )
    urgency: Optional[Literal["LOW", "NORMAL", "HIGH", "CRITICAL"]] = None

class PriorityContext(BaseModel):
    prioritized_items: list[PriorityItem] = Field(
        default_factory=list,
        description="Work items ordered by WorkWeave's recommended priority"
    )
    top_priority_id: Optional[str] = Field(
        default=None,
        description="Work item WorkWeave recommends addressing first"
    )

class WorkContext(BaseModel):
    active_items: list[WorkItem] = Field(
        default_factory=list,
        description="Current active work assigned to the employee"
    )
    carryover_items: list[WorkItem] = Field(
        default_factory=list,
        description="Unfinished work carried over from previous work periods"
    )
    blocked_items: list[WorkItem] = Field(
        default_factory=list,
        description="Current work items that are blocked"
    )

class CompanionSession(BaseModel):
    work_session_id: Optional[str] = Field(
        default=None,
        description="Current Work Companion session ID"
    )
    shift_instance_id: Optional[str] = Field(
        default=None,
        description="Shift instance associated with the work session"
    )
    status: Optional[str] = Field(
        default=None,
        description="Current Work Companion session status"
    )
    started_at: Optional[str] = Field(
        default=None,
        description="When the Work Companion session started"
    )
    focused_work_item_id: Optional[str] = Field(
        default=None,
        description="Work item currently being focused on"
    )

class CompanionConversation(BaseModel):
    user_message: Optional[str] = Field(
        default=None,
        description="Current employee message to the Work Companion"
    )
    assistant_message: Optional[str] = Field(
        default=None,
        description="Current response generated by the Work Companion"
    )
    input_kind: Optional[Literal["TEXT", "VOICE_TRANSCRIPT"]] = Field(
        default=None,
        description="How the employee input was received"
    )
    is_opening_brief: bool = Field(
        default=False,
        description="Whether the current assistant message is the opening work brief"
    )
    history: list[dict] = Field(
        default_factory=list,
        description="Recent turns ({role, text}), for follow-ups such as 'that one' or 'do the same for 952'"
    )

class CompanionResponseAnalysis(BaseModel):
    intent: Literal["START_WORK", "WORK_OVERVIEW", "WORK_QUESTION", "STATUS_UPDATE", "BLOCKER", "BLOCKER_RESOLVED", "PRIORITY_CHANGE", "SCHEDULE_REQUEST", "CALENDAR_INQUIRY", "DELEGATE_WORK", "CONFIRM_DELEGATION", "ASSIGNMENT_QUESTION", "APP_ACTION", "WORK_DATA_QUESTION", "PAUSE_REQUEST", "OTHER"]
    referenced_work_item_id: Optional[str] = Field(
        default=None,
        description="Work item the employee is referring to, if identifiable"
    )
    recommended_action: Literal["FOCUS", "OVERVIEW", "GUIDE", "UPDATE_STATUS", "HANDLE_BLOCKER", "REPRIORITIZE", "SCHEDULE", "CALENDAR", "DELEGATE", "CONFIRM_DELEGATION", "EXPLAIN_ASSIGNMENT", "APP_ACTION", "ANSWER_WORK_DATA", "PAUSE", "CLARIFY"]

class WorkUpdateAnalysis(BaseModel):
    update_type: Literal["STATUS_CHANGE", "BLOCKER", "BLOCKER_RESOLVED", "PROGRESS_UPDATE"]
    work_item_id: str = Field(
        description="Work item being updated"
    )
    reported_status: Optional[str] = Field(
        default=None,
        description=(
            "Status explicitly reported by the employee, if one was provided"
        )
    )
    blocker: Optional[str] = Field(
        default=None,
        description=(
            "Blocker explicitly reported by the employee, if one was provided"
        )
    )
    description: str = Field(
        description=(
            "Short factual description of the employee's reported work update"
        )
    )

class ReportedWorkUpdate(BaseModel):
    reported_update_id: Optional[str] = None
    work_item_id: str
    reported_status: Optional[str] = None
    blocker: Optional[str] = None
    reported_at: Optional[str] = None
    source_sync_status: Literal[ "AWAITING_SOURCE", "MATCHED", "NEEDS_REVIEW"] = "AWAITING_SOURCE"

class ShiftTeammate(BaseModel):
    employee_id: str
    name: str

class DelegationPick(BaseModel):
    work_item_id: str = Field(description="One of the shift lead's own open work items")
    employee_id: str = Field(description="One of the teammates on the same shift")
    reason: str = Field(description="Short factual reason based on the request and the provided work")

class DelegationPlan(BaseModel):
    assignments: list[DelegationPick] = Field(default_factory=list)

class DelegationContext(BaseModel):
    # The employee speaking ("me", "I"): known on every message.
    speaker: Optional[ShiftTeammate] = None
    shift_instance_id: Optional[str] = None
    shift_name: Optional[str] = None
    is_shift_lead: bool = False
    teammates: list[ShiftTeammate] = Field(default_factory=list)
    # Open work items the shift lead may assign: their own, teammates' on the shift, and unassigned.
    shift_work: list[dict] = Field(default_factory=list)
    # Proposed only: WorkWeave creates a delegation proposal that the shift lead must confirm.
    proposal: list[DelegationPick] = Field(default_factory=list)
    # The shift lead confirmed the proposal in the chat; WorkWeave performs the confirmation.
    confirm_requested: bool = False

class AssignmentChoice(BaseModel):
    work_item_id: Optional[str] = Field(default=None, description="The work item the question is about, from the provided list, or null")

class AssignmentQuestionContext(BaseModel):
    work_item_id: Optional[str] = None
    options: list[dict] = Field(default_factory=list)

class WorkCompanionState(BaseModel):
    employee: Employee
    session: CompanionSession = Field(
        default_factory=CompanionSession
    )
    work: WorkContext = Field(
        default_factory=WorkContext
    )
    employee_work_state: EmployeeWorkState = Field(
        default_factory=EmployeeWorkState
    )
    priority: PriorityContext = Field(
        default_factory=PriorityContext
    )
    response_analysis: Optional[CompanionResponseAnalysis] = None
    conversation: CompanionConversation = Field(
        default_factory=CompanionConversation
    )
    scheduling: SchedulingContext = Field(
        default_factory=SchedulingContext
    )
    delegation: DelegationContext = Field(
        default_factory=DelegationContext
    )
    assignment_question: AssignmentQuestionContext = Field(
        default_factory=AssignmentQuestionContext
    )
    # The app action the employee asked for (WorkWeave performs it).
    app_action: Optional[dict] = None

class WorkUpdateState(WorkCompanionState):
    resolved_work_item: Optional[WorkItem] = None
    update_analysis: Optional[WorkUpdateAnalysis] = None
    reported_update: Optional[ReportedWorkUpdate] = None
    source_status: Optional[str] = None
    source_sync_result: Optional[Literal["AWAITING_SOURCE", "MATCHED", "NEEDS_REVIEW"]] = None
    work_event_id: Optional[str] = None

class WorkGuidanceState(WorkCompanionState):
    resolved_work_item: Optional[WorkItem] = None
    knowledge_hierarchy: list[dict] = Field(
        default_factory=list
    )
    selected_knowledge_scope: Optional[KnowledgeScopeSelection] = None
    retrieved_knowledge: list[RetrievedKnowledgeChunk] = Field(
        default_factory=list
    )

class SchedulingState(WorkCompanionState):
    pass

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

def calculate_priority_score(item: WorkItem) -> tuple[int, str, str]:
    score = 0
    reasons = []
    now = datetime.now(timezone.utc)

    # Source priority
    priority_scores = {"CRITICAL": 40, "HIGH": 30, "MEDIUM": 20, "LOW": 10,}
    source_priority = (item.priority.upper() if item.priority else "MEDIUM")
    score += priority_scores.get(source_priority, 20)
    reasons.append(f"Source priority is {source_priority.lower()}.")

    # SLA urgency
    if item.sla_due_at:
        sla_due = datetime.fromisoformat(item.sla_due_at)
        remaining_seconds = (sla_due - now).total_seconds()

        if remaining_seconds <= 0:
            score += 60
            reasons.append("SLA is overdue.")

        elif remaining_seconds <= 3600:
            score += 50
            reasons.append("SLA is due within 1 hour.")

        elif remaining_seconds <= 7200:
            score += 40
            reasons.append("SLA is due within 2 hours.")

        elif remaining_seconds <= 14400:
            score += 25
            reasons.append( "SLA is due within 4 hours.")

    # Normal due date
    elif item.due_at:
        due_at = datetime.fromisoformat(item.due_at)
        remaining_seconds = (due_at - now).total_seconds()

        if remaining_seconds <= 0:
            score += 40
            reasons.append("Work item is overdue.")

        elif remaining_seconds <= 14400:
            score += 25
            reasons.append("Work item is due soon.")

    reported_status = (
        item.reported_status.upper()
        if item.reported_status
        else None
    )

    # Employee-reported completion awaiting source reconciliation
    if (item.source_sync_status == "AWAITING_SOURCE" and reported_status in {"COMPLETED", "RESOLVED"}):
        # Keep critically urgent source work visible.
        if score >= 80:
            score -= 15
            reasons.append("Employee reported completion, but source confirmation is still pending.")
        else:
            score -= 30
            reasons.append("Employee reported completion; source confirmation is still pending.")

        score = max(score, 0)

    # Account for reported blockers without hiding urgent work.
    if item.is_blocked:
        if item.blocker_source == "EMPLOYEE_REPORTED":
            reasons.append(
                "Employee reported a blocker; "
                "source confirmation is pending."
            )
        else:
            reasons.append(
                "Work item has a confirmed blocker."
            )

    # Translate score to urgency
    if score >= 80:
        urgency = "CRITICAL"
    elif score >= 55:
        urgency = "HIGH"
    elif score >= 30:
        urgency = "NORMAL"
    else:
        urgency = "LOW"

    return (score, urgency, " ".join(reasons))

def extract_llm_text(content) -> str:
    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        return "\n".join(
            block["text"]
            for block in content
            if isinstance(block, dict)
            and isinstance(block.get("text"), str)
        ).strip()

    raise TypeError(
        f"Unexpected LLM content type: {type(content).__name__}"
    )

# Graph
def initialize_companion(state: WorkCompanionState) -> WorkCompanionState:
    employee = state.employee
    companion_session = state.session

    if companion_session.work_session_id is None:
        raise ValueError(
            "work_session_id is required for the "
            "current existing-session test."
        )

    query = text("""
        SELECT
            work_session_id,
            shift_instance_id,
            started_at,
            status

        FROM workweave.work_sessions

        WHERE organization_id = :organization_id
          AND workspace_id = :workspace_id
          AND employee_id = :employee_id
          AND work_session_id = :work_session_id
          AND status = 'ACTIVE'
    """)

    with SessionLocal() as db_session:
        result = db_session.execute(
            query,
            {
                "organization_id": employee.organization_id,
                "workspace_id": employee.workspace_id,
                "employee_id": employee.employee_id,
                "work_session_id": (
                    companion_session.work_session_id
                ),
            }
        )

        session_data = result.mappings().first()

    if session_data is None:
        raise ValueError(
            "No valid active Work Companion session"
        )

    state.session.work_session_id = str(
        session_data["work_session_id"]
    )

    state.session.shift_instance_id = (
        str(session_data["shift_instance_id"])
        if session_data["shift_instance_id"] is not None
        else None
    )

    state.session.status = session_data["status"]

    state.session.started_at = (
        session_data["started_at"].isoformat()
        if session_data["started_at"] is not None
        else None
    )

    return state

def reconcile_pending_status_reports(state: WorkCompanionState) -> WorkCompanionState:
    query = text("""
        UPDATE workweave.work_item_reported_updates AS r
        SET
            source_sync_status = 'MATCHED',
            updated_at = CURRENT_TIMESTAMP,
            revision = r.revision + 1
        FROM workweave.work_items AS wi
        WHERE r.organization_id = :organization_id
          AND r.workspace_id = :workspace_id
          AND r.employee_id = :employee_id
          AND r.organization_id = wi.organization_id
          AND r.workspace_id = wi.workspace_id
          AND r.work_item_id = wi.work_item_id
          AND r.source_sync_status = 'AWAITING_SOURCE'
          AND r.reported_status IS NOT NULL
          AND UPPER(TRIM(r.reported_status)) =
              UPPER(TRIM(wi.status))
    """)

    with SessionLocal.begin() as session:
        session.execute(
            query,
            {
                "organization_id": state.employee.organization_id,
                "workspace_id": state.employee.workspace_id,
                "employee_id": state.employee.employee_id,
            },
        )

    return state

def load_work_context(state: WorkCompanionState) -> WorkCompanionState:
    query = text("""
        SELECT
            wi.work_item_id,
            wi.work_item_type,
            wi.external_id,
            wi.title,
            wi.description,
            wi.priority,
            wi.status,
            wi.due_at,
            wi.sla_due_at,
            wia.assigned_at,
            latest_blocker.blocker AS reported_blocker,
            latest_blocker.source_sync_status AS blocker_sync_status,
            latest_report.reported_status AS reported_status,
            latest_report.source_sync_status AS source_sync_status,
            latest_blocker.update_type AS blocker_update_type
        FROM workweave.work_item_assignments AS wia
        JOIN workweave.work_items AS wi
            ON wi.organization_id = wia.organization_id
            AND wi.workspace_id = wia.workspace_id
            AND wi.work_item_id = wia.work_item_id
        LEFT JOIN LATERAL (
            SELECT
                wiru.reported_status,
                wiru.source_sync_status
            FROM workweave.work_item_reported_updates AS wiru
            WHERE wiru.organization_id = wi.organization_id
                AND wiru.workspace_id = wi.workspace_id
                AND wiru.work_item_id = wi.work_item_id
                AND wiru.employee_id = wia.employee_id
                AND wiru.assignment_id = wia.assignment_id
                AND wiru.source_sync_status = 'AWAITING_SOURCE'
                AND wiru.reported_status IS NOT NULL
            ORDER BY wiru.reported_at DESC
            LIMIT 1
            ) AS latest_report ON TRUE
        LEFT JOIN LATERAL (
            SELECT
                wiru.blocker,
                wiru.update_type,
                wiru.source_sync_status
            FROM workweave.work_item_reported_updates AS wiru
            WHERE wiru.organization_id = wi.organization_id
                AND wiru.workspace_id = wi.workspace_id
                AND wiru.work_item_id = wi.work_item_id
                AND wiru.employee_id = wia.employee_id
                AND wiru.assignment_id = wia.assignment_id
                AND wiru.update_type IN ('BLOCKER', 'BLOCKER_RESOLVED')
            ORDER BY wiru.reported_at DESC, wiru.reported_update_id DESC
            LIMIT 1
        ) AS latest_blocker ON TRUE
        WHERE wia.organization_id = :organization_id
          AND wia.workspace_id = :workspace_id
          AND wia.employee_id = :employee_id
          AND wia.status IN ('ASSIGNED', 'ACCEPTED', 'IN_PROGRESS')
          AND wi.status NOT IN ('COMPLETED', 'CANCELLED')
        ORDER BY
            COALESCE(wi.sla_due_at, wi.due_at) ASC NULLS LAST,
            wia.assigned_at ASC
    """)

    params = {
        "organization_id": state.employee.organization_id,
        "workspace_id": state.employee.workspace_id,
        "employee_id": state.employee.employee_id,
    }

    with SessionLocal() as session:
        result = session.execute(
            query,
            params,
        )

        rows = result.mappings().all()

    active_items = []

    for row in rows:
        reported_blocker = (
            row["reported_blocker"]
            if row["blocker_update_type"] == "BLOCKER"
            else None
        )
        item = WorkItem(
            work_item_id=str(row["work_item_id"]),
            work_type=row["work_item_type"],
            external_id=row["external_id"],
            title=row["title"],
            description=row["description"],
            status=row["status"],
            priority=row["priority"],
            due_at=(
                row["due_at"].isoformat()
                if row["due_at"] is not None
                else None
            ),
            sla_due_at=(
                row["sla_due_at"].isoformat()
                if row["sla_due_at"] is not None
                else None
            ),
            reported_status=row["reported_status"],
            source_sync_status=row["source_sync_status"],
            is_blocked=bool(reported_blocker),
            blocker=reported_blocker,
            blocker_source=(
                "EMPLOYEE_REPORTED"
                if reported_blocker
                else None
            )
        )

        active_items.append(item)

    state.work.active_items = active_items
    state.work.blocked_items = [
        item for item in active_items
        if item.is_blocked
    ]

    return state

def load_employee_work_state(state: WorkCompanionState) -> WorkCompanionState:
    query = text("""
        SELECT
            work_context_key,
            workload_state,
            momentum_state,
            assistance_need,
            active_work_count,
            blocked_work_count,
            overdue_work_count
        FROM workweave.employee_work_state
        WHERE organization_id = :organization_id
          AND workspace_id = :workspace_id
          AND employee_id = :employee_id
          AND (shift_instance_id = :shift_instance_id
              OR (:shift_instance_id IS NULL
                  AND shift_instance_id IS NULL)
          )
        ORDER BY updated_at DESC
        LIMIT 1
    """)

    params = {
        "organization_id": state.employee.organization_id,
        "workspace_id": state.employee.workspace_id,
        "employee_id": state.employee.employee_id,
        "shift_instance_id": state.session.shift_instance_id,
    }

    with SessionLocal() as session:
        result = session.execute(
            query,
            params,
        )

        row = result.mappings().first()

    if row is None:
        state.employee_work_state = EmployeeWorkState()
        return state

    state.employee_work_state = EmployeeWorkState(
        work_context_key=row["work_context_key"],
        workload_state=row["workload_state"],
        momentum_state=row["momentum_state"],
        assistance_need=row["assistance_need"],
        active_work_count=row["active_work_count"],
        blocked_work_count=row["blocked_work_count"],
        overdue_work_count=row["overdue_work_count"],
    )

    return state

def determine_priorities(state: WorkCompanionState) -> WorkCompanionState:
    scored_items = []

    for item in state.work.active_items:
        score, urgency, reason = (calculate_priority_score(item))
        scored_items.append((item, score, urgency, reason,))

    scored_items.sort(key=lambda result: result[1], reverse=True)
    prioritized_items = []

    for rank, (item, score, urgency, reason) in enumerate(scored_items, start=1):
        prioritized_items.append(
            PriorityItem(
                work_item_id=item.work_item_id,
                rank=rank,
                urgency=urgency,
                reason=reason,
            )
        )

    state.priority.prioritized_items = (prioritized_items)
    state.priority.top_priority_id = (prioritized_items[0].work_item_id if prioritized_items else None)

    return state

def generate_opening_brief(state: WorkCompanionState) -> WorkCompanionState:
    work_by_id = {item.work_item_id: item for item in state.work.active_items}
    priority_context = []

    for priority in state.priority.prioritized_items:
        item = work_by_id.get(priority.work_item_id)

        if item is None:
            continue

        priority_context.append({
            "work_item_id": item.work_item_id,
            "work_type": item.work_type,
            "title": item.title,
            "status": item.status,
            "source_priority": item.priority,
            "due_at": item.due_at,
            "sla_due_at": item.sla_due_at,
            "rank": priority.rank,
            "urgency": priority.urgency,
            "priority_reason": priority.reason,
        })

    prompt = f"""
    You are the WorkWeave AI Work Companion.

    You are starting a work session with an employee.

    Current prioritized work:
    {json.dumps(priority_context, indent=2)}

    Current employee work state:
    {state.employee_work_state.model_dump_json(indent=2)}

    Your task is to give the employee a short, useful opening
    brief about their current work.

    Behavior:
    - Be proactive. The employee should not need to tell you what
      work they have.
    - Briefly summarize the employee's current workload.
    - Mention the most important work item first.
    - Explain why it deserves attention using the provided priority
      information.
    - Mention other relevant work only when useful.
    - If something is approaching its SLA or deadline, make that clear.
    - Do not change or invent the priority order.
    - Do not invent tasks, deadlines, statuses, blockers, or SLAs.
    - Do not expose internal priority scores or system logic.
    - Do not mention database fields or internal state names.
    - Keep the response concise and natural.
    - Speak like a helpful work companion, not a manager or
      productivity coach.
    - Do not overwhelm the employee with every available detail.

    Employee-state guidance:
    - Use workload, momentum, or assistance information only when
      it is actually present.
    - Use it to adjust how much support you offer, not to make
      judgments about the employee.
    - Do not infer emotions, personality, motivation, or ability.

    Ending:
    - End with exactly one short question asking whether the
      employee wants to start with the highest-priority item.
    - Refer to that item naturally by its title or recognizable
      work reference.

    Return only the message that should be shown to the employee.
    """

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
    )

    if not response.text:
        raise ValueError(
            "Gemini did not generate an opening work brief."
        )

    state.conversation.user_message = None
    state.conversation.input_kind = None
    state.conversation.assistant_message = (response.text.strip())
    state.conversation.is_opening_brief = True

    return state

def remember_turn(state: WorkCompanionState, role: str, text: str | None) -> None:
    history = state.conversation.history

    if text and not (history and history[-1] == {"role": role, "text": text}):
        history.append({"role": role, "text": text})
        del history[:-12]

def wait_for_user(state: WorkCompanionState) -> WorkCompanionState:
    remember_turn(state, "assistant", state.conversation.assistant_message)

    user_response = interrupt({
        "message": state.conversation.assistant_message
    })

    state.conversation.user_message = (
        user_response["message"]
        if isinstance(user_response, dict)
        else str(user_response)
    )
    remember_turn(state, "employee", state.conversation.user_message)

    return state

def analyze_user_response(state: WorkCompanionState) -> WorkCompanionState:
    # Assignments can change between messages (a shift lead reassigns work): reload first.
    state = load_work_context(state)
    # A shift lead may also refer to teammates' work on the shift (empty for everyone else).
    state = load_shift_team(state)
    state = load_shift_work(state)
    user_message = state.conversation.user_message

    if not user_message:
        raise ValueError(
            "User message is required for response analysis."
        )

    work_context = [
        {
            "work_item_id": item.work_item_id,
            "work_type": item.work_type,
            "reference": item.external_id,
            "title": item.title,
            "status": item.status,
            "priority": item.priority,
            "due_at": item.due_at,
            "sla_due_at": item.sla_due_at,
            "blocker": item.blocker
        }
        for item in state.work.active_items
    ]
    own_ids = {item.work_item_id for item in state.work.active_items}
    work_context += [
        {key: item[key] for key in ("work_item_id", "reference", "title", "assigned_to")}
        for item in state.delegation.shift_work
        if item["work_item_id"] not in own_ids
    ]

    prompt = f"""
    You are analyzing an employee's message to the
    WorkWeave AI Work Companion.

    Current work:
    {json.dumps(work_context, indent=2)}

    The employee speaking ("me", "I", "myself" mean this person):
    {state.delegation.speaker.name if state.delegation.speaker else "unknown"}{", lead of the " + str(state.delegation.shift_name) + " shift in progress" if state.delegation.is_shift_lead else ""}

    Current highest-priority work item:
    {state.priority.top_priority_id}

    The AI previously said:
    {state.conversation.assistant_message}

    The employee responded:
    {user_message}

    Determine the employee's work intent using only information
    supported by their message and the current work context.

    Intent definitions:
    - START_WORK: the employee wants to begin or continue working
      on a work item.
    - WORK_OVERVIEW: The employee asks about assigned work,
      active tickets, pending tasks, priorities, or deadlines
      from the WorkWeave work context.
      Do not classify requests about existing Google Calendar
      events or meetings as WORK_OVERVIEW.
    - WORK_QUESTION: the employee asks for information, instructions,
      or guidance about their work.
    - STATUS_UPDATE: the employee reports that the status or progress
      of a work item has changed.
    - BLOCKER: the employee reports something preventing or delaying
      progress.
    - BLOCKER_RESOLVED: the employee reports that a previously
      reported blocker has been cleared.
    - PRIORITY_CHANGE: the employee wants to work on something other
      than the currently recommended priority or asks to reconsider
      the work order.
    - SCHEDULE_REQUEST: the employee asks about when work should be
      done or wants help planning their work.
    - CALENDAR_INQUIRY: The employee asks to view, retrieve,
      summarize, or check existing Google Calendar events,
      meetings, appointments, or scheduled activities.
        Examples:
        - "What's on my calendar tomorrow?"
        - "Do I have meetings today?"
        - "Show my calendar events this week."
        - "What's my next meeting?"
        - "What appointments do I have on Friday?"
        Calendar inquiries are different from WORK_OVERVIEW.
        WORK_OVERVIEW refers to assigned work items from
        WorkWeave's work context.
        A calendar inquiry does not request the creation
        of new calendar events.
    - DELEGATE_WORK: the employee asks to assign, hand over, or
      reassign their own work items to a teammate (for example
      "give the Machine #22 ticket to Sam" or "split my tickets
      between the team" or "reassign ticket 910 to Jamie"). This is not
      the same as PRIORITY_CHANGE.
    - CONFIRM_DELEGATION: right after the AI prepared a delegation
      proposal, the employee confirms it (for example "confirm",
      "yes, assign it", "go ahead").
    - ASSIGNMENT_QUESTION: the employee asks why a work item was
      assigned to them or to a teammate, or who it was assigned to and
      on what basis (for example "why did I get the Machine #22 ticket?"
      or "why is Sam on #910?").
    - APP_ACTION: the employee asks the app to do one of these:
      show a view ("show only blocked tickets", "show my updates",
      "back to my briefing"); open a work item in the ticket system;
      accept a work item assigned to them ("I'll take 910");
      change or cancel the delegation proposal just prepared ("give
      it to Sam instead", "cancel that proposal"); save or submit a
      knowledge note ("save this as a note: ...", "submit my note");
      or change how replies are read ("stop reading", "speak slower",
      "turn off read aloud").
    - WORK_DATA_QUESTION: the employee asks a factual question about
      the state of work: statuses, who has what, reports and whether
      the ticket system confirmed them, recent ticket system changes,
      what is overdue or unassigned, who is on the shift.
      Asking how to do the work is WORK_QUESTION instead.
    - PAUSE_REQUEST: the employee wants to stop or pause the current
      work interaction.
    - OTHER: none of the above clearly applies.

    Recommended actions:
    - START_WORK -> FOCUS
    - WORK_OVERVIEW -> OVERVIEW
    - WORK_QUESTION -> GUIDE
    - STATUS_UPDATE -> UPDATE_STATUS
    - BLOCKER -> HANDLE_BLOCKER
    - BLOCKER_RESOLVED -> HANDLE_BLOCKER
    - PRIORITY_CHANGE -> REPRIORITIZE
    - SCHEDULE_REQUEST -> SCHEDULE
    - CALENDAR_INQUIRY -> CALENDAR
    - DELEGATE_WORK -> DELEGATE
    - CONFIRM_DELEGATION -> CONFIRM_DELEGATION
    - ASSIGNMENT_QUESTION -> EXPLAIN_ASSIGNMENT
    - APP_ACTION -> APP_ACTION
    - WORK_DATA_QUESTION -> ANSWER_WORK_DATA
    - PAUSE_REQUEST -> PAUSE
    - If the employee's meaning or referenced work item is unclear,
      use CLARIFY.

    Work-item resolution:
    - Set referenced_work_item_id only when the employee clearly
      refers to one of the provided work items.
    - The employee may refer to an item by ID, its reference or
      ticket number (for example "Ticket #910", "#910" or "910"),
      title, or an unambiguous natural reference such as "the incident."
    - If the previous AI message explicitly asked about one specific
      work item and the employee replies naturally with something
      like "yes", "let's do it", or "start that", that item may be
      resolved from the conversation context.
    - Never invent a work_item_id.
    - If multiple items could reasonably match the reference,
      leave referenced_work_item_id null and recommend CLARIFY.
    - Asking to view today's assigned tasks is WORK_OVERVIEW,
      not SCHEDULE_REQUEST.
    - WORK_OVERVIEW does not require a referenced_work_item_id.
    - For DELEGATE_WORK and ASSIGNMENT_QUESTION, the employee may
      name a work item that is not in the current work list (a
      teammate's or an unassigned item). Still use DELEGATE or
      EXPLAIN_ASSIGNMENT, not CLARIFY, and leave
      referenced_work_item_id null; the next step finds the item.
    - SCHEDULE_REQUEST means planning or changing when work
      will be performed.

    Recent conversation (oldest first):
    {json.dumps(state.conversation.history[-8:], indent=2)}

    Work item in focus:
    {state.session.focused_work_item_id}

    Follow-ups:
    - Use the recent conversation for follow-ups such as "that one",
      "do the same for 952", "and why?" or "no, Sam instead".

    Important:
    - Analyze observable work intent only.
    - Do not infer emotions, motivation, personality, productivity,
      competence, or mental state.
    - Do not perform the requested action yet.
    """

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config={
            "response_mime_type": "application/json",
            "response_json_schema": (
                CompanionResponseAnalysis.model_json_schema()
            ),
        },
    )

    if not response.text:
        raise ValueError(
            "Gemini did not return Companion response analysis."
        )

    analysis = CompanionResponseAnalysis.model_validate_json(
        response.text
    )

    # Validate Gemini's referenced ID against actual loaded work.
    if analysis.referenced_work_item_id is not None:
        valid_ids = {
            item.work_item_id
            for item in state.work.active_items
        } | {item["work_item_id"] for item in state.delegation.shift_work}

        if analysis.referenced_work_item_id not in valid_ids:
            analysis.referenced_work_item_id = None
            analysis.recommended_action = "CLARIFY"

    state.response_analysis = analysis

    return state

def focus_work(state: WorkCompanionState) -> WorkCompanionState:
    analysis = state.response_analysis

    if (analysis is None or analysis.referenced_work_item_id is None):
        state.conversation.assistant_message = (
            "Which work item would you like to start with?"
        )
        return state

    work_item = next(
        (
            item
            for item in state.work.active_items
            if item.work_item_id == analysis.referenced_work_item_id
        ),
        None,
    )

    if work_item is None:
        # A shift lead opening a teammate's work item on the shift.
        shift_item = next(
            (
                item
                for item in state.delegation.shift_work
                if item["work_item_id"] == analysis.referenced_work_item_id
            ),
            None,
        )

        if shift_item is not None:
            state.session.focused_work_item_id = shift_item["work_item_id"]
            state.conversation.assistant_message = (
                f"Here's {shift_item['reference'] or shift_item['title']}: {shift_item['title']}, "
                f"assigned to {shift_item['assigned_to']}. "
                "You can reassign it or ask why it went to them."
            )
            state.conversation.is_opening_brief = False
            return state

        mine = ", ".join(i.external_id or i.title for i in state.work.active_items[:5])
        state.conversation.assistant_message = (
            "I couldn't match that to a ticket you can open here. "
            + (f"Your current tickets are {mine}. " if mine else "You have no tickets assigned right now. ")
            + "Which one do you mean? If it's a teammate's ticket, your shift lead can open it."
        )
        return state

    state.session.focused_work_item_id = (work_item.work_item_id)

    state.conversation.assistant_message = (
        f"Let's start with {work_item.title}. "
        "What would you like help with?"
    )

    state.conversation.is_opening_brief = False

    return state

# SUBGRAPH - WORK GUIDANCE
def resolve_work_item(state: WorkGuidanceState) -> WorkGuidanceState:
    work_item_id = None

    if (state.response_analysis is not None and state.response_analysis.referenced_work_item_id is not None):
        work_item_id = (
            state.response_analysis.referenced_work_item_id
        )

    elif state.session.focused_work_item_id is not None:
        work_item_id = (
            state.session.focused_work_item_id
        )

    if work_item_id is None:
        return state

    work_item = next(
        (
            item
            for item in state.work.active_items
            if item.work_item_id == work_item_id
        ),
        None,
    )

    if work_item is None:
        return state

    state.resolved_work_item = work_item

    return state

def load_knowledge_hierarchy(state: WorkGuidanceState) -> WorkGuidanceState:
    query = text("""
        SELECT DISTINCT
            d.document_id,
            d.document_code,
            d.title,
            COALESCE(s.topic_heading, c.section_path->>0) AS topic,
            COALESCE(s.subtopic_heading, c.heading) AS subtopic
        FROM workweave.knowledge_documents AS d
        JOIN workweave.knowledge_document_versions AS v
            ON v.organization_id = d.organization_id
            AND v.workspace_id = d.workspace_id
            AND v.document_id = d.document_id
        JOIN workweave.knowledge_chunks AS c
            ON c.organization_id = v.organization_id
            AND c.workspace_id = v.workspace_id
            AND c.document_version_id = v.document_version_id
        LEFT JOIN workweave.knowledge_sections AS s
            ON s.organization_id = c.organization_id
            AND s.workspace_id = c.workspace_id
            AND s.document_version_id = c.document_version_id
            AND s.section_id = c.source_section_id
        JOIN workweave.source_records AS r
            ON r.organization_id = c.organization_id
            AND r.workspace_id = c.workspace_id
            AND r.source_id = c.source_id
            AND r.source_id = v.source_id
        WHERE d.organization_id = :organization_id
          AND d.workspace_id = :workspace_id
          AND d.current_version_id = v.document_version_id
          AND v.approval_status = 'APPROVED'
          AND v.temporal_status = 'CURRENT'
          AND r.revoked_at IS NULL
        ORDER BY
            d.title,
            topic,
            subtopic
    """)

    params = {
        "organization_id": (
            state.employee.organization_id
        ),
        "workspace_id": (
            state.employee.workspace_id
        ),
    }

    with SessionLocal() as session:
        result = session.execute(
            query,
            params,
        )

        rows = result.mappings().all()

    state.knowledge_hierarchy = [
        {
            "document_id": str(row["document_id"]),
            "document_code": row["document_code"],
            "title": row["title"],
            "topic": row["topic"],
            "subtopic": row["subtopic"],
        }
        for row in rows
    ]

    return state

def identify_knowledge_scope(state: WorkGuidanceState) -> WorkGuidanceState:
    if state.resolved_work_item is None:
        return state

    if not state.knowledge_hierarchy:
        return state

    work_item = state.resolved_work_item

    prompt = f"""
    You are routing an employee's work question to the correct
    organizational knowledge scope.

    Current work item:

    Type:
    {work_item.work_type}

    Title:
    {work_item.title}

    Description:
    {work_item.description}

    Employee question:
    {state.conversation.user_message}

    Available knowledge scopes:
    {json.dumps(state.knowledge_hierarchy, indent=2)}

    Select the single knowledge scope that best matches the
    employee's current work item and question.

    Important:
    - You may only select a scope from the provided list.
    - Do not create a document, title, topic, or subtopic.
    - Consider the work item context, not only the employee's
      question.
    - Prefer the most specific matching subtopic when one clearly
      applies.
    - If none of the available scopes are relevant, return null
      values.
    """

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config={
            "response_mime_type": "application/json",
            "response_json_schema": (
                KnowledgeScopeSelection.model_json_schema()
            ),
        },
    )

    if not response.text:
        raise ValueError(
            "Gemini did not return a knowledge scope."
        )

    selection = (
        KnowledgeScopeSelection.model_validate_json(
            response.text
        )
    )

    state.selected_knowledge_scope = selection

    return state

def build_work_retrieval_query(state: WorkGuidanceState) -> str:
    item = state.resolved_work_item

    if item is None:
        return ""

    user_question = (state.conversation.user_message or "")
    parts = [f"Work type: {item.work_type}", f"Work item: {item.title}"]

    if item.description:
        parts.append(f"Work description: {item.description}")

    parts.append(f"Employee question: {user_question}")

    return "\n".join(parts)

def retrieve_relevant_chunks(state: WorkGuidanceState) -> WorkGuidanceState:
    scope = state.selected_knowledge_scope

    if (state.resolved_work_item is None or scope is None or scope.document_id is None):
        return state

    retrieval_query = build_work_retrieval_query(state)
    query_embedding = embed_query(retrieval_query)

    query = text("""
        SELECT
            c.chunk_id,
            d.document_id,
            d.document_code,
            d.title,
            s.topic_heading AS topic,
            s.subtopic_heading AS subtopic,
            c.content,
            1 - (c.embedding <=> CAST(:query_embedding AS vector)
            ) AS similarity
        FROM workweave.knowledge_documents AS d
        JOIN workweave.knowledge_document_versions AS v
            ON v.organization_id = d.organization_id
            AND v.workspace_id = d.workspace_id
            AND v.document_id = d.document_id
        JOIN workweave.knowledge_chunks AS c
            ON c.organization_id = v.organization_id
            AND c.workspace_id = v.workspace_id
            AND c.document_version_id = v.document_version_id
        LEFT JOIN workweave.knowledge_sections AS s
            ON s.organization_id = c.organization_id
            AND s.workspace_id = c.workspace_id
            AND s.document_version_id = c.document_version_id
            AND s.section_id = c.source_section_id
        JOIN workweave.source_records AS r
            ON r.organization_id = c.organization_id
            AND r.workspace_id = c.workspace_id
            AND r.source_id = c.source_id
            AND r.source_id = v.source_id
        WHERE d.organization_id = :organization_id
          AND d.workspace_id = :workspace_id
          AND d.document_id = :document_id
          AND d.current_version_id = v.document_version_id
          AND v.approval_status = 'APPROVED'
          AND v.temporal_status = 'CURRENT'
          AND r.revoked_at IS NULL
          AND c.embedding IS NOT NULL
          AND (CAST(:topic AS text) IS NULL OR s.topic_heading = CAST(:topic AS text))
          AND (CAST(:subtopic AS text) IS NULL OR s.subtopic_heading = CAST(:subtopic AS text))
        ORDER BY c.embedding <=> CAST(:query_embedding AS vector)
        LIMIT 5
    """)

    params = {
        "organization_id": (
            state.employee.organization_id
        ),
        "workspace_id": (
            state.employee.workspace_id
        ),
        "document_id": scope.document_id,
        "topic": scope.topic,
        "subtopic": scope.subtopic,
        "query_embedding": query_embedding,
    }

    with SessionLocal() as session:
        result = session.execute(query, params)
        rows = result.mappings().all()

    state.retrieved_knowledge = [
        RetrievedKnowledgeChunk(
            chunk_id=str(row["chunk_id"]),
            document_id=str(row["document_id"]),
            document_code=row["document_code"],
            title=row["title"],
            topic=row["topic"],
            subtopic=row["subtopic"],
            content=row["content"],
            similarity=float(row["similarity"]),
        )
        for row in rows
    ]

    return state

def generate_work_guidance(state: WorkGuidanceState) -> WorkGuidanceState:
    work_item = state.resolved_work_item

    if work_item is None:
        state.conversation.assistant_message = (
            "Which work item would you like help with?"
        )
        return state

    if not state.retrieved_knowledge:
        state.conversation.assistant_message = (
            f"I searched the approved procedures for {work_item.external_id or work_item.title} and found nothing that answers this. "
            "Could you say which step or part you need help with? "
            "If it isn't covered by an approved procedure yet, your shift lead can confirm what to do."
        )
        return state

    knowledge_context = "\n\n".join(
        (
            f"Source: {chunk.document_code} | "
            f"{chunk.title}\n"
            f"Topic: {chunk.topic}\n"
            f"Subtopic: {chunk.subtopic}\n"
            f"Content:\n{chunk.content}"
        )
        for chunk in state.retrieved_knowledge
    )

    prompt = f"""
    You are the WorkWeave AI Work Companion.

    Your role is to help an employee perform their current work
    using approved organizational knowledge.

    CURRENT WORK ITEM

    Type:
    {work_item.work_type}

    Title:
    {work_item.title}

    Description:
    {work_item.description}

    Status:
    {work_item.status}

    EMPLOYEE QUESTION

    {state.conversation.user_message}

    APPROVED ORGANIZATIONAL KNOWLEDGE

    {knowledge_context}

    INSTRUCTIONS

    Answer the employee's question using the approved
    organizational knowledge provided above.

    Relate the knowledge to the employee's current work item.

    When the knowledge provides specific procedures or steps,
    explain them clearly and practically.

    Do not invent:
    - procedures
    - systems
    - tools
    - policies
    - commands
    - escalation paths
    - deadlines
    - people or teams

    Do not claim that an action has been performed.

    Do not change the work item's status.

    If the provided knowledge does not contain enough information
    to answer the employee's question, clearly say that the
    available approved knowledge does not provide enough
    information.

    Do not fill missing information using assumptions.

    Keep the response concise and focused on helping the employee
    with the current work item.

    Return only the response that should be shown to the employee.
    """

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
    )

    if not response.text:
        raise ValueError(
            "Gemini did not generate work guidance."
        )

    state.conversation.assistant_message = (response.text.strip())
    state.conversation.is_opening_brief = False

    return state

# Work Guidance Subgraph
work_guidance_builder = StateGraph(WorkGuidanceState)
work_guidance_builder.add_node("resolve_work_item", resolve_work_item)
work_guidance_builder.add_node("load_knowledge_hierarchy", load_knowledge_hierarchy)
work_guidance_builder.add_node("identify_knowledge_scope", identify_knowledge_scope)
work_guidance_builder.add_node("retrieve_relevant_chunks", retrieve_relevant_chunks)
work_guidance_builder.add_node("generate_work_guidance", generate_work_guidance)

work_guidance_builder.add_edge(START, "resolve_work_item")
work_guidance_builder.add_edge("resolve_work_item", "load_knowledge_hierarchy")
work_guidance_builder.add_edge("load_knowledge_hierarchy", "identify_knowledge_scope")
work_guidance_builder.add_edge("identify_knowledge_scope", "retrieve_relevant_chunks")
work_guidance_builder.add_edge("retrieve_relevant_chunks", "generate_work_guidance")
work_guidance_builder.add_edge("generate_work_guidance", END)

work_guidance_graph = work_guidance_builder.compile()

def clarify_request(state: WorkCompanionState) -> WorkCompanionState:
    state.conversation.assistant_message = "Could you clarify what you'd like help with or which work item you're referring to?"
    state.conversation.is_opening_brief = False

    return state

def pause_companion(state: WorkCompanionState) -> WorkCompanionState:
    state.conversation.assistant_message = "Got it. I'll pause here. You can continue when you're ready."
    state.conversation.is_opening_brief = False

    return state

# SUBGRAPH - WORK UPDATE
def resolve_update_work_item(state: WorkUpdateState) -> WorkUpdateState:
    analysis = state.response_analysis

    work_item_id = (
        analysis.referenced_work_item_id
        if analysis and analysis.referenced_work_item_id
        else state.session.focused_work_item_id
    )

    if not work_item_id:
        return state

    state.resolved_work_item = next(
        (
            item
            for item in state.work.active_items
            if item.work_item_id == work_item_id
        ),
        None,
    )

    return state

def interpret_work_update(state: WorkUpdateState) -> WorkUpdateState:
    work_item = state.resolved_work_item
    user_message = state.conversation.user_message

    if work_item is None or not user_message:
        return state

    prompt = f"""
    You are interpreting an employee-reported work update
    for the WorkWeave AI Work Companion.

    CURRENT WORK ITEM

    ID:
    {work_item.work_item_id}

    Type:
    {work_item.work_type}

    Title:
    {work_item.title}

    Current source-system status:
    {work_item.status}

    Current reported blocker:
    {work_item.blocker}

    EMPLOYEE MESSAGE

    {user_message}

    Determine exactly what update the employee is reporting.

    Rules:

    - STATUS_CHANGE means the employee explicitly reports that
      the work item's status has changed, such as completing,
      resolving, reopening, or otherwise changing its state.

    - BLOCKER means the employee explicitly reports something
      preventing or delaying progress.

    - PROGRESS_UPDATE means the employee reports progress but
      does not clearly report a status change or blocker.

    - reported_status must describe only a status explicitly
      supported by the employee's message.

    - Do not copy the current source-system status into
      reported_status unless the employee actually reports it.

    - blocker must contain only a blocker explicitly reported
      by the employee.

    - Do not assume that the employee's reported status is
      already reflected in the source system.

    - Do not decide whether the employee's report is verified.

    - Do not modify or reinterpret the source-system status.

    - work_item_id must be the provided current work item ID.

    - description should be a short factual summary of what
      the employee reported.

    - BLOCKER_RESOLVED means the employee explicitly reports
     that a previously reported blocker is no longer preventing progress.

    - Examples: "Finance approved it", "I'm no longer blocked",
     "The access issue has been fixed."

    - For BLOCKER_RESOLVED:
        - reported_status should normally be null.
        - blocker should be null.
        - description must summarize the resolution.
        - Do not invent a source-system status change.

    - If the employee reports a new blocker, use BLOCKER instead.

    BLOCKER HANDLING RULES:

    - If the employee reports something preventing or delaying
    progress, classify the update as BLOCKER.

    - Extract the blocker exactly as supported by the message.

    - Do not invent a blocker or assume its severity.

    - Do not change reported_status to BLOCKED unless the
    employee explicitly reports a status change.

    - For a BLOCKER update, reported_status should normally
    be null.

    - The blocker is an employee-reported condition, not a
    confirmed source-system status.

    - Do not assume the blocker has been recorded in the
    external ticketing system.

    Do not invent information.
    """

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config={
            "response_mime_type": "application/json",
            "response_json_schema": (
                WorkUpdateAnalysis.model_json_schema()
            ),
        },
    )

    if not response.text:
        raise ValueError(
            "Gemini did not return work update analysis."
        )

    update_analysis = WorkUpdateAnalysis.model_validate_json(
        response.text
    )

    # Gemini must not be allowed to change the resolved work item.
    if update_analysis.work_item_id != work_item.work_item_id:
        update_analysis.work_item_id = work_item.work_item_id

    state.update_analysis = update_analysis

    return state

def normalize_reported_status(state: WorkUpdateState) -> WorkUpdateState:
    analysis = state.update_analysis

    if analysis is None:
        return state

    if analysis.update_type != "STATUS_CHANGE":
        return state

    if analysis.reported_status is None:
        return state

    raw_status = analysis.reported_status.strip().upper()

    status_map = {
        "DONE": "COMPLETED",
        "COMPLETED": "COMPLETED",
        "FINISHED": "COMPLETED",
        "FIXED": "RESOLVED",
        "RESOLVED": "RESOLVED",
        "REOPENED": "ACTIVE",
        "OPEN": "ACTIVE",
        "ACTIVE": "ACTIVE",
    }

    normalized_status = status_map.get(raw_status)

    if normalized_status is None:
        analysis.reported_status = None
        return state

    analysis.reported_status = normalized_status

    return state

def persist_reported_update(state: WorkUpdateState) -> WorkUpdateState:
    work_item = state.resolved_work_item
    analysis = state.update_analysis

    if work_item is None or analysis is None:
        return state

    # A status-change report must have a usable reported status.
    if (analysis.update_type == "STATUS_CHANGE" and analysis.reported_status is None):
        return state

    if analysis.update_type == "BLOCKER" and not (analysis.blocker and analysis.blocker.strip()):
        return state

    if analysis.update_type == "BLOCKER_RESOLVED" and not work_item.is_blocked:
        return state

    assignment_query = text("""
        SELECT assignment_id
        FROM workweave.work_item_assignments
        WHERE organization_id = :organization_id
          AND workspace_id = :workspace_id
          AND work_item_id = :work_item_id
          AND employee_id = :employee_id
          AND status IN ('ASSIGNED', 'ACCEPTED', 'IN_PROGRESS')
        ORDER BY assigned_at DESC
        LIMIT 1
    """)

    insert_query = text("""
        INSERT INTO workweave.work_item_reported_updates (
            organization_id,
            workspace_id,
            assignment_id,
            work_item_id,
            employee_id,
            work_session_id,
            reported_status,
            blocker,
            description,
            source_status_at_report,
            source_sync_status,
            update_type
        )
        VALUES (
            :organization_id,
            :workspace_id,
            :assignment_id,
            :work_item_id,
            :employee_id,
            :work_session_id,
            :reported_status,
            :blocker,
            :description,
            :source_status_at_report,
            'AWAITING_SOURCE',
            :update_type
        )
        RETURNING
            reported_update_id,
            reported_at
    """)

    params = {
        "organization_id": state.employee.organization_id,
        "workspace_id": state.employee.workspace_id,
        "work_item_id": work_item.work_item_id,
        "employee_id": state.employee.employee_id,
        "update_type": analysis.update_type
    }

    with SessionLocal.begin() as session:
        assignment = session.execute(
            assignment_query,
            params,
        ).mappings().first()

        if assignment is None:
            raise ValueError(
                "No active assignment found for this work item."
            )

        result = session.execute(
            insert_query,
            {
                **params,
                "assignment_id": str(
                    assignment["assignment_id"]
                ),
                "work_session_id": (
                    state.session.work_session_id
                ),
                "reported_status": (
                    analysis.reported_status
                ),
                "blocker": analysis.blocker,
                "description": analysis.description,
                "source_status_at_report": (
                    work_item.status
                ),
            },
        ).mappings().first()

    if result is None:
        raise ValueError(
            "Reported work update was not persisted."
        )

    state.reported_update = ReportedWorkUpdate(
        reported_update_id=str(result["reported_update_id"]),
        work_item_id=work_item.work_item_id,
        reported_status=analysis.reported_status,
        blocker=analysis.blocker,
        reported_at=result["reported_at"].isoformat(),
        source_sync_status="AWAITING_SOURCE",
    )

    return state

def reconcile_reported_update(state: WorkUpdateState) -> WorkUpdateState:
    work_item = state.resolved_work_item
    reported_update = state.reported_update
    analysis = state.update_analysis

    if (work_item is None or reported_update is None or analysis is None):
        return state

    if analysis.update_type != "STATUS_CHANGE":
        return state

    if reported_update.reported_status is None:
        return state

    query = text("""
        SELECT status
        FROM workweave.work_items
        WHERE organization_id = :organization_id
          AND workspace_id = :workspace_id
          AND work_item_id = :work_item_id
        LIMIT 1
    """)

    params = {
        "organization_id": state.employee.organization_id,
        "workspace_id": state.employee.workspace_id,
        "work_item_id": work_item.work_item_id,
    }

    with SessionLocal() as session:
        row = session.execute(
            query,
            params,
        ).mappings().first()

    if row is None:
        raise ValueError(
            "Work item could not be found during reconciliation."
        )

    source_status = row["status"]

    state.source_status = source_status

    if (source_status.strip().upper() == reported_update.reported_status.strip().upper()):
        state.source_sync_result = "MATCHED"
    else:
        state.source_sync_result = "AWAITING_SOURCE"

    return state

def persist_reconciliation_result(state: WorkUpdateState) -> WorkUpdateState:
    reported_update = state.reported_update
    sync_result = state.source_sync_result

    if (reported_update is None or reported_update.reported_update_id is None or sync_result is None):
        return state

    query = text("""
        UPDATE workweave.work_item_reported_updates
        SET
            source_sync_status = :source_sync_status,
            updated_at = CURRENT_TIMESTAMP,
            revision = revision + 1
        WHERE reported_update_id = :reported_update_id
          AND organization_id = :organization_id
          AND workspace_id = :workspace_id
        RETURNING reported_update_id
    """)

    with SessionLocal.begin() as session:
        result = session.execute(
            query,
            {
                "reported_update_id": reported_update.reported_update_id,
                "organization_id": state.employee.organization_id,
                "workspace_id": state.employee.workspace_id,
                "source_sync_status": sync_result,
            },
        ).mappings().first()

        if result is None:
            raise ValueError(
                "Could not persist source reconciliation result."
            )

    reported_update.source_sync_status = sync_result

    return state

def generate_update_response(state: WorkUpdateState) -> WorkUpdateState:
    reported_update = state.reported_update

    if reported_update is None:
        if state.resolved_work_item is None:
            # The ticket isn't among this person's assigned work (e.g. it's a teammate's).
            state.conversation.assistant_message = (
                "I can only record updates on tickets assigned to you, and this one isn't in your current work. "
                "If someone else has it, they can report it, or your shift lead can reassign it. "
                "The ticket system shows who has it."
            )
        else:
            state.conversation.assistant_message = (
                "I couldn't record that update. Could you say what changed, for example done, blocked, or still in progress?"
            )
        return state

    # How the person knows the ticket ("Ticket #829"), never its internal ID.
    work_item = state.resolved_work_item
    ticket = (work_item.external_id or work_item.title) if work_item else "this ticket"

    if (state.update_analysis is not None and state.update_analysis.update_type == "BLOCKER_RESOLVED"):
        message = (
            f"I've recorded that the blocker for "
            f"{ticket} has been resolved. "
            "I'll no longer show that reported blocker "
            "in your active work overview."
        )

    elif (state.update_analysis is not None and state.update_analysis.update_type == "BLOCKER"):
        message = (
            f"I've recorded your reported blocker for "
            f"{ticket}: "
            f"{reported_update.blocker}. "
            "The source system hasn't confirmed this blocker."
        )

    elif state.source_sync_result == "MATCHED":
        message = (
            f"Got it. I've recorded your update, and the source system "
            f"already reflects the status as "
            f"{reported_update.reported_status}."
        )

    elif state.source_sync_result == "AWAITING_SOURCE":
        message = (
            f"Got it. I've recorded that you reported this work as "
            f"{reported_update.reported_status}. "
            f"The source system hasn't reflected that change yet, "
            f"so I'll keep it visible for now."
        )

    else:
        message = (
            "Got it. I've recorded your work update."
        )

    state.conversation.assistant_message = message
    state.conversation.is_opening_brief = False

    return state

# Work Update Builder Subgraph
work_update_graph = StateGraph(WorkUpdateState)
work_update_graph.add_node("resolve_update_work_item",  resolve_update_work_item)
work_update_graph.add_node("interpret_work_update", interpret_work_update)
work_update_graph.add_node("normalize_reported_status", normalize_reported_status)
work_update_graph.add_node("persist_reported_update", persist_reported_update)
work_update_graph.add_node("reconcile_reported_update", reconcile_reported_update)
work_update_graph.add_node("persist_reconciliation_result", persist_reconciliation_result)
work_update_graph.add_node("generate_update_response", generate_update_response)

work_update_graph.add_edge(START, "resolve_update_work_item")
work_update_graph.add_edge("resolve_update_work_item", "interpret_work_update")
work_update_graph.add_edge("interpret_work_update", "normalize_reported_status")
work_update_graph.add_edge("normalize_reported_status", "persist_reported_update")
work_update_graph.add_edge("persist_reported_update", "reconcile_reported_update")
work_update_graph.add_edge("reconcile_reported_update", "persist_reconciliation_result")
work_update_graph.add_edge("persist_reconciliation_result", "generate_update_response")
work_update_graph.add_edge("generate_update_response", END)

work_update_subgraph = work_update_graph.compile()

def refresh_after_work_update(state: WorkCompanionState) -> WorkCompanionState:
    state = reconcile_pending_status_reports(state)
    state = load_work_context(state)
    state = determine_priorities(state)

    return state

def generate_work_overview(state: WorkCompanionState) -> WorkCompanionState:
    # Refresh authoritative work and priorities.
    state = reconcile_pending_status_reports(state)
    state = load_work_context(state)
    state = load_employee_work_state(state)
    state = determine_priorities(state)

    work_by_id = {
        item.work_item_id: item
        for item in state.work.active_items
    }

    if not state.priority.prioritized_items:
        state.conversation.assistant_message = (
            "You currently have no active assigned work."
        )
        state.conversation.is_opening_brief = False
        return state

    lines = [
        "Here's your current assigned work, "
        "ordered by priority:"
    ]

    for priority in state.priority.prioritized_items:
        item = work_by_id.get(priority.work_item_id)

        if item is None:
            continue

        lines.append(
            f"{priority.rank}. {item.title} "
            f"[{item.work_type}] — {priority.urgency}\n"
            f"   {priority.reason}"
        )

        if (item.source_sync_status == "AWAITING_SOURCE" and item.reported_status):
            lines.append(
                f"   Reported as {item.reported_status}; "
                "awaiting source confirmation."
            )

        if item.is_blocked and item.blocker:
            lines.append(
                f"   Blocker: {item.blocker}"
            )

            if item.blocker_source == "EMPLOYEE_REPORTED":
                lines.append(
                    "   This blocker was reported by the employee "
                    "and has not been source-confirmed."
                )

    state.conversation.assistant_message = "\n".join(lines)
    state.conversation.is_opening_brief = False

    return state

def reprioritize_work(state: WorkCompanionState) -> WorkCompanionState:
    # Refresh work and priority recommendations.
    state = reconcile_pending_status_reports(state)
    state = load_work_context(state)
    state = determine_priorities(state)

    priorities = state.priority.prioritized_items

    if not priorities:
        state.conversation.assistant_message = (
            "You currently have no active assigned work to prioritize."
        )
        return state

    work_by_id = {
        item.work_item_id: item
        for item in state.work.active_items
    }

    priority_by_id = {
        item.work_item_id: item
        for item in priorities
    }

    analysis = state.response_analysis
    requested_id = (
        analysis.referenced_work_item_id
        if analysis else None
    )

    requested_item = work_by_id.get(requested_id)
    requested_priority = priority_by_id.get(requested_id)

    if (analysis is not None and analysis.intent == "PRIORITY_CHANGE" and requested_item is None and not any(phrase in (state.conversation.user_message or "").lower() for phrase in ["rearrange", "reorder", "prioritize my", "review priorities"])):
        state.conversation.assistant_message = (
            "Which work item would you like me to reconsider?"
        )
        return state

    priority_context = []

    for priority in priorities:
        item = work_by_id[priority.work_item_id]

        priority_context.append({
            "work_item_id": item.work_item_id,
            "title": item.title,
            "status": item.status,
            "source_priority": item.priority,
            "due_at": item.due_at,
            "sla_due_at": item.sla_due_at,
            "is_blocked": item.is_blocked,
            "blocker": item.blocker,
            "reported_status": item.reported_status,
            "source_sync_status": item.source_sync_status,
            "rank": priority.rank,
            "urgency": priority.urgency,
            "reason": priority.reason,
        })

    requested_context = (
        {
            "work_item_id": requested_item.work_item_id,
            "title": requested_item.title,
            "rank": requested_priority.rank,
            "urgency": requested_priority.urgency,
        }
        if requested_item and requested_priority
        else None
    )

    prompt = f"""
    You are the WorkWeave AI Work Companion.

    The employee requested help with reprioritizing work.

    EMPLOYEE REQUEST:
    {state.conversation.user_message}

    DETERMINISTIC PRIORITY ORDER:
    {json.dumps(priority_context, indent=2)}

    REQUESTED WORK ITEM:
    {json.dumps(requested_context, indent=2)}

    Instructions:
    - Explain the recommended work order using the provided ranks.
    - Treat the deterministic order as the baseline.
    - Do not invent or change ranks, deadlines, or source priorities.
    - If the employee wants a lower-ranked item first,
      acknowledge their preference.
    - Explain any important trade-offs, especially urgent SLAs.
    - A blocked item may still require urgent follow-up.
    - Do not assume a blocker has been resolved.
    - Distinguish employee-reported completion from
      source-confirmed completion.
    - Do not claim that tasks have been reassigned,
      rescheduled, or updated in external systems.
    - Do not claim that a requested order has been saved.
    - If the request is general, recommend the highest-ranked
      actionable item and briefly explain the next priorities.
    - If the employee requests a specific item, explain whether
      working on it first is reasonable given the supplied data.
    - Keep the response concise and practical.
    - End with one useful question about which task to focus on.

    Return only the employee-facing response.
    """

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
    )

    if not response.text:
        raise ValueError(
            "Gemini did not generate a reprioritization response."
        )

    state.conversation.assistant_message = response.text.strip()
    state.conversation.is_opening_brief = False

    return state

# SUBGRAPH - SCHEDULING
def load_employee_shift(state: SchedulingState) -> SchedulingState:
    employee = state.employee

    query = text("""
        SELECT
            e.email,
            si.shift_instance_id,
            sh.name AS shift_name,
            sh.timezone,
            si.scheduled_start_at,
            si.scheduled_end_at,
            si.status
        FROM workweave.employees e
        JOIN workweave.shift_instance_memberships m
            ON m.employee_id = e.employee_id
            AND m.organization_id = e.organization_id
            AND m.workspace_id = e.workspace_id
        JOIN workweave.shift_instances si
            ON si.shift_instance_id = m.shift_instance_id
            AND si.organization_id = m.organization_id
            AND si.workspace_id = m.workspace_id
        JOIN workweave.shifts sh
            ON sh.shift_id = si.shift_id
            AND sh.organization_id = si.organization_id
            AND sh.workspace_id = si.workspace_id
        WHERE e.employee_id = :employee_id
            AND e.organization_id = :organization_id
            AND e.workspace_id = :workspace_id
            AND si.scheduled_end_at > NOW()
            AND si.status IN ('SCHEDULED', 'ACTIVE')
        ORDER BY si.scheduled_start_at ASC
        LIMIT 1
    """)

    with engine.connect() as conn:
        result = conn.execute(
            query,
            {
                "employee_id": employee.employee_id,
                "organization_id": employee.organization_id,
                "workspace_id": employee.workspace_id,
            }
        ).mappings().first()

    if result is None:
        state.scheduling.error = (
            "No active or upcoming shift was found for this employee."
        )
        return state

    shift_data = dict(result)

    # Temporary static email for Google Calendar integration.
    # Later, remove this override to use the database email.
    shift_data["email"] = os.getenv("WORKWEAVE_EMPLOYEE_EMAIL")
    print(shift_data)

    if not shift_data["email"]:
        state.scheduling.error = (
            "Google Calendar employee email is not configured."
        )
        return state

    state.scheduling.employee_email = shift_data["email"]

    state.scheduling.shifts = [
        EmployeeShift(
            shift_instance_id=str(shift_data["shift_instance_id"]),
            shift_name=shift_data["shift_name"],
            timezone=shift_data["timezone"],
            scheduled_start_at=shift_data["scheduled_start_at"],
            scheduled_end_at=shift_data["scheduled_end_at"],
            status=shift_data["status"],
        )
    ]

    state.scheduling.error = None

    return state

def load_calendar_availability(state: SchedulingState) -> SchedulingState:
    if state.scheduling.error:
        return state

    shifts = state.scheduling.shifts

    if not shifts:
        state.scheduling.error = "No employee shift available."
        return state

    shift = shifts[0]

    calendar_api_url = os.getenv(
        "GOOGLE_CALENDAR_API_URL",
        "http://localhost:8001"
    )

    try:
        response = requests.get(
            f"{calendar_api_url}/calendar/availability",
            params={
                "start": shift.scheduled_start_at.isoformat(),
                "end": shift.scheduled_end_at.isoformat()
            },
            timeout=15
        )

        response.raise_for_status()
        data = response.json()

        state.scheduling.busy_periods = [
            CalendarBusyPeriod(
                start=datetime.fromisoformat(period["start"]),
                end=datetime.fromisoformat(period["end"])
            )
            for period in data.get("busy_periods", [])
        ]

        state.scheduling.error = None

    except requests.RequestException as exc:
        print(f"calendar availability error: {exc}")  # details stay in the server log, never in the reply
        state.scheduling.error = (
            "I couldn't check your calendar availability because an error was encountered. Nothing was scheduled; try again in a moment."
        )

    return state

class ScheduleStartRequest(BaseModel):
    start: datetime | None = None

def requested_schedule_start(state: SchedulingState, shift: EmployeeShift) -> datetime | None:
    message = state.conversation.user_message or ""

    if not message.strip():
        return None

    tz = ZoneInfo(shift.timezone)
    now = datetime.now(tz)

    try:
        result = llm_chat.with_structured_output(
            ScheduleStartRequest
        ).invoke([
            SystemMessage(content=f"""
                Extract the earliest start time the employee asked for when planning their work.

                Current local datetime: {now.isoformat()}
                Timezone: {shift.timezone}

                Examples:
                "Plan my tasks starting at 1 PM" -> today at 1 PM
                "Schedule my work an hour from now" -> the current time plus one hour
                "Schedule my tasks" -> null

                Rules:
                - Interpret times in the employee's timezone.
                - Return null when no start time is mentioned.
            """),
            HumanMessage(content=message)
        ])
    except Exception as exc:
        print(f"schedule start extraction error: {exc}")  # details stay in the server log, never in the reply
        return None

    start = result.start

    if start is not None and start.tzinfo is None:
        start = start.replace(tzinfo=tz)

    return start

def calculate_free_slots(state: SchedulingState) -> SchedulingState:
    if state.scheduling.error:
        return state

    state.scheduling.available_slots = []

    if not state.scheduling.shifts:
        state.scheduling.error = "No employee shift available."
        return state

    shift = state.scheduling.shifts[0]

    shift_start = shift.scheduled_start_at.astimezone(timezone.utc)
    shift_end = shift.scheduled_end_at.astimezone(timezone.utc)

    if shift_end <= shift_start:
        state.scheduling.error = "Invalid employee shift window."
        return state

    # Restrict scheduling to the remaining shift time.
    now = datetime.now(timezone.utc)
    window_start = max(shift_start, now)

    # Start no earlier than a time the employee asked for ("start at 1 PM", "an hour from now").
    requested_start = requested_schedule_start(state, shift)

    if requested_start is not None:
        window_start = max(
            window_start,
            requested_start.astimezone(timezone.utc)
        )

    if window_start >= shift_end:
        return state

    # Normalize and clip busy periods to the shift window.
    busy_intervals = []

    for period in state.scheduling.busy_periods:
        busy_start = period.start.astimezone(timezone.utc)
        busy_end = period.end.astimezone(timezone.utc)

        start = max(busy_start, window_start)
        end = min(busy_end, shift_end)

        if start < end:
            busy_intervals.append((start, end))

    busy_intervals.sort(key=lambda interval: interval[0])

    # Merge overlapping or adjacent busy periods.
    merged_busy = []

    for start, end in busy_intervals:
        if merged_busy and start <= merged_busy[-1][1]:
            previous_start, previous_end = merged_busy[-1]
            merged_busy[-1] = (
                previous_start,
                max(previous_end, end)
            )
        else:
            merged_busy.append((start, end))

    # Subtract busy periods from the shift window.
    available_slots = []
    cursor = window_start

    for busy_start, busy_end in merged_busy:
        if cursor < busy_start:
            available_slots.append(
                AvailableTimeSlot(
                    start=cursor,
                    end=busy_start,
                    duration_minutes=int(
                        (busy_start - cursor).total_seconds() // 60
                    )
                )
            )

        cursor = max(cursor, busy_end)

    # Include remaining free time after the final meeting.
    if cursor < shift_end:
        available_slots.append(
            AvailableTimeSlot(
                start=cursor,
                end=shift_end,
                duration_minutes=int(
                    (shift_end - cursor).total_seconds() // 60
                )
            )
        )

    # Exclude slots shorter than one minute.
    state.scheduling.available_slots = [
        slot
        for slot in available_slots
        if slot.duration_minutes >= 1
    ]

    return state

def generate_schedule_proposal(state: SchedulingState) -> SchedulingState:
    if state.scheduling.error:
        return state

    proposal = ScheduleProposal()

    # Retrieve work items by ID.
    work_by_id = {
        item.work_item_id: item
        for item in state.work.active_items
    }

    # Preserve the Work Companion's priority ranking.
    ranked_items = sorted(
        state.priority.prioritized_items,
        key=lambda priority: priority.rank
    )

    # Copy available slots to avoid modifying original availability.
    remaining_slots = [
        {
            "start": slot.start,
            "end": slot.end
        }
        for slot in state.scheduling.available_slots
    ]

    for priority in ranked_items:

        work_item_id = str(priority.work_item_id)

        # Resolve the actual work item.
        item = work_by_id.get(work_item_id)

        if item is None:
            proposal.unscheduled_work_item_ids.append(
                work_item_id
            )
            continue

        title = item.title

        # Temporary estimate until task durations are available.
        estimated_minutes = DEFAULT_TASK_DURATION_MINUTES

        allocated = False

        for slot in remaining_slots:

            available_minutes = (
                slot["end"] - slot["start"]
            ).total_seconds() / 60

            if available_minutes < estimated_minutes:
                continue

            task_start = slot["start"]

            task_end = task_start + timedelta(
                minutes=estimated_minutes
            )

            proposal.tasks.append(
                ScheduledTask(
                    work_item_id=work_item_id,
                    title=title,
                    start=task_start,
                    end=task_end,
                    duration_minutes=estimated_minutes
                )
            )

            proposal.total_scheduled_minutes += (
                estimated_minutes
            )

            # Advance the slot to prevent overlapping tasks.
            slot["start"] = task_end

            allocated = True
            break

        if not allocated:
            proposal.unscheduled_work_item_ids.append(
                work_item_id
            )

    state.scheduling.proposal = proposal

    return state

def generate_scheduling_response(state: SchedulingState) -> SchedulingState:
    scheduling = state.scheduling

    if scheduling.error:
        scheduling.response = (
            f"I couldn't prepare your schedule. "
            f"{scheduling.error}"
        )
        scheduling.approval_status = "not_requested"
        return state

    if not scheduling.shifts:
        scheduling.response = (
            "I couldn't find a scheduled shift to plan around."
        )
        scheduling.approval_status = "not_requested"
        return state

    shift = scheduling.shifts[0]
    timezone = ZoneInfo(shift.timezone)
    proposal = scheduling.proposal

    def local_time(value):
        return value.astimezone(timezone).strftime(
            "%b %d, %Y %I:%M %p"
        )

    scheduled_tasks = [
        {
            "work_item_id": task.work_item_id,
            "title": task.title,
            "start": local_time(task.start),
            "end": local_time(task.end),
            "duration_minutes": task.duration_minutes,
        }
        for task in proposal.tasks
    ]

    context = {
        "timezone": shift.timezone,
        "shift_start": local_time(
            shift.scheduled_start_at
        ),
        "shift_end": local_time(
            shift.scheduled_end_at
        ),
        "scheduled_tasks": scheduled_tasks,
        "unscheduled_work_item_ids": (
            proposal.unscheduled_work_item_ids
        ),
        "total_scheduled_minutes": (
            proposal.total_scheduled_minutes
        ),
    }

    if not proposal.tasks:
        scheduling.response = (
            "I couldn't allocate any tasks within your "
            "available shift time. Your calendar may be "
            "fully booked, or the tasks may not fit the "
            "remaining available slots."
        )
        scheduling.approval_status = "not_requested"
        return state

    messages = [
        SystemMessage(
            content="""
                You are WorkWeave's AI Work Scheduling Assistant.

                Explain the proposed work schedule using the provided data.

                Rules:
                - Use only the supplied schedule information.
                - Preserve task names, dates, times, and durations.
                - Do not invent tasks or calendar events.
                - Clearly mention any unscheduled tasks.
                - Explain that this is a proposal, not a confirmed schedule.
                - Do not claim any Google Calendar events were created.
                - Ask the employee whether they approve the proposed schedule.
                - Keep the response clear, professional, and conversational.
                """
        ),
        HumanMessage(
            content=json.dumps(context, default=str)
        ),
    ]

    result = llm_chat.invoke(messages)

    scheduling.response = extract_llm_text(result.content)

    if not scheduling.response:
        raise ValueError("Gemini returned an empty scheduling response.")

    scheduling.approval_status = "pending"
    state.conversation.assistant_message = scheduling.response
    state.conversation.is_opening_brief = False

    return state

def finalize_scheduling_response(state: SchedulingState) -> SchedulingState:
    state.conversation.assistant_message = (
        state.scheduling.response or "I couldn't put a schedule together this time, so nothing was added to your calendar. Try asking again, or name the day you want planned."
    )
    state.conversation.is_opening_brief = False
    return state

# Scheduling Subgraph
scheduling_builder = StateGraph(SchedulingState)
scheduling_builder.add_node("load_employee_shift", load_employee_shift)
scheduling_builder.add_node("load_calendar_availability", load_calendar_availability)
scheduling_builder.add_node("calculate_free_slots", calculate_free_slots)
scheduling_builder.add_node("generate_schedule_proposal", generate_schedule_proposal)
scheduling_builder.add_node("generate_scheduling_response", generate_scheduling_response)
scheduling_builder.add_node("finalize_scheduling_response", finalize_scheduling_response)

scheduling_builder.add_edge(START, "load_employee_shift")
scheduling_builder.add_edge("load_employee_shift", "load_calendar_availability")
scheduling_builder.add_edge("load_calendar_availability", "calculate_free_slots")
scheduling_builder.add_edge("calculate_free_slots", "generate_schedule_proposal")
scheduling_builder.add_edge("generate_schedule_proposal", "generate_scheduling_response")
scheduling_builder.add_edge("generate_scheduling_response", "finalize_scheduling_response")
scheduling_builder.add_edge("finalize_scheduling_response", END)
scheduling_subgraph = scheduling_builder.compile()

def calendar_inquiry(state: WorkCompanionState) -> WorkCompanionState:
    user_message = state.conversation.user_message

    employee_timezone = ZoneInfo("Asia/Manila")
    now = datetime.now(employee_timezone)

    # Step 1: Interpret the employee's requested period.
    range_llm = llm_chat.with_structured_output(
        CalendarInquiryRange
    )

    date_range = range_llm.invoke([
        SystemMessage(content=f"""
            You extract calendar date ranges from employee requests.

            Current datetime: {now.isoformat()}
            Employee timezone: Asia/Manila

            Rules:
            - Return start and end as timezone-aware datetimes.
            - "Today" means local midnight today to local midnight tomorrow.
            - "Tomorrow" means local midnight tomorrow to local midnight the following day.
            - "This week" means Monday 00:00 through next Monday 00:00.
            - "Next week" means next Monday 00:00 through the following Monday 00:00.
            - "Next meeting" means now through 7 days from now.
            - If no period is specified, use today.
            - End is exclusive.
            - Do not invent calendar events.
            """),
        HumanMessage(content=user_message)
    ])

    start = date_range.start
    end = date_range.end

    if start.tzinfo is None or end.tzinfo is None or end <= start:
        state.conversation.assistant_message = (
            "I couldn't determine the calendar period. "
            "Could you specify a date or time range?"
        )
        state.conversation.is_opening_brief = False
        return state

    # Step 2: Retrieve existing Google Calendar events.
    try:
        response = requests.get(
            "http://localhost:8001/calendar/events",
            params={
                "start": start.isoformat(),
                "end": end.isoformat()
            },
            timeout=15
        )

        response.raise_for_status()
        calendar_data = response.json()

    except requests.RequestException as exc:
        print(f"calendar service error: {exc}")  # details stay in the server log, never in the reply
        state.conversation.assistant_message = (
            "I couldn't check your calendar because an error was encountered. Nothing was changed. Try again in a moment."
        )
        state.conversation.is_opening_brief = False
        return state

    events = calendar_data.get("events", [])

    # Step 3: Handle an empty calendar.
    if not events:
        state.conversation.assistant_message = (
            f"You don't have any calendar events scheduled "
            f"between {start.astimezone(employee_timezone):%b %d, %Y %I:%M %p} "
            f"and {end.astimezone(employee_timezone):%b %d, %Y %I:%M %p}."
        )
        state.conversation.is_opening_brief = False
        return state

    # Step 4: Generate a natural-language response.
    summary = llm_chat.invoke([
        SystemMessage(content="""
            You are WorkWeave's Calendar Assistant.

            Summarize the employee's existing Google Calendar events.

            Rules:
            - Use only the retrieved events.
            - Preserve event titles, dates, and times.
            - Present times in the employee's local timezone.
            - Include locations when available.
            - Do not invent meetings, attendees, or tasks.
            - Do not claim events were created or modified.
            - If asked for the next meeting, identify the earliest upcoming event.
            - Keep the response clear and concise.
            """),
        HumanMessage(content=json.dumps({
            "user_request": user_message,
            "timezone": "Asia/Manila",
            "current_datetime": now.isoformat(),
            "events": events
        }, default=str))
    ])

    state.conversation.assistant_message = extract_llm_text(summary.content)
    state.conversation.is_opening_brief = False

    return state

def handle_schedule_approval(state: WorkCompanionState) -> WorkCompanionState:
    scheduling = state.scheduling

    if scheduling.approval_status != "pending":
        state.conversation.assistant_message = (
            "There is no pending schedule awaiting approval."
        )
        return state

    decision_llm = llm_chat.with_structured_output(
        ScheduleApprovalDecision
    )

    result = decision_llm.invoke([
        SystemMessage(content="""
            You classify an employee's response to a proposed work schedule.

            Return one of:
            - APPROVE: Explicitly agrees to the proposed schedule.
            - REJECT: Declines or cancels the proposed schedule.
            - MODIFY: Requests changes to the proposed schedule.
            - UNCLEAR: Does not clearly approve, reject, or request changes.

            Examples:
            "Yes, schedule it" -> APPROVE
            "Looks good, go ahead" -> APPROVE
            "No, don't schedule those" -> REJECT
            "Cancel that proposal" -> REJECT
            "Move the first task to 3 PM" -> MODIFY
            "Can you make it later?" -> MODIFY
            "Maybe" -> UNCLEAR

            Rules:
            - Do not interpret ambiguous responses as approval.
            - Do not create or modify calendar events.
        """),
        HumanMessage(content=state.conversation.user_message)
    ])

    if result.decision == "APPROVE":
        scheduling.approval_status = "approved"
        scheduling.response = (
            "Your proposed schedule has been approved. The tasks have not been added to Google Calendar yet."
        )

    elif result.decision == "REJECT":
        scheduling.approval_status = "rejected"
        scheduling.response = (
            "Your proposed schedule has been rejected. No Google Calendar events were created."
        )

    elif result.decision == "MODIFY":
        scheduling.approval_status = "changes_requested"
        scheduling.response = "Updating your proposed schedule..."

    else:
        scheduling.approval_status = "pending"
        scheduling.response = (
            "Would you like to approve or reject the proposed schedule?"
        )

    state.conversation.assistant_message = scheduling.response
    state.conversation.is_opening_brief = False

    return state

def modify_schedule_proposal(state: WorkCompanionState) -> WorkCompanionState:
    scheduling = state.scheduling

    if not scheduling.proposal.tasks:
        scheduling.response = (
            "There is no proposed event to modify."
        )
        state.conversation.assistant_message = scheduling.response
        return state

    # The proposal stays open while we ask a follow-up question ("which
    # event?", "that time has passed"), so the employee's answer is handled
    # as a change to it, not as a new request that plans from now.
    scheduling.approval_status = "pending"

    timezone_name = (
        scheduling.shifts[0].timezone
        if scheduling.shifts
        else "Asia/Manila"
    )

    tz = ZoneInfo(timezone_name)
    now = datetime.now(tz)

    class ScheduleModification(BaseModel):
        work_item_ids: list[str] = Field(default_factory=list)
        shift_minutes: int | None = None
        start: datetime | None = None
        end: datetime | None = None
        title: str | None = None

    modification_llm = llm_chat.with_structured_output(
        ScheduleModification
    )

    modification = modification_llm.invoke([
        SystemMessage(content=f"""
            Extract changes requested for an existing schedule proposal.

            Current local datetime: {now.isoformat()}
            Timezone: {timezone_name}

            Existing proposal:
            {scheduling.proposal.model_dump_json(indent=2)}

            Fields:
            - work_item_ids: the proposed tasks the change is for, by work_item_id.
              Leave it empty when the employee means the whole proposal: "it",
              "them", "both", "all of them", "the schedule", or no task named.
            - shift_minutes: a relative move. "30 minutes later" -> 30,
              "an hour earlier" -> -60. Leave start null then.
            - start: a new start time. "at 1 PM" -> today at 1 PM,
              "an hour from now" -> the current local datetime plus one hour.
            - end: only when a new end time is explicitly requested.
            - title: only when a new name is explicitly requested.

            Rules:
            - Interpret times in the employee's timezone.
            - Return null for fields not requested.
            - Resolve midnight correctly.
            - Do not approve or create calendar events.
        """),
        HumanMessage(
            content=state.conversation.user_message or ""
        )
    ])

    tasks = scheduling.proposal.tasks

    targets = (
        [
            task
            for task in tasks
            if task.work_item_id in modification.work_item_ids
        ]
        if modification.work_item_ids
        else list(tasks)
    )

    if not targets:
        names = ", ".join(task.title for task in tasks)
        scheduling.response = (
            f"Which proposed event would you like to change: {names}?"
        )
        state.conversation.assistant_message = scheduling.response
        return state

    targets.sort(key=lambda task: task.start)

    # Move the events together: the first one goes to the new start (or
    # all of them by the same amount), keeping their lengths and the gaps
    # between them.
    if modification.shift_minutes:
        delta = timedelta(minutes=modification.shift_minutes)

    elif modification.start is not None:
        new_start = modification.start

        if new_start.tzinfo is None:
            new_start = new_start.replace(tzinfo=tz)

        delta = new_start - targets[0].start

    else:
        delta = timedelta(0)

    moves = [
        (task, task.start + delta, task.end + delta)
        for task in targets
    ]

    if modification.end is not None and len(moves) == 1:
        end = modification.end

        if end.tzinfo is None:
            end = end.replace(tzinfo=tz)

        moves = [(moves[0][0], moves[0][1], end)]

    renamed = bool(modification.title) and len(targets) == 1

    if delta == timedelta(0) and modification.end is None and not renamed:
        scheduling.response = (
            "What would you like to change: the start time, "
            "or how long it takes?"
        )
        state.conversation.assistant_message = scheduling.response
        return state

    moved = {id(task) for task, _, _ in moves}
    others = [task for task in tasks if id(task) not in moved]

    for task, start, end in moves:
        if end <= start:
            scheduling.response = (
                "The ending time must be after the starting time. "
                "What time would you like the event to end?"
            )
            state.conversation.assistant_message = scheduling.response
            return state

        if start <= now:
            scheduling.response = (
                "That time has already passed. "
                "Please choose a future time."
            )
            state.conversation.assistant_message = scheduling.response
            return state

        # Validate against the employee's shift.
        if scheduling.shifts:
            shift = scheduling.shifts[0]

            if (
                start < shift.scheduled_start_at
                or end > shift.scheduled_end_at
            ):
                scheduling.response = (
                    "That time is outside your scheduled shift. "
                    "Please choose a time within your shift."
                )
                state.conversation.assistant_message = scheduling.response
                return state

        # Validate against the previously retrieved busy periods.
        # Refresh availability before final approval.
        for busy in scheduling.busy_periods:
            if start < busy.end and end > busy.start:
                scheduling.response = (
                    "That time conflicts with an existing calendar event. "
                    "Please choose another time."
                )
                state.conversation.assistant_message = scheduling.response
                return state

        # Don't overlap the proposal's other events.
        for other in others:
            if start < other.end and end > other.start:
                scheduling.response = (
                    f"That time overlaps **{other.title}** in this proposal. "
                    "Please choose another time, or move both together."
                )
                state.conversation.assistant_message = scheduling.response
                return state

    for task, start, end in moves:
        task.start = start
        task.end = end
        task.duration_minutes = int(
            (end - start).total_seconds() / 60
        )

    if renamed:
        targets[0].title = modification.title

    tasks.sort(key=lambda task: task.start)

    scheduling.proposal.total_scheduled_minutes = sum(
        item.duration_minutes
        for item in tasks
    )

    scheduling.approval_status = "pending"

    lines = "\n\n".join(
        f"**{task.title}**\n"
        f"Time: {task.start.astimezone(tz):%b %d, %I:%M %p}"
        f" – {task.end.astimezone(tz):%b %d, %I:%M %p}"
        for task in tasks
    )

    scheduling.response = (
        f"I've updated your proposal:\n\n{lines}\n\n"
        "Would you like me to add this to Google Calendar?"
    )

    state.conversation.assistant_message = scheduling.response
    state.conversation.is_opening_brief = False

    return state

def create_approved_calendar_events(state: WorkCompanionState) -> WorkCompanionState:
    scheduling = state.scheduling

    if scheduling.approval_status != "approved":
        state.conversation.assistant_message = (
            "Calendar events were not created because "
            "the schedule has not been approved."
        )
        return state

    if not scheduling.proposal.tasks:
        scheduling.approval_status = "not_requested"
        state.conversation.assistant_message = (
            "There are no scheduled tasks to add."
        )
        return state

    payload = {
        "events": [
            {
                "work_item_id": task.work_item_id,
                "title": task.title,
                "start": task.start.isoformat(),
                "end": task.end.isoformat()
            }
            for task in scheduling.proposal.tasks
        ]
    }

    try:
        now = datetime.now(timezone.utc)

        for task in scheduling.proposal.tasks:
            if task.start.astimezone(timezone.utc) <= now:
                scheduling.approval_status = "changes_requested"
                scheduling.response = (
                    "Your proposed schedule is no longer current "
                    "because one or more tasks were scheduled to "
                    "start in the past. Would you like me to "
                    "generate an updated schedule?"
                )

                state.conversation.assistant_message = scheduling.response
                state.conversation.is_opening_brief = False
                return state

        response = requests.post(
            "http://localhost:8001/calendar/events",
            json=payload,
            timeout=60
        )
        response.raise_for_status()
        result = response.json()

    except requests.RequestException as exc:
        print(f"calendar event creation error: {exc}")  # details stay in the server log, never in the reply
        scheduling.approval_status = "creation_failed"
        scheduling.response = (
            "I couldn't confirm that your calendar events were created because an error was encountered. "
            "Please check Google Calendar before trying again."
        )

        state.conversation.assistant_message = scheduling.response
        return state

    created_events = result.get("created_events", [])

    if result.get("status") == "created":
        scheduling.approval_status = "created"
        scheduling.response = (
            f"Successfully added {len(created_events)} "
            "scheduled task(s) to your Google Calendar."
        )

    else:
        scheduling.approval_status = "creation_failed"
        scheduling.response = (
            f"Only {len(created_events)} event(s) were created. "
            "Please check your calendar before retrying."
        )

    state.conversation.assistant_message = scheduling.response
    state.conversation.is_opening_brief = False

    return state

# APP ACTIONS
class AppActionRequest(BaseModel):
    action: Literal[
        "SHOW_BRIEFING", "SHOW_WORK_ITEMS", "SHOW_WORK_UPDATES",
        "OPEN_TICKET_SYSTEM", "ACCEPT_ASSIGNMENT",
        "CHANGE_PROPOSAL_PERSON", "REJECT_PROPOSAL",
        "SAVE_NOTE", "SUBMIT_NOTE",
        "READ_ALOUD_ON", "READ_ALOUD_OFF", "STOP_READING", "SPEAK_SLOWER", "SPEAK_FASTER", "NORMAL_SPEED",
        "NONE",
    ]
    work_item_reference: Optional[str] = Field(default=None, description="Ticket number or title the employee named, as said")
    person_name: Optional[str] = Field(default=None, description="Person the employee named, as said")
    status_filter: list[Literal["ACTIVE", "IN_PROGRESS", "BLOCKED"]] = Field(default_factory=list)
    note_text: Optional[str] = Field(default=None, description="The knowledge note's text, only what the employee dictated")
    note_audience: Optional[Literal["PRIVATE", "TEAM", "ORGANIZATION"]] = None
    reason: Optional[str] = Field(default=None, description="Reason the employee gave, e.g. for cancelling a proposal")

def request_app_action(state: WorkCompanionState) -> WorkCompanionState:
    """Names the app action the employee asked for. WorkWeave checks permissions, performs it, and
    replaces this message with what actually happened."""
    prompt = f"""
    The employee asked the WorkWeave Work Companion app to do something.

    Recent conversation (oldest first):
    {json.dumps(state.conversation.history[-6:], indent=2)}

    The employee said:
    {state.conversation.user_message}

    Choose the single matching action:
    - SHOW_BRIEFING: back to the briefing / starting view.
    - SHOW_WORK_ITEMS: show work items; set status_filter when they ask
      for only some statuses (for example only BLOCKED).
    - SHOW_WORK_UPDATES: show recent work updates.
    - OPEN_TICKET_SYSTEM: open a work item in the ticket system.
    - ACCEPT_ASSIGNMENT: the employee accepts a work item assigned to them.
    - CHANGE_PROPOSAL_PERSON: in the delegation proposal just prepared,
      give the work item to a different person (person_name).
    - REJECT_PROPOSAL: cancel the delegation proposal just prepared.
    - SAVE_NOTE: save a knowledge note; note_text is only what the
      employee dictated, word for word. Default audience PRIVATE.
    - SUBMIT_NOTE: submit their latest knowledge note for review.
    - READ_ALOUD_ON / READ_ALOUD_OFF / STOP_READING / SPEAK_SLOWER /
      SPEAK_FASTER / NORMAL_SPEED: how replies are read aloud.
    - NONE: none of these clearly applies.

    Rules:
    - Copy work item references and names as the employee said them.
    - Do not invent text for notes. Do not decide permissions.
    """

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config={
            "response_mime_type": "application/json",
            "response_json_schema": AppActionRequest.model_json_schema(),
        },
    )

    if not response.text:
        raise ValueError("Gemini did not return an app action.")

    state.app_action = AppActionRequest.model_validate_json(response.text).model_dump()
    state.conversation.assistant_message = "On it…"
    state.conversation.is_opening_brief = False

    return state

# QUESTIONS ABOUT WORK DATA
def answer_work_data(state: WorkCompanionState) -> WorkCompanionState:
    """Answers factual questions from the work the employee may see: a shift lead sees the work on
    their shift in progress, everyone else only work assigned to them."""
    state = load_shift_team(state)
    state = load_shift_work(state)
    delegation = state.delegation

    if delegation.is_shift_lead:
        items = [dict(item) for item in delegation.shift_work]
    else:
        items = [
            {
                "work_item_id": item.work_item_id,
                "reference": item.external_id,
                "title": item.title,
                "priority": item.priority,
                "due_at": item.due_at,
                "assigned_to": "you",
            }
            for item in state.work.active_items
        ]

    ids = [item["work_item_id"] for item in items]

    details_query = text("""
        SELECT
            wi.work_item_id,
            wi.status,
            (SELECT r.reported_status || COALESCE(' (' || r.update_type || ')', '') || ': ' || r.source_sync_status
             FROM workweave.work_item_reported_updates AS r
             WHERE r.organization_id = wi.organization_id
               AND r.workspace_id = wi.workspace_id
               AND r.work_item_id = wi.work_item_id
               AND r.source_sync_status <> 'SUPERSEDED'
             ORDER BY r.reported_at DESC
             LIMIT 1) AS latest_report,
            (SELECT json_agg(x) FROM (
                SELECT ev.event_type, ev.description, ev.observed_at
                FROM workweave.work_events AS ev
                WHERE ev.organization_id = wi.organization_id
                  AND ev.workspace_id = wi.workspace_id
                  AND ev.work_item_id = wi.work_item_id
                ORDER BY ev.observed_at DESC
                LIMIT 3) AS x) AS recent_events
        FROM workweave.work_items AS wi
        WHERE wi.organization_id = :organization_id
          AND wi.workspace_id = :workspace_id
          AND wi.work_item_id = ANY(CAST(:ids AS uuid[]))
    """)

    with SessionLocal() as session:
        rows = session.execute(
            details_query,
            {
                "organization_id": state.employee.organization_id,
                "workspace_id": state.employee.workspace_id,
                "ids": ids,
            },
        ).mappings().all()

    details = {str(row["work_item_id"]): row for row in rows}

    for item in items:
        row = details.get(item["work_item_id"])
        item.pop("assignee_id", None)
        item["status"] = row["status"] if row else None
        item["latest_report"] = row["latest_report"] if row else None
        item["recent_events"] = row["recent_events"] if row else []

    roster = (
        [teammate.name for teammate in delegation.teammates]
        if delegation.is_shift_lead
        else None
    )

    prompt = f"""
    You are the WorkWeave AI Work Companion. Answer the employee's
    question about the state of their work.

    Who is asking:
    {delegation.speaker.name if delegation.speaker else "the employee"}{" (shift lead of the " + str(delegation.shift_name) + " shift in progress)" if delegation.is_shift_lead else ""}

    Work they may see (status is the ticket system's real status;
    latest_report is what someone said in the Companion and whether
    the ticket system confirmed it):
    {json.dumps(items, indent=2, default=str)}

    People on the shift besides the asker (shift lead only):
    {json.dumps(roster)}

    Recent conversation (oldest first):
    {json.dumps(state.conversation.history[-6:], indent=2)}

    The employee asked:
    {state.conversation.user_message}

    Rules:
    - Use only the data above. If it doesn't answer the question,
      say so plainly.
    - A report is not the real status; say whether the ticket system
      confirmed it.
    - Give counts and lists, never ratings or judgments of people.
    - Refer to work items by reference and title.
    - Keep it short.

    Return only the message for the employee.
    """

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
    )

    if not response.text:
        raise ValueError("Gemini did not answer the work data question.")

    state.conversation.assistant_message = response.text.strip()
    state.conversation.is_opening_brief = False

    return state

# SUBGRAPH - DELEGATION
def load_shift_team(state: WorkCompanionState) -> WorkCompanionState:
    """Is the employee the lead of a shift in progress, and who else is on that shift?"""
    state.delegation = DelegationContext()

    shift_query = text("""
        SELECT si.shift_instance_id, sh.name AS shift_name
        FROM workweave.shift_instances AS si
        JOIN workweave.shifts AS sh
            ON sh.organization_id = si.organization_id
            AND sh.workspace_id = si.workspace_id
            AND sh.shift_id = si.shift_id
        WHERE si.organization_id = :organization_id
          AND si.workspace_id = :workspace_id
          AND si.shift_lead_employee_id = :employee_id
          AND si.status NOT IN ('CANCELLED', 'COMPLETED')
          AND si.scheduled_start_at <= NOW()
          AND si.scheduled_end_at > NOW()
        ORDER BY si.scheduled_start_at DESC
        LIMIT 1
    """)

    teammates_query = text("""
        SELECT e.employee_id, e.first_name || ' ' || e.last_name AS name
        FROM workweave.shift_instance_memberships AS m
        JOIN workweave.employees AS e
            ON e.organization_id = m.organization_id
            AND e.workspace_id = m.workspace_id
            AND e.employee_id = m.employee_id
        WHERE m.organization_id = :organization_id
          AND m.workspace_id = :workspace_id
          AND m.shift_instance_id = :shift_instance_id
          AND m.employee_id <> :employee_id
          AND e.employment_status <> 'EXITED'
        ORDER BY e.first_name, e.last_name
    """)

    params = {
        "organization_id": state.employee.organization_id,
        "workspace_id": state.employee.workspace_id,
        "employee_id": state.employee.employee_id,
    }

    speaker_query = text("""
        SELECT first_name || ' ' || last_name AS name
        FROM workweave.employees
        WHERE organization_id = :organization_id
          AND workspace_id = :workspace_id
          AND employee_id = :employee_id
    """)

    with SessionLocal() as session:
        speaker = session.execute(speaker_query, params).mappings().first()

        if speaker is not None:
            state.delegation.speaker = ShiftTeammate(
                employee_id=state.employee.employee_id,
                name=speaker["name"],
            )

        shift = session.execute(shift_query, params).mappings().first()

        if shift is None:
            return state

        rows = session.execute(
            teammates_query,
            {**params, "shift_instance_id": str(shift["shift_instance_id"])},
        ).mappings().all()

    state.delegation.shift_instance_id = str(shift["shift_instance_id"])
    state.delegation.shift_name = shift["shift_name"]
    state.delegation.is_shift_lead = True
    state.delegation.teammates = [
        ShiftTeammate(employee_id=str(row["employee_id"]), name=row["name"])
        for row in rows
    ]

    return state

def load_shift_work(state: WorkCompanionState) -> WorkCompanionState:
    """Open work items the shift lead may assign: held by the lead or a teammate on the shift,
    or not assigned to anyone."""
    delegation = state.delegation

    if not delegation.is_shift_lead:
        return state

    people = [state.employee.employee_id] + [teammate.employee_id for teammate in delegation.teammates]

    query = text("""
        SELECT
            wi.work_item_id,
            wi.external_id,
            wi.title,
            wi.priority,
            wi.due_at,
            a.employee_id AS assignee_id,
            e.first_name || ' ' || e.last_name AS assignee
        FROM workweave.work_items AS wi
        LEFT JOIN LATERAL (
            SELECT wia.employee_id
            FROM workweave.work_item_assignments AS wia
            WHERE wia.organization_id = wi.organization_id
              AND wia.workspace_id = wi.workspace_id
              AND wia.work_item_id = wi.work_item_id
              AND wia.status NOT IN ('CANCELLED', 'COMPLETED')
            ORDER BY wia.assigned_at DESC
            LIMIT 1
        ) AS a ON TRUE
        LEFT JOIN workweave.employees AS e
            ON e.organization_id = wi.organization_id
            AND e.workspace_id = wi.workspace_id
            AND e.employee_id = a.employee_id
        WHERE wi.organization_id = :organization_id
          AND wi.workspace_id = :workspace_id
          AND wi.status IN ('ACTIVE', 'IN_PROGRESS', 'BLOCKED')
          AND COALESCE(wi.metadata->>'historical_only', 'false') <> 'true'
          AND (a.employee_id IS NULL OR a.employee_id = ANY(CAST(:people AS uuid[])))
        ORDER BY wi.external_id
    """)

    with SessionLocal() as session:
        rows = session.execute(
            query,
            {
                "organization_id": state.employee.organization_id,
                "workspace_id": state.employee.workspace_id,
                "people": people,
            },
        ).mappings().all()

    delegation.shift_work = [
        {
            "work_item_id": str(row["work_item_id"]),
            "reference": row["external_id"],
            "title": row["title"],
            "priority": row["priority"],
            "due_at": row["due_at"].isoformat() if row["due_at"] else None,
            "assigned_to": row["assignee"] or "nobody",
            "assignee_id": str(row["assignee_id"]) if row["assignee_id"] else None,
        }
        for row in rows
    ]

    return state

def propose_delegation(state: WorkCompanionState) -> WorkCompanionState:
    delegation = state.delegation

    if not delegation.is_shift_lead or not delegation.shift_work:
        return state

    work_context = [
        {key: item[key] for key in ("work_item_id", "reference", "title", "priority", "due_at", "assigned_to")}
        for item in delegation.shift_work
    ]
    people = [teammate.model_dump() | {"is_you": False} for teammate in delegation.teammates]

    if delegation.speaker is not None:
        people.append(delegation.speaker.model_dump() | {"is_you": True})

    prompt = f"""
    You are helping a shift lead assign or reassign open work items
    to people on the same shift, including the shift lead.

    Open work items on the shift (each shows who has it now):
    {json.dumps(work_context, indent=2)}

    People who can take work on this shift ("is_you" marks the shift
    lead, who is speaking; "me", "myself" or "I" mean them):
    {json.dumps(people, indent=2)}

    The shift lead said:
    {state.conversation.user_message}

    Propose assignments that follow the shift lead's request.

    Rules:
    - Use only work_item_id and employee_id values from the lists above.
    - A work item may be named by its reference (for example
      "Ticket #910" or "910") or its title. Match it exactly.
    - Include only work items the request names or clearly covers.
      If the request names a work item that is not in the list,
      return no assignments. Never substitute a different item.
    - If the request names a person, use that person.
    - Do not propose giving an item to the person who already has it.
    - If the request asks to share or split work, spread items across
      teammates and keep the most urgent items first.
    - Give a short factual reason using only the request and the work
      item details. Do not judge or describe people.
    - Do not invent skills, availability, workload, or deadlines.
    - If the request is unclear, return no assignments.
    """

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config={
            "response_mime_type": "application/json",
            "response_json_schema": DelegationPlan.model_json_schema(),
        },
    )

    if not response.text:
        raise ValueError("Gemini did not return a delegation plan.")

    plan = DelegationPlan.model_validate_json(response.text)

    # Keep only real items and teammates, one teammate per item, never to its current holder.
    holders = {item["work_item_id"]: item["assignee_id"] for item in delegation.shift_work}
    teammate_ids = {teammate.employee_id for teammate in delegation.teammates}

    if delegation.speaker is not None:
        teammate_ids.add(delegation.speaker.employee_id)

    picks = {}

    for pick in plan.assignments:
        if pick.work_item_id in holders and pick.employee_id in teammate_ids and holders[pick.work_item_id] != pick.employee_id:
            picks.setdefault(pick.work_item_id, pick)

    delegation.proposal = list(picks.values())

    return state

def generate_delegation_response(state: WorkCompanionState) -> WorkCompanionState:
    delegation = state.delegation

    if not delegation.is_shift_lead:
        message = (
            "Only the lead of the shift in progress can assign work. "
            "Ask your shift lead if a ticket should move to someone else."
        )
    elif not delegation.teammates and delegation.speaker is None:
        message = "There's no one on your shift to assign work to right now."
    elif not delegation.shift_work:
        message = "There are no open work items on your shift to assign."
    elif not delegation.proposal:
        message = (
            "I couldn't match that to an open work item on your shift and someone who can take it. "
            "Which work item (for example its ticket number) should go to whom? You can also say \"to me\"."
        )
    else:
        items = {item["work_item_id"]: item for item in delegation.shift_work}
        names = {teammate.employee_id: teammate.name for teammate in delegation.teammates}

        if delegation.speaker is not None:
            names[delegation.speaker.employee_id] = f"you ({delegation.speaker.name})"

        lines = [
            f"- {items[pick.work_item_id]['reference'] or items[pick.work_item_id]['title']}: "
            f"{items[pick.work_item_id]['assigned_to']} → {names[pick.employee_id]}"
            for pick in delegation.proposal
        ]
        message = (
            "I've prepared a delegation proposal:\n"
            + "\n".join(lines)
            + "\n\nSay \"confirm\" or use Confirm in the work area to assign. "
            "Nothing changes until you confirm."
        )

    state.conversation.assistant_message = message
    state.conversation.is_opening_brief = False

    return state

def confirm_delegation(state: WorkCompanionState) -> WorkCompanionState:
    """The shift lead confirmed in the chat. WorkWeave checks and performs the confirmation and
    replaces this message with the result."""
    state.delegation.confirm_requested = True
    state.conversation.assistant_message = "Confirming the delegation proposal…"
    state.conversation.is_opening_brief = False

    return state

# Delegation Subgraph
delegation_builder = StateGraph(WorkCompanionState)
delegation_builder.add_node("load_shift_team", load_shift_team)
delegation_builder.add_node("load_shift_work", load_shift_work)
delegation_builder.add_node("propose_delegation", propose_delegation)
delegation_builder.add_node("generate_delegation_response", generate_delegation_response)

delegation_builder.add_edge(START, "load_shift_team")
delegation_builder.add_edge("load_shift_team", "load_shift_work")
delegation_builder.add_edge("load_shift_work", "propose_delegation")
delegation_builder.add_edge("propose_delegation", "generate_delegation_response")
delegation_builder.add_edge("generate_delegation_response", END)
delegation_graph = delegation_builder.compile()

# SUBGRAPH - ASSIGNMENT EXPLANATION
def load_assignment_options(state: WorkCompanionState) -> WorkCompanionState:
    """Assignments the employee may ask about: their own, and, for the lead of the shift in
    progress, those of the members on that shift. Includes the facts saved at assignment time."""
    state.assignment_question = AssignmentQuestionContext()
    state = load_shift_team(state)
    people = [state.employee.employee_id]

    if state.delegation.is_shift_lead:
        people += [teammate.employee_id for teammate in state.delegation.teammates]

    query = text("""
        SELECT
            wi.work_item_id,
            wi.external_id,
            wi.title,
            a.employee_id,
            e.first_name || ' ' || e.last_name AS assignee,
            a.assignment_source,
            a.match_data,
            b.first_name || ' ' || b.last_name AS assigned_by
        FROM workweave.work_item_assignments AS a
        JOIN workweave.work_items AS wi
            ON wi.organization_id = a.organization_id
            AND wi.workspace_id = a.workspace_id
            AND wi.work_item_id = a.work_item_id
        JOIN workweave.employees AS e
            ON e.organization_id = a.organization_id
            AND e.workspace_id = a.workspace_id
            AND e.employee_id = a.employee_id
        LEFT JOIN workweave.employees AS b
            ON b.organization_id = a.organization_id
            AND b.workspace_id = a.workspace_id
            AND b.employee_id = a.assigned_by_employee_id
        WHERE a.organization_id = :organization_id
          AND a.workspace_id = :workspace_id
          AND a.employee_id = ANY(CAST(:people AS uuid[]))
          AND a.status NOT IN ('CANCELLED', 'COMPLETED')
          AND wi.status NOT IN ('COMPLETED', 'CANCELLED', 'CLOSED')
        ORDER BY wi.external_id
    """)

    with SessionLocal() as session:
        rows = session.execute(
            query,
            {
                "organization_id": state.employee.organization_id,
                "workspace_id": state.employee.workspace_id,
                "people": people,
            },
        ).mappings().all()

    options = []

    for row in rows:
        facts = dict(row["match_data"] or {})

        # Only the shift lead may see how teammates compared.
        if not state.delegation.is_shift_lead:
            facts.pop("compared", None)

        options.append({
            "work_item_id": str(row["work_item_id"]),
            "reference": row["external_id"],
            "title": row["title"],
            "assignee": row["assignee"],
            "assigned_to_me": str(row["employee_id"]) == state.employee.employee_id,
            "how_assigned": row["assignment_source"],
            "assigned_by": row["assigned_by"],
            "facts_at_assignment": facts,
        })

    state.assignment_question.options = options

    return state

def select_assignment(state: WorkCompanionState) -> WorkCompanionState:
    options = state.assignment_question.options

    if not options:
        return state

    referenced = (
        state.response_analysis.referenced_work_item_id
        if state.response_analysis
        else None
    )
    ids = {option["work_item_id"] for option in options}

    if referenced in ids:
        state.assignment_question.work_item_id = referenced
        return state

    choices = [
        {key: option[key] for key in ("work_item_id", "reference", "title", "assignee")}
        for option in options
    ]

    prompt = f"""
    The employee asked about why a work item was assigned.

    Assigned work items they may ask about:
    {json.dumps(choices, indent=2)}

    The employee said:
    {state.conversation.user_message}

    Return the work_item_id of the item the question is about.
    Use only an ID from the list. If it is unclear, return null.
    """

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config={
            "response_mime_type": "application/json",
            "response_json_schema": AssignmentChoice.model_json_schema(),
        },
    )

    if not response.text:
        raise ValueError("Gemini did not return an assignment choice.")

    choice = AssignmentChoice.model_validate_json(response.text)

    if choice.work_item_id in ids:
        state.assignment_question.work_item_id = choice.work_item_id

    return state

def generate_assignment_explanation(state: WorkCompanionState) -> WorkCompanionState:
    question = state.assignment_question
    selected = next(
        (option for option in question.options if option["work_item_id"] == question.work_item_id),
        None,
    )

    if selected is None:
        state.conversation.assistant_message = (
            "I can explain assignments for your own work items"
            + (" and your shift's work items" if state.delegation.is_shift_lead else "")
            + ". Which work item do you mean?"
        )
        state.conversation.is_opening_brief = False
        return state

    prompt = f"""
    You are the WorkWeave AI Work Companion.

    Explain why this work item is assigned to its assignee, using only
    the facts below. These facts were saved when it was assigned.

    {json.dumps(selected, indent=2, default=str)}

    How to read the facts:
    - how_assigned AUTOMATIC means WorkWeave assigned it by its
      competency rule ("rule": "competency-v1"): among members on the
      shift, the fewest required competencies without validated
      evidence, then the fewest open work items.
    - "requirements" lists each required competency and whether the
      assignee had validated evidence for it ("met").
    - "open_work_before" is how many open work items the assignee had.
    - "compared", when present, shows how the members on the shift
      compared; refer to it only in general terms.
    - rule "lead-override" means the shift lead chose this person,
      replacing an earlier assignment.
    - rule "delegation-proposal" means the shift lead confirmed a
      delegation proposal; "recommendation_reason" says why it was
      suggested, and "lead_changed_recommendation" says whether the
      lead picked someone other than the recommended person.

    Rules:
    - Use only these facts. Do not invent skills, experience, ratings,
      availability, or reasons.
    - Say plainly when a required competency had no validated evidence.
    - Describe evidence, never the person's ability or character.
    - The person asking is {"the assignee" if selected["assigned_to_me"] else "not the assignee"}.
      Use "you" only for the person asking; otherwise call the assignee by name ({selected["assignee"]}).
    - Keep it short: two to four sentences.

    Return only the message for the employee.
    """

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
    )

    if not response.text:
        raise ValueError("Gemini did not generate an assignment explanation.")

    state.conversation.assistant_message = response.text.strip()
    state.conversation.is_opening_brief = False

    return state

# Assignment Explanation Subgraph
assignment_question_builder = StateGraph(WorkCompanionState)
assignment_question_builder.add_node("load_assignment_options", load_assignment_options)
assignment_question_builder.add_node("select_assignment", select_assignment)
assignment_question_builder.add_node("generate_assignment_explanation", generate_assignment_explanation)

assignment_question_builder.add_edge(START, "load_assignment_options")
assignment_question_builder.add_edge("load_assignment_options", "select_assignment")
assignment_question_builder.add_edge("select_assignment", "generate_assignment_explanation")
assignment_question_builder.add_edge("generate_assignment_explanation", END)
assignment_question_graph = assignment_question_builder.compile()

# ROUTING
def route_action(state: WorkCompanionState) -> str:
    analysis = state.response_analysis

    if analysis is None:
        return "clarify"

    action_routes = {
        "FOCUS": "focus",
        "GUIDE": "guide",
        "UPDATE_STATUS": "update_status",
        "OVERVIEW": "overview",
        "HANDLE_BLOCKER": "handle_blocker",
        "REPRIORITIZE": "reprioritize",
        "SCHEDULE": "schedule",
        "CALENDAR": "calendar",
        "DELEGATE": "delegate",
        "CONFIRM_DELEGATION": "confirm_delegation",
        "EXPLAIN_ASSIGNMENT": "explain_assignment",
        "APP_ACTION": "app_action",
        "ANSWER_WORK_DATA": "work_data",
        "PAUSE": "pause",
        "CLARIFY": "clarify"
    }

    return action_routes.get(analysis.recommended_action, "clarify")

def route_pending_schedule(state: WorkCompanionState) -> str:
    if state.scheduling.approval_status == "pending":
        return "schedule_approval"

    return "analyze_user_response"

def route_schedule_approval(state: WorkCompanionState) -> str:
    status = state.scheduling.approval_status

    if status == "approved":
        return "create_events"

    if status == "changes_requested":
        return "modify"

    return "wait_for_user"

# Work Companion Builder Graph
work_companion_builder = StateGraph(WorkCompanionState)
# checkpointer = InMemorySaver()

# Nodes
work_companion_builder.add_node("initialize_companion", initialize_companion)
work_companion_builder.add_node("load_work_context", load_work_context)
work_companion_builder.add_node("load_employee_work_state", load_employee_work_state)
work_companion_builder.add_node("determine_priorities", determine_priorities)
work_companion_builder.add_node("generate_opening_brief", generate_opening_brief)
work_companion_builder.add_node("wait_for_user", wait_for_user)
work_companion_builder.add_node("analyze_user_response", analyze_user_response)
work_companion_builder.add_node("focus_work", focus_work)
work_companion_builder.add_node("work_guidance", work_guidance_graph)
work_companion_builder.add_node("work_overview", generate_work_overview)
work_companion_builder.add_node("clarify_request", clarify_request)
work_companion_builder.add_node("pause_companion", pause_companion)
work_companion_builder.add_node("work_update", work_update_subgraph)
work_companion_builder.add_node("reconcile_pending_status_reports", reconcile_pending_status_reports)
work_companion_builder.add_node("refresh_after_work_update", refresh_after_work_update)
work_companion_builder.add_node("reprioritize_work", reprioritize_work)
work_companion_builder.add_node("schedule_work", scheduling_subgraph)
work_companion_builder.add_node("calendar_inquiry", calendar_inquiry)
work_companion_builder.add_node("handle_schedule_approval", handle_schedule_approval)
work_companion_builder.add_node("modify_schedule_proposal", modify_schedule_proposal)
work_companion_builder.add_node("create_approved_calendar_events", create_approved_calendar_events)
work_companion_builder.add_node("delegate_work", delegation_graph)
work_companion_builder.add_node("confirm_delegation", confirm_delegation)
work_companion_builder.add_node("explain_assignment", assignment_question_graph)
work_companion_builder.add_node("request_app_action", request_app_action)
work_companion_builder.add_node("answer_work_data", answer_work_data)

# Edges
work_companion_builder.add_edge(START, "initialize_companion")
work_companion_builder.add_edge("initialize_companion", "reconcile_pending_status_reports")
work_companion_builder.add_edge("reconcile_pending_status_reports", "load_work_context")
work_companion_builder.add_edge("load_work_context", "load_employee_work_state")
work_companion_builder.add_edge("load_employee_work_state", "determine_priorities")
work_companion_builder.add_edge("determine_priorities", "generate_opening_brief")
work_companion_builder.add_edge("generate_opening_brief", "wait_for_user")
work_companion_builder.add_conditional_edges(
    "wait_for_user",
    route_pending_schedule,
    {
        "schedule_approval": "handle_schedule_approval",
        "analyze_user_response": "analyze_user_response"
    }
)
work_companion_builder.add_conditional_edges(
    "analyze_user_response",
    route_action,
    {
        "focus": "focus_work",
        "guide": "work_guidance",
        "update_status": "work_update",
        "overview": "work_overview",
        "handle_blocker": "work_update",
        "reprioritize": "reprioritize_work",
        "schedule": "schedule_work",
        "calendar": "calendar_inquiry",
        "delegate": "delegate_work",
        "confirm_delegation": "confirm_delegation",
        "explain_assignment": "explain_assignment",
        "app_action": "request_app_action",
        "work_data": "answer_work_data",
        "pause": "pause_companion",
        "clarify": "clarify_request"
    },
)
work_companion_builder.add_edge("focus_work", "wait_for_user")
work_companion_builder.add_edge("work_guidance", "wait_for_user")
work_companion_builder.add_edge("clarify_request", "wait_for_user")
work_companion_builder.add_edge("work_overview", "wait_for_user")
work_companion_builder.add_edge("work_update", "refresh_after_work_update")
work_companion_builder.add_edge("refresh_after_work_update", "wait_for_user")
work_companion_builder.add_edge("reprioritize_work", "wait_for_user")
work_companion_builder.add_edge("schedule_work", "wait_for_user")
work_companion_builder.add_edge("calendar_inquiry", "wait_for_user")
work_companion_builder.add_edge("delegate_work", "wait_for_user")
work_companion_builder.add_edge("confirm_delegation", "wait_for_user")
work_companion_builder.add_edge("explain_assignment", "wait_for_user")
work_companion_builder.add_edge("request_app_action", "wait_for_user")
work_companion_builder.add_edge("answer_work_data", "wait_for_user")
work_companion_builder.add_conditional_edges(
    "handle_schedule_approval",
    route_schedule_approval,
    {
        "create_events": "create_approved_calendar_events",
        "modify": "modify_schedule_proposal",
        "wait_for_user": "wait_for_user"
    }
)

work_companion_builder.add_edge("create_approved_calendar_events", "wait_for_user")
work_companion_builder.add_edge("modify_schedule_proposal", "wait_for_user")
work_companion_builder.add_edge("pause_companion", END)

graph = work_companion_builder.compile()
# graph = work_companion_builder.compile(checkpointer=InMemorySaver())

# Can you help me schedule my prioritized tasks for my current shift based on my Google Calendar availability?

# work_session_id="00dc1070-499f-408f-b58f-15c6c93c4717",
# employee_id="b1a70fb7-4b01-4a01-9972-31e586dc1378",
# organization_id="90244cc2-7441-4484-96dd-1d6f68e47b77",
# workspace_id="4c7facc7-3375-4fda-9bc6-6a65637cc626"
# shift_instance_id="304f3e77-04da-449d-bc5a-058bae9de9c7"
# 00dc1070-499f-408f-b58f-15c6c93c4717	90244cc2-7441-4484-96dd-1d6f68e47b77	4c7facc7-3375-4fda-9bc6-6a65637cc626	b1a70fb7-4b01-4a01-9972-31e586dc1378	304f3e77-04da-449d-bc5a-058bae9de9c7	2026-10-09 23:12:40.634 +0800		ww-work-00dc1070-499f-408f-b58f-15c6c93c4717	ACTIVE	2026-10-09 23:12:40.634 +0800	2026-10-09 23:12:40.634 +0800	1