"""Runtime configuration (environment only; no secrets in code or the frontend)."""

from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import quote

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

LOCAL_ENV = Path(__file__).resolve().parents[2] / "local" / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=LOCAL_ENV, extra="ignore")

    # Either a full SQLAlchemy URL, or the local Compose variables from src/local/.env.
    database_url: str | None = None
    postgres_user: str = "workweave"
    postgres_password: str | None = None
    postgres_db: str = "workweave"
    postgres_host: str = "127.0.0.1"
    postgres_port: int = 5432

    session_ttl_minutes: int = Field(default=480, ge=5, le=7 * 24 * 60)
    # Connections per API instance (DB_POOL_SIZE + DB_MAX_OVERFLOW). Keep instances x total under the
    # Cloud SQL tier's connection limit.
    db_pool_size: int = Field(default=5, ge=1, le=50)
    db_max_overflow: int = Field(default=5, ge=0, le=50)
    # Local HTTP development only; set true behind HTTPS.
    cookie_secure: bool = False
    api_prefix: str = "/api"
    # WORKWEAVE_ENV. Only "test" allows installing a deterministic tutor engine (tests only).
    workweave_env: Literal["development", "test", "release"] = "development"

    # Onboarding tutor (ADR-030): "langgraph" drives the AI engineer's graph over the LangGraph API at
    # LANGGRAPH_URL (locally `langgraph dev`, http://127.0.0.1:5678). "none" reports it not connected.
    tutor_engine: Literal["none", "langgraph"] = "none"
    langgraph_url: str | None = None
    langgraph_assistant: str = "ai_adaptive_onboarding"

    # Work Companion (ADR-034): "langgraph" drives the AI engineer's Companion graph at
    # LANGGRAPH_COMPANION_URL (locally its own `langgraph dev`, http://127.0.0.1:5679).
    companion_engine: Literal["none", "langgraph"] = "none"
    langgraph_companion_url: str | None = None
    langgraph_companion_assistant: str = "ai_work_companion"
    # The graph's scheduling and calendar steps (owner decision 2026-10-10: on). They reach the AI
    # engineer's calendar service, which uses one Google account for now; COMPANION_CALENDAR=false
    # stops them in the app (e.g. a public deployment before per-employee calendars exist).
    companion_calendar: bool = True
    # ADR-035: open tickets with no assignee are assigned automatically, by competency, to members on
    # the shift in progress when the Work Companion opens; the shift lead can override.
    auto_assign_work: bool = True
    # The AI engineer's calendar service (google_calendar_auth.py). The backend only asks whether it is
    # connected to Google; the employee's browser opens {url}/auth/google to sign in (one static
    # account for now, WORKWEAVE_EMPLOYEE_EMAIL in her service).
    calendar_service_url: str = "http://127.0.0.1:8001"
    # Where the browser opens the Google sign-in. Unset: the service itself ({url}/auth/google, local
    # development). In the cloud the service listens on localhost only, so this is the API's
    # pass-through, /api/calendar/auth/google (ADR-052).
    calendar_connect_url: str | None = None
    # Shift Handover graph (docs/31, ADR-043): its own `langgraph dev` on port 5680. HANDOVER_ENGINE=none
    # turns it off (the copilot and gap check then say they aren't connected).
    handover_engine: str = "langgraph"
    langgraph_handover_url: str = "http://127.0.0.1:5680"
    langgraph_handover_assistant: str = "ai_shift_handover"
    # Exit KT graph (docs/32, ADR-044): its own `langgraph dev` on port 5681. EXIT_KT_ENGINE=none turns it off.
    exit_kt_engine: str = "langgraph"
    langgraph_exit_kt_url: str = "http://127.0.0.1:5681"
    langgraph_exit_kt_assistant: str = "ai_exit_knowledge_transfer"
    # Curriculum source ingestion (ADR-040): the AI engineer's vector_embedding package, run with her
    # own Python environment and .env (her Gemini embedding settings) as a separate process after a
    # source version is approved. Unset = ingestion reported as not connected.
    ingestion_python: str | None = None
    ingestion_dir: str | None = None
    ingestion_timeout_seconds: int = 600
    # Container image only: pass the deployment's Gemini settings to her ingestion (no .env of hers there).
    ingestion_pass_gemini_env: bool = False
    # Notification inbox (blueprint/19, ADR-048): the dispatcher projects outbox events into a recipient-scoped
    # Firestore inbox. Locally that's the emulator in local/compose.yaml (FIRESTORE_EMULATOR_HOST); in the cloud
    # the service's own credentials. NOTIFICATIONS=none turns the inbox off (it then says it isn't connected).
    notifications: str = "firestore"
    firestore_project: str = "workweave-local"
    firestore_emulator_host: str | None = "127.0.0.1:8085"
    # Deliver from the API process every few seconds (local development). In the cloud a separate worker
    # runs `python -m app.cli dispatch --loop` instead, and this is switched off.
    dispatcher_in_process: bool = True
    dispatcher_interval_seconds: float = Field(default=3.0, ge=0.5, le=60)
    # Private originals of uploaded sources (dev: local folder; Cloud Storage later).
    local_storage_dir: str = "../local/storage"

    # Voice transport (Gemini). Without GEMINI_API_KEY voice is reported unavailable. Model IDs and
    # voice are configuration so the AI engineer can change them without code changes.
    gemini_api_key: SecretStr | None = None
    # Optional paid-tier key used only for evaluator runs' voice listening (ADR-029). Unset: the
    # regular key is used for everyone.
    gemini_evaluator_api_key: SecretStr | None = None
    voice_listen_model: str = "gemini-3.5-transcribe-live"
    voice_tts_model: str = "gemini-3.8-flash-lite-tts"
    voice_tts_voice: str = "Kore"
    voice_language_codes: list[str] = Field(default_factory=lambda: ["en-US"])
    # VERBATIM keeps the learner's exact words (fillers included); SMART cleans them up.
    voice_transcript_mode: Literal["VERBATIM", "SMART"] = "VERBATIM"
    # Spoken replies: "auto" uses Vertex AI when GOOGLE_GENAI_USE_VERTEXAI=true (Cloud Run, paid by
    # the project's credits) and the Gemini API key otherwise; "vertex" / "gemini_api" force one.
    voice_tts_backend: Literal["auto", "vertex", "gemini_api"] = "auto"
    google_genai_use_vertexai: bool = False
    google_cloud_project: str | None = None
    google_cloud_location: str = "global"

    @model_validator(mode="after")
    def _release_profile(self) -> "Settings":
        """WORKWEAVE_ENV=release (Cloud Run) must use secure cookies; test hooks are already test-only."""
        if self.workweave_env == "release" and not self.cookie_secure:
            raise ValueError("WORKWEAVE_ENV=release requires COOKIE_SECURE=true (the site is served over HTTPS).")
        return self

    def url(self, database: str | None = None) -> str:
        if self.database_url and database is None:
            return self.database_url
        if not self.postgres_password:
            raise RuntimeError("Set DATABASE_URL, or POSTGRES_PASSWORD in src/local/.env.")
        return (
            f"postgresql+psycopg://{quote(self.postgres_user)}:{quote(self.postgres_password)}"
            f"@{self.postgres_host}:{self.postgres_port}/{database or self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
