"""The Companion's Google Calendar sign-in through the API (ADR-052): in the cloud the calendar
service listens on localhost only, so the browser's two sign-in steps pass through the API."""

import httpx
import pytest

from app.config import get_settings
from app.integrations import calendar_service
from tests.test_companion_commands import fresh

GOOGLE = "https://accounts.google.com/o/oauth2/auth?client_id=x&state=s1"


@pytest.fixture
def service():
    seen: list[httpx.Request] = []
    answers = {"/auth/google": httpx.Response(307, headers={"location": GOOGLE}), "/auth/google/callback": httpx.Response(200, json={"status": "connected", "email": "test@example.com"})}

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return answers[req.url.path]

    calendar_service.install_test_client(httpx.Client(transport=httpx.MockTransport(handler)))
    yield answers, seen
    calendar_service.install_test_client(None)


def test_the_connect_link_is_the_api_pass_through_when_configured(monkeypatch):
    assert calendar_service.connect_url() == "http://127.0.0.1:8001/auth/google"  # local development
    monkeypatch.setattr(get_settings(), "calendar_connect_url", "/api/calendar/auth/google")
    assert calendar_service.connect_url() == "/api/calendar/auth/google"


def test_sign_in_starts_for_a_persona_and_sends_the_browser_to_google(client, service):
    fresh(client, "Alex")
    r = client.get("/api/calendar/auth/google", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == GOOGLE and r.headers["cache-control"] == "no-store"


def test_sign_in_needs_a_demo_persona(client, service):
    r = client.get("/api/calendar/auth/google", follow_redirects=False)
    assert r.status_code in (401, 403)
    assert service[1] == []  # the calendar service was never asked


def test_only_a_google_address_is_followed(client, service):
    fresh(client, "Alex")
    service[0]["/auth/google"] = httpx.Response(307, headers={"location": "https://evil.example/phish"})
    r = client.get("/api/calendar/auth/google", follow_redirects=False)
    assert r.status_code == 400 and "error was encountered" in r.text


def test_sign_in_is_off_when_the_calendar_is_off(client, service, monkeypatch):
    fresh(client, "Alex")
    monkeypatch.setattr(get_settings(), "companion_calendar", False)
    assert client.get("/api/calendar/auth/google", follow_redirects=False).status_code == 400
    assert service[1] == []


@pytest.mark.parametrize(("answer", "status", "words"), [
    (200, 200, "is connected"),
    (403, 400, "only its own test calendar account"),
    (400, 400, "expired"),
    (500, 400, "error was encountered"),
])
def test_the_callback_shows_only_the_outcome(client, service, answer, status, words):
    service[0]["/auth/google/callback"] = httpx.Response(answer, json={"status": "connected", "email": "test@example.com", "detail": "internal detail"})
    r = client.get("/api/calendar/auth/google/callback", params={"state": "s1", "code": "c1", "scope": "openid", "extra": "dropped"})
    assert r.status_code == status and words in r.text
    assert "test@example.com" not in r.text and "internal detail" not in r.text  # no account or error details
    forwarded = service[1][-1].url.params
    assert forwarded["state"] == "s1" and forwarded["code"] == "c1" and "extra" not in forwarded


def test_a_cancelled_or_incomplete_callback_never_reaches_the_service(client, service):
    assert "cancelled" in client.get("/api/calendar/auth/google/callback", params={"error": "access_denied", "state": "s1"}).text
    assert "expired" in client.get("/api/calendar/auth/google/callback", params={"state": "s1"}).text
    assert service[1] == []


# ---------------------------------------------------------------- ingestion in the container (ADR-052)
def test_ingestion_gets_gemini_settings_only_when_the_deployment_says_so(monkeypatch):
    from app.integrations import ingestion

    for k, v in {"GEMINI_API_KEY": "key", "GEMINI_EMBED_MODEL": "gemini-embedding-2", "GEMINI_EMBED_DIM": "768", "GOOGLE_GENAI_USE_VERTEXAI": "true", "DATABASE_URL": "secret"}.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("AI_GEMINI", raising=False)
    env = ingestion._gemini_env()
    assert env == {"GEMINI_EMBED_MODEL": "gemini-embedding-2", "GEMINI_EMBED_DIM": "768", "GEMINI_API_KEY": "key"}  # API key mode: no Vertex switch
    monkeypatch.setenv("AI_GEMINI", "vertex")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "p")
    assert ingestion._gemini_env() == {"GEMINI_EMBED_MODEL": "gemini-embedding-2", "GEMINI_EMBED_DIM": "768", "GOOGLE_GENAI_USE_VERTEXAI": "true", "GOOGLE_CLOUD_PROJECT": "p"}
    assert get_settings().ingestion_pass_gemini_env is False  # locally her .env supplies them
