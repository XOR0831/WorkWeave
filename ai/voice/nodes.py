"""LangGraph pieces that work with any state shape.

1. resolve_voice_input: call it on the value returned by `interrupt(...)` in wait_for_user. A resume
   payload can then carry audio instead of text:
       {"audio_b64": "<base64 16-bit mono PCM or WAV>", "sample_rate": 16000}
   and comes back as {"message": "<transcript>", "input_kind": "VOICE_TRANSCRIPT"}. Text payloads
   pass through unchanged, so typed input keeps working.

2. make_stt_node / make_tts_node: nodes you add to the graph, with small functions saying where the
   audio/text lives in your state. Nothing about the onboarding state is assumed.
"""

from collections.abc import Callable
from typing import Any

from .audio import unb64, wav_to_pcm, b64
from .stt import Transcript, transcribe_pcm
from .tts import synthesize as _synthesize

Transcribe = Callable[[bytes, int], Transcript]
Synthesize = Callable[[str], bytes]


class NoSpeech(ValueError):
    """The audio contained no words. Ask the learner to try again or type."""


def _default_transcribe(pcm: bytes, rate: int) -> Transcript:
    return transcribe_pcm(pcm, rate)


def resolve_voice_input(user_input: Any, *, transcribe: Transcribe = _default_transcribe) -> Any:
    if not isinstance(user_input, dict) or not user_input.get("audio_b64"):
        return user_input
    pcm, rate = wav_to_pcm(unb64(user_input["audio_b64"]))
    rate = int(user_input.get("sample_rate") or rate)
    t = transcribe(pcm, rate)
    if t.empty:
        raise NoSpeech("No speech was recognised in the audio.")
    rest = {k: v for k, v in user_input.items() if k not in ("audio_b64", "sample_rate")}
    return {**rest, "message": t.text, "input_kind": "VOICE_TRANSCRIPT"}


def make_stt_node(get_audio: Callable[[Any], tuple[bytes, int] | None], set_text: Callable[[Any, str], Any], *, transcribe: Transcribe = _default_transcribe) -> Callable[[Any], Any]:
    """Node: audio in state -> transcript in state. get_audio returns (pcm_or_wav_bytes, rate) or None."""

    def speech_to_text(state: Any) -> Any:
        audio = get_audio(state)
        if not audio:
            return state
        pcm, rate = wav_to_pcm(audio[0])
        t = transcribe(pcm, audio[1] or rate)
        if t.empty:
            raise NoSpeech("No speech was recognised in the audio.")
        return set_text(state, t.text)

    return speech_to_text


def make_tts_node(get_text: Callable[[Any], str | None], set_audio: Callable[[Any, str], Any], *, synthesize: Synthesize = lambda t: _synthesize(t)) -> Callable[[Any], Any]:
    """Node: text in state (e.g. the assistant message) -> base64 WAV in state."""

    def text_to_speech(state: Any) -> Any:
        text = get_text(state)
        if not text:
            return state
        return set_audio(state, b64(synthesize(text)))

    return text_to_speech
