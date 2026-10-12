"""Standalone voice for the onboarding LangGraph flow: speech-to-text with voice activity detection
(Gemini Live transcription) and text-to-speech (Gemini TTS).

Transport only: it turns speech into text and text into speech. It has no tutor logic and does not
analyse how someone sounds (no tone, emotion or hesitation inference). Drop-in pieces:

- resolve_voice_input(payload): use inside wait_for_user so an interrupt can be resumed with audio.
- make_stt_node / make_tts_node: LangGraph nodes for any state shape (you choose the fields).
- transcribe_pcm / synthesize: plain functions.
- python -m voice.console: a local mic/speaker client for testing the graph under `langgraph dev`.
"""

from .config import VoiceConfig, load_config
from .nodes import make_stt_node, make_tts_node, resolve_voice_input
from .stt import Transcript, transcribe_pcm
from .tts import synthesize

__all__ = ["VoiceConfig", "load_config", "Transcript", "transcribe_pcm", "synthesize", "resolve_voice_input", "make_stt_node", "make_tts_node"]
