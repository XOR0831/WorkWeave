"""Text to speech with Gemini TTS: reads the given text verbatim and returns WAV bytes."""

from typing import Any

from .audio import pcm_to_wav
from .config import VoiceConfig, load_config

MAX_CHARS = 4000


def synthesize(text: str, *, cfg: VoiceConfig | None = None, client: Any = None) -> bytes:
    cfg = cfg or load_config()
    text = (text or "").strip()
    if not text:
        raise ValueError("Nothing to read aloud.")
    from google.genai import types

    if client is None:
        from .stt import _client

        client = _client(cfg)
    res = client.models.generate_content(
        model=cfg.tts_model,
        contents=text[:MAX_CHARS],
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(voice_config=types.VoiceConfig(prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=cfg.tts_voice))),
        ),
    )
    for part in (res.candidates or [None])[0].content.parts if res.candidates else []:
        inline = getattr(part, "inline_data", None)
        if inline and inline.data:
            data = inline.data
            if data[:4] == b"RIFF":
                return data
            rate = 24000
            for bit in (inline.mime_type or "").replace(" ", "").split(";"):
                if bit.startswith("rate="):
                    rate = int(bit[5:])
            return pcm_to_wav(data, rate)
    raise RuntimeError("The TTS model returned no audio.")
