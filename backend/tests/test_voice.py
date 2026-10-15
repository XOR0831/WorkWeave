"""Voice transport: Gemini adapter (mocked HTTP, no real calls) and the onboarding voice endpoints."""

import base64
import json
import struct
import uuid

import httpx
import pytest

from app.integrations import voice as voice_mod
from app.integrations.tutor import install_test_tutor
from app.integrations.voice import GeminiVoice, ListenGrant, VoiceUnavailable, install_test_voice, silence_wav, to_wav
from tests.test_demo_slice import code, open_company, pick
from tests.tutor_fakes import ScriptedTutor, cite, ok, teaching


# ---------------------------------------------------------------- Gemini adapter (mock transport)
def gemini(handler) -> GeminiVoice:
    return GeminiVoice("test-key", "gemini-transcribe-test", "gemini-tts-test", "Kore", ["en-US"], "VERBATIM", client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_listen_grant_requests_a_single_use_token_locked_to_transcription():
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["url"], seen["key"], seen["body"] = str(req.url), req.headers.get("x-goog-api-key"), json.loads(req.content)
        return httpx.Response(200, json={"name": "auth_tokens/abc123"})

    for mode, vad_disabled in (("TAP", True), ("HANDS_FREE", False)):
        g = gemini(handler).listen_grant(mode)
        body = seen["body"]
        # Ephemeral tokens are v1alpha-only; the REST body uses bidiGenerateContentSetup + fieldMask.
        assert seen["url"] == "https://generativelanguage.googleapis.com/v1alpha/auth_tokens" and seen["key"] == "test-key"
        assert body["uses"] == 1 and body["expireTime"] and body["newSessionExpireTime"]
        assert "liveConnectConstraints" not in body  # the SDK's name, rejected by the REST API
        locked = body["bidiGenerateContentSetup"]
        assert locked["model"] == "models/gemini-transcribe-test"
        assert locked["generationConfig"]["responseModalities"] == ["TEXT"]  # transcripts only, never a model reply
        assert locked["inputAudioTranscription"] == {"languageCodes": ["en-US"], "mode": "VERBATIM"}
        assert locked["realtimeInputConfig"]["automaticActivityDetection"]["disabled"] is vad_disabled
        assert body["fieldMask"] == "model,generationConfig.responseModalities,inputAudioTranscription,realtimeInputConfig"
        assert g.setup == locked  # the browser sends exactly what the token locks
        assert g.token == "auth_tokens/abc123" and g.mode == mode
        assert g.ws_url == "wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1alpha.GenerativeService.BidiGenerateContentConstrained"
        assert g.setup["model"] == locked["model"] and g.setup["generationConfig"]["responseModalities"] == ["TEXT"]
        assert "test-key" not in json.dumps(g.__dict__)  # the API key never reaches the browser


def test_speak_reads_the_text_and_returns_wav():
    pcm = struct.pack("<4h", 1, -1, 2, -2)
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["url"], seen["body"] = str(req.url), json.loads(req.content)
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"inlineData": {"mimeType": "audio/L16;codec=pcm;rate=24000", "data": base64.b64encode(pcm).decode()}}]}}]})

    wav = gemini(handler).speak("Use the current approved version.")
    assert seen["url"].endswith("/models/gemini-tts-test:generateContent")
    assert seen["body"]["contents"][0]["parts"][0]["text"] == "Use the current approved version."  # verbatim, no added prompt
    assert seen["body"]["generationConfig"]["responseModalities"] == ["AUDIO"]
    assert wav[:4] == b"RIFF" and wav.endswith(pcm)
    assert to_wav(wav, "audio/wav") == wav  # an existing WAV passes through


@pytest.mark.parametrize("status,retryable", [(429, True), (503, True), (400, False), (403, False)])
def test_gemini_errors_become_typed_unavailability(status, retryable):
    g = gemini(lambda req: httpx.Response(status, json={"error": {"message": "no"}}))
    with pytest.raises(VoiceUnavailable) as e:
        g.listen_grant("TAP")
    assert e.value.retryable is retryable


def test_no_key_means_voice_is_unavailable(monkeypatch):
    monkeypatch.setattr(voice_mod.get_settings(), "gemini_api_key", None)
    assert voice_mod.get_voice().available is False


# ---------------------------------------------------------------- endpoints (fake provider)
class FakeVoice:
    provider = "fake"
    available = True

    def __init__(self):
        self.spoken: list[str] = []
        self.modes: list[str] = []

    def listen_grant(self, mode):
        self.modes.append(mode)
        return ListenGrant(token="fake-token", ws_url="wss://example.invalid/live", model="fake-transcribe", mode=mode, expires_at="2099-01-01T00:00:00+00:00", setup={"model": "models/fake-transcribe"})

    def speak(self, text):
        self.spoken.append(text)
        return silence_wav()

    def speak_stream(self, text):
        from app.integrations.voice import SpeechStream

        self.spoken.append(text)
        return SpeechStream(24000, iter([b"\x01\x00\x02\x00", b"\x03\x00"]))


@pytest.fixture()
def fake_voice():
    v = FakeVoice()
    install_test_voice(v)
    yield v
    install_test_voice(None)


def learner_session(client) -> dict:
    open_company(client, "northstar", intent="FRESH")
    pick(client, "Sam")
    return client.post("/api/onboarding/sessions").json()["data"]


def test_capabilities_report_voice_only_when_configured(client, fake_voice):
    assert client.get("/api/capabilities").json()["data"]["voice_adapter"] == "AVAILABLE"
    install_test_voice(None)
    caps = client.get("/api/capabilities").json()["data"]
    assert caps["voice_adapter"] == "UNAVAILABLE" and caps["conversation_engine"] == "UNAVAILABLE"


def test_only_the_session_owner_gets_a_listening_grant(client, other_client, fake_voice):
    s = learner_session(client)
    r = client.post(f"/api/onboarding/sessions/{s['learning_session_id']}/voice/listen", json={"mode": "HANDS_FREE"})
    assert r.status_code == 200 and r.json()["data"]["token"] == "fake-token" and fake_voice.modes == ["HANDS_FREE"]
    learner_session(other_client)
    r = other_client.post(f"/api/onboarding/sessions/{s['learning_session_id']}/voice/listen", json={"mode": "TAP"})
    assert r.status_code == 404 and code(r) == "NOT_FOUND"
    r = client.post(f"/api/onboarding/sessions/{s['learning_session_id']}/voice/listen", json={"mode": "TAP"}, headers={"X-WorkWeave-Client": ""})
    assert r.status_code == 403
    assert client.post(f"/api/onboarding/sessions/{s['learning_session_id']}/voice/listen", json={"mode": "LOUD"}).status_code == 422


def test_no_grant_for_a_paused_session_or_without_a_provider(client, fake_voice):
    s = learner_session(client)
    sid = s["learning_session_id"]
    client.post(f"/api/onboarding/sessions/{sid}/pause", json={"client_turn_id": f"pause-{uuid.uuid4()}", "expected_revision": s["revision"]})
    r = client.post(f"/api/onboarding/sessions/{sid}/voice/listen", json={"mode": "TAP"})
    assert r.status_code == 409 and code(r) == "GUARD_FAILED"
    client.post("/api/onboarding/sessions")  # resume
    install_test_voice(None)
    r = client.post(f"/api/onboarding/sessions/{sid}/voice/listen", json={"mode": "TAP"})
    assert r.status_code == 501 and code(r) == "CAPABILITY_UNAVAILABLE"


def test_speech_is_only_for_committed_tutor_replies(client, other_client, engine, fake_voice):
    t = ScriptedTutor(engine)
    install_test_tutor(t)
    try:
        s = learner_session(client)
        sid = s["learning_session_id"]
        from sqlalchemy import text as sql

        with engine.connect() as c:
            ver, sec = c.execute(sql("""SELECT ks.document_version_id, ks.section_id FROM workweave.knowledge_sections ks
                                       JOIN workweave.learning_sessions ls ON ls.workspace_id = ks.workspace_id
                                       WHERE ls.learning_session_id=:s AND ks.section_key='h2:1/h3:1'"""), {"s": sid}).one()
        t.then(ok(teaching([cite(ver, sec)])))
        v = client.post(f"/api/onboarding/sessions/{sid}/turns", json={"client_turn_id": str(uuid.uuid4()), "expected_revision": s["revision"], "text": "Hi", "input_kind": "VOICE_TRANSCRIPT"}).json()["data"]
        learner_msg, reply = v["transcript"]
        assert learner_msg["input_kind"] == "VOICE_TRANSCRIPT"
        r = client.get(f"/api/onboarding/sessions/{sid}/voice/speech/{reply['message_id']}")
        assert r.status_code == 200 and r.headers["content-type"] == "audio/wav" and r.content[:4] == b"RIFF"
        assert "no-store" in r.headers["cache-control"]  # never cached (app-wide API policy)
        assert fake_voice.spoken == [reply["text"]]  # exactly the committed reply text
        assert client.get(f"/api/onboarding/sessions/{sid}/voice/speech/{learner_msg['message_id']}").status_code == 422  # not the learner's words
        assert client.get(f"/api/onboarding/sessions/{sid}/voice/speech/{uuid.uuid4()}:out").status_code == 404
        assert client.get(f"/api/onboarding/sessions/{sid}/voice/speech/not-a-message").status_code == 422
        learner_session(other_client)
        assert other_client.get(f"/api/onboarding/sessions/{sid}/voice/speech/{reply['message_id']}").status_code == 404  # someone else's session
        assert len(fake_voice.spoken) == 1
    finally:
        install_test_tutor(None)


# ---------------------------------------------------------------- Vertex AI speech (ADR-026 hybrid)
class FixedToken:
    def __init__(self):
        self.calls = 0

    def get(self) -> str:
        self.calls += 1
        return "ya29.test"


def test_vertex_speech_reads_the_text_with_the_service_account_token():
    from app.integrations.voice import VertexSpeech

    pcm = struct.pack("<4h", 3, -3, 4, -4)
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["url"], seen["auth"], seen["key"], seen["body"] = str(req.url), req.headers.get("authorization"), req.headers.get("x-goog-api-key"), json.loads(req.content)
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"inlineData": {"mimeType": "audio/L16;codec=pcm;rate=24000", "data": base64.b64encode(pcm).decode()}}]}}]})

    speech = VertexSpeech("demo-proj", "global", "gemini-tts-test", "Kore", httpx.Client(transport=httpx.MockTransport(handler)), FixedToken())
    g = GeminiVoice("test-key", "gemini-transcribe-test", "gemini-tts-test", "Kore", ["en-US"], "VERBATIM", client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500))), speech=speech)
    wav = g.speak("Use the current approved version.")
    assert seen["url"] == "https://aiplatform.googleapis.com/v1/projects/demo-proj/locations/global/publishers/google/models/gemini-tts-test:generateContent"
    assert seen["auth"] == "Bearer ya29.test" and seen["key"] is None  # IAM, never the API key
    assert seen["body"]["contents"][0]["parts"][0]["text"] == "Use the current approved version."  # verbatim
    assert seen["body"]["generationConfig"]["speechConfig"]["voiceConfig"]["prebuiltVoiceConfig"]["voiceName"] == "Kore"
    assert wav[:4] == b"RIFF" and wav.endswith(pcm) and g.speech_backend == "vertex"


def test_vertex_regional_location_uses_the_regional_host():
    from app.integrations.voice import VertexSpeech

    s = VertexSpeech("p", "asia-southeast1", "m", "Kore", httpx.Client(), FixedToken())
    assert s.url.startswith("https://asia-southeast1-aiplatform.googleapis.com/v1/projects/p/locations/asia-southeast1/")


@pytest.mark.parametrize("status,retryable", [(429, True), (503, True), (403, False)])
def test_vertex_errors_become_typed_unavailability(status, retryable):
    from app.integrations.voice import VertexSpeech

    s = VertexSpeech("p", "global", "m", "Kore", httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(status))), FixedToken())
    with pytest.raises(VoiceUnavailable) as e:
        s.speak("Hi")
    assert e.value.retryable is retryable


def test_metadata_token_is_cached_until_near_expiry_and_failures_are_typed():
    from app.integrations.voice import MetadataToken

    calls = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(req)
        assert req.headers["metadata-flavor"] == "Google"
        return httpx.Response(200, json={"access_token": f"tok-{len(calls)}", "expires_in": 3599})

    t = MetadataToken(httpx.Client(transport=httpx.MockTransport(handler)))
    assert t.get() == "tok-1" and t.get() == "tok-1" and len(calls) == 1
    t._token = ("old", 0.0)  # expired
    assert t.get() == "tok-2"
    broken = MetadataToken(httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(404))))
    with pytest.raises(VoiceUnavailable) as e:
        broken.get()
    assert e.value.retryable


def test_speech_backend_follows_configuration(monkeypatch):
    from app.config import get_settings

    monkeypatch.setenv("GEMINI_API_KEY", "k")
    # "auto" reads aloud with the API key even on Cloud Run (Vertex's audio clips); Vertex is the fallback there.
    cases = [({}, "gemini_api"), ({"GOOGLE_GENAI_USE_VERTEXAI": "true", "GOOGLE_CLOUD_PROJECT": "p"}, "gemini_api"),
             ({"GOOGLE_GENAI_USE_VERTEXAI": "true"}, "gemini_api"),  # no project: can't address Vertex
             ({"GOOGLE_GENAI_USE_VERTEXAI": "true", "GOOGLE_CLOUD_PROJECT": "p", "VOICE_TTS_BACKEND": "gemini_api"}, "gemini_api"),
             ({"VOICE_TTS_BACKEND": "vertex", "GOOGLE_CLOUD_PROJECT": "p"}, "vertex"),
             ({"VOICE_TTS_BACKEND": "cloud_tts", "GOOGLE_CLOUD_PROJECT": "p"}, "cloud_tts"),  # Cloud Run (owner 2026-10-15)
             ({"VOICE_TTS_BACKEND": "cloud_tts", "GOOGLE_GENAI_USE_VERTEXAI": "true", "GOOGLE_CLOUD_PROJECT": "p"}, "cloud_tts"),
             ({"VOICE_TTS_BACKEND": "cloud_tts"}, "gemini_api")]  # no project: the key only
    try:
        for env, expected in cases:
            for k in ("GOOGLE_GENAI_USE_VERTEXAI", "GOOGLE_CLOUD_PROJECT", "VOICE_TTS_BACKEND"):
                monkeypatch.delenv(k, raising=False)
            for k, v in env.items():
                monkeypatch.setenv(k, v)
            get_settings.cache_clear()
            v = voice_mod.get_voice()
            assert v.speech_backend == expected, env
            assert (v._fallback is not None) == (env == {"GOOGLE_GENAI_USE_VERTEXAI": "true", "GOOGLE_CLOUD_PROJECT": "p"}), env  # only "auto" on Cloud Run
    finally:
        get_settings.cache_clear()


# ---------------------------------------------------------------- streamed read-aloud
def sse(*events) -> bytes:
    return "".join(f"data: {json.dumps(e)}\r\n\r\n" for e in events).encode()


def audio_event(pcm: bytes, mime="audio/l16; rate=24000; channels=1") -> dict:
    return {"candidates": [{"content": {"parts": [{"inlineData": {"mimeType": mime, "data": base64.b64encode(pcm).decode()}}]}}]}


def test_streamed_speech_yields_audio_as_it_arrives():
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["url"], seen["body"] = str(req.url), json.loads(req.content)
        return httpx.Response(200, content=sse(audio_event(b"\x01\x00\x02\x00"), {"usageMetadata": {}}, audio_event(b"\x03\x00")), headers={"content-type": "text/event-stream"})

    st = gemini(handler).speak_stream("Use the current approved version.")
    assert seen["url"].endswith("/models/gemini-tts-test:streamGenerateContent?alt=sse")
    assert seen["body"]["contents"][0]["parts"][0]["text"] == "Use the current approved version."  # verbatim
    assert st.rate == 24000 and b"".join(st.chunks) == b"\x01\x00\x02\x00\x03\x00"


@pytest.mark.parametrize("status,retryable", [(429, True), (503, True), (400, False)])
def test_streamed_speech_errors_before_audio_are_typed(status, retryable):
    g = gemini(lambda req: httpx.Response(status, json={"error": {"message": "no"}}))
    with pytest.raises(VoiceUnavailable) as e:
        g.speak_stream("Hi")
    assert e.value.retryable is retryable


def test_streamed_speech_without_audio_is_unavailable():
    g = gemini(lambda req: httpx.Response(200, content=sse({"usageMetadata": {}}), headers={"content-type": "text/event-stream"}))
    with pytest.raises(VoiceUnavailable):
        g.speak_stream("Hi")


def test_read_aloud_falls_back_to_vertex_only_when_the_api_key_fails():
    from app.integrations.voice import VertexSpeech

    vertex_calls = []

    def vertex(req: httpx.Request) -> httpx.Response:
        vertex_calls.append(str(req.url))
        return httpx.Response(200, content=sse(audio_event(b"\x07\x00", "audio/L16;codec=pcm;rate=24000")), headers={"content-type": "text/event-stream"})

    fallback = VertexSpeech("p", "global", "m", "Kore", httpx.Client(transport=httpx.MockTransport(vertex)), FixedToken())
    ok = GeminiVoice("k", "l", "m", "Kore", ["en-US"], "VERBATIM", client=httpx.Client(transport=httpx.MockTransport(
        lambda r: httpx.Response(200, content=sse(audio_event(b"\x01\x00", "audio/L16;codec=pcm;rate=24000")), headers={"content-type": "text/event-stream"}))), fallback=fallback)
    assert b"".join(ok.speak_stream("Hi").chunks) == b"\x01\x00" and vertex_calls == []  # the API key's audio when it works
    out_of_balance = GeminiVoice("k", "l", "m", "Kore", ["en-US"], "VERBATIM", client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(429))), fallback=fallback)
    assert b"".join(out_of_balance.speak_stream("Hi").chunks) == b"\x07\x00" and len(vertex_calls) == 1  # Vertex keeps read-aloud going
    no_fallback = GeminiVoice("k", "l", "m", "Kore", ["en-US"], "VERBATIM", client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(429))))
    with pytest.raises(VoiceUnavailable):
        no_fallback.speak_stream("Hi")


def wav(pcm: bytes, rate: int = 24000) -> bytes:
    import io
    import wave

    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return b.getvalue()


def test_cloud_text_to_speech_reads_the_text_with_the_chirp_voice_and_the_service_token():
    from app.integrations.voice import CloudSpeech

    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["url"], seen["auth"], seen["body"] = str(req.url), req.headers.get("authorization"), json.loads(req.content)
        return httpx.Response(200, json={"audioContent": base64.b64encode(wav(b"\x01\x00\x02\x00")).decode()})

    cs = CloudSpeech("p", "en-US-Chirp3-HD-Kore", httpx.Client(transport=httpx.MockTransport(handler)), FixedToken())
    st = cs.speak_stream("Would you like me to add this to Google Calendar?")
    assert seen["url"] == "https://texttospeech.googleapis.com/v1/text:synthesize" and seen["auth"] == "Bearer ya29.test"
    assert seen["body"] == {"input": {"text": "Would you like me to add this to Google Calendar?"}, "voice": {"languageCode": "en-US", "name": "en-US-Chirp3-HD-Kore"},
                            "audioConfig": {"audioEncoding": "LINEAR16", "sampleRateHertz": 24000}}
    assert st.rate == 24000 and b"".join(st.chunks) == b"\x01\x00\x02\x00"  # the WAV header is removed: raw PCM, one piece
    assert cs.speak("Hi")[:4] == b"RIFF"


def test_read_aloud_uses_cloud_text_to_speech_and_the_api_key_only_if_it_fails():
    from app.integrations.voice import CloudSpeech

    key_calls = []

    def key(req: httpx.Request) -> httpx.Response:
        key_calls.append(str(req.url))
        return httpx.Response(200, content=sse(audio_event(b"\x09\x00", "audio/L16;codec=pcm;rate=24000")), headers={"content-type": "text/event-stream"})

    def voice(cloud_status: int) -> GeminiVoice:
        cloud = CloudSpeech("p", "en-US-Chirp3-HD-Kore", httpx.Client(transport=httpx.MockTransport(
            lambda r: httpx.Response(cloud_status, json={"audioContent": base64.b64encode(wav(b"\x07\x00")).decode()} if cloud_status == 200 else {"error": {"message": "no"}}))), FixedToken())
        return GeminiVoice("k", "l", "m", "Kore", ["en-US"], "VERBATIM", client=httpx.Client(transport=httpx.MockTransport(key)), speech=cloud)

    assert b"".join(voice(200).speak_stream("Hi").chunks) == b"\x07\x00" and key_calls == []
    assert b"".join(voice(503).speak_stream("Hi").chunks) == b"\x09\x00" and len(key_calls) == 1  # the key keeps read-aloud going


def test_vertex_streamed_speech_uses_the_stream_endpoint_with_the_service_token():
    from app.integrations.voice import VertexSpeech

    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["url"], seen["auth"] = str(req.url), req.headers.get("authorization")
        return httpx.Response(200, content=sse(audio_event(b"\x05\x00", "audio/L16;codec=pcm;rate=24000")), headers={"content-type": "text/event-stream"})

    st = VertexSpeech("p", "global", "m", "Kore", httpx.Client(transport=httpx.MockTransport(handler)), FixedToken()).speak_stream("Hi")
    assert seen["url"] == "https://aiplatform.googleapis.com/v1/projects/p/locations/global/publishers/google/models/m:streamGenerateContent?alt=sse"
    assert seen["auth"] == "Bearer ya29.test" and b"".join(st.chunks) == b"\x05\x00"


def test_stream_endpoint_reads_only_committed_tutor_replies(client, other_client, engine, fake_voice):
    t = ScriptedTutor(engine)
    install_test_tutor(t)
    try:
        s = learner_session(client)
        sid = s["learning_session_id"]
        from sqlalchemy import text as sql

        with engine.connect() as c:
            ver, sec = c.execute(sql("""SELECT ks.document_version_id, ks.section_id FROM workweave.knowledge_sections ks
                                       JOIN workweave.learning_sessions ls ON ls.workspace_id = ks.workspace_id
                                       WHERE ls.learning_session_id=:s AND ks.section_key='h2:1/h3:1'"""), {"s": sid}).one()
        t.then(ok(teaching([cite(ver, sec)])))
        v = client.post(f"/api/onboarding/sessions/{sid}/turns", json={"client_turn_id": str(uuid.uuid4()), "expected_revision": s["revision"], "text": "Hi", "input_kind": "TEXT"}).json()["data"]
        learner_msg, reply = v["transcript"]
        r = client.get(f"/api/onboarding/sessions/{sid}/voice/speech/{reply['message_id']}/stream")
        assert r.status_code == 200 and r.content == b"\x01\x00\x02\x00\x03\x00"
        assert r.headers["x-sample-rate"] == "24000" and r.headers["content-type"].startswith("audio/L16") and "no-store" in r.headers["cache-control"]
        assert fake_voice.spoken == [reply["text"]]
        assert client.get(f"/api/onboarding/sessions/{sid}/voice/speech/{learner_msg['message_id']}/stream").status_code == 422
        learner_session(other_client)
        assert other_client.get(f"/api/onboarding/sessions/{sid}/voice/speech/{reply['message_id']}/stream").status_code == 404
    finally:
        install_test_tutor(None)



# ---------------------------------------------------------------- replaying a reply (audio cache)
def _reply(client, engine, tutor, text=None):
    s = learner_session(client)
    sid = s["learning_session_id"]
    from sqlalchemy import text as sql

    with engine.connect() as c:
        ver, sec = c.execute(sql("""SELECT ks.document_version_id, ks.section_id FROM workweave.knowledge_sections ks
                                   JOIN workweave.learning_sessions ls ON ls.workspace_id = ks.workspace_id
                                   WHERE ls.learning_session_id=:s AND ks.section_key='h2:1/h3:1'"""), {"s": sid}).one()
    extra = {"reply": {"kind": "TEACHING", "text": text, "strategy": "CONCISE", "citations": [cite(ver, sec)]}} if text else {}
    tutor.then(ok(teaching([cite(ver, sec)], **extra)))
    v = client.post(f"/api/onboarding/sessions/{sid}/turns", json={"client_turn_id": str(uuid.uuid4()), "expected_revision": s["revision"], "text": "Hi", "input_kind": "TEXT"}).json()["data"]
    return f"/api/onboarding/sessions/{sid}/voice/speech/{v['transcript'][-1]['message_id']}/stream", s


@pytest.fixture()
def tutor(engine):
    t = ScriptedTutor(engine)
    install_test_tutor(t)
    yield t
    install_test_tutor(None)


def test_replaying_a_reply_reuses_its_audio_without_a_new_call_or_allowance(client, engine, fake_voice, tutor):
    from sqlalchemy import text as sql

    with engine.begin() as c:  # count read-aloud use for this test (the suite runs with caps off)
        c.execute(sql("DELETE FROM workweave.demo_usage"))
        c.execute(sql("UPDATE workweave.demo_usage_limits SET daily_limit=10 WHERE tier='PUBLIC' AND scope_type='POOL' AND usage_kind='VOICE_SPEECH'"))
    try:
        _replay_check(client, engine, fake_voice, tutor)
    finally:
        with engine.begin() as c:
            c.execute(sql("DELETE FROM workweave.demo_usage"))
            c.execute(sql("UPDATE workweave.demo_usage_limits SET daily_limit=0"))


def _replay_check(client, engine, fake_voice, tutor):
    url, s = _reply(client, engine, tutor)
    first = client.get(url)
    again = client.get(url)
    assert first.status_code == again.status_code == 200 and again.content == first.content
    assert again.headers["x-sample-rate"] == "24000"
    assert len(fake_voice.spoken) == 1  # Gemini was asked once
    with engine.connect() as c:
        from sqlalchemy import text as sql

        used = c.execute(sql("SELECT used FROM workweave.demo_usage WHERE scope_type='PUBLIC_POOL' AND usage_kind='VOICE_SPEECH'")).scalar_one()
    assert used == 1  # the replay didn't count against the read-aloud limit


def test_a_stream_cut_short_is_not_replayed(client, engine, fake_voice, tutor):
    from app.integrations.voice import SpeechStream

    calls = []

    def cut_short(text):
        calls.append(text)
        st = SpeechStream(24000, iter([b"\x01\x00"]))
        st.truncated = True
        return st

    fake_voice.speak_stream = cut_short
    url, _ = _reply(client, engine, tutor)
    client.get(url)
    client.get(url)
    assert len(calls) == 2  # generated again: a partial clip is never cached


def test_the_audio_cache_drops_the_oldest_replies_when_full():
    from app.services.voice import AudioCache

    c = AudioCache(max_bytes=10)
    c.put(("s", "a"), 24000, b"12345")
    c.put(("s", "b"), 24000, b"12345")
    assert c.get(("s", "a"))  # touched: now the most recent
    c.put(("s", "c"), 24000, b"12345")  # over the limit: "b" (least recently used) goes
    assert c.get(("s", "b")) is None and c.get(("s", "a")) and c.get(("s", "c"))
    c.put(("s", "huge"), 24000, b"x" * 11)  # larger than the whole cache: never stored
    assert c.get(("s", "huge")) is None


# ---------------------------------------------------------------- reading a reply sentence by sentence
LONG_REPLY = (
    "Good question! Start with what you saw yourself on the floor today. "
    "Then add what someone else told you, and say who it came from. "
    "Keep anything you're assuming separate, and mark it as an assumption so the next shift can check it. "
    "Finally, list what you don't know yet."
)


def test_speech_parts_are_a_short_opening_then_parts_that_grow():
    from app.services.voice import FIRST_PART_MAX, GROWTH, GROWTH_MIN, REST_MAX, speech_parts

    parts = speech_parts(LONG_REPLY)
    assert len(parts) >= 2 and len(parts[0]) <= FIRST_PART_MAX
    assert " ".join(parts) == LONG_REPLY
    # A long reply: each part at most GROWTH times the one before (so it's ready before that one ends).
    long_reply = "Here is your plan. " + " ".join(f"Ticket {800 + i} needs a check of the bolts on line {i}, and the readings go in the log." for i in range(12))
    parts = speech_parts(long_reply)
    assert " ".join(parts) == long_reply and len(parts) >= 3
    assert all(len(b) <= max(GROWTH_MIN, GROWTH * len(a)) for a, b in zip(parts, parts[1:]))
    long = " ".join(f"Sentence number {i} is here." for i in range(400))
    assert all(len(p) <= REST_MAX for p in speech_parts(long)) and " ".join(speech_parts(long)) == long
    assert speech_parts('He said "Stop now." Then he left.') == ['He said "Stop now." Then he left.']  # the quote stays
    assert speech_parts("Use e.g. SOP-001 v3.4 here.") == ["Use e.g. SOP-001 v3.4 here."]  # no split inside
    lines = speech_parts("Two things.\n- Ticket #829.\n- Ticket #910.")
    assert lines == ["Two things.\nTicket #829.", "Ticket #910."]  # a short opening takes the next line; bullets dropped, lines kept apart


def test_the_spoken_form_reads_schedules_cleanly_without_changing_the_words():
    from app.services.voice import spoken_text

    reply = ("I've updated your proposal:\n\n**Machine #14 inspection**\nTime: Oct 15, 01:00 PM – Oct 15, 01:30 PM\n\n"
             "- **Ticket #829 · Machine #14 inspection**: 12:10 PM – 12:40 PM (30 min)\n## Next\nWould you like me to add this to Google Calendar?")
    assert spoken_text(reply) == (
        "I've updated your proposal.\nMachine #14 inspection.\nTime: Oct 15, 1:00 PM to Oct 15, 1:30 PM.\n"
        "Ticket #829, Machine #14 inspection: 12:10 PM to 12:40 PM (30 min).\nNext.\nWould you like me to add this to Google Calendar?"
    )
    assert spoken_text("Version 3.4 of SOP-001, ticket #829, costs 10:05.") == "Version 3.4 of SOP-001, ticket #829, costs 10:05."  # nothing else changes


def test_a_reply_read_in_parts_costs_one_allowance_and_each_part_replays_free(client, engine, fake_voice, tutor):
    from sqlalchemy import text as sql

    from app.services.voice import audio_cache, charged, speech_parts

    audio_cache.clear()
    charged.clear()
    with engine.begin() as c:
        c.execute(sql("DELETE FROM workweave.demo_usage"))
        c.execute(sql("UPDATE workweave.demo_usage_limits SET daily_limit=10 WHERE tier='PUBLIC' AND scope_type='POOL' AND usage_kind='VOICE_SPEECH'"))
    try:
        url, _ = _reply(client, engine, tutor, LONG_REPLY)
        expected = speech_parts(LONG_REPLY)
        first = client.get(url, params={"part": 0})
        assert first.status_code == 200 and first.headers["x-speech-parts"] == str(len(expected)) and first.headers["x-sample-rate"] == "24000"
        for n in range(1, len(expected)):
            assert client.get(url, params={"part": n}).headers["x-speech-parts"] == str(len(expected))
        assert fake_voice.spoken == expected  # one Gemini call per part, each part's own text
        assert client.get(url, params={"part": 0}).content == first.content and len(fake_voice.spoken) == len(expected)  # replayed from the cache
        assert client.get(url, params={"part": len(expected)}).status_code == 422  # no such part
        assert client.get(url, params={"part": -1}).status_code == 422
        assert "x-speech-parts" not in client.get(url).headers  # without ?part: the whole reply, as before
        with engine.connect() as c:
            used = c.execute(sql("SELECT used FROM workweave.demo_usage WHERE scope_type='PUBLIC_POOL' AND usage_kind='VOICE_SPEECH'")).scalar_one()
        assert used == 2  # the reply read in parts once, plus the separate whole-reply request
    finally:
        audio_cache.clear()
        charged.clear()
        with engine.begin() as c:
            c.execute(sql("DELETE FROM workweave.demo_usage"))
            c.execute(sql("UPDATE workweave.demo_usage_limits SET daily_limit=0"))
