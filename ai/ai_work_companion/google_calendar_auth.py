import os
import secrets

from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.responses import RedirectResponse
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2 import id_token
from pydantic import BaseModel, Field
from typing import Literal

load_dotenv(override=True)

app = FastAPI()

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI")

# Temporary static employee email
EMPLOYEE_EMAIL = os.getenv("WORKWEAVE_EMPLOYEE_EMAIL")

GOOGLE_SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/calendar.freebusy",
    "https://www.googleapis.com/auth/calendar.events.readonly",
    "https://www.googleapis.com/auth/calendar.events"
]

CLIENT_CONFIG = {
    "web": {
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": [GOOGLE_REDIRECT_URI],
    }
}

# Temporary local storage; replace with a secure shared store later.
oauth_states = {}
calendar_credentials = {}

class CalendarEventInput(BaseModel):
    work_item_id: str | None = None
    event_type: Literal["TASK", "FOCUS", "CUSTOM"] = "TASK"
    title: str
    start: datetime
    end: datetime


class CreateCalendarEventsRequest(BaseModel):
    events: list[CalendarEventInput] = Field(
        min_length=1
    )

def create_google_flow(state=None):
    return Flow.from_client_config(
        CLIENT_CONFIG,
        scopes=GOOGLE_SCOPES,
        state=state,
        redirect_uri=GOOGLE_REDIRECT_URI,
    )

@app.get("/auth/google")
def google_login():
    flow = create_google_flow()

    authorization_url, state = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        # include_granted_scopes="false",
        login_hint=EMPLOYEE_EMAIL,
    )

    oauth_states[state] = flow.code_verifier

    return RedirectResponse(authorization_url)

@app.get("/auth/google/callback")
def google_callback(request: Request):
    state = request.query_params.get("state")
    code = request.query_params.get("code")

    code_verifier = oauth_states.pop(state, None) if state else None

    if not code_verifier:
        raise HTTPException(
            status_code=400,
            detail="Invalid OAuth state or missing PKCE verifier.",
        )

    if not code:
        raise HTTPException(
            status_code=400,
            detail="Missing authorization code.",
        )

    flow = create_google_flow(state=state)
    flow.code_verifier = code_verifier

    flow.fetch_token(code=code)

    credentials = flow.credentials

    if not credentials.id_token:
        raise HTTPException(
            status_code=400,
            detail="Google did not return an ID token.",
        )

    claims = id_token.verify_oauth2_token(
        credentials.id_token,
        GoogleRequest(),
        GOOGLE_CLIENT_ID,
    )

    authenticated_email = claims.get("email")

    if not (
        claims.get("email_verified")
        and authenticated_email
        and EMPLOYEE_EMAIL
        and authenticated_email.lower() == EMPLOYEE_EMAIL.lower()
    ):
        raise HTTPException(
            status_code=403,
            detail="Google account does not match the configured employee.",
        )

    calendar_credentials[EMPLOYEE_EMAIL.lower()] = credentials

    return {
        "status": "connected",
        "email": authenticated_email,
        "message": "Google Calendar connected successfully.",
    }

# @app.get("/calendar/availability")
# def get_calendar_availability():
#     email = EMPLOYEE_EMAIL.lower()
#     credentials = calendar_credentials.get(email)

#     if credentials is None:
#         raise HTTPException(
#             status_code=401,
#             detail="Google Calendar is not connected.",
#         )

#     if credentials.expired and credentials.refresh_token:
#         credentials.refresh(GoogleRequest())

#     service = build(
#         "calendar",
#         "v3",
#         credentials=credentials,
#     )

#     start = datetime.now(timezone.utc)
#     end = start + timedelta(days=1)

#     result = service.freebusy().query(
#         body={
#             "timeMin": start.isoformat(),
#             "timeMax": end.isoformat(),
#             "items": [{"id": "primary"}],
#         }
#     ).execute()

#     calendar = result["calendars"]["primary"]

#     if calendar.get("errors"):
#         raise HTTPException(
#             status_code=502,
#             detail="Unable to retrieve calendar availability.",
#         )

#     return {
#         "employee_email": email,
#         "window_start": start.isoformat(),
#         "window_end": end.isoformat(),
#         "busy_periods": calendar.get("busy", []),
#     }

@app.get("/calendar/availability")
def get_calendar_availability(start: datetime = Query(...), end: datetime = Query(...)):
    email = EMPLOYEE_EMAIL.lower()

    credentials = calendar_credentials.get(email)

    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail="Google Calendar is not connected."
        )

    if start.tzinfo is None or end.tzinfo is None:
        raise HTTPException(
            status_code=400,
            detail="Start and end must include timezone information."
        )

    if end <= start:
        raise HTTPException(
            status_code=400,
            detail="End must be after start."
        )

    if credentials.expired:
        if not credentials.refresh_token:
            raise HTTPException(
                status_code=401,
                detail="Google Calendar authorization has expired."
            )

        credentials.refresh(GoogleRequest())

    service = build(
        "calendar",
        "v3",
        credentials=credentials
    )

    result = service.freebusy().query(
        body={
            "timeMin": start.astimezone(timezone.utc).isoformat(),
            "timeMax": end.astimezone(timezone.utc).isoformat(),
            "items": [{"id": "primary"}]
        }
    ).execute()

    calendar = result["calendars"]["primary"]

    if calendar.get("errors"):
        raise HTTPException(
            status_code=502,
            detail="Unable to retrieve Google Calendar availability."
        )

    return {
        "employee_email": email,
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
        "busy_periods": calendar.get("busy", [])
    }

@app.get("/calendar/events")
def get_calendar_events(start: datetime, end: datetime):
    email = os.getenv("WORKWEAVE_EMPLOYEE_EMAIL")

    credentials = calendar_credentials.get(email)

    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail="Google Calendar is not connected."
        )

    if not credentials.valid:
        if credentials.expired and credentials.refresh_token:
            credentials.refresh(GoogleRequest())
        else:
            raise HTTPException(
                status_code=401,
                detail="Google Calendar authorization expired."
            )

    service = build(
        "calendar",
        "v3",
        credentials=credentials
    )

    result = service.events().list(
        calendarId="primary",
        timeMin=start.astimezone(timezone.utc).isoformat(),
        timeMax=end.astimezone(timezone.utc).isoformat(),
        singleEvents=True,
        orderBy="startTime",
        maxResults=100
    ).execute()

    events = [
        {
            "event_id": event["id"],
            "title": event.get("summary", "Untitled event"),
            "description": event.get("description"),
            "start": event.get("start", {}).get("dateTime")
                     or event.get("start", {}).get("date"),
            "end": event.get("end", {}).get("dateTime")
                   or event.get("end", {}).get("date"),
            "location": event.get("location"),
            "html_link": event.get("htmlLink"),
        }
        for event in result.get("items", [])
    ]

    return {
        "email": email,
        "events": events,
        "total_events": len(events)
    }

@app.post("/calendar/events")
def create_calendar_events(payload: CreateCalendarEventsRequest):
    email = os.getenv("WORKWEAVE_EMPLOYEE_EMAIL")
    credentials = calendar_credentials.get(email)

    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail="Google Calendar is not connected."
        )

    if not credentials.valid:
        if credentials.expired and credentials.refresh_token:
            try:
                credentials.refresh(GoogleRequest())
            except Exception:
                raise HTTPException(
                    status_code=401,
                    detail="Google Calendar authorization expired."
                )
        else:
            raise HTTPException(
                status_code=401,
                detail="Google Calendar authorization expired."
            )

    if not credentials.has_scopes([
        "https://www.googleapis.com/auth/calendar.events"
    ]):
        raise HTTPException(
            status_code=403,
            detail="Calendar write permission is missing."
        )

    service = build(
        "calendar",
        "v3",
        credentials=credentials
    )

    events = sorted(
        payload.events,
        key=lambda event: event.start
    )

    now = datetime.now(timezone.utc)

    for event in events:
        if (
            event.start.tzinfo is None
            or event.end.tzinfo is None
            or event.start >= event.end
            or event.start.astimezone(timezone.utc) <= now
        ):
            raise HTTPException(
                status_code=400,
                detail="All events must have valid future time ranges."
            )

    for previous, current in zip(events, events[1:]):
        if previous.end > current.start:
            raise HTTPException(
                status_code=400,
                detail="Proposed events overlap."
            )

    # Recheck availability immediately before insertion.
    try:
        result = service.freebusy().query(
            body={
                "timeMin": events[0].start.astimezone(
                    timezone.utc
                ).isoformat(),
                "timeMax": max(
                    event.end for event in events
                ).astimezone(timezone.utc).isoformat(),
                "items": [{"id": "primary"}]
            }
        ).execute()

        calendar_result = result["calendars"]["primary"]

        if calendar_result.get("errors"):
            raise HTTPException(
                status_code=409,
                detail="Unable to verify calendar availability."
            )

        busy_periods = calendar_result.get("busy", [])

        for event in events:
            for busy in busy_periods:
                busy_start = datetime.fromisoformat(
                    busy["start"].replace("Z", "+00:00")
                )
                busy_end = datetime.fromisoformat(
                    busy["end"].replace("Z", "+00:00")
                )

                if (
                    event.start < busy_end
                    and event.end > busy_start
                ):
                    raise HTTPException(
                        status_code=409,
                        detail=(
                            "Calendar availability changed. "
                            "Please generate a new schedule."
                        )
                    )

    except HttpError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Google Calendar availability check failed: {exc.status_code}"
        )

    created_events = []

    for event in events:
        body = {
            "summary": event.title,
            "description": (
                "Scheduled by WorkWeave\n"
                f"Work item ID: {event.work_item_id}"
            ),
            "start": {
                "dateTime": event.start.isoformat()
            },
            "end": {
                "dateTime": event.end.isoformat()
            },
            "extendedProperties": {
                "private": {
                    "workweave_work_item_id": event.work_item_id
                }
            }
        }

        try:
            created = service.events().insert(
                calendarId="primary",
                body=body
            ).execute()

            created_events.append({
                "work_item_id": event.work_item_id,
                "event_id": created["id"],
                "title": created.get("summary"),
                "html_link": created.get("htmlLink")
            })

        except HttpError as exc:
            # Earlier events may already have been created.
            return {
                "status": "partial_failure",
                "created_events": created_events,
                "failed_work_item_id": event.work_item_id,
                "error": f"Google Calendar returned HTTP {exc.status_code}"
            }

    return {
        "status": "created",
        "created_events": created_events,
        "total_created": len(created_events)
    }