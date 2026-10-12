import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { isBargeIn } from "@/lib/voice/barge-in";
import { BARGE_IN_GRACE_MS, VoiceComposer, type Listener } from "@/features/onboarding/VoiceComposer";
import type { ListenerEvents, ListenMode, VoiceGrant } from "@/lib/voice/live-listener";

const REPLY = "Use the current approved procedure version, and record the exact reference.";

describe("echo filter (voice interrupt on speakers)", () => {
  it("ignores the tutor's own words and triggers on new words from the learner", () => {
    expect(isBargeIn("use the current approved procedure", REPLY)).toBe(false); // echo of the reply
    expect(isBargeIn("Record the exact reference.", REPLY)).toBe(false);
    expect(isBargeIn("wait which version", REPLY)).toBe(true); // two consecutive new words
    expect(isBargeIn("the current hmm version", REPLY)).toBe(false); // one stray word isn't enough
    expect(isBargeIn("procedure hold on", REPLY)).toBe(true);
  });
});

class FakeListener implements Listener {
  calls: string[] = [];
  constructor(
    public mode: ListenMode,
    public events: ListenerEvents,
  ) {}
  async start() {
    this.calls.push("start");
  }
  async finish() {
    this.calls.push("finish");
  }
  pause() {
    this.calls.push("pause");
  }
  resume() {
    this.calls.push("resume");
  }
  discardPending() {
    this.calls.push("discard");
  }
  close() {
    this.calls.push("close");
  }
}

function harness(initial: { speaking?: boolean; voiceInterrupt?: boolean } = {}) {
  const listeners: FakeListener[] = [];
  const onInterrupt = vi.fn();
  const onSend = vi.fn(async () => true);
  const getGrant = vi.fn(async (mode: ListenMode) => ({ mode }) as VoiceGrant);
  const props = (p: { speaking?: boolean; voiceInterrupt?: boolean }) => ({
    label: "Message",
    onSend,
    voiceAvailable: true,
    speakingText: REPLY,
    onInterrupt,
    getGrant,
    createListener: (g: VoiceGrant, e: ListenerEvents) => {
      const l = new FakeListener(g.mode, e);
      listeners.push(l);
      return l;
    },
    ...p,
  });
  const utils = render(<VoiceComposer {...props(initial)} />);
  return { listeners, onInterrupt, onSend, getGrant, rerender: (p: { speaking?: boolean; voiceInterrupt?: boolean }) => utils.rerender(<VoiceComposer {...props(p)} />) };
}

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("interrupting a reply that's being read aloud", () => {
  it("tap-to-talk: Interrupt stops the reply and starts listening at once", async () => {
    const h = harness({ speaking: true });
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Interrupt (Space)" })));
    expect(h.onInterrupt).toHaveBeenCalledTimes(1);
    expect(h.getGrant).toHaveBeenCalledWith("TAP");
  });

  it("Space interrupts, but not while typing in the message box", async () => {
    const h = harness({ speaking: true });
    fireEvent.keyDown(screen.getByLabelText("Message"), { key: " ", code: "Space" });
    expect(h.onInterrupt).not.toHaveBeenCalled();
    await act(async () => fireEvent.keyDown(window, { key: " ", code: "Space" }));
    expect(h.onInterrupt).toHaveBeenCalledTimes(1);
  });

  it("hands-free: paused during playback; Interrupt stops the reply and listening resumes without re-enabling", async () => {
    const h = harness();
    await act(async () => fireEvent.click(screen.getByRole("switch", { name: "Hands-free" })));
    const l = h.listeners[0]!;
    h.rerender({ speaking: true });
    expect(l.calls.at(-1)).toBe("pause");
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Interrupt (Space)" })));
    expect(h.onInterrupt).toHaveBeenCalledTimes(1);
    expect(h.getGrant).toHaveBeenCalledTimes(1); // still the same hands-free session
    h.rerender({ speaking: false }); // the page stopped playback
    expect(l.calls.at(-1)).toBe("resume");
    expect(screen.getByRole("switch", { name: "Hands-free" })).toBeChecked();
  });

  it("voice interrupt: echo is ignored, a real barge-in after the grace period interrupts", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    const h = harness({ voiceInterrupt: true });
    await act(async () => fireEvent.click(screen.getByRole("switch", { name: "Hands-free" })));
    const l = h.listeners[0]!;
    h.rerender({ speaking: true, voiceInterrupt: true });
    expect(l.calls.at(-1)).toBe("resume"); // keeps listening during playback
    act(() => l.events.onInterim?.("wait which version")); // within the grace period
    expect(h.onInterrupt).not.toHaveBeenCalled();
    vi.advanceTimersByTime(BARGE_IN_GRACE_MS + 50);
    act(() => l.events.onInterim?.("use the current approved procedure")); // the tutor's own voice
    expect(h.onInterrupt).not.toHaveBeenCalled();
    expect(screen.getByLabelText("Message")).toHaveValue(""); // echo isn't shown
    act(() => l.events.onUtterance?.("use the current approved procedure version")); // echo utterance
    expect(screen.queryByText(/Sending in/)).toBeNull(); // never auto-sent
    act(() => l.events.onInterim?.("hold on which version"));
    expect(h.onInterrupt).toHaveBeenCalledTimes(1);
    expect(l.calls).toContain("discard"); // echoed words dropped before the learner's own
  });
});
