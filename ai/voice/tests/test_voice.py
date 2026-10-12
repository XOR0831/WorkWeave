"""Tests for the standalone voice module. No network, microphone or speaker: Gemini and the
LangGraph server are replaced by small fakes.

Run from the repository root:  .ai_builder_env/bin/python -m unittest discover -s voice/tests -t .
"""

import array
import asyncio
import base64
import io
import time
import unittest
import wave
from types import SimpleNamespace as NS

from voice.audio import chunks, pcm_to_wav, resample_pcm16, wav_to_pcm
from voice.config import VoiceConfig
from voice.console import run_conversation
from voice.nodes import NoSpeech, make_stt_node, make_tts_node, resolve_voice_input
from voice.stt import Transcript, transcribe_pcm, transcribe_stream
from voice.tts import synthesize

CFG = VoiceConfig(api_key="test", listen_model="transcribe-test", tts_model="tts-test", tts_voice="Kore", language_codes=["en-US"], transcript_mode="VERBATIM", silence_ms=700)


def tone(n: int) -> bytes:
    return array.array("h", [1000] * n).tobytes()


def msg(interim=None, final=None, turn_complete=False, lang="en-US", generation_complete=False):
    return NS(
        server_content=NS(
            interim_input_transcription=NS(text=interim) if interim else None,
            input_transcription=NS(text=final, language_code=lang) if final else None,
            turn_complete=turn_complete,
            generation_complete=generation_complete,
        )
    )


class FakeSession:
    def __init__(self, script, hold_open=False):
        self.script = script
        self.hold_open = hold_open
        self.sent = []

    async def send_realtime_input(self, **kw):
        self.sent.append(kw)

    async def receive(self):
        for m in self.script:
            await asyncio.sleep(0)
            yield m
        if self.hold_open:  # a live stream that never says turn_complete
            await asyncio.sleep(3600)


class FakeLive:
    def __init__(self, session):
        self.session = session
        self.calls = []

    def connect(self, *, model, config):
        self.calls.append((model, config))
        session = self.session

        class Ctx:
            async def __aenter__(self):
                return session

            async def __aexit__(self, *a):
                return False

        return Ctx()


def live_client(session):
    live = FakeLive(session)
    return NS(aio=NS(live=live)), live


class AudioTests(unittest.TestCase):
    def test_chunks_wav_and_resample(self):
        pcm = tone(16000)  # 1 s at 16 kHz
        self.assertEqual([len(c) for c in chunks(pcm)], [3200] * 10)
        self.assertEqual(wav_to_pcm(pcm_to_wav(pcm, 16000)), (pcm, 16000))
        self.assertEqual(len(resample_pcm16(tone(48000), 48000, 16000)), 32000)


class SpeechToTextTests(unittest.TestCase):
    def test_streams_audio_with_server_vad_and_returns_the_final_transcript(self):
        session = FakeSession([msg(interim="use the"), msg(final="Use the current"), msg(final="approved version."), msg(turn_complete=True)])
        client, live = live_client(session)
        interim = []
        t = asyncio.run(transcribe_stream([tone(1600), tone(1600)], cfg=CFG, on_interim=interim.append, client=client))
        self.assertEqual(t, Transcript("Use the current approved version.", "en-US"))
        self.assertEqual(interim, ["use the"])
        model, config = live.calls[0]
        self.assertEqual(model, "transcribe-test")
        self.assertEqual([m.value if hasattr(m, "value") else m for m in config.response_modalities], ["TEXT"])  # transcripts only, never a reply
        self.assertEqual(config.input_audio_transcription.mode, "VERBATIM")
        vad = config.realtime_input_config.automatic_activity_detection
        self.assertFalse(vad.disabled)
        self.assertEqual(vad.silence_duration_ms, 700)
        audio = [s["audio"] for s in session.sent if "audio" in s]
        self.assertEqual(len(audio), 2)
        self.assertEqual(audio[0].mime_type, "audio/pcm;rate=16000")
        self.assertIn({"audio_stream_end": True}, session.sent)

    def test_hands_free_returns_after_a_pause_without_turn_complete(self):
        session = FakeSession([msg(final="I think it's v3.4")], hold_open=True)
        client, _ = live_client(session)
        t = asyncio.run(transcribe_stream([tone(1600)], cfg=CFG, client=client, settle_s=0.2, timeout_s=5))
        self.assertEqual(t.text, "I think it's v3.4")

    def test_tap_to_talk_returns_right_after_stop_without_turn_complete(self):
        # The transcription-only model ends with generation_complete and never sends turn_complete.
        session = FakeSession([msg(final="Which version should I follow?"), msg(generation_complete=True)], hold_open=True)
        client, _ = live_client(session)
        started = time.monotonic()
        t = asyncio.run(transcribe_stream([tone(1600)], cfg=CFG, client=client, stop_after_utterance=False, timeout_s=30))
        self.assertEqual(t.text, "Which version should I follow?")
        self.assertLess(time.monotonic() - started, 3)

    def test_tap_to_talk_with_nothing_said_returns_empty_soon_after_stop(self):
        session = FakeSession([], hold_open=True)
        client, _ = live_client(session)
        started = time.monotonic()
        t = asyncio.run(transcribe_stream([tone(1600)], cfg=CFG, client=client, stop_after_utterance=False, timeout_s=30))
        self.assertEqual(t.text, "")
        self.assertLess(time.monotonic() - started, 8)

    def test_synchronous_helper_resamples_a_recording(self):
        session = FakeSession([msg(final="Hello"), msg(turn_complete=True)])
        client, _ = live_client(session)
        self.assertEqual(transcribe_pcm(tone(4800), 48000, cfg=CFG, client=client).text, "Hello")
        self.assertEqual(sum(len(s["audio"].data) for s in session.sent if "audio" in s), 3200)  # 0.1 s at 16 kHz


class TextToSpeechTests(unittest.TestCase):
    def client(self, data, mime="audio/L16;codec=pcm;rate=24000"):
        calls = []

        def generate_content(**kw):
            calls.append(kw)
            return NS(candidates=[NS(content=NS(parts=[NS(inline_data=NS(data=data, mime_type=mime) if data is not None else None)]))])

        return NS(models=NS(generate_content=generate_content)), calls

    def test_reads_text_verbatim_with_the_configured_voice_and_returns_wav(self):
        pcm = tone(10)
        client, calls = self.client(pcm)
        wav = synthesize("Use the current approved version.", cfg=CFG, client=client)
        self.assertEqual(calls[0]["contents"], "Use the current approved version.")  # no added prompt
        self.assertEqual(calls[0]["model"], "tts-test")
        self.assertEqual(calls[0]["config"].speech_config.voice_config.prebuilt_voice_config.voice_name, "Kore")
        with wave.open(io.BytesIO(wav)) as w:
            self.assertEqual((w.getframerate(), w.readframes(w.getnframes())), (24000, pcm))

    def test_errors(self):
        client, _ = self.client(None)
        with self.assertRaises(RuntimeError):
            synthesize("Hi", cfg=CFG, client=client)
        with self.assertRaises(ValueError):
            synthesize("   ", cfg=CFG, client=client)


class NodeTests(unittest.TestCase):
    def test_resolve_voice_input_turns_audio_into_a_voice_transcript(self):
        self.assertEqual(resolve_voice_input("typed"), "typed")
        self.assertEqual(resolve_voice_input({"message": "typed", "input_kind": "TEXT"}), {"message": "typed", "input_kind": "TEXT"})
        seen = []
        out = resolve_voice_input(
            {"audio_b64": base64.b64encode(pcm_to_wav(tone(800), 16000)).decode(), "extra": 1},
            transcribe=lambda pcm, rate: seen.append((len(pcm), rate)) or Transcript("Which version?"),
        )
        self.assertEqual(out, {"extra": 1, "message": "Which version?", "input_kind": "VOICE_TRANSCRIPT"})
        self.assertEqual(seen, [(1600, 16000)])
        with self.assertRaises(NoSpeech):
            resolve_voice_input({"audio_b64": base64.b64encode(tone(10)).decode()}, transcribe=lambda pcm, rate: Transcript(""))

    def test_node_factories_work_with_any_state_shape(self):
        stt = make_stt_node(lambda s: (s["audio"], 16000) if s.get("audio") else None, lambda s, t: {**s, "user_message": t}, transcribe=lambda pcm, rate: Transcript("Hi"))
        self.assertEqual(stt({"audio": tone(10)})["user_message"], "Hi")
        self.assertEqual(stt({}), {})
        tts = make_tts_node(lambda s: s.get("assistant_message"), lambda s, a: {**s, "assistant_audio": a}, synthesize=lambda t: b"RIFFwav")
        self.assertEqual(base64.b64decode(tts({"assistant_message": "Hello"})["assistant_audio"]), b"RIFFwav")


class FakeGraph:
    """Minimal langgraph_sdk sync client: two interrupts, then the run ends."""

    def __init__(self):
        self.waits = []
        self.pending = [{"value": {"message": "Welcome! What do you know about SOP-001?"}}, {"value": {"message": "Which version is current?"}}]
        self.threads = NS(create=lambda: {"thread_id": "t1"}, get_state=lambda tid: {"tasks": [{"interrupts": self.pending[:1]}]})
        self.runs = NS(wait=self.wait)

    def wait(self, thread_id, graph, input=None, command=None):  # noqa: A002
        self.waits.append({"input": input, "command": command})
        if command:
            self.pending.pop(0)
        return {"conversation": {"assistant_message": "Great, v3.4 is current." if not self.pending else "…"}}


class ConsoleTests(unittest.TestCase):
    def test_speaks_each_interrupt_listens_and_resumes_with_a_voice_transcript(self):
        g = FakeGraph()
        answers = iter(["", "I've read it once", "v3.4"])
        spoken = []
        run_conversation(g, "ai_adaptive_onboarding", {"employee": {"employee_id": "e"}}, lambda: next(answers), lambda t: spoken.append(t) or False, log=lambda s: None)
        self.assertEqual(g.waits[0]["input"], {"employee": {"employee_id": "e"}})
        resumes = [w["command"]["resume"] for w in g.waits if w["command"]]
        self.assertEqual(resumes, [{"message": "I've read it once", "input_kind": "VOICE_TRANSCRIPT"}, {"message": "v3.4", "input_kind": "VOICE_TRANSCRIPT"}])  # empty answer not sent
        self.assertEqual(spoken[0], "Welcome! What do you know about SOP-001?")
        self.assertEqual(spoken[-1], "Great, v3.4 is current.")


if __name__ == "__main__":
    unittest.main()
