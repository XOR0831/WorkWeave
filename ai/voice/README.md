# voice — standalone speech for the onboarding graph

Speech-to-text with voice activity detection (Gemini Live, transcription-only model) and
text-to-speech (Gemini TTS), packaged so it can be inserted into the LangGraph flow or used next to
it. Built for testing under `langgraph dev`; connecting it to the WorkWeave backend and UI comes later.

**Transport only.** It converts speech to text and text to speech. It has no tutor logic and does not
analyse how someone sounds (no tone, emotion or hesitation inference). The transcription model only
transcribes; it never generates a reply. Audio is not saved.

## Configuration (the same `.env` the graph uses)

| Variable | Default | Meaning |
|---|---|---|
| `GEMINI_API_KEY` | — | Required for real calls |
| `VOICE_LISTEN_MODEL` | `gemini-3.5-transcribe-live` | Live transcription model |
| `VOICE_TTS_MODEL` | `gemini-3.8-flash-lite-tts` | Text-to-speech model |
| `VOICE_TTS_VOICE` | `Kore` | Prebuilt voice |
| `VOICE_LANGUAGE_CODES` | `["en-US"]` | Transcription language hints |
| `VOICE_TRANSCRIPT_MODE` | `VERBATIM` | `VERBATIM` keeps exact words; `SMART` removes fillers |
| `VOICE_SILENCE_MS` | `800` | Pause length that ends an utterance (server VAD) |

## 1. Try it now without changing the graph: the voice console (workaround)

Start the graph (`langgraph dev` in `ai_adaptive_onboarding/`), then from the repository root:

```sh
pip install sounddevice          # microphone and speaker (only the console needs it)
python -m voice.console \
  --employee-id <id> --organization-id <id> --workspace-id <id> --session-id <learning session id> \
  --mode hands-free              # or: --mode tap (Enter to start/stop), --mode text (type), --mute
```

The console starts a run, reads each `interrupt` message aloud, listens to your answer and resumes
the interrupt with `{"message": <transcript>, "input_kind": "VOICE_TRANSCRIPT"}` — the payload
`wait_for_user` already accepts. While a reply plays, **Ctrl+C interrupts it**. The microphone is
closed during playback, so laptop speakers can't make the tutor interrupt itself.

## 2. Insert it into the graph

The graph runs from `ai_adaptive_onboarding/`, so `voice` must be importable from there first. Pick one:

- add `".."` to `"dependencies"` in `langgraph.json` once the root `pyproject.toml` declares the
  `voice` package, or
- install the repository root in the environment (`pip install -e .`) with `voice` listed as a package.

### a) Audio in the interrupt resume (one line in `wait_for_user`)

```python
from voice import resolve_voice_input

def wait_for_user(state):
    user_input = interrupt({"message": state.conversation.assistant_message})
    user_input = resolve_voice_input(user_input)   # audio -> {"message": ..., "input_kind": "VOICE_TRANSCRIPT"}
    ...
```

Resume with `{"audio_b64": "<base64 16-bit mono PCM or WAV>", "sample_rate": 16000}`. Text payloads
pass through unchanged. No words in the audio raises `voice.nodes.NoSpeech`.

### b) Nodes, for any state shape

```python
from voice import make_stt_node, make_tts_node

speak_reply = make_tts_node(
    get_text=lambda s: s.conversation.assistant_message,
    set_audio=lambda s, b64wav: (setattr(s.conversation, "assistant_audio_b64", b64wav), s)[1],
)
builder.add_node("text_to_speech", speak_reply)       # e.g. after the teaching/opening node
```

This needs a field to hold the audio, e.g. `assistant_audio_b64: Optional[str] = None` on
`ConversationState` (Pydantic rejects unknown attributes). `make_stt_node(get_audio, set_text)` is the mirror image (audio field -> user message). The nodes
call Gemini synchronously; keep them out of database transactions.

### c) Plain functions

`voice.transcribe_pcm(pcm, rate) -> Transcript`, `voice.transcribe_stream(chunks, on_interim=...)`
(async, for live audio) and `voice.synthesize(text) -> WAV bytes`.

## Tests (no network, microphone or speaker)

```sh
.ai_builder_env/bin/python -m unittest discover -s voice/tests -t .
```

## Later: connecting to WorkWeave

The WorkWeave app already has the browser side of this (tap-to-talk, hands-free, interruption,
reading replies aloud) using the same models and settings. When the graph is connected, the
browser sends the transcript as a normal turn with `input_kind: "VOICE_TRANSCRIPT"` and an
`interrupted_previous_reply` flag; this module stays useful for console testing and offline runs.
