"""HTTP transport for the demo entry slice (blueprint/07-api-contracts.md §Identity, catalog).

Session transport: one HttpOnly, SameSite=Lax `__session` cookie scoped to the API path (see
app/api/session_cookie.py): the run currently in use plus this visitor's run per company, so each
company resumes independently. One cookie because Firebase Hosting forwards only `__session`.
State-changing requests must send X-WorkWeave-Client (forces a CORS preflight cross-origin).
"""

import json
from datetime import date
from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.config import get_settings
from app.db import transaction
from app.errors import ApiError
from app.integrations import calendar_service
from app.api import session_cookie
from app.services import access, assignment, companion, demo_clock, exit_kt_ai, handover_ai, companion_turns, curriculum_authoring, curriculum_revisions, exit_kt, handover, knowledge, reviews, curricula, demo, engine_turns, notifications, onboarding, usage, voice, work_commands, work_sync

router = APIRouter()


def envelope(request: Request, data: Any) -> dict[str, Any]:
    return {"request_id": str(request.state.request_id), "data": data}


def require_client_header(request: Request) -> None:
    if request.headers.get("x-workweave-client") != "web":
        raise ApiError("FORBIDDEN", "Missing client header.")


def token(request: Request) -> str | None:
    """The current run's session token (from the __session cookie)."""
    return session_cookie.read(request).current


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "workweave-api", "scope": "demo-entry slice"}


@router.get("/scenarios")
def scenarios(request: Request) -> dict[str, Any]:
    with transaction() as conn:
        return envelope(request, [demo.scenario_card(s) for s in demo.repo.ready_catalog(conn)])


class OpenSession(BaseModel):
    scenario_id: str = Field(max_length=64)
    intent: Literal["RESUME", "FRESH"] = "RESUME"
    pack_version: str | None = Field(default=None, max_length=64)


@router.post("/demo-sessions", dependencies=[Depends(require_client_header)])
def open_session(body: OpenSession, request: Request, response: Response) -> dict[str, Any]:
    jar = session_cookie.read(request)
    runs = jar.runs
    with transaction() as conn:
        # The run cookie is looked up by the catalog's company key, resolved server-side.
        scenario = next((s for s in demo.repo.ready_catalog(conn) if str(s["scenario_id"]) == body.scenario_id), None)
        run_token = runs.get(scenario["company_key"]) if scenario else None
        code = access.valid_code(conn, jar.access)
        opened = demo.open_session(conn, body.scenario_id, body.intent, body.pack_version, run_token, request.state.request_id, code)
    # Cookies change only after the transaction committed.
    jar.current = opened.token
    jar.runs.pop(opened.company_key, None)  # re-insert last: the cookie keeps the most recent runs
    jar.runs[opened.company_key] = opened.token
    session_cookie.write(response, jar)
    return envelope(request, {**opened.dto, "resumed": opened.resumed})


@router.get("/demo-sessions/current")
def current(request: Request) -> dict[str, Any]:
    with transaction() as conn:
        r = demo.resolve(conn, token(request), required=False)
        return envelope(request, demo.session_dto(conn, r) if r else None)


@router.delete("/demo-sessions/current", dependencies=[Depends(require_client_header)])
def leave(request: Request, response: Response) -> dict[str, Any]:
    """PROPOSED: stop using the current run in this browser. The run itself stays resumable."""
    jar = session_cookie.read(request)
    jar.current = None  # this company's run stays resumable from the catalog
    session_cookie.write(response, jar)
    return envelope(request, None)


@router.get("/demo-sessions/runs")
def visitor_runs(request: Request) -> dict[str, Any]:
    """PROPOSED: this visitor's resumable runs (catalog 'Run in progress' and Resume)."""
    with transaction() as conn:
        jar = session_cookie.read(request)
        out = demo.runs(conn, jar.runs)
        current = demo.try_resolve(conn, jar.current)
        for r in out:
            r["is_active_session"] = bool(current and str(current.session["workspace_id"]) == r["workspace_id"])
        return envelope(request, out)


def _jar_hashes(jar: session_cookie.SessionCookie) -> list[str]:
    return [demo.hash_token(t) for t in {jar.current, *jar.runs.values()} if t]


class AccessBody(BaseModel):
    code: str = Field(min_length=1, max_length=64)


@router.get("/demo-access")
def get_access(request: Request) -> dict[str, Any]:
    """This browser's evaluator access, even before a company is opened."""
    with transaction() as conn:
        return envelope(request, access.dto(access.valid_code(conn, session_cookie.read(request).access)))


@router.get("/notifications")
def list_notifications(request: Request) -> dict[str, Any]:
    """This persona's inbox (backend-mediated Firestore projection, ADR-048). Reading changes nothing else."""
    return envelope(request, notifications.list_mine(token(request)))


@router.patch("/notifications/{notification_id}/read", dependencies=[Depends(require_client_header)])
def read_notification(notification_id: str, request: Request) -> dict[str, Any]:
    """Sets only the read marker; it doesn't accept work, acknowledge a handover or approve anything."""
    return envelope(request, notifications.mark_read(token(request), notification_id))


@router.get("/demo-usage")
def demo_usage(request: Request) -> dict[str, Any]:
    """The daily caps for this browser's tier, and the open run's use of them today."""
    jar = session_cookie.read(request)
    with transaction() as conn:
        r = demo.try_resolve(conn, jar.current)
        return envelope(request, usage.summary(conn, r.session if r else None, access.valid_code(conn, jar.access)))


@router.post("/demo-access", dependencies=[Depends(require_client_header)])
def redeem_access(body: AccessBody, request: Request, response: Response) -> dict[str, Any]:
    """Evaluator access code (ADR-029): upgrades this browser's runs and its future ones."""
    jar = session_cookie.read(request)
    normalized, code = access.redeem(body.code, _jar_hashes(jar))
    jar.access = normalized
    session_cookie.write(response, jar)
    return envelope(request, access.dto(code))


@router.delete("/demo-access", dependencies=[Depends(require_client_header)])
def release_access(request: Request, response: Response) -> dict[str, Any]:
    """Stop using evaluator access in this browser (its runs become public runs again)."""
    jar = session_cookie.read(request)
    access.release(_jar_hashes(jar))
    jar.access = None
    session_cookie.write(response, jar)
    return envelope(request, access.dto(None))


class SwitchPersona(BaseModel):
    employee_id: str = Field(max_length=64)


@router.post("/demo-sessions/current/persona", dependencies=[Depends(require_client_header)])
def switch_persona(body: SwitchPersona, request: Request) -> dict[str, Any]:
    with transaction() as conn:
        return envelope(request, demo.switch_persona(conn, token(request), body.employee_id, request.state.request_id))


@router.get("/personas")
def personas(request: Request) -> dict[str, Any]:
    with transaction() as conn:
        return envelope(request, demo.list_personas(conn, token(request)))




@router.get("/onboarding")
def onboarding_overview(request: Request) -> dict[str, Any]:
    with transaction() as conn:
        return envelope(request, onboarding.overview(conn, token(request)))


@router.get("/capabilities")
def get_capabilities(request: Request) -> dict[str, Any]:
    return envelope(request, voice.capabilities())


class ListenBody(BaseModel):
    mode: Literal["TAP", "HANDS_FREE"] = "TAP"


@router.post("/onboarding/sessions/{session_id}/voice/listen", dependencies=[Depends(require_client_header)])
def voice_listen(session_id: str, body: ListenBody, request: Request) -> dict[str, Any]:
    # Not wrapped in a transaction: the service authorizes in a short one, then calls Gemini.
    return envelope(request, voice.listen_grant(token(request), session_id, body.mode))


@router.get("/onboarding/sessions/{session_id}/voice/speech/{message_id}")
def voice_speech(session_id: str, message_id: str, request: Request) -> Response:
    audio = voice.speech(token(request), session_id, message_id)
    return Response(content=audio, media_type="audio/wav", headers={"Cache-Control": "private, no-store"})


@router.get("/onboarding/sessions/{session_id}/voice/speech/{message_id}/stream")
def voice_speech_stream(session_id: str, message_id: str, request: Request) -> StreamingResponse:
    """Raw 16-bit mono PCM (rate in X-Sample-Rate) streamed as Gemini generates it."""
    stream = voice.speech_stream(token(request), session_id, message_id)
    return StreamingResponse(
        stream.chunks,
        media_type=f"audio/L16;rate={stream.rate};channels=1",
        headers={"Cache-Control": "private, no-store, no-transform", "X-Accel-Buffering": "no", "X-Sample-Rate": str(stream.rate)},
    )


# ---------------------------------------------------------------- Work Companion (reads + shell + voice)
@router.get("/work-state")
def work_state(request: Request) -> dict[str, Any]:
    with transaction() as conn:
        return envelope(request, companion.dashboard(conn, token(request)))


@router.get("/assignments")
def assignments(request: Request) -> dict[str, Any]:
    with transaction() as conn:
        return envelope(request, companion.items(conn, token(request)))


@router.get("/work-events")
def work_events(request: Request) -> dict[str, Any]:
    with transaction() as conn:
        return envelope(request, companion.events(conn, token(request)))


@router.post("/work-sessions", dependencies=[Depends(require_client_header)])
def start_work_session(request: Request) -> dict[str, Any]:
    """Opens (or resumes) the session; with the AI engine connected, its opening brief (ADR-034)."""
    with transaction() as conn:
        view = companion.start_session(conn, token(request))
    if companion_turns.engine() is None:
        return envelope(request, view)
    return envelope(request, companion_turns.ensure_opening(token(request), view["work_session_id"]))


@router.get("/work-sessions/{work_session_id}")
def get_work_session(work_session_id: str, request: Request) -> dict[str, Any]:
    with transaction() as conn:
        return envelope(request, companion.get_session(conn, token(request), work_session_id))


@router.get("/calendar/status")
def calendar_status(request: Request) -> dict[str, Any]:
    """Whether the calendar service is signed in to Google (the page polls it while the employee signs in)."""
    return envelope(request, companion_turns.calendar_status(token(request)))


_SIGN_IN_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Google Calendar</title><style>body{{font:16px/1.5 system-ui,sans-serif;margin:0;display:grid;place-items:center;min-height:100vh;background:#f6f8f6;color:#1d2b22}}
main{{max-width:28rem;padding:24px}}h1{{font-size:1.15rem;margin:0 0 8px}}</style></head>
<body><main><h1>{title}</h1><p>{text}</p></main>{script}</body></html>"""
_SIGN_IN_OUTCOMES = {
    "CONNECTED": ("Google Calendar is connected", "You can close this window and go back to WorkWeave."),
    "WRONG_ACCOUNT": ("That account can't be used here", "This demo connects only its own test calendar account. Close this window and sign in with that account."),
    "EXPIRED": ("The sign-in expired", "Close this window and select Connect Google Calendar again."),
    "CANCELLED": ("Google Calendar wasn't connected", "The sign-in was cancelled. Close this window to go back to WorkWeave."),
    "FAILED": ("Google Calendar wasn't connected", "Couldn't do that because an error was encountered. Close this window and try again."),
}


def _sign_in_page(outcome: str) -> Response:
    title, text_ = _SIGN_IN_OUTCOMES[outcome]
    script = "<script>setTimeout(function(){window.close()},1500)</script>" if outcome == "CONNECTED" else ""
    return Response(_SIGN_IN_PAGE.format(title=title, text=text_, script=script), media_type="text/html",
                    status_code=200 if outcome == "CONNECTED" else 400, headers={"Cache-Control": "no-store"})


@router.get("/calendar/auth/google")
def calendar_sign_in(request: Request) -> Response:
    """Opens Google sign-in for the Companion's calendar through the API (ADR-052): the calendar
    service listens on localhost only. Needs a persona with work access."""
    url = companion_turns.calendar_sign_in(token(request))
    if not url:
        return _sign_in_page("FAILED")
    return Response(status_code=302, headers={"Location": url, "Cache-Control": "no-store"})


@router.get("/calendar/auth/google/callback")
def calendar_sign_in_callback(request: Request) -> Response:
    """Google's redirect after sign-in; the calendar service checks the state and the account."""
    params = {k: v for k, v in request.query_params.items() if k in ("state", "code", "scope", "error", "authuser", "prompt", "iss")}
    if "error" in params:
        return _sign_in_page("CANCELLED")
    if not params.get("code") or not params.get("state"):
        return _sign_in_page("EXPIRED")
    return _sign_in_page(calendar_service.finish_sign_in(params))


@router.get("/work-sessions/{work_session_id}/guidance/{guidance_id}")
def work_guidance(work_session_id: str, guidance_id: str, request: Request) -> dict[str, Any]:
    with transaction() as conn:
        return envelope(request, companion_turns.guidance(conn, token(request), work_session_id, guidance_id))


class WorkMessageBody(BaseModel):
    client_turn_id: str = Field(max_length=64)
    expected_revision: int = Field(ge=1)
    text: str = Field(min_length=1, max_length=5000)
    input_kind: Literal["TEXT", "VOICE_TRANSCRIPT"] = "TEXT"


@router.post("/work-sessions/{work_session_id}/messages", dependencies=[Depends(require_client_header)])
def work_message(work_session_id: str, body: WorkMessageBody, request: Request) -> dict[str, Any]:
    if companion_turns.engine() is not None:
        # No transaction is held while the AI engine runs (it writes in its own transactions).
        return envelope(request, companion_turns.send(token(request), work_session_id, body.client_turn_id, body.expected_revision, body.text, body.input_kind, request.state.request_id))
    with transaction() as conn:
        return envelope(request, companion.send_message(conn, token(request), work_session_id))


@router.get("/work-sessions/{work_session_id}/voice/speech/{message_id}")
def work_voice_speech(work_session_id: str, message_id: str, request: Request) -> Response:
    audio = voice.work_speech(token(request), work_session_id, message_id)
    return Response(content=audio, media_type="audio/wav", headers={"Cache-Control": "private, no-store"})


@router.get("/work-sessions/{work_session_id}/voice/speech/{message_id}/stream")
def work_voice_speech_stream(work_session_id: str, message_id: str, request: Request) -> StreamingResponse:
    """A companion reply read aloud: raw 16-bit mono PCM (rate in X-Sample-Rate), streamed."""
    stream = voice.work_speech_stream(token(request), work_session_id, message_id)
    return StreamingResponse(
        stream.chunks,
        media_type=f"audio/L16;rate={stream.rate};channels=1",
        headers={"Cache-Control": "private, no-store, no-transform", "X-Accel-Buffering": "no", "X-Sample-Rate": str(stream.rate)},
    )


@router.post("/work-sessions/{work_session_id}/messages/stream", dependencies=[Depends(require_client_header)])
def work_message_stream(work_session_id: str, body: WorkMessageBody, request: Request) -> StreamingResponse:
    """The same message as /messages, answered as server-sent events: `progress` {label} while the AI
    engine works, then `done` {request_id, data: view} or `error` {request_id, error}."""
    rid = str(request.state.request_id)
    if companion_turns.engine() is not None:
        events = companion_turns.send_stream(token(request), work_session_id, body.client_turn_id, body.expected_revision, body.text, body.input_kind, request.state.request_id)
    else:
        def unavailable():
            try:
                with transaction() as conn:
                    yield "done", companion.send_message(conn, token(request), work_session_id)
            except ApiError as e:
                yield "error", {"code": e.code, "message": e.message, "retryable": e.retryable, **e.details}

        events = unavailable()

    def stream():
        for event, data in events:
            if event == "done":
                yield _sse("done", {"request_id": rid, "data": data})
            elif event == "error":
                yield _sse("error", {"request_id": rid, "error": data})
            else:
                yield _sse(event, data)

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-store, no-transform", "X-Accel-Buffering": "no"})


@router.post("/work-sessions/{work_session_id}/voice/listen", dependencies=[Depends(require_client_header)])
def work_voice_listen(work_session_id: str, body: ListenBody, request: Request) -> dict[str, Any]:
    return envelope(request, companion.listen_grant(token(request), work_session_id, body.mode))


# ---------------------------------------------------------------- Work Companion commands (ADR-032)
class CommandBody(BaseModel):
    idempotency_key: str = Field(min_length=1, max_length=128)
    expected_revision: int | None = Field(default=None, ge=1)


class WorkReportBody(CommandBody):
    reported_status: Literal["IN_PROGRESS", "BLOCKED", "DONE"]
    description: str = Field(min_length=1, max_length=2000)


@router.post("/work-items/{work_item_id}/reports", dependencies=[Depends(require_client_header)])
def work_report(work_item_id: str, body: WorkReportBody, request: Request) -> dict[str, Any]:
    """What the employee says about the item; it never changes the ticket's status (ADR-033)."""
    with transaction() as conn:
        return envelope(request, work_sync.report(conn, token(request), work_item_id, body.reported_status, body.description, body.idempotency_key, body.expected_revision, request.state.request_id))


class ReassignBody(CommandBody):
    employee_id: str = Field(min_length=1, max_length=64)


@router.get("/work-items/{work_item_id}/assignment")
def work_assignment(work_item_id: str, request: Request) -> dict[str, Any]:
    """Why the ticket went to its assignee (the assignee, or the lead of the shift in progress; ADR-035)."""
    with transaction() as conn:
        return envelope(request, assignment.explain(conn, token(request), work_item_id))


@router.get("/work-items/{work_item_id}/assignment-candidates")
def work_assignment_candidates(work_item_id: str, request: Request) -> dict[str, Any]:
    with transaction() as conn:
        return envelope(request, assignment.candidates(conn, token(request), work_item_id))


@router.post("/work-items/{work_item_id}/assignee", dependencies=[Depends(require_client_header)])
def work_reassign(work_item_id: str, body: ReassignBody, request: Request) -> dict[str, Any]:
    """The shift lead overrides who works on the ticket (ADR-035)."""
    with transaction() as conn:
        return envelope(request, assignment.reassign(conn, token(request), work_item_id, body.employee_id, body.idempotency_key, body.expected_revision, request.state.request_id))


# ---------------------------------------------------------------- Shift Handover (owner decisions 2026-10-10)
class SectionBody(CommandBody):
    content: str = Field(default="", max_length=8000)
    declaration: Literal["UNKNOWN_WITH_FOLLOW_UP", "NOT_APPLICABLE"] | None = None
    reason: str = Field(default="", max_length=2000)


class SuggestionBody(CommandBody):
    handover_id: str = Field(min_length=1, max_length=64)
    mode: Literal["APPLY", "REPORT_ONLY", "VALIDATE_COMPLETION"] = "APPLY"
    note: str | None = Field(default=None, max_length=4000)


class TemplateSectionBody(BaseModel):
    section_id: str | None = Field(default=None, max_length=64)
    name: str = Field(max_length=120)
    is_required: bool = False


class TemplateBody(CommandBody):
    sections: list[TemplateSectionBody] = Field(min_length=1, max_length=20)


class AckBody(BaseModel):
    idempotency_key: str = Field(min_length=1, max_length=128)
    comment: str = Field(default="", max_length=2000)


@router.post("/handovers/active", dependencies=[Depends(require_client_header)])
def handover_active(request: Request) -> dict[str, Any]:
    """The handover from the team's shift in progress; its lead's first open creates the draft."""
    with transaction() as conn:
        return envelope(request, handover.workspace(conn, token(request)))


@router.patch("/handovers/{handover_id}/sections/{section_id}", dependencies=[Depends(require_client_header)])
def handover_section(handover_id: str, section_id: str, body: SectionBody, request: Request) -> dict[str, Any]:
    with transaction() as conn:
        return envelope(request, handover.edit_section(conn, token(request), handover_id, section_id, body.content, body.declaration, body.reason, body.idempotency_key, body.expected_revision, request.state.request_id))


@router.post("/handover-suggestions/{suggestion_id}/accept", dependencies=[Depends(require_client_header)])
def handover_accept(suggestion_id: str, body: SuggestionBody, request: Request) -> dict[str, Any]:
    with transaction() as conn:
        return envelope(request, handover.accept_suggestion(conn, token(request), body.handover_id, suggestion_id, body.mode, body.note, body.idempotency_key, body.expected_revision, request.state.request_id))


@router.post("/handover-suggestions/{suggestion_id}/ignore", dependencies=[Depends(require_client_header)])
def handover_ignore(suggestion_id: str, body: SuggestionBody, request: Request) -> dict[str, Any]:
    with transaction() as conn:
        return envelope(request, handover.ignore_suggestion(conn, token(request), body.handover_id, suggestion_id, body.idempotency_key, body.expected_revision, request.state.request_id))


@router.post("/handovers/{handover_id}/template-versions", dependencies=[Depends(require_client_header)])
def handover_template(handover_id: str, body: TemplateBody, request: Request) -> dict[str, Any]:
    with transaction() as conn:
        return envelope(request, handover.create_template_version(conn, token(request), handover_id, [x.model_dump() for x in body.sections], body.idempotency_key, body.expected_revision, request.state.request_id))


@router.post("/handovers/{handover_id}/publish", dependencies=[Depends(require_client_header)])
def handover_publish(handover_id: str, body: CommandBody, request: Request) -> dict[str, Any]:
    with transaction() as conn:
        return envelope(request, handover.publish(conn, token(request), handover_id, body.idempotency_key, body.expected_revision, request.state.request_id))


@router.post("/handover-publications/{publication_id}/receipt", dependencies=[Depends(require_client_header)])
def handover_receipt(publication_id: str, body: AckBody, request: Request) -> dict[str, Any]:
    with transaction() as conn:
        return envelope(request, handover.confirm_receipt(conn, token(request), publication_id, body.idempotency_key, request.state.request_id))


@router.post("/handover-acknowledgements/{cycle_id}/{decision}", dependencies=[Depends(require_client_header)])
def handover_ack(cycle_id: str, decision: Literal["acknowledge", "dispute"], body: AckBody, request: Request) -> dict[str, Any]:
    with transaction() as conn:
        return envelope(request, handover.respond(conn, token(request), cycle_id, decision.upper(), body.comment, body.idempotency_key, request.state.request_id))


class CopilotBody(BaseModel):
    idempotency_key: str = Field(min_length=1, max_length=128)
    text: str = Field(default="", max_length=4000)


class SectionDraftsBody(BaseModel):
    section_ids: list[str] = Field(default_factory=list, max_length=20)


@router.post("/handovers/{handover_id}/copilot", dependencies=[Depends(require_client_header)])
def handover_copilot(handover_id: str, body: CopilotBody, request: Request) -> dict[str, Any]:
    """A turn with the handover graph (docs/31); an empty message asks for the incoming lead's brief.
    The graph runs outside any transaction; the conversation is stored only when it answers."""
    return envelope(request, handover_ai.ask(token(request), body.text, body.idempotency_key, request.state.request_id))


def _pcm(stream: Any) -> StreamingResponse:
    return StreamingResponse(
        stream.chunks,
        media_type=f"audio/L16;rate={stream.rate};channels=1",
        headers={"Cache-Control": "private, no-store, no-transform", "X-Accel-Buffering": "no", "X-Sample-Rate": str(stream.rate)},
    )


@router.post("/handover/voice/listen", dependencies=[Depends(require_client_header)])
def handover_voice_listen(body: ListenBody, request: Request) -> dict[str, Any]:
    """Voice input for the handover copilot (ADR-045): shift leads only, the same caps as onboarding."""
    return envelope(request, voice.handover_listen_grant(token(request), body.mode))


@router.get("/handover/voice/speech/{message_id}/stream")
def handover_voice_speech(message_id: str, request: Request) -> StreamingResponse:
    """A copilot answer from this lead's own conversation, read aloud (raw PCM, rate in X-Sample-Rate)."""
    return _pcm(voice.handover_speech_stream(token(request), message_id))


@router.post("/exit-kt/voice/listen", dependencies=[Depends(require_client_header)])
def kt_voice_listen(body: ListenBody, request: Request) -> dict[str, Any]:
    """Voice input for the Exit KT copilot and the employee's interview (ADR-045). Audio is never stored."""
    return envelope(request, voice.kt_listen_grant(token(request), body.mode))


@router.get("/exit-kt/voice/speech/{message_id}/stream")
def kt_voice_speech(message_id: str, request: Request) -> StreamingResponse:
    """A copilot answer or interview question from this person's own conversation, read aloud."""
    return _pcm(voice.kt_speech_stream(token(request), message_id))


@router.post("/handovers/{handover_id}/gap-check", dependencies=[Depends(require_client_header)])
def handover_gap_check(handover_id: str, body: AckBody, request: Request) -> dict[str, Any]:
    return envelope(request, handover_ai.check(token(request), body.idempotency_key, request.state.request_id))


@router.post("/handovers/{handover_id}/section-drafts", dependencies=[Depends(require_client_header)])
def handover_section_drafts(handover_id: str, body: SectionDraftsBody, request: Request) -> dict[str, Any]:
    """Proposed section text for the editor; nothing is stored until the lead saves the section."""
    return envelope(request, handover_ai.draft(token(request), body.section_ids))


# ---------------------------------------------------------------- demo shift clock (ADR-042): evaluator tool, visitor runs only
class ShiftClockBody(BaseModel):
    idempotency_key: str = Field(min_length=1, max_length=128)
    confirm_unpublished: bool = False


@router.get("/demo-sessions/current/shift-clock")
def shift_clock(request: Request) -> dict[str, Any]:
    with transaction() as conn:
        return envelope(request, demo_clock.status(conn, token(request)))


@router.post("/demo-sessions/current/shift-clock/advance", dependencies=[Depends(require_client_header)])
def shift_clock_advance(body: ShiftClockBody, request: Request) -> dict[str, Any]:
    with transaction() as conn:
        return envelope(request, demo_clock.advance(conn, token(request), body.confirm_unpublished, body.idempotency_key, request.state.request_id))


# ---------------------------------------------------------------- Reviews (ADR-041)
class NoteDecisionBody(BaseModel):
    idempotency_key: str = Field(min_length=1, max_length=128)
    decision: Literal["APPROVE", "REJECT"]
    comment: str = Field(default="", max_length=2000)


@router.get("/reviews")
def review_queue(request: Request) -> dict[str, Any]:
    with transaction() as conn:
        return envelope(request, reviews.queue(conn, token(request)))


@router.post("/memory-drafts/{draft_id}/decision", dependencies=[Depends(require_client_header)])
def memory_draft_decision(draft_id: str, body: NoteDecisionBody, request: Request) -> dict[str, Any]:
    with transaction() as conn:
        return envelope(request, reviews.decide_note(conn, token(request), draft_id, body.decision, body.comment, body.idempotency_key, request.state.request_id))


# ---------------------------------------------------------------- Knowledge (owner decision 2026-10-10, ADR-040)
@router.get("/knowledge/timeline")
def knowledge_timeline(request: Request) -> dict[str, Any]:
    """Approved document versions (current and superseded) and approved notes this reader may see."""
    with transaction() as conn:
        return envelope(request, knowledge.timeline(conn, token(request)))


@router.get("/knowledge/documents")
def knowledge_documents(request: Request) -> dict[str, Any]:
    with transaction() as conn:
        return envelope(request, knowledge.documents(conn, token(request)))


@router.get("/knowledge/documents/{document_version_id}")
def knowledge_document(document_version_id: str, request: Request) -> dict[str, Any]:
    with transaction() as conn:
        return envelope(request, knowledge.content(conn, token(request), document_version_id))


# ---------------------------------------------------------------- Exit KT (owner decisions 2026-10-10, ADR-039)
class KtItemBody(CommandBody):
    title: str = Field(max_length=200)
    description: str = Field(default="", max_length=4000)


class KtFindingBody(CommandBody):
    decision: Literal["CONFIRM", "DISMISS", "RESOLVE"]
    reason: str = Field(default="", max_length=2000)


class KtArtifactBody(CommandBody):
    title: str = Field(default="", max_length=200)
    content: str = Field(max_length=20000)


class KtRevisionBody(CommandBody):
    artifact_revision_id: str = Field(min_length=1, max_length=64)
    audience: Literal["TEAM", "ORGANIZATION"] = "TEAM"
    decision: Literal["APPROVE", "REQUEST_REVISION", "REJECT"] = "APPROVE"
    comment: str = Field(default="", max_length=4000)


class KtOwnerBody(CommandBody):
    final_owner_employee_id: str = Field(min_length=1, max_length=64)


class KtPackageDecisionBody(CommandBody):
    decision: Literal["APPROVE", "REJECT"]
    comment: str = Field(default="", max_length=4000)


class KtChecklistBody(CommandBody):
    evidence_ref: str = Field(default="", max_length=200)
    reason: str = Field(default="", max_length=2000)


def _kt(request: Request, fn, *args) -> dict[str, Any]:
    with transaction() as conn:
        return envelope(request, fn(conn, token(request), *args))


@router.get("/exit-kt/case")
def kt_case(request: Request) -> dict[str, Any]:
    """The Exit KT case this persona takes part in (null when none), filtered by their role."""
    return _kt(request, exit_kt.get_case)


class KtTextBody(BaseModel):
    idempotency_key: str = Field(default="", max_length=128)
    text: str = Field(default="", max_length=4000)
    consent: bool = False


class KtPlanBody(CommandBody):
    required: bool = True


@router.post("/exit-kt/discovery", dependencies=[Depends(require_client_header)])
def kt_discovery(body: AckBody, request: Request) -> dict[str, Any]:
    """The graph reconstructs the inventory (docs/32); it runs outside any transaction and only proposes."""
    return envelope(request, exit_kt_ai.discover(token(request), body.idempotency_key, request.state.request_id))


@router.post("/exit-kt/recommendations", dependencies=[Depends(require_client_header)])
def kt_recommend(body: AckBody, request: Request) -> dict[str, Any]:
    return envelope(request, exit_kt_ai.recommend(token(request), body.idempotency_key, request.state.request_id))


@router.post("/exit-kt/plan/{item_id}/{decision}", dependencies=[Depends(require_client_header)])
def kt_plan_item(item_id: str, decision: Literal["accept", "decline"], body: KtPlanBody, request: Request) -> dict[str, Any]:
    return _kt(request, exit_kt_ai.decide_plan_item, item_id, decision.upper(), body.required, body.idempotency_key, body.expected_revision, request.state.request_id)


@router.post("/exit-kt/copilot", dependencies=[Depends(require_client_header)])
def kt_copilot(body: KtTextBody, request: Request) -> dict[str, Any]:
    return envelope(request, exit_kt_ai.ask(token(request), body.text, body.idempotency_key or "", request.state.request_id))


class KtCaseBody(BaseModel):
    idempotency_key: str = Field(min_length=1, max_length=128)
    employee_id: str = Field(min_length=1, max_length=64)
    case_kind: Literal["DEPARTURE", "ROLE_TRANSITION"]
    final_working_date: date | None = None


class KtSuccessorBody(CommandBody):
    successor_employee_id: str = Field(min_length=1, max_length=64)


@router.post("/exit-kt/cases", dependencies=[Depends(require_client_header)])
def kt_new_case(body: KtCaseBody, request: Request) -> dict[str, Any]:
    """The manager opens a case (docs/32); resignation and retirement are departures, transfers and role changes are role transitions."""
    return _kt(request, exit_kt.create_case, body.employee_id, body.case_kind, body.final_working_date, body.idempotency_key, request.state.request_id)


@router.post("/exit-kt/successor", dependencies=[Depends(require_client_header)])
def kt_assign_successor(body: KtSuccessorBody, request: Request) -> dict[str, Any]:
    return _kt(request, exit_kt.assign_successor, body.successor_employee_id, body.idempotency_key, body.expected_revision, request.state.request_id)


@router.post("/exit-kt/interviews/{interview_id}/messages", dependencies=[Depends(require_client_header)])
def kt_interview_message(interview_id: str, body: KtTextBody, request: Request) -> dict[str, Any]:
    return envelope(request, exit_kt_ai.answer_interview(token(request), interview_id, body.text, request.state.request_id))


@router.post("/exit-kt/interviews/{interview_id}/draft", dependencies=[Depends(require_client_header)])
def kt_interview_draft(interview_id: str, request: Request) -> dict[str, Any]:
    return envelope(request, exit_kt_ai.draft_from_interview(token(request), interview_id, request.state.request_id))


@router.post("/exit-kt/knowledge-items", dependencies=[Depends(require_client_header)])
def kt_add_item(body: KtItemBody, request: Request) -> dict[str, Any]:
    return _kt(request, exit_kt.add_knowledge_item, body.title, body.description, body.idempotency_key, body.expected_revision, request.state.request_id)


@router.post("/exit-kt/knowledge-items/{kt_item_id}/link-existing", dependencies=[Depends(require_client_header)])
def kt_link(kt_item_id: str, body: CommandBody, request: Request) -> dict[str, Any]:
    return _kt(request, exit_kt.link_existing, kt_item_id, body.idempotency_key, body.expected_revision, request.state.request_id)


@router.post("/exit-kt/knowledge-items/{kt_item_id}/interview", dependencies=[Depends(require_client_header)])
def kt_start_interview(kt_item_id: str, body: KtTextBody, request: Request) -> dict[str, Any]:
    """The employee's own targeted interview, after accepting the purpose, audience and retention notice."""
    return envelope(request, exit_kt_ai.start_interview(token(request), kt_item_id, body.consent, body.idempotency_key, request.state.request_id))


@router.post("/exit-kt/knowledge-items/{kt_item_id}/artifacts", dependencies=[Depends(require_client_header)])
def kt_create_artifact(kt_item_id: str, body: KtArtifactBody, request: Request) -> dict[str, Any]:
    return _kt(request, exit_kt.create_artifact, kt_item_id, body.title, body.content, body.idempotency_key, body.expected_revision, request.state.request_id)


@router.post("/exit-kt/findings/{finding_id}/review", dependencies=[Depends(require_client_header)])
def kt_review_finding(finding_id: str, body: KtFindingBody, request: Request) -> dict[str, Any]:
    return _kt(request, exit_kt.review_finding, finding_id, body.decision, body.reason, body.idempotency_key, body.expected_revision, request.state.request_id)


@router.patch("/exit-kt/artifacts/{artifact_id}", dependencies=[Depends(require_client_header)])
def kt_edit_artifact(artifact_id: str, body: KtArtifactBody, request: Request) -> dict[str, Any]:
    return _kt(request, exit_kt.edit_artifact, artifact_id, body.content, body.idempotency_key, body.expected_revision, request.state.request_id)


@router.post("/exit-kt/artifacts/{artifact_id}/submit", dependencies=[Depends(require_client_header)])
def kt_submit_artifact(artifact_id: str, body: KtRevisionBody, request: Request) -> dict[str, Any]:
    return _kt(request, exit_kt.submit_artifact, artifact_id, body.artifact_revision_id, body.audience, body.idempotency_key, body.expected_revision, request.state.request_id)


@router.post("/exit-kt/artifacts/{artifact_id}/decision", dependencies=[Depends(require_client_header)])
def kt_decide_artifact(artifact_id: str, body: KtRevisionBody, request: Request) -> dict[str, Any]:
    return _kt(request, exit_kt.decide_artifact, artifact_id, body.artifact_revision_id, body.decision, body.comment, body.idempotency_key, body.expected_revision, request.state.request_id)


@router.post("/exit-kt/artifacts/{artifact_id}/promote", dependencies=[Depends(require_client_header)])
def kt_promote(artifact_id: str, body: KtRevisionBody, request: Request) -> dict[str, Any]:
    return _kt(request, exit_kt.promote_artifact, artifact_id, body.artifact_revision_id, body.idempotency_key, body.expected_revision, request.state.request_id)


@router.patch("/exit-kt/transfers/{transfer_id}", dependencies=[Depends(require_client_header)])
def kt_edit_transfer(transfer_id: str, body: KtOwnerBody, request: Request) -> dict[str, Any]:
    return _kt(request, exit_kt.edit_transfer, transfer_id, body.final_owner_employee_id, body.idempotency_key, body.expected_revision, request.state.request_id)


@router.post("/exit-kt/transfers/{transfer_id}/effective-time", dependencies=[Depends(require_client_header)])
def kt_effective_time(transfer_id: str, body: CommandBody, request: Request) -> dict[str, Any]:
    return _kt(request, exit_kt.review_effective_time, transfer_id, body.idempotency_key, body.expected_revision, request.state.request_id)


@router.post("/exit-kt/transfers/{transfer_id}/confirm", dependencies=[Depends(require_client_header)])
def kt_confirm_transfer(transfer_id: str, body: CommandBody, request: Request) -> dict[str, Any]:
    return _kt(request, exit_kt.confirm_transfer, transfer_id, body.idempotency_key, body.expected_revision, request.state.request_id)


@router.post("/exit-kt/package/assemble", dependencies=[Depends(require_client_header)])
def kt_assemble(body: CommandBody, request: Request) -> dict[str, Any]:
    return _kt(request, exit_kt.assemble_package, body.idempotency_key, body.expected_revision, request.state.request_id)


@router.post("/exit-kt/package/submit", dependencies=[Depends(require_client_header)])
def kt_submit_package(body: CommandBody, request: Request) -> dict[str, Any]:
    return _kt(request, exit_kt.submit_package, body.idempotency_key, body.expected_revision, request.state.request_id)


@router.post("/exit-kt/package/decision", dependencies=[Depends(require_client_header)])
def kt_decide_package(body: KtPackageDecisionBody, request: Request) -> dict[str, Any]:
    return _kt(request, exit_kt.decide_package, body.decision, body.comment, body.idempotency_key, body.expected_revision, request.state.request_id)


@router.post("/exit-kt/package/versions/{package_version_id}/receipt", dependencies=[Depends(require_client_header)])
def kt_receive(package_version_id: str, body: CommandBody, request: Request) -> dict[str, Any]:
    return _kt(request, exit_kt.receive_package, package_version_id, body.idempotency_key, request.state.request_id)


@router.post("/exit-kt/package/questions", dependencies=[Depends(require_client_header)])
def kt_ask_package(body: KtTextBody, request: Request) -> dict[str, Any]:
    """The successor's questions about the approved package (docs/32)."""
    return envelope(request, exit_kt_ai.ask(token(request), body.text, body.idempotency_key or "", request.state.request_id))


@router.post("/exit-kt/checklist/{item_id}/resolve", dependencies=[Depends(require_client_header)])
def kt_resolve(item_id: str, body: KtChecklistBody, request: Request) -> dict[str, Any]:
    return _kt(request, exit_kt.resolve_checklist, item_id, body.evidence_ref, body.idempotency_key, body.expected_revision, request.state.request_id)


@router.post("/exit-kt/checklist/{item_id}/exception", dependencies=[Depends(require_client_header)])
def kt_exception(item_id: str, body: KtChecklistBody, request: Request) -> dict[str, Any]:
    return _kt(request, exit_kt.checklist_exception, item_id, body.reason, body.idempotency_key, body.expected_revision, request.state.request_id)


@router.post("/exit-kt/complete", dependencies=[Depends(require_client_header)])
def kt_complete(body: CommandBody, request: Request) -> dict[str, Any]:
    return _kt(request, exit_kt.complete_case, body.idempotency_key, body.expected_revision, request.state.request_id)


@router.get("/ticket-system")
def ticket_system(request: Request) -> dict[str, Any]:
    """The company's ticket tool, simulated for the demo: the tickets' real status."""
    with transaction() as conn:
        return envelope(request, work_sync.ticket_system(conn, token(request)))


class TicketStatusBody(CommandBody):
    status: Literal["IN_PROGRESS", "BLOCKED", "COMPLETED", "CANCELLED"]
    note: str = Field(default="", max_length=2000)


@router.post("/ticket-system/items/{work_item_id}/status", dependencies=[Depends(require_client_header)])
def ticket_status(work_item_id: str, body: TicketStatusBody, request: Request) -> dict[str, Any]:
    with transaction() as conn:
        return envelope(request, work_sync.update_ticket(conn, token(request), work_item_id, body.status, body.note, body.idempotency_key, body.expected_revision, request.state.request_id))


@router.get("/delegation-proposals")
def delegation_list(request: Request) -> dict[str, Any]:
    with transaction() as conn:
        return envelope(request, work_commands.list_proposals(conn, token(request)))


@router.get("/delegation-proposals/{proposal_id}")
def delegation_get(proposal_id: str, request: Request) -> dict[str, Any]:
    with transaction() as conn:
        return envelope(request, work_commands.get_proposal(conn, token(request), proposal_id))


class ProposalEditBody(CommandBody):
    work_item_id: str = Field(max_length=64)
    final_employee_id: str = Field(max_length=64)


@router.patch("/delegation-proposals/{proposal_id}", dependencies=[Depends(require_client_header)])
def delegation_edit(proposal_id: str, body: ProposalEditBody, request: Request) -> dict[str, Any]:
    with transaction() as conn:
        return envelope(request, work_commands.edit_proposal(conn, token(request), proposal_id, body.work_item_id, body.final_employee_id, body.idempotency_key, body.expected_revision, request.state.request_id))


@router.post("/delegation-proposals/{proposal_id}/confirm", dependencies=[Depends(require_client_header)])
def delegation_confirm(proposal_id: str, body: CommandBody, request: Request) -> dict[str, Any]:
    with transaction() as conn:
        return envelope(request, work_commands.confirm_proposal(conn, token(request), proposal_id, body.idempotency_key, body.expected_revision, request.state.request_id))


class RejectBody(CommandBody):
    reason: str = Field(default="", max_length=2000)


@router.post("/delegation-proposals/{proposal_id}/reject", dependencies=[Depends(require_client_header)])
def delegation_reject(proposal_id: str, body: RejectBody, request: Request) -> dict[str, Any]:
    with transaction() as conn:
        return envelope(request, work_commands.reject_proposal(conn, token(request), proposal_id, body.reason, body.idempotency_key, body.expected_revision, request.state.request_id))


@router.get("/memory-drafts")
def memory_drafts(request: Request) -> dict[str, Any]:
    with transaction() as conn:
        return envelope(request, work_commands.my_drafts(conn, token(request)))


class DraftBody(CommandBody):
    content: str = Field(min_length=1, max_length=5000)
    requested_audience: Literal["PRIVATE", "TEAM", "ORGANIZATION"] = "PRIVATE"


@router.post("/memory-drafts", dependencies=[Depends(require_client_header)])
def memory_draft_create(body: DraftBody, request: Request) -> dict[str, Any]:
    with transaction() as conn:
        return envelope(request, work_commands.create_draft(conn, token(request), body.content, body.requested_audience, body.idempotency_key, request.state.request_id))


@router.post("/memory-drafts/{draft_id}/review", dependencies=[Depends(require_client_header)])
def memory_draft_submit(draft_id: str, body: CommandBody, request: Request) -> dict[str, Any]:
    with transaction() as conn:
        return envelope(request, work_commands.submit_draft(conn, token(request), draft_id, body.idempotency_key, body.expected_revision, request.state.request_id))


@router.delete("/memory-drafts/{draft_id}", dependencies=[Depends(require_client_header)])
def memory_draft_delete(draft_id: str, request: Request, idempotency_key: str) -> dict[str, Any]:
    with transaction() as conn:
        return envelope(request, work_commands.delete_draft(conn, token(request), draft_id, idempotency_key, request.state.request_id))


@router.get("/curricula")
def curricula_catalog(request: Request) -> dict[str, Any]:
    with transaction() as conn:
        return envelope(request, curricula.catalog(conn, token(request)))


@router.get("/curricula/{curriculum_id}")
def curriculum_detail(curriculum_id: str, request: Request) -> dict[str, Any]:
    with transaction() as conn:
        return envelope(request, curricula.detail(conn, token(request), curriculum_id))


# ---------------------------------------------------------------- curriculum authoring (ADR-040)
class CurriculumCreateBody(BaseModel):
    idempotency_key: str = Field(min_length=1, max_length=128)
    name: str = Field(max_length=100)
    version: str = Field(max_length=30)
    description: str = Field(default="", max_length=300)


class CurriculumSourceBody(CommandBody):
    document_code: str = Field(max_length=40)
    title: str = Field(max_length=200)
    version: str = Field(max_length=30)
    document_type: Literal["SOP", "PROCEDURE", "GUIDE", "CHECKLIST", "REFERENCE"] = "SOP"
    filename: str = Field(max_length=200)
    content: str = Field(max_length=300_000)


class CurriculumReviewBody(CommandBody):
    decision: Literal["APPROVED", "REJECTED"]
    reason: str = Field(default="", max_length=2000)
    reviewed_exact_version: bool = False


class ObjectiveBody(CommandBody):
    description: str = Field(max_length=1000)
    assessment_criteria: str = Field(max_length=2000)


@router.post("/curricula", dependencies=[Depends(require_client_header)])
def curriculum_create(body: CurriculumCreateBody, request: Request) -> dict[str, Any]:
    with transaction() as conn:
        return envelope(request, curriculum_authoring.create(conn, token(request), body.name, body.version, body.description, body.idempotency_key, request.state.request_id))


@router.post("/curricula/{curriculum_id}/sources", dependencies=[Depends(require_client_header)])
def curriculum_add_source(curriculum_id: str, body: CurriculumSourceBody, request: Request) -> dict[str, Any]:
    """Uploads a Markdown source (its text, read in the browser) as a new version pending review."""
    with transaction() as conn:
        return envelope(request, curriculum_authoring.add_source(conn, token(request), curriculum_id, body.document_code, body.title, body.version, body.document_type,
                                                                 body.filename, body.content, body.idempotency_key, body.expected_revision, request.state.request_id))


@router.post("/curricula/{curriculum_id}/sources/{curriculum_source_id}/review", dependencies=[Depends(require_client_header)])
def curriculum_review_source(curriculum_id: str, curriculum_source_id: str, body: CurriculumReviewBody, request: Request, background: BackgroundTasks) -> dict[str, Any]:
    with transaction() as conn:
        out, job = curriculum_authoring.review(conn, token(request), curriculum_id, curriculum_source_id, body.decision, body.reason, body.reviewed_exact_version,
                                               body.idempotency_key, body.expected_revision, request.state.request_id)
    if job:  # after commit: ingestion runs outside the request transaction
        background.add_task(curriculum_authoring.run_job, job)
    return envelope(request, out)


@router.post("/curricula/{curriculum_id}/ingestion-jobs/{job_id}/retry", dependencies=[Depends(require_client_header)])
def curriculum_retry_ingestion(curriculum_id: str, job_id: str, body: AckBody, request: Request, background: BackgroundTasks) -> dict[str, Any]:
    with transaction() as conn:
        out, job = curriculum_authoring.retry(conn, token(request), curriculum_id, job_id, body.idempotency_key, request.state.request_id)
    if job:
        background.add_task(curriculum_authoring.run_job, job)
    return envelope(request, out)


@router.put("/curricula/{curriculum_id}/subtopics/{subtopic_id}/objective", dependencies=[Depends(require_client_header)])
def curriculum_objective(curriculum_id: str, subtopic_id: str, body: ObjectiveBody, request: Request) -> dict[str, Any]:
    with transaction() as conn:
        return envelope(request, curriculum_authoring.save_objective(conn, token(request), curriculum_id, subtopic_id, body.description, body.assessment_criteria,
                                                                     body.idempotency_key, body.expected_revision, request.state.request_id))


@router.post("/curricula/{curriculum_id}/revisions", dependencies=[Depends(require_client_header)])
def curriculum_create_revision(curriculum_id: str, body: AckBody, request: Request) -> dict[str, Any]:
    """A draft revision of a published curriculum (ADR-050); an open draft revision is returned instead."""
    with transaction() as conn:
        return envelope(request, curriculum_revisions.create(conn, token(request), curriculum_id, body.idempotency_key, request.state.request_id))


@router.delete("/curricula/{curriculum_id}/sources/{curriculum_source_id}", dependencies=[Depends(require_client_header)])
def curriculum_remove_source(curriculum_id: str, curriculum_source_id: str, body: CommandBody, request: Request) -> dict[str, Any]:
    with transaction() as conn:
        return envelope(request, curriculum_revisions.remove_source(conn, token(request), curriculum_id, curriculum_source_id, body.idempotency_key, body.expected_revision, request.state.request_id))


class SubtopicIncludeBody(CommandBody):
    included: bool


@router.post("/curricula/{curriculum_id}/subtopics/{subtopic_id}/inclusion", dependencies=[Depends(require_client_header)])
def curriculum_set_subtopic(curriculum_id: str, subtopic_id: str, body: SubtopicIncludeBody, request: Request) -> dict[str, Any]:
    with transaction() as conn:
        return envelope(request, curriculum_revisions.set_subtopic(conn, token(request), curriculum_id, subtopic_id, body.included, body.idempotency_key, body.expected_revision, request.state.request_id))


class TopicMoveBody(CommandBody):
    direction: Literal["UP", "DOWN"]


@router.post("/curricula/{curriculum_id}/topics/{topic_id}/move", dependencies=[Depends(require_client_header)])
def curriculum_move_topic(curriculum_id: str, topic_id: str, body: TopicMoveBody, request: Request) -> dict[str, Any]:
    with transaction() as conn:
        return envelope(request, curriculum_revisions.move_topic(conn, token(request), curriculum_id, topic_id, body.direction, body.idempotency_key, body.expected_revision, request.state.request_id))


@router.post("/curricula/{curriculum_id}/publish", dependencies=[Depends(require_client_header)])
def curriculum_publish(curriculum_id: str, body: CommandBody, request: Request) -> dict[str, Any]:
    with transaction() as conn:
        return envelope(request, curriculum_authoring.publish(conn, token(request), curriculum_id, body.idempotency_key, body.expected_revision, request.state.request_id))


@router.get("/onboarding/progress")
def onboarding_progress(request: Request) -> dict[str, Any]:
    with transaction() as conn:
        return envelope(request, onboarding.team_progress(conn, token(request)))


class TurnBody(BaseModel):
    client_turn_id: str = Field(max_length=64)
    expected_revision: int = Field(ge=1)
    text: str = Field(min_length=1, max_length=5000)
    input_kind: Literal["TEXT", "VOICE_TRANSCRIPT"] = "TEXT"
    # The learner interrupted the previous reply while it was being read aloud.
    interrupted_previous_reply: bool = False


def _sse(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


@router.post("/onboarding/sessions/{session_id}/turns/stream", dependencies=[Depends(require_client_header)])
def learning_turn_stream(session_id: str, body: TurnBody, request: Request) -> StreamingResponse:
    """The same message as /turns, answered as server-sent events: `progress` {label} while the tutor
    works (ADR-030 engine only), then `done` {request_id, data: view} or `error` {request_id, error}.
    Checks that fail before the tutor starts return the usual JSON error instead."""
    rid = str(request.state.request_id)
    if engine_turns.active():
        events = engine_turns.send_turn_stream(token(request), session_id, body.client_turn_id, body.expected_revision, body.text, body.input_kind, request.state.request_id, body.interrupted_previous_reply)
    else:
        view = onboarding.send_turn(token(request), session_id, body.client_turn_id, body.expected_revision, body.text, body.input_kind, request.state.request_id, body.interrupted_previous_reply)
        events = iter([("done", view)])

    def stream():
        for event, data in events:
            if event == "done":
                yield _sse("done", {"request_id": rid, "data": data})
            elif event == "error":
                yield _sse("error", {"request_id": rid, "error": data})
            else:
                yield _sse(event, data)

    # no-transform: proxies (the Next.js dev proxy, Firebase Hosting) must not compress or buffer events.
    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-store, no-transform", "X-Accel-Buffering": "no"})


class PauseBody(BaseModel):
    client_turn_id: str = Field(min_length=8, max_length=64)
    expected_revision: int = Field(ge=1)


@router.post("/onboarding/sessions", dependencies=[Depends(require_client_header)])
def start_learning_session(request: Request) -> dict[str, Any]:
    with transaction() as conn:
        view = onboarding.start_session(conn, token(request), request.state.request_id)
    # The AI engineer's graph opens the conversation after the session is saved (no transaction open).
    if engine_turns.active():
        view = engine_turns.ensure_opening(token(request), view["learning_session_id"])
    return envelope(request, view)


@router.get("/onboarding/sessions/{session_id}")
def get_learning_session(session_id: str, request: Request) -> dict[str, Any]:
    with transaction() as conn:
        return envelope(request, onboarding.get_session(conn, token(request), session_id))


@router.post("/onboarding/sessions/{session_id}/turns", dependencies=[Depends(require_client_header)])
def learning_turn(session_id: str, body: TurnBody, request: Request) -> dict[str, Any]:
    # No transaction here: the service commits in short phases so none is open during the engine call.
    return envelope(
        request,
        onboarding.send_turn(token(request), session_id, body.client_turn_id, body.expected_revision, body.text, body.input_kind, request.state.request_id, body.interrupted_previous_reply),
    )


class ContinueBody(BaseModel):
    expected_revision: int = Field(ge=1)


@router.post("/onboarding/sessions/{session_id}/continue", dependencies=[Depends(require_client_header)])
def continue_learning_session(session_id: str, body: ContinueBody, request: Request) -> dict[str, Any]:
    """After a completed item, the tutor opens the next one (ADR-030; only with the LangGraph engine)."""
    if not engine_turns.active():
        raise ApiError("CAPABILITY_UNAVAILABLE", "Moving to the next item needs the tutor, which isn't connected.")
    return envelope(request, engine_turns.continue_session(token(request), session_id, body.expected_revision, request.state.request_id))


@router.post("/onboarding/sessions/{session_id}/pause", dependencies=[Depends(require_client_header)])
def pause_learning_session(session_id: str, body: PauseBody, request: Request) -> dict[str, Any]:
    with transaction() as conn:
        return envelope(request, onboarding.pause(conn, token(request), session_id, body.client_turn_id, body.expected_revision, request.state.request_id))
