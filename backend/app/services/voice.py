"""Voice endpoints (transport only; see app/integrations/voice.py).

POST /onboarding/sessions/{id}/voice/listen     -> a single-use listening grant for the session owner
GET  /onboarding/sessions/{id}/voice/speech/{m} -> WAV of a committed tutor reply in that session
GET  /work-sessions/{id}/voice/speech/{m}       -> the same for a Work Companion reply (ADR-034)
POST /handover/voice/listen, GET /handover/voice/speech/{m}/stream -> the lead's handover copilot (ADR-045)
POST /exit-kt/voice/listen,  GET /exit-kt/voice/speech/{m}/stream  -> the Exit KT copilot and interview (ADR-045)
GET  /capabilities                              -> which external capabilities are connected

Authorization runs in a short read-only transaction; the Gemini call happens after it closes.
No audio is received or stored by the backend, and speech is only generated for text the tutor
already committed (never arbitrary text), so the endpoint can't be used as a general TTS service. Companion replies follow the same rules:
only the session's own employee, only the companion's saved replies.
"""

import threading
import uuid as _uuid
from collections import OrderedDict
from collections.abc import Iterator
from dataclasses import asdict
from typing import Any

from sqlalchemy import text

from app.config import get_settings
from app.db import transaction
from app.errors import ApiError
from app.integrations.tutor import get_tutor
from app.integrations.voice import Mode, SpeechStream, VoiceUnavailable, get_voice
from app.repositories import turns
from app.services import usage
from app.services.onboarding import _owned_session


def capabilities() -> dict[str, Any]:
    return {
        "conversation_engine": "UNAVAILABLE" if get_tutor().provider == "none" else "AVAILABLE",
        "voice_adapter": "AVAILABLE" if get_voice().available else "UNAVAILABLE",
        "semantic_indexing": "UNAVAILABLE",
        "kt_drafting": "UNAVAILABLE",
        "recommendation": "UNAVAILABLE",
        "inbox_delivery": "SIMULATED",
    }


def _unavailable(e: VoiceUnavailable) -> ApiError:
    return ApiError("DEPENDENCY_UNAVAILABLE" if e.retryable else "CAPABILITY_UNAVAILABLE", e.message, retryable=e.retryable)


def listen_grant(token: str | None, session_id: str, mode: Mode) -> dict[str, Any]:
    with transaction() as conn:
        conn.execute(text("SET TRANSACTION READ ONLY"))
        r, _, s = _owned_session(conn, token, session_id, None)
        if s["status"] != "ACTIVE":
            raise ApiError("GUARD_FAILED", "Resume the conversation before using voice.")
    return _grant(s["workspace_id"], r.session, mode)


def _grant(workspace_id: Any, session: dict[str, Any], mode: Mode) -> dict[str, Any]:
    if not get_voice().available:
        raise ApiError("CAPABILITY_UNAVAILABLE", "Voice isn't configured on this server. Type your message instead.")
    with transaction() as conn:
        tier = usage.charge(conn, "VOICE_LISTEN", workspace_id, session)
    # Evaluators get the paid listening key when one is configured (ADR-029); otherwise the free one.
    voice = get_voice(paid=tier == "EVALUATOR")
    try:
        return asdict(voice.listen_grant(mode))
    except VoiceUnavailable as e:
        raise _unavailable(e) from None


class AudioCache:
    """Recently spoken replies, so replaying one (Listen again) costs no Gemini call and no read-aloud
    allowance. Kept in this process only, bounded by size, least recently used dropped first. Keyed
    by session and message, so audio is never shared across conversations. Only complete audio is kept."""

    def __init__(self, max_bytes: int = 48 * 1024 * 1024):
        self.max_bytes = max_bytes
        self._items: OrderedDict[tuple[str, ...], tuple[int, bytes]] = OrderedDict()
        self._size = 0
        self._lock = threading.Lock()

    def get(self, key: tuple[str, ...]) -> tuple[int, bytes] | None:
        with self._lock:
            hit = self._items.get(key)
            if hit:
                self._items.move_to_end(key)
            return hit

    def put(self, key: tuple[str, ...], rate: int, audio: bytes) -> None:
        if not audio or len(audio) > self.max_bytes:
            return
        with self._lock:
            old = self._items.pop(key, None)
            if old:
                self._size -= len(old[1])
            self._items[key] = (rate, audio)
            self._size += len(audio)
            while self._size > self.max_bytes:
                _, (_, dropped) = self._items.popitem(last=False)
                self._size -= len(dropped)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()
            self._size = 0


audio_cache = AudioCache()
CHUNK = 32 * 1024


def speech_stream(token: str | None, session_id: str, message_id: str) -> SpeechStream:
    """Like speech(), but the audio streams as it is generated (read-aloud starts within seconds).
    A reply already spoken in full is replayed from the cache, free of charge and allowance."""
    reply, voice, s, r = _authorized_reply(token, session_id, message_id)
    return _cached_stream(("learning", str(s["learning_session_id"]), message_id), reply, voice, s["workspace_id"], r.session)


def _cached_stream(scope: tuple[str, ...], reply: str, voice: Any, workspace_id: Any, session: dict[str, Any]) -> SpeechStream:
    settings = get_settings()
    key = (*scope, settings.voice_tts_model, settings.voice_tts_voice)
    hit = audio_cache.get(key)
    if hit:
        rate, audio = hit
        return SpeechStream(rate, (audio[i : i + CHUNK] for i in range(0, len(audio), CHUNK)))
    _charge_speech(workspace_id, session)
    try:
        stream = voice.speak_stream(reply)
    except VoiceUnavailable as e:
        raise _unavailable(e) from None

    def remember() -> Iterator[bytes]:
        parts: list[bytes] = []
        complete = False
        try:
            for chunk in stream.chunks:
                parts.append(chunk)
                yield chunk
            complete = True
        finally:
            # A stream cut short (listener stopped, network) is not cached, so a partial clip never replays.
            if complete and not stream.truncated:
                audio_cache.put(key, stream.rate, b"".join(parts))

    return SpeechStream(stream.rate, remember())


def _authorized_reply(token: str | None, session_id: str, message_id: str) -> tuple[str, Any, dict[str, Any], Any]:
    """The committed reply text of this owner's session (and the session), once voice is available."""
    turn_part, _, kind = message_id.partition(":")
    try:
        turn_id = _uuid.UUID(turn_part)
    except ValueError:
        raise ApiError("MALFORMED_INPUT", "Unknown message.") from None
    if kind != "out":
        raise ApiError("MALFORMED_INPUT", "Only tutor replies can be read aloud.")
    with transaction() as conn:
        conn.execute(text("SET TRANSACTION READ ONLY"))
        r, _, s = _owned_session(conn, token, session_id, None)
        reply = turns.committed_reply(conn, s["organization_id"], s["workspace_id"], s["learning_session_id"], turn_id)
    if not reply:
        raise ApiError("NOT_FOUND", "That reply isn't part of this conversation.")
    voice = get_voice()
    if not voice.available:
        raise ApiError("CAPABILITY_UNAVAILABLE", "Spoken replies aren't configured on this server.")
    return reply, voice, s, r


def _charge_speech(workspace_id: Any, session: dict[str, Any]) -> None:
    with transaction() as conn:
        usage.charge(conn, "VOICE_SPEECH", workspace_id, session)


def speech(token: str | None, session_id: str, message_id: str) -> bytes:
    reply, voice, s, r = _authorized_reply(token, session_id, message_id)
    _charge_speech(s["workspace_id"], r.session)
    try:
        return voice.speak(reply)
    except VoiceUnavailable as e:
        raise _unavailable(e) from None


# ---------------------------------------------------------------- Work Companion replies (ADR-034)
def _authorized_work_reply(token: str | None, work_session_id: str, message_id: str) -> tuple[str, Any, dict[str, Any], Any]:
    """A saved companion reply in this employee's own work session, once voice is available."""
    from app.repositories import work
    from app.services.companion_turns import _owned as owned_work_session

    try:
        mid = _uuid.UUID(message_id)
    except ValueError:
        raise ApiError("MALFORMED_INPUT", "Unknown message.") from None
    with transaction() as conn:
        conn.execute(text("SET TRANSACTION READ ONLY"))
        r, _, _, s = owned_work_session(conn, token, work_session_id)
        reply = work.ai_reply(conn, s["organization_id"], s["workspace_id"], s["work_session_id"], mid)
    if not reply:
        raise ApiError("NOT_FOUND", "That reply isn't part of this conversation.")
    voice = get_voice()
    if not voice.available:
        raise ApiError("CAPABILITY_UNAVAILABLE", "Spoken replies aren't configured on this server.")
    return reply, voice, s, r


def work_speech_stream(token: str | None, work_session_id: str, message_id: str) -> SpeechStream:
    reply, voice, s, r = _authorized_work_reply(token, work_session_id, message_id)
    return _cached_stream(("work", str(s["work_session_id"]), message_id), reply, voice, s["workspace_id"], r.session)


def work_speech(token: str | None, work_session_id: str, message_id: str) -> bytes:
    reply, voice, s, r = _authorized_work_reply(token, work_session_id, message_id)
    _charge_speech(s["workspace_id"], r.session)
    try:
        return voice.speak(reply)
    except VoiceUnavailable as e:
        raise _unavailable(e) from None


# ---------------------------------------------------------------- Shift Handover and Exit KT (ADR-045)
# The same transport and caps. Speech is only for the assistant's saved replies in the person's own
# conversation (never their own words, never another person's thread), read exactly as shown.
def _message_id(message_id: str) -> _uuid.UUID:
    try:
        return _uuid.UUID(message_id)
    except ValueError:
        raise ApiError("MALFORMED_INPUT", "Unknown message.") from None


def _shown(content: str, unknowns: list[str] | None) -> str:
    return content + ("\n\nNot in the records: " + "; ".join(unknowns) if unknowns else "")


def _speakable(reply: str | None) -> Any:
    if not reply:
        raise ApiError("NOT_FOUND", "That reply isn't part of this conversation.")
    voice = get_voice()
    if not voice.available:
        raise ApiError("CAPABILITY_UNAVAILABLE", "Spoken replies aren't configured on this server.")
    return voice


def handover_listen_grant(token: str | None, mode: Mode) -> dict[str, Any]:
    from app.services import handover

    with transaction() as conn:
        conn.execute(text("SET TRANSACTION READ ONLY"))
        c = handover.Ctx(conn, token)  # shift leads only
    return _grant(c.ws, c.session, mode)


def handover_speech_stream(token: str | None, message_id: str) -> SpeechStream:
    from app.services import handover

    mid = _message_id(message_id)
    with transaction() as conn:
        conn.execute(text("SET TRANSACTION READ ONLY"))
        c = handover.Ctx(conn, token)
        m = conn.execute(text("""SELECT content, unknowns FROM workweave.handover_copilot_messages
                                 WHERE organization_id=:o AND workspace_id=:w AND message_id=:m AND employee_id=:e AND sender='AI'"""),
                         {"o": c.org, "w": c.ws, "m": mid, "e": c.me}).mappings().first()
    reply = _shown(m["content"], m["unknowns"]) if m else None
    return _cached_stream(("handover", str(c.me), message_id), reply, _speakable(reply), c.ws, c.session)


def kt_listen_grant(token: str | None, mode: Mode) -> dict[str, Any]:
    from app.services import exit_kt

    with transaction() as conn:
        conn.execute(text("SET TRANSACTION READ ONLY"))
        c = exit_kt.Ctx(conn, token)
        if not c.case:
            raise ApiError("FORBIDDEN", "You aren't part of an Exit KT case in this workspace.")
    return _grant(c.ws, c.session, mode)


def kt_speech_stream(token: str | None, message_id: str) -> SpeechStream:
    """A copilot answer in this person's own case conversation, or a question in their own interview."""
    from app.services import exit_kt

    mid = _message_id(message_id)
    with transaction() as conn:
        conn.execute(text("SET TRANSACTION READ ONLY"))
        c = exit_kt.Ctx(conn, token)
        p = {"o": c.org, "w": c.ws, "m": mid, "e": c.me}
        m = None if not c.case else conn.execute(text("""SELECT content, unknowns FROM workweave.exit_kt_copilot_messages
                                 WHERE organization_id=:o AND workspace_id=:w AND exit_kt_case_id=:c AND message_id=:m AND employee_id=:e AND sender='AI'"""),
                                 {**p, "c": c.case["exit_kt_case_id"]}).mappings().first()
        reply = _shown(m["content"], m["unknowns"]) if m else None
        if not reply and c.case:
            reply = conn.execute(text("""SELECT x.content FROM workweave.exit_kt_interview_messages x
                                         JOIN workweave.exit_kt_interviews i ON i.organization_id=x.organization_id AND i.workspace_id=x.workspace_id AND i.interview_id=x.interview_id
                                         WHERE x.organization_id=:o AND x.workspace_id=:w AND x.message_id=:m AND x.sender_type='AI' AND i.employee_id=:e"""), p).scalar()
    return _cached_stream(("exit-kt", str(c.me), message_id), reply, _speakable(reply), c.ws, c.session)
