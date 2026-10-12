"""PCM/WAV helpers. Gemini Live transcription takes 16 kHz, 16-bit, mono PCM; TTS returns 24 kHz PCM."""

import base64
import io
import wave

LISTEN_RATE = 16000
CHUNK_MS = 100


def chunks(pcm: bytes, rate: int = LISTEN_RATE, ms: int = CHUNK_MS) -> list[bytes]:
    """Split 16-bit mono PCM into ~100 ms chunks (what the Live API expects)."""
    size = rate * 2 * ms // 1000
    return [pcm[i : i + size] for i in range(0, len(pcm), size)] or [b""]


def wav_to_pcm(data: bytes) -> tuple[bytes, int]:
    """Return (16-bit mono PCM, sample rate) from WAV bytes; raw PCM passes through at 16 kHz."""
    if data[:4] != b"RIFF":
        return data, LISTEN_RATE
    with wave.open(io.BytesIO(data)) as w:
        if w.getsampwidth() != 2 or w.getnchannels() != 1:
            raise ValueError("WAV audio must be 16-bit mono")
        return w.readframes(w.getnframes()), w.getframerate()


def pcm_to_wav(pcm: bytes, rate: int) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


def resample_pcm16(pcm: bytes, from_rate: int, to_rate: int = LISTEN_RATE) -> bytes:
    """Linear resample of 16-bit mono PCM (stdlib only)."""
    if from_rate == to_rate or not pcm:
        return pcm
    import array

    src = array.array("h")
    src.frombytes(pcm[: len(pcm) - len(pcm) % 2])
    n = int(len(src) * to_rate / from_rate)
    out = array.array("h", [0]) * n
    ratio = from_rate / to_rate
    for i in range(n):
        pos = i * ratio
        lo = int(pos)
        hi = min(lo + 1, len(src) - 1)
        out[i] = int(src[lo] + (src[hi] - src[lo]) * (pos - lo))
    return out.tobytes()


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def unb64(data: str) -> bytes:
    return base64.b64decode(data)
