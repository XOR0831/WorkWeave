"""Is the AI engineer's calendar service signed in to Google? (ADR-034)

Her service (`google_calendar_auth.py`) keeps the Google sign-in in memory and answers 401 to calendar
requests until someone signs in at /auth/google. The backend asks before her graph's calendar steps
run, so the employee gets a "Connect Google Calendar" button instead of a raw error. It reads a
one-minute free/busy window only; nothing about the calendar is kept.
"""

from datetime import UTC, datetime, timedelta
from typing import Literal

import httpx

from app.config import get_settings

Status = Literal["CONNECTED", "NOT_CONNECTED", "UNREACHABLE"]

_client: httpx.Client | None = None


def install_test_client(client: httpx.Client | None) -> None:
    global _client
    _client = client


def connect_url() -> str:
    s = get_settings()
    return s.calendar_connect_url or f"{s.calendar_service_url.rstrip('/')}/auth/google"


# ---------------------------------------------------------------- sign-in pass-through (ADR-052)
# In the cloud her service listens on 127.0.0.1 inside the API container, so only the API can reach
# its calendar endpoints. The browser's two sign-in steps come through the API instead.
SignIn = Literal["CONNECTED", "WRONG_ACCOUNT", "EXPIRED", "FAILED"]


def sign_in_redirect() -> str | None:
    """Starts her sign-in; returns the Google address to send the browser to, or None."""
    base = get_settings().calendar_service_url.rstrip("/")
    client = _client or httpx.Client(timeout=httpx.Timeout(8.0, connect=3.0))
    try:
        r = client.get(f"{base}/auth/google", follow_redirects=False)
    except httpx.HTTPError:
        return None
    location = r.headers.get("location", "")
    return location if r.is_redirect and location.startswith("https://accounts.google.com/") else None


def finish_sign_in(params: dict[str, str]) -> SignIn:
    """Hands Google's answer to her service. Only the outcome comes back, not the account or tokens."""
    base = get_settings().calendar_service_url.rstrip("/")
    client = _client or httpx.Client(timeout=httpx.Timeout(20.0, connect=3.0))
    try:
        r = client.get(f"{base}/auth/google/callback", params=params, follow_redirects=False)
    except httpx.HTTPError:
        return "FAILED"
    if r.status_code < 300:
        return "CONNECTED"
    return {403: "WRONG_ACCOUNT", 400: "EXPIRED"}.get(r.status_code, "FAILED")


def status() -> Status:
    base = get_settings().calendar_service_url.rstrip("/")
    now = datetime.now(UTC)
    client = _client or httpx.Client(timeout=httpx.Timeout(8.0, connect=3.0))
    try:
        r = client.get(f"{base}/calendar/availability", params={"start": now.isoformat(), "end": (now + timedelta(minutes=1)).isoformat()})
    except httpx.HTTPError:
        return "UNREACHABLE"
    if r.status_code == 401:
        return "NOT_CONNECTED"
    return "CONNECTED" if r.status_code < 400 else "UNREACHABLE"
