"""Voice settings from the environment (the same .env the graph uses). Model IDs are configuration."""

import json
import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class VoiceConfig:
    api_key: str = ""
    listen_model: str = "gemini-3.5-transcribe-live"
    tts_model: str = "gemini-3.8-flash-lite-tts"
    tts_voice: str = "Kore"
    language_codes: list[str] = field(default_factory=lambda: ["en-US"])
    # VERBATIM keeps the speaker's exact words; SMART removes fillers and formats text.
    transcript_mode: str = "VERBATIM"
    # Voice activity detection: how long a pause ends an utterance (server side).
    silence_ms: int = 800


def load_config() -> VoiceConfig:
    langs = os.getenv("VOICE_LANGUAGE_CODES", '["en-US"]')
    try:
        language_codes = [str(x) for x in json.loads(langs)]
    except ValueError:
        language_codes = [x.strip() for x in langs.split(",") if x.strip()]
    return VoiceConfig(
        api_key=os.getenv("GEMINI_API_KEY", ""),
        listen_model=os.getenv("VOICE_LISTEN_MODEL", VoiceConfig.listen_model),
        tts_model=os.getenv("VOICE_TTS_MODEL", VoiceConfig.tts_model),
        tts_voice=os.getenv("VOICE_TTS_VOICE", VoiceConfig.tts_voice),
        language_codes=language_codes,
        transcript_mode=os.getenv("VOICE_TRANSCRIPT_MODE", VoiceConfig.transcript_mode),
        silence_ms=int(os.getenv("VOICE_SILENCE_MS", str(VoiceConfig.silence_ms))),
    )
