"""Speech to text with voice activity detection: Gemini's transcription-only Live model.

The model only transcribes (text output); it never answers. Automatic activity detection runs on
the server: it decides where speech starts and ends, so silence before/after is ignored and an
utterance ends after a pause (VoiceConfig.silence_ms).
"""

import asyncio
from collections.abc import AsyncIterator, Callable, Iterable
from dataclasses import dataclass
from typing import Any

from .audio import LISTEN_RATE, chunks, resample_pcm16
from .config import VoiceConfig, load_config


@dataclass(frozen=True)
class Transcript:
    text: str
    language_code: str | None = None

    @property
    def empty(self) -> bool:
        return not self.text.strip()


def live_config(cfg: VoiceConfig) -> Any:
    from google.genai import types

    return types.LiveConnectConfig(
        response_modalities=[types.Modality.TEXT],
        input_audio_transcription=types.AudioTranscriptionConfig(language_codes=cfg.language_codes or None, mode=cfg.transcript_mode),
        realtime_input_config=types.RealtimeInputConfig(
            automatic_activity_detection=types.AutomaticActivityDetection(disabled=False, silence_duration_ms=cfg.silence_ms)
        ),
    )


def _client(cfg: VoiceConfig) -> Any:
    from google import genai

    if not cfg.api_key:
        raise RuntimeError("GEMINI_API_KEY is not set; voice is unavailable.")
    return genai.Client(api_key=cfg.api_key)


async def transcribe_stream(
    audio: AsyncIterator[bytes] | Iterable[bytes],
    *,
    cfg: VoiceConfig | None = None,
    on_interim: Callable[[str], None] | None = None,
    stop_after_utterance: bool = True,
    settle_s: float = 0.8,
    timeout_s: float = 120.0,
    client: Any = None,
) -> Transcript:
    """Stream 16 kHz PCM chunks to Gemini Live; return the finalized transcript.

    With stop_after_utterance, returns once the server's VAD has finalized speech and nothing new
    arrived for settle_s (hands-free). Otherwise returns when the audio ends (tap-to-talk/files).
    """
    cfg = cfg or load_config()
    client = client or _client(cfg)
    finals: list[str] = []
    language: list[str | None] = [None]
    done = asyncio.Event()
    ended_at: list[float | None] = [None]  # when the audio stream ended (tap: the learner pressed Stop)
    last_final = [0.0]
    loop = asyncio.get_running_loop()

    async with client.aio.live.connect(model=cfg.listen_model, config=live_config(cfg)) as session:
        from google.genai import types

        async def send() -> None:
            if hasattr(audio, "__aiter__"):
                async for c in audio:  # type: ignore[union-attr]
                    if done.is_set():
                        return
                    await session.send_realtime_input(audio=types.Blob(data=c, mime_type=f"audio/pcm;rate={LISTEN_RATE}"))
            else:
                for c in audio:  # type: ignore[union-attr]
                    await session.send_realtime_input(audio=types.Blob(data=c, mime_type=f"audio/pcm;rate={LISTEN_RATE}"))
            await session.send_realtime_input(audio_stream_end=True)
            ended_at[0] = loop.time()

        async def receive() -> None:
            async for msg in session.receive():
                sc = getattr(msg, "server_content", None)
                if not sc:
                    continue
                if sc.interim_input_transcription and sc.interim_input_transcription.text and on_interim:
                    on_interim(" ".join([*finals, sc.interim_input_transcription.text.strip()]))
                if sc.input_transcription and sc.input_transcription.text:
                    finals.append(sc.input_transcription.text.strip())
                    language[0] = sc.input_transcription.language_code or language[0]
                    last_final[0] = loop.time()
                # The transcription-only model ends an utterance with generation_complete and sends
                # no turn_complete (observed 2026-10-04), so accept either. In tap-to-talk a pause
                # mid-sentence also ends an utterance, so only finish once the audio has ended.
                if (sc.turn_complete or sc.generation_complete) and finals and (stop_after_utterance or ended_at[0] is not None):
                    done.set()
                    return

        async def settle() -> None:
            while not done.is_set():
                await asyncio.sleep(0.1)
                ended = ended_at[0] is not None
                if (stop_after_utterance or ended) and finals and loop.time() - last_final[0] >= settle_s:
                    done.set()
                # Nothing was said: don't wait for the 2-minute timeout after Stop.
                elif ended and not finals and loop.time() - ended_at[0] >= 5.0:
                    done.set()

        tasks = [asyncio.create_task(send()), asyncio.create_task(receive()), asyncio.create_task(settle())]
        try:
            await asyncio.wait_for(done.wait(), timeout=timeout_s)
        except TimeoutError:
            pass
        finally:
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
    return Transcript(" ".join(finals).strip(), language[0])


def transcribe_pcm(pcm: bytes, rate: int = LISTEN_RATE, *, cfg: VoiceConfig | None = None, client: Any = None) -> Transcript:
    """Transcribe a finished recording (16-bit mono PCM). Synchronous helper for graph nodes."""
    data = resample_pcm16(pcm, rate, LISTEN_RATE)
    coro = transcribe_stream(chunks(data), cfg=cfg, stop_after_utterance=False, timeout_s=60.0, client=client)
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    # Called from inside a running loop (e.g. an async graph): run in a worker thread.
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(1) as ex:
        return ex.submit(asyncio.run, coro).result()
