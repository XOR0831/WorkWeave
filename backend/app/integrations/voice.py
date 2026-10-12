"""Voice transport for onboarding: listening (speech to text) and speaking (text to speech).

Built by the application side at the AI engineer's request (product owner, 2026-10-04), strictly as
TRANSPORT: it turns the learner's speech into a transcript and speaks already-committed tutor
replies. It has no tutor logic, no prompts beyond the reply text itself, and no analysis of how the
learner sounds (no hesitation, emotion or other vocal signals). The LangGraph tutor stays the only
source of replies; a finalized transcript becomes an ordinary turn (input_kind VOICE_TRANSCRIPT).

Listening: the browser streams microphone audio directly to Gemini's transcription-only Live model
(voice activity detection on the server, interim and final transcripts) using a short-lived,
single-use ephemeral token minted here. The API key never leaves the backend.
Speaking: Gemini text-to-speech reads the committed reply text verbatim; audio is returned as WAV.
On Cloud Run speech goes through Vertex AI (ADR-026 hybrid: paid by the project's credits,
authenticated as the service account through the metadata server, no key); elsewhere it uses the
Gemini API key. Listening always uses the key, because only the Gemini API mints browser tokens.

Model IDs, voice and languages are configuration so the AI engineer can change them. Without
GEMINI_API_KEY the provider reports itself unavailable; there is no simulated microphone or voice.
"""

import base64
import io
import json
import logging
import struct
import threading
import time
import wave
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from collections.abc import Iterator
from typing import Any, Literal, Protocol

import httpx

from app.config import get_settings

_log = logging.getLogger("workweave.voice")

API = "https://generativelanguage.googleapis.com/v1beta"
# Ephemeral tokens and the constrained Live endpoint exist only in v1alpha (verified 2026-10-04 against
# the google-genai SDK: v1beta rejects the token's setup fields with 400).
TOKENS_API = "https://generativelanguage.googleapis.com/v1alpha"
LIVE_WS = "wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1alpha.GenerativeService.BidiGenerateContentConstrained"
# Every field of the setup below is locked into the token, so the browser can't change model or output.
TOKEN_FIELD_MASK = "model,generationConfig.responseModalities,inputAudioTranscription,realtimeInputConfig"
MAX_SPEECH_CHARS = 4000
VERTEX = "https://aiplatform.googleapis.com/v1"
METADATA_TOKEN = "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token"

Mode = Literal["TAP", "HANDS_FREE"]


class VoiceUnavailable(Exception):
    def __init__(self, message: str, retryable: bool = False):
        super().__init__(message)
        self.message = message
        self.retryable = retryable


@dataclass(frozen=True)
class ListenGrant:
    """What the browser needs to open one listening session. The token is single-use and short-lived."""

    token: str
    ws_url: str
    model: str
    mode: Mode
    expires_at: str
    # The exact setup message the browser must send first (the token is locked to this config).
    setup: dict[str, Any]
    audio_mime_type: str = "audio/pcm;rate=16000"
    sample_rate: int = 16000


@dataclass
class SpeechStream:
    """Spoken reply as it is generated: 16-bit mono little-endian PCM at `rate`. Errors before the
    first audio raise VoiceUnavailable; a failure later ends the stream early (the text stays on screen)."""

    rate: int
    chunks: Iterator[bytes]
    truncated: bool = False  # set when the stream ended early after some audio (never cache it)


log = logging.getLogger(__name__)


def _rate_of(mime: str, default: int = 24000) -> int:
    for part in mime.replace(" ", "").split(";"):
        if part.lower().startswith("rate="):
            try:
                return int(part[5:])
            except ValueError:
                return default
    return default


def _stream_audio(client: httpx.Client, url: str, body: dict[str, Any], headers: dict[str, str]) -> SpeechStream:
    """POST to a streamGenerateContent?alt=sse endpoint and yield audio as server-sent events arrive."""
    cm = client.stream("POST", url, json=body, headers=headers)
    try:
        r = cm.__enter__()
    except httpx.HTTPError as e:
        raise VoiceUnavailable("Voice input couldn't start because an error was encountered. Try again, or type instead.", retryable=True) from e

    def close() -> None:
        cm.__exit__(None, None, None)

    if r.status_code >= 400:
        r.read()
        close()
        _raise_for(r)

    def parts() -> Iterator[tuple[str, bytes]]:
        for line in r.iter_lines():
            if not line.startswith("data:"):
                continue
            try:
                event = json.loads(line[5:])
            except ValueError:
                continue
            for part in ((event.get("candidates") or [{}])[0].get("content") or {}).get("parts") or []:
                inline = part.get("inlineData") or part.get("inline_data") or {}
                if inline.get("data"):
                    yield inline.get("mimeType") or inline.get("mime_type") or "", base64.b64decode(inline["data"])

    gen = parts()
    try:
        mime, first = next(gen)
    except StopIteration:
        close()
        raise VoiceUnavailable("The reply couldn't be read aloud because an error was encountered. It stays on screen; try again in a moment.") from None
    except httpx.HTTPError as e:
        close()
        raise VoiceUnavailable("The reply couldn't be read aloud because an error was encountered. It stays on screen; try again in a moment.", retryable=True) from e

    def chunks() -> Iterator[bytes]:
        try:
            yield first
            for _, data in gen:
                yield data
        except httpx.HTTPError:
            log.warning("spoken reply stream ended early")
            result.truncated = True
        finally:
            close()

    result = SpeechStream(_rate_of(mime), chunks())
    return result


class VoiceProvider(Protocol):
    provider: str

    @property
    def available(self) -> bool: ...

    def listen_grant(self, mode: Mode) -> ListenGrant: ...

    def speak(self, text: str) -> bytes: ...

    def speak_stream(self, text: str) -> SpeechStream: ...


class NotConfiguredVoice:
    provider = "none"
    available = False

    def listen_grant(self, mode: Mode) -> ListenGrant:
        raise VoiceUnavailable("Voice isn't configured on this server. Type your message instead.")

    def speak(self, text: str) -> bytes:
        raise VoiceUnavailable("Spoken replies aren't configured on this server.")

    def speak_stream(self, text: str) -> SpeechStream:
        raise VoiceUnavailable("Spoken replies aren't configured on this server.")


def transcription_config(mode: Mode, language_codes: list[str], transcript_mode: str) -> dict[str, Any]:
    """Live transcription session config: text-only output, transcripts on, VAD by mode.

    Tap-to-talk disables automatic activity detection (the browser sends activityStart/activityEnd);
    hands-free keeps it on so the server decides when the learner has finished speaking.
    """
    return {
        "responseModalities": ["TEXT"],
        "inputAudioTranscription": {"languageCodes": language_codes, "mode": transcript_mode},
        "realtimeInputConfig": {"automaticActivityDetection": {"disabled": mode == "TAP"}},
    }


def to_wav(data: bytes, mime_type: str) -> bytes:
    """Return WAV bytes: pass a RIFF file through; wrap headerless 16-bit mono PCM (rate from the MIME type)."""
    if data[:4] == b"RIFF":
        return data
    rate = 24000
    for part in mime_type.replace(" ", "").split(";"):
        if part.startswith("rate="):
            rate = int(part[5:])
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(data)
    return buf.getvalue()


def _raise_for(r: httpx.Response) -> dict[str, Any]:
    if r.status_code == 429 or r.status_code >= 500:
        raise VoiceUnavailable("The voice service is busy. Try again in a moment, or type instead.", retryable=True)
    if r.status_code >= 400:
        _log.warning("voice service rejected the request (%s)", r.status_code)  # the reason stays in the server log
        raise VoiceUnavailable("Voice couldn't be used because an error was encountered. Type instead.")
    return r.json()


def _speech_body(text: str, voice: str) -> dict[str, Any]:
    text = text.strip()
    if not text:
        raise VoiceUnavailable("There's nothing to read aloud.")
    return {
        "contents": [{"role": "user", "parts": [{"text": text[:MAX_SPEECH_CHARS]}]}],
        "generationConfig": {"responseModalities": ["AUDIO"], "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}}},
    }


def _audio_of(res: dict[str, Any]) -> bytes:
    for part in ((res.get("candidates") or [{}])[0].get("content") or {}).get("parts") or []:
        inline = part.get("inlineData") or part.get("inline_data")
        if inline and inline.get("data"):
            return to_wav(base64.b64decode(inline["data"]), inline.get("mimeType") or inline.get("mime_type") or "")
    raise VoiceUnavailable("The reply couldn't be read aloud because an error was encountered. It stays on screen; try again in a moment.")


class MetadataToken:
    """The Cloud Run service account's OAuth token from the metadata server, cached until shortly
    before it expires. No key and no extra library; only works on Google Cloud."""

    def __init__(self, client: httpx.Client):
        self._client = client
        self._lock = threading.Lock()
        self._token: tuple[str, float] | None = None

    def get(self) -> str:
        with self._lock:
            if self._token and self._token[1] - 60 > time.monotonic():
                return self._token[0]
            try:
                r = self._client.get(METADATA_TOKEN, headers={"Metadata-Flavor": "Google"}, timeout=3.0)
                r.raise_for_status()
                data = r.json()
            except (httpx.HTTPError, ValueError) as e:
                raise VoiceUnavailable("The reply couldn't be read aloud because an error was encountered. It stays on screen; try again in a moment.", retryable=True) from e
            self._token = (data["access_token"], time.monotonic() + float(data.get("expires_in", 300)))
            return self._token[0]


class VertexSpeech:
    """Gemini TTS through Vertex AI (same model, voice and audio as the Gemini API path)."""

    def __init__(self, project: str, location: str, model: str, voice: str, client: httpx.Client, token: Any):
        host = VERTEX if location == "global" else VERTEX.replace("aiplatform.", f"{location}-aiplatform.")
        self.url = f"{host}/projects/{project}/locations/{location}/publishers/google/models/{model}:generateContent"
        self.voice = voice
        self._client = client
        self._token = token

    def speak_stream(self, text: str) -> SpeechStream:
        body = _speech_body(text, self.voice)
        url = self.url.replace(":generateContent", ":streamGenerateContent?alt=sse")
        return _stream_audio(self._client, url, body, {"Authorization": f"Bearer {self._token.get()}"})

    def speak(self, text: str) -> bytes:
        body = _speech_body(text, self.voice)
        try:
            r = self._client.post(self.url, json=body, headers={"Authorization": f"Bearer {self._token.get()}"})
        except httpx.HTTPError as e:
            raise VoiceUnavailable("Voice input couldn't start because an error was encountered. Try again, or type instead.", retryable=True) from e
        return _audio_of(_raise_for(r))


class GeminiVoice:
    provider = "gemini"

    def __init__(self, api_key: str, listen_model: str, tts_model: str, tts_voice: str, language_codes: list[str], transcript_mode: str, client: httpx.Client | None = None, speech: VertexSpeech | None = None):
        self._key = api_key
        self.listen_model = listen_model
        self.tts_model = tts_model
        self.tts_voice = tts_voice
        self.language_codes = language_codes
        self.transcript_mode = transcript_mode
        self._client = client or httpx.Client(timeout=httpx.Timeout(20.0, connect=5.0))
        # Vertex AI speech when configured (Cloud Run); otherwise TTS through the Gemini API key.
        self._speech = speech

    @property
    def available(self) -> bool:
        return True

    def _post(self, url: str, body: dict[str, Any]) -> dict[str, Any]:
        try:
            r = self._client.post(url, json=body, headers={"x-goog-api-key": self._key})
        except httpx.HTTPError as e:
            raise VoiceUnavailable("Voice input couldn't start because an error was encountered. Try again, or type instead.", retryable=True) from e
        return _raise_for(r)

    def listen_grant(self, mode: Mode) -> ListenGrant:
        now = datetime.now(UTC)
        expires = now + timedelta(minutes=30)
        model = f"models/{self.listen_model}"
        config = transcription_config(mode, self.language_codes, self.transcript_mode)
        # The Live setup message, as the browser sends it; the token locks exactly these fields.
        setup = {"model": model, "generationConfig": {"responseModalities": config["responseModalities"]}, **{k: v for k, v in config.items() if k != "responseModalities"}}
        res = self._post(
            f"{TOKENS_API}/auth_tokens",
            {
                "uses": 1,
                "expireTime": expires.strftime("%Y-%m-%dT%H:%M:%SZ"),
                # The browser must open the session within a minute; the session may then run until expireTime.
                "newSessionExpireTime": (now + timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "bidiGenerateContentSetup": setup,
                "fieldMask": TOKEN_FIELD_MASK,
            },
        )
        token = res.get("name") or (res.get("token") or {}).get("name")
        if not token:
            raise VoiceUnavailable("Voice input couldn't start because an error was encountered. Try again, or type instead.")
        return ListenGrant(token=token, ws_url=LIVE_WS, model=self.listen_model, mode=mode, expires_at=expires.isoformat(), setup=setup)

    @property
    def speech_backend(self) -> str:
        return "vertex" if self._speech else "gemini_api"

    def speak_stream(self, text: str) -> SpeechStream:
        """Audio as it is generated (first sound in ~1.5 s instead of waiting for the whole reply)."""
        if self._speech:
            return self._speech.speak_stream(text)
        url = f"{API}/models/{self.tts_model}:streamGenerateContent?alt=sse"
        return _stream_audio(self._client, url, _speech_body(text, self.tts_voice), {"x-goog-api-key": self._key})

    def speak(self, text: str) -> bytes:
        if self._speech:
            return self._speech.speak(text)
        return _audio_of(self._post(f"{API}/models/{self.tts_model}:generateContent", _speech_body(text, self.tts_voice)))


_installed: VoiceProvider | None = None
_installed_paid: VoiceProvider | None = None


def install_test_voice(provider: VoiceProvider | None, paid: VoiceProvider | None = None) -> None:
    """Install (or remove) fake providers (`paid`: the evaluator listening key). Test env only."""
    global _installed, _installed_paid
    if get_settings().workweave_env != "test":
        raise RuntimeError("A test voice provider can only be installed when WORKWEAVE_ENV=test.")
    _installed, _installed_paid = provider, paid


def get_voice(paid: bool = False) -> VoiceProvider:
    """`paid`: an evaluator run (ADR-029). Uses GEMINI_EVALUATOR_API_KEY when it is set, so judges'
    voice listening isn't subject to the free tier's limits; otherwise the regular key."""
    s = get_settings()
    if _installed is not None and s.workweave_env == "test":
        return _installed_paid if paid and _installed_paid is not None else _installed
    paid_key = s.gemini_evaluator_api_key.get_secret_value() if paid and s.gemini_evaluator_api_key else ""
    key = paid_key or (s.gemini_api_key.get_secret_value() if s.gemini_api_key else "")
    if not key:
        return NotConfiguredVoice()
    return GeminiVoice(key, s.voice_listen_model, s.voice_tts_model, s.voice_tts_voice, s.voice_language_codes, s.voice_transcript_mode, _SHARED, vertex_speech())


_SHARED = httpx.Client(timeout=httpx.Timeout(20.0, connect=5.0))
_TOKEN = MetadataToken(_SHARED)


def vertex_speech() -> VertexSpeech | None:
    """Speech through Vertex AI when VOICE_TTS_BACKEND says so ("auto": whenever
    GOOGLE_GENAI_USE_VERTEXAI=true and GOOGLE_CLOUD_PROJECT are set, i.e. on Cloud Run)."""
    s = get_settings()
    use = s.voice_tts_backend == "vertex" or (s.voice_tts_backend == "auto" and s.google_genai_use_vertexai)
    if not use or not s.google_cloud_project:
        return None
    return VertexSpeech(s.google_cloud_project, s.google_cloud_location, s.voice_tts_model, s.voice_tts_voice, _SHARED, _TOKEN)


def silence_wav(seconds: float = 0.1, rate: int = 24000) -> bytes:
    """Tiny valid WAV (used by tests and fakes)."""
    return to_wav(struct.pack(f"<{int(rate * seconds)}h", *([0] * int(rate * seconds))), f"audio/L16;rate={rate}")
