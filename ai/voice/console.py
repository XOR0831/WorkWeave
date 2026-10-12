"""Local voice console for testing the onboarding graph under `langgraph dev` (a workaround until the
graph is connected to the WorkWeave backend and UI).

It starts a run, reads each interrupt's message aloud, listens to your answer (Gemini Live
transcription with voice activity detection) and resumes the interrupt with
{"message": <transcript>, "input_kind": "VOICE_TRANSCRIPT"} — the payload wait_for_user already
accepts, so the graph needs no change. Audio is never saved.

    python -m voice.console --employee-id ... --organization-id ... --workspace-id ... --session-id ...
        [--url http://127.0.0.1:2024] [--graph ai_adaptive_onboarding] [--mode hands-free|tap|text] [--mute]

Hands-free: speak; a pause ends your answer. Tap: press Enter to start and Enter to stop.
Text: type answers (no microphone). While a reply plays, press Ctrl+C to interrupt it.
The microphone is closed while a reply plays, so speakers can't make the tutor interrupt itself.
Needs `sounddevice` for the microphone and speaker (`pip install sounddevice`).
"""

import argparse
import asyncio
import io
import sys
import threading
import wave
from collections.abc import Callable
from typing import Any

from .audio import LISTEN_RATE
from .config import load_config
from .stt import transcribe_stream
from .tts import synthesize

Listen = Callable[[], str]
Speak = Callable[[str], bool]  # returns True if the learner interrupted


def interrupts_of(state: dict[str, Any]) -> list[dict[str, Any]]:
    found = list(state.get("interrupts") or [])
    for task in state.get("tasks") or []:
        found.extend(task.get("interrupts") or [])
    return found


def interrupt_message(intr: dict[str, Any]) -> str:
    value = intr.get("value")
    return str(value.get("message") or "") if isinstance(value, dict) else str(value or "")


def run_conversation(client: Any, graph: str, initial: dict[str, Any], listen: Listen, speak: Speak, log: Callable[[str], None] = print, max_turns: int = 50) -> dict[str, Any]:
    """Drive one thread: speak each interrupt message, listen, resume. Returns the final state values."""
    thread_id = client.threads.create()["thread_id"]
    values = client.runs.wait(thread_id, graph, input=initial)
    for _ in range(max_turns):
        pending = interrupts_of(client.threads.get_state(thread_id))
        if not pending:
            break
        message = interrupt_message(pending[0])
        log(f"\nTutor: {message}")
        interrupted = speak(message)
        if interrupted:
            log("(reply interrupted)")
        answer = listen()
        if not answer.strip():
            log("(nothing heard; try again or type)")
            continue
        log(f"You: {answer}")
        values = client.runs.wait(thread_id, graph, command={"resume": {"message": answer, "input_kind": "VOICE_TRANSCRIPT"}})
    final = (values or {}).get("conversation", {}) if isinstance(values, dict) else {}
    if final.get("assistant_message"):
        log(f"\nTutor: {final['assistant_message']}")
        speak(final["assistant_message"])
    log("\n(run finished)")
    return values


# ---------------------------------------------------------------- microphone and speaker
def _sd():
    try:
        import sounddevice as sd  # noqa: PLC0415
    except ImportError:
        sys.exit("The voice console needs `sounddevice` for the microphone and speaker: pip install sounddevice  (or use --mode text)")
    return sd


def mic_listener(mode: str) -> Listen:
    cfg = load_config()

    def listen() -> str:
        sd = _sd()
        loop = asyncio.new_event_loop()
        queue: asyncio.Queue[bytes | None] = asyncio.Queue()
        stop = threading.Event()

        def on_audio(indata, frames, time, status):  # noqa: ARG001
            if not stop.is_set():
                loop.call_soon_threadsafe(queue.put_nowait, bytes(indata))

        async def mic():
            while True:
                chunk = await queue.get()
                if chunk is None:
                    return
                yield chunk

        if mode == "tap":
            input("Press Enter to talk…")
        stream = sd.RawInputStream(samplerate=LISTEN_RATE, channels=1, dtype="int16", blocksize=LISTEN_RATE // 10, callback=on_audio)
        stream.start()
        print("Listening… " + ("press Enter to stop." if mode == "tap" else "pause when you're done."), flush=True)
        if mode == "tap":
            threading.Thread(target=lambda: (input(), stop.set(), loop.call_soon_threadsafe(queue.put_nowait, None)), daemon=True).start()

        def interim(text: str) -> None:
            print(f"\r  … {text}", end="", flush=True)

        try:
            result = loop.run_until_complete(transcribe_stream(mic(), cfg=cfg, on_interim=interim, stop_after_utterance=mode != "tap"))
        finally:
            stop.set()
            stream.stop()
            stream.close()
            loop.close()
        print()
        return result.text

    return listen


def speaker(muted: bool) -> Speak:
    cfg = load_config()

    def speak(text: str) -> bool:
        if muted or not text.strip():
            return False
        sd = _sd()
        import numpy as np  # noqa: PLC0415

        with wave.open(io.BytesIO(synthesize(text, cfg=cfg))) as w:
            rate = w.getframerate()
            pcm = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
        try:
            sd.play(pcm, rate)
            sd.wait()
            return False
        except KeyboardInterrupt:  # Ctrl+C interrupts the reply, not the console
            sd.stop()
            return True

    return speak


def text_listener() -> Listen:
    return lambda: input("You (type): ")


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="voice.console", description=__doc__.split("\n\n")[0])
    p.add_argument("--url", default="http://127.0.0.1:2024")
    p.add_argument("--graph", default="ai_adaptive_onboarding")
    p.add_argument("--employee-id", required=True)
    p.add_argument("--organization-id", required=True)
    p.add_argument("--workspace-id", required=True)
    p.add_argument("--session-id", required=True)
    p.add_argument("--mode", choices=["hands-free", "tap", "text"], default="hands-free")
    p.add_argument("--mute", action="store_true", help="Don't read replies aloud")
    a = p.parse_args(argv)
    from dotenv import load_dotenv  # noqa: PLC0415
    from langgraph_sdk import get_sync_client  # noqa: PLC0415

    load_dotenv()
    initial = {"employee": {"employee_id": a.employee_id, "organization_id": a.organization_id, "workspace_id": a.workspace_id, "session_id": a.session_id}}
    listen = text_listener() if a.mode == "text" else mic_listener(a.mode)
    run_conversation(get_sync_client(url=a.url), a.graph, initial, listen, speaker(a.mute))


if __name__ == "__main__":
    main()
