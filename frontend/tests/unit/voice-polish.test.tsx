import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { TAP_MAX_MS, TAP_SILENCE_MS, VoiceComposer, type ComposerVoicePrefs, type Listener } from "@/features/onboarding/VoiceComposer";
import type { ListenerEvents, ListenMode, ListenerState, VoiceGrant } from "@/lib/voice/live-listener";
import { loadPrefs, savePrefs } from "@/lib/voice/prefs";
import { rms } from "@/lib/voice/live-listener";

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
    this.events.onUtterance?.("What I said before stopping.");
  }
  pause() {}
  resume() {}
  discardPending() {}
  close() {
    this.calls.push("close");
  }
  drop() {
    this.events.onState?.("closed" as ListenerState);
  }
}

function harness(prefs: Partial<ComposerVoicePrefs> = {}, extra: Partial<Parameters<typeof VoiceComposer>[0]> = {}) {
  const listeners: FakeListener[] = [];
  const onPrefsChange = vi.fn();
  const playCue = vi.fn();
  const getGrant = vi.fn(async (mode: ListenMode) => ({ mode }) as VoiceGrant);
  render(
    <VoiceComposer
      label="Message"
      onSend={vi.fn(async () => true)}
      voiceAvailable
      prefs={{ sounds: true, handsFree: false, micExplained: true, ...prefs }}
      onPrefsChange={onPrefsChange}
      playCue={playCue}
      getGrant={getGrant}
      createListener={(g, e) => {
        const l = new FakeListener(g.mode, e);
        listeners.push(l);
        return l;
      }}
      {...extra}
    />,
  );
  return { listeners, onPrefsChange, playCue, getGrant };
}

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  window.localStorage.clear();
});

describe("voice polish", () => {
  it("shows a level meter and says when it's hearing you; sounds mark start and stop", async () => {
    const h = harness();
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Tap to talk" })));
    expect(h.playCue).toHaveBeenCalledWith("start");
    act(() => h.listeners[0]!.events.onLevel?.(0.5));
    expect(screen.getByText(/Hearing you\./)).toBeInTheDocument();
    expect(document.querySelector(".mic-meter > span")).toHaveStyle({ width: "50%" });
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Stop (Space)" })));
    expect(h.playCue).toHaveBeenLastCalledWith("stop");
  });

  it("sounds can be switched off", async () => {
    const h = harness({ sounds: false });
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Tap to talk" })));
    expect(h.playCue).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("checkbox", { name: "Sounds" }));
    expect(h.onPrefsChange).toHaveBeenCalledWith({ sounds: true });
  });

  it("explains the microphone before the browser asks, once; skipped when access is already granted", async () => {
    const h = harness({ micExplained: false }, { micPermission: async () => "prompt" as PermissionState });
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Tap to talk" })));
    expect(screen.getByText("Your browser will ask to use the microphone")).toBeInTheDocument();
    expect(h.getGrant).not.toHaveBeenCalled(); // nothing opened yet
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Continue" })));
    expect(h.onPrefsChange).toHaveBeenCalledWith({ micExplained: true });
    expect(h.getGrant).toHaveBeenCalledWith("TAP");
    cleanup();
    const g = harness({ micExplained: false }, { micPermission: async () => "granted" as PermissionState });
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Tap to talk" })));
    expect(screen.queryByText("Your browser will ask to use the microphone")).toBeNull();
    expect(g.getGrant).toHaveBeenCalledWith("TAP");
  });

  it("remembered hands-free is offered, never switched on without a tap", async () => {
    const h = harness({ handsFree: true });
    expect(screen.getByText("Hands-free was on last time.")).toBeInTheDocument();
    expect(h.getGrant).not.toHaveBeenCalled();
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Turn on hands-free" })));
    expect(h.getGrant).toHaveBeenCalledWith("HANDS_FREE");
    expect(screen.getByRole("switch", { name: "Hands-free" })).toBeChecked();
  });

  it("tap-to-talk stops itself after 10 s of silence, keeping what was said", async () => {
    vi.useFakeTimers({ toFake: ["setInterval", "clearInterval", "Date"] });
    const h = harness();
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Tap to talk" })));
    act(() => h.listeners[0]!.events.onLevel?.(0.5));
    await act(async () => vi.advanceTimersByTimeAsync(TAP_SILENCE_MS + 1000));
    expect(h.listeners[0]!.calls).toContain("finish");
    expect(screen.getByText(/Stopped after 10 seconds of silence/)).toBeInTheDocument();
    expect(screen.getByLabelText("Message")).toHaveValue("What I said before stopping.");
  });

  it("tap-to-talk warns near 2 minutes and stops at 2 minutes", async () => {
    vi.useFakeTimers({ toFake: ["setInterval", "clearInterval", "Date"] });
    const h = harness();
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Tap to talk" })));
    const keepTalking = async (ms: number) => {
      for (let t = 0; t < ms; t += 5000) {
        act(() => h.listeners[0]!.events.onLevel?.(0.5));
        await act(async () => vi.advanceTimersByTimeAsync(5000));
      }
    };
    await keepTalking(106_000);
    expect(screen.getByText(/Stopping in \d+s/)).toBeInTheDocument();
    await keepTalking(TAP_MAX_MS - 106_000 + 5000);
    expect(screen.getByText(/Stopped after 2 minutes/)).toBeInTheDocument();
  });

  it("hands-free reconnects quietly after a drop, and gives up after repeated drops", async () => {
    const h = harness();
    await act(async () => fireEvent.click(screen.getByRole("switch", { name: "Hands-free" })));
    await act(async () => h.listeners[0]!.drop());
    expect(h.getGrant).toHaveBeenCalledTimes(2);
    expect(screen.getByRole("switch", { name: "Hands-free" })).toBeChecked();
    expect(h.playCue.mock.calls.filter(([c]) => c === "start")).toHaveLength(1); // no extra start tone on reconnect
    await act(async () => h.listeners[1]!.drop());
    await act(async () => h.listeners[2]!.drop());
    expect(screen.getByRole("alert")).toHaveTextContent("Hands-free stopped because the connection kept dropping.");
    expect(screen.getByRole("switch", { name: "Hands-free" })).not.toBeChecked();
  });
});

describe("voice preferences and level", () => {
  it("remembers settings per browser and falls back to defaults when storage is unusable", () => {
    expect(loadPrefs()).toMatchObject({ readAloud: false, speed: 1, sounds: true });
    savePrefs({ readAloud: true, speed: 1.25 });
    expect(loadPrefs()).toMatchObject({ readAloud: true, speed: 1.25 });
    window.localStorage.setItem("ww.voice.prefs.v1", "{not json");
    expect(loadPrefs().speed).toBe(1);
    expect(loadPrefs(true).sounds).toBe(false); // reduced motion: quiet by default
    const spy = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(savePrefs({ speed: 0.9 }).speed).toBe(0.9); // still works for this page
    spy.mockRestore();
  });

  it("computes a 0–1 level", () => {
    expect(rms(new Float32Array(0))).toBe(0);
    expect(rms(new Float32Array(10))).toBe(0);
    expect(rms(new Float32Array(10).fill(1))).toBe(1);
  });
});
