import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { VoiceComposer, type Listener } from "@/features/onboarding/VoiceComposer";
import type { ListenerEvents, ListenMode, VoiceGrant } from "@/lib/voice/live-listener";

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
    this.events.onUtterance?.("Use the current approved version.");
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

function setup(props: Partial<Parameters<typeof VoiceComposer>[0]> = {}) {
  const listeners: FakeListener[] = [];
  const onSend = vi.fn(async () => true);
  const getGrant = vi.fn(async (mode: ListenMode) => ({ mode }) as VoiceGrant);
  const utils = render(
    <VoiceComposer
      label="Ask, answer, or tell me what you need"
      onSend={onSend}
      voiceAvailable
      getGrant={getGrant}
      createListener={(g, e) => {
        const l = new FakeListener(g.mode, e);
        listeners.push(l);
        return l;
      }}
      {...props}
    />,
  );
  return { listeners, onSend, getGrant, ...utils };
}

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("VoiceComposer (API mode)", () => {
  it("Space is a full tap-to-talk toggle outside text fields, controls and dialogs", async () => {
    const { listeners, getGrant, onSend } = setup();
    const box = screen.getByLabelText("Ask, answer, or tell me what you need");
    fireEvent.keyDown(box, { key: " ", code: "Space" }); // typing a space: ignored
    fireEvent.keyDown(screen.getByRole("button", { name: "Tap to talk" }), { key: " ", code: "Space" }); // a focused control: ignored
    fireEvent.keyDown(window, { key: " ", code: "Space", repeat: true }); // held key: ignored
    fireEvent.keyDown(window, { key: " ", code: "Space", shiftKey: true }); // with a modifier: ignored
    expect(getGrant).not.toHaveBeenCalled();
    await act(async () => fireEvent.keyDown(window, { key: " ", code: "Space" })); // start
    expect(getGrant).toHaveBeenCalledWith("TAP");
    expect(screen.getByRole("button", { name: "Stop (Space)" })).toBeInTheDocument();
    await act(async () => fireEvent.keyDown(document.body, { key: " ", code: "Space" })); // stop and review
    expect(listeners[0]!.calls).toEqual(["start", "finish"]);
    expect(box).toHaveValue("Use the current approved version.");
    expect(onSend).not.toHaveBeenCalled(); // still reviewed before sending
  });

  it("Space does nothing when voice isn't available", () => {
    const { getGrant } = setup({ voiceAvailable: false });
    fireEvent.keyDown(window, { key: " ", code: "Space" });
    expect(getGrant).not.toHaveBeenCalled();
  });

  it("is honest when voice isn't configured: controls disabled with the reason, typing still works", async () => {
    const { onSend } = setup({ voiceAvailable: false, unavailableReason: "Voice isn't configured on this server." });
    expect(screen.getByRole("button", { name: "Tap to talk" })).toBeDisabled();
    expect(screen.getByRole("switch", { name: "Hands-free" })).toBeDisabled();
    expect(screen.getByText("Voice isn't configured on this server.")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Ask, answer, or tell me what you need"), { target: { value: "Typed question" } });
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Send" })));
    expect(onSend).toHaveBeenCalledWith("Typed question", "TEXT");
  });

  it("hands-free says to wait while the voice service connects, then that you can talk", async () => {
    let ready: () => void = () => undefined;
    const started = new Promise<void>((r) => (ready = r));
    setup({
      prefs: { sounds: false, handsFree: false, micExplained: true },
      createListener: (g, e) => Object.assign(new FakeListener(g.mode, e), { start: () => started }),
    });
    await act(async () => fireEvent.click(screen.getByRole("switch", { name: "Hands-free" })));
    expect(screen.getByTestId("voice-connecting")).toHaveTextContent("Connecting hands-free… Wait a moment before you talk.");
    expect(screen.queryByTestId("voice-ready")).toBeNull(); // not before the service is ready
    await act(async () => ready());
    expect(screen.queryByTestId("voice-connecting")).toBeNull();
    expect(screen.getByTestId("voice-ready")).toHaveTextContent(/You can talk now\. Hands-free is listening/);
  });

  it("tap-to-talk fills the box for review; nothing is sent until you press Send", async () => {
    const { listeners, onSend, getGrant } = setup();
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Tap to talk" })));
    expect(getGrant).toHaveBeenCalledWith("TAP");
    expect(screen.getByTestId("voice-ready")).toHaveTextContent(/You can talk now\. Tap Stop/); // only once the voice service is ready
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Stop (Space)" })));
    expect(listeners[0]!.calls).toEqual(["start", "finish"]);
    expect(screen.getByLabelText("Ask, answer, or tell me what you need")).toHaveValue("Use the current approved version.");
    expect(onSend).not.toHaveBeenCalled();
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Send" })));
    expect(onSend).toHaveBeenCalledWith("Use the current approved version.", "VOICE_TRANSCRIPT");
  });

  it("hands-free auto-sends after a visible countdown; Cancel or typing stops it", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    const { listeners, onSend, getGrant } = setup();
    await act(async () => fireEvent.click(screen.getByRole("switch", { name: "Hands-free" })));
    expect(getGrant).toHaveBeenCalledWith("HANDS_FREE");
    const l = listeners[0]!;
    act(() => l.events.onUtterance?.("First answer"));
    expect(screen.getByText("Sending in 1s…")).toBeInTheDocument();
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Cancel and edit" })));
    await act(async () => vi.advanceTimersByTimeAsync(3000));
    expect(onSend).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText("Ask, answer, or tell me what you need"), { target: { value: "" } });

    act(() => l.events.onUtterance?.("Second answer"));
    fireEvent.change(screen.getByLabelText("Ask, answer, or tell me what you need"), { target: { value: "Second answer, edited" } });
    await act(async () => vi.advanceTimersByTimeAsync(3000));
    expect(onSend).not.toHaveBeenCalled(); // typing took over

    fireEvent.change(screen.getByLabelText("Ask, answer, or tell me what you need"), { target: { value: "" } });
    act(() => l.events.onUtterance?.("Third answer"));
    expect(screen.getByText("Sending in 1s…")).toBeInTheDocument();
    await act(async () => vi.advanceTimersByTimeAsync(500));
    expect(onSend).not.toHaveBeenCalled(); // still time to cancel
    await act(async () => vi.advanceTimersByTimeAsync(500));
    expect(onSend).toHaveBeenCalledWith("Third answer", "VOICE_TRANSCRIPT");
  });

  it("hands-free pauses while sending or while a reply is read aloud", async () => {
    const { listeners, rerender, onSend, getGrant } = setup();
    await act(async () => fireEvent.click(screen.getByRole("switch", { name: "Hands-free" })));
    const l = listeners[0]!;
    const props = { label: "Ask, answer, or tell me what you need", onSend, voiceAvailable: true, getGrant, createListener: () => l };
    rerender(<VoiceComposer {...props} speaking />);
    expect(l.calls.at(-1)).toBe("pause");
    expect(screen.getByText(/paused while the reply is read aloud/)).toBeInTheDocument();
    rerender(<VoiceComposer {...props} speaking={false} pending />);
    expect(l.calls.at(-1)).toBe("pause");
    rerender(<VoiceComposer {...props} speaking={false} pending={false} />);
    expect(l.calls.at(-1)).toBe("resume");
    await act(async () => fireEvent.click(screen.getByRole("switch", { name: "Hands-free" })));
    expect(l.calls.at(-1)).toBe("close");
  });

  it("shows a voice error and returns to typing", async () => {
    setup({ getGrant: async () => Promise.reject(new Error("Voice isn't configured on this server. Type your message instead.")) });
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Tap to talk" })));
    expect(screen.getByRole("alert")).toHaveTextContent("Type your message instead.");
    expect(screen.getByRole("button", { name: "Tap to talk" })).toBeEnabled();
  });
});

describe("when the conversation can't take a message (item complete)", () => {
  afterEach(() => {
    cleanup();
    vi.useRealTimers();
  });

  it("hands-free stops, says why, and can't be turned back on until the box unlocks", async () => {
    const { listeners, rerender, onSend, getGrant } = setup();
    await act(async () => fireEvent.click(screen.getByRole("switch", { name: "Hands-free" })));
    const l = listeners[0]!;
    const props = { label: "Ask, answer, or tell me what you need", onSend, voiceAvailable: true, getGrant, createListener: () => l };
    rerender(<VoiceComposer {...props} disabled />);
    await act(async () => new Promise((r) => setTimeout(r, 10))); // the stop runs right after the lock renders
    expect(l.calls).toContain("close");
    expect(screen.getByRole("switch", { name: "Hands-free" })).not.toBeChecked();
    expect(screen.getByRole("switch", { name: "Hands-free" })).toBeDisabled();
    expect(screen.getByText(/Hands-free is off while this item is complete/)).toBeInTheDocument();
    // A transcript that arrives late from the closed microphone is ignored.
    act(() => l.events.onUtterance?.("Said while clicking Continue"));
    rerender(<VoiceComposer {...props} disabled={false} />);
    await act(async () => new Promise((r) => setTimeout(r, 1500)));
    expect(onSend).not.toHaveBeenCalled();
    expect(screen.getByLabelText("Ask, answer, or tell me what you need")).toHaveValue("");
    expect(screen.getByRole("switch", { name: "Hands-free" })).toBeEnabled(); // the learner turns it on again
    expect(getGrant).toHaveBeenCalledTimes(1); // it never restarted by itself
  });

  it("a voice transcript waiting to be sent is dropped, never sent after Continue", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    const { listeners, rerender, onSend, getGrant } = setup();
    await act(async () => fireEvent.click(screen.getByRole("switch", { name: "Hands-free" })));
    const l = listeners[0]!;
    act(() => l.events.onUtterance?.("The answer to the last question"));
    expect(screen.getByText("Sending in 1s…")).toBeInTheDocument();
    const props = { label: "Ask, answer, or tell me what you need", onSend, voiceAvailable: true, getGrant, createListener: () => l };
    rerender(<VoiceComposer {...props} disabled />);
    await act(async () => vi.advanceTimersByTimeAsync(2000));
    rerender(<VoiceComposer {...props} disabled={false} />);
    await act(async () => vi.advanceTimersByTimeAsync(2000));
    expect(onSend).not.toHaveBeenCalled();
    expect(screen.queryByText(/Sending in/)).toBeNull();
    expect(screen.getByLabelText("Ask, answer, or tell me what you need")).toHaveValue("");
  });

  it("text the learner typed is kept", async () => {
    const { rerender, onSend, getGrant } = setup();
    fireEvent.change(screen.getByLabelText("Ask, answer, or tell me what you need"), { target: { value: "My typed note" } });
    const props = { label: "Ask, answer, or tell me what you need", onSend, voiceAvailable: true, getGrant, createListener: () => ({}) as never };
    rerender(<VoiceComposer {...props} disabled />);
    await act(async () => new Promise((r) => setTimeout(r, 10)));
    rerender(<VoiceComposer {...props} disabled={false} />);
    expect(screen.getByLabelText("Ask, answer, or tell me what you need")).toHaveValue("My typed note");
  });
});
