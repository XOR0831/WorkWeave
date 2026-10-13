import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

vi.mock("next/navigation", () => ({
  usePathname: () => "/companion/",
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

// Labelled test data shaped like the API (POST /work-sessions, GET /work-state, /capabilities).
const PERSONA = { employee_id: "test-jamie", first_name: "Jamie", last_name: "Chen", role_name: "Technician", team_name: "Maintenance", team_role: "MEMBER", employment_status: "ACTIVE", scenario_note: "", grants: ["work.read"] };
const SESSION = {
  session_id: "s",
  scenario: { scenario_id: "x", key: "northstar", company_name: "Northstar Manufacturing", industry: "manufacturing", terminology: { workItems: "tickets" } },
  workspace_id: "w",
  pack_version: "v",
  persona: PERSONA,
  persona_selected: true,
  expires_at: "2099-01-01T00:00:00Z",
};
const BRIEF = { message_id: "b1", sender: "AI", text: "Your top priority is Ticket #829.", citations: [], provenance: "WORK_ENGINE", ui_action: "NO_VIEW_CHANGE" };
const ASKED = { message_id: "e1", sender: "EMPLOYEE", text: "Let's start", citations: [], provenance: "EMPLOYEE_INPUT" };
const FOCUS = { message_id: "r1", sender: "AI", text: "Let's start with Ticket #829.", citations: [], provenance: "WORK_ENGINE", ui_action: "NO_VIEW_CHANGE" };
const view = (transcript: unknown[]) => ({ work_session_id: "ws1", revision: transcript.length, transcript, canvas: { view: "BRIEFING" }, script_prompts: [], assistant: { status: "ok", message: "" } });
const DASH = { active_count: 1, blocked_count: 0, overdue_count: 0, work_state: "ON_TRACK", shift_label: null, incoming_continuity: null, priorities: [], awaiting_sync_count: 0, needs_review_count: 0, can_delegate: false, system_name: "Northstar ticket system" };

const json = (data: unknown) => new Response(JSON.stringify({ request_id: "r", data }), { status: 200, headers: { "content-type": "application/json" } });
const heard: string[] = [];

/** Web Audio stand-in: a reply counts as heard once its streamed audio starts. */
class FakeAudioContext {
  currentTime = 0;
  state = "running";
  destination = {};
  async resume() {}
  createBuffer(_channels: number, length: number, rate: number) {
    return { duration: length / rate, copyToChannel: () => undefined };
  }
  createBufferSource() {
    return { buffer: null as unknown, playbackRate: { value: 1 }, onended: null, connect: () => undefined, stop: () => undefined, start: () => heard.push("audio") };
  }
}
const pcm = () =>
  new Response(
    new ReadableStream<Uint8Array>({
      start(c) {
        c.enqueue(new Uint8Array([1, 0, 2, 0]));
        c.close();
      },
    }),
    { status: 200, headers: { "content-type": "audio/L16;rate=24000;channels=1", "x-sample-rate": "24000" } },
  );

async function renderPage(transcript: unknown[], opts: { readAloud?: boolean; activated?: boolean } = {}) {
  vi.stubEnv("NEXT_PUBLIC_WORKWEAVE_MODE", "http");
  vi.resetModules();
  vi.stubGlobal("AudioContext", FakeAudioContext);
  Object.defineProperty(navigator, "userActivation", { configurable: true, value: { hasBeenActive: opts.activated ?? true } });
  window.localStorage.setItem("ww.voice.prefs.v1", JSON.stringify({ readAloud: opts.readAloud ?? true, readAloudOffered: true }));
  const fetch = vi.fn(async (url: string) => {
    const u = String(url);
    if (u.endsWith("/demo-sessions/current")) return json(SESSION);
    if (u.endsWith("/personas")) return json([PERSONA]);
    if (u.endsWith("/capabilities")) return json({ voice_adapter: "AVAILABLE", conversation_engine: "AVAILABLE" });
    if (u.endsWith("/work-sessions")) return json(view(transcript));
    if (u.endsWith("/work-state")) return json(DASH);
    if (u.endsWith("/assignments") || u.endsWith("/work-events")) return json([]);
    if (u.includes("/voice/speech/") && u.split("?")[0]!.endsWith("/stream")) return pcm(); // read in parts: ?part=0 first
    return json(null);
  });
  vi.stubGlobal("fetch", fetch);
  const { ClientProvider } = await import("@/lib/preview/client-context");
  const { default: CompanionPage } = await import("@/app/companion/page");
  render(
    <ClientProvider>
      <CompanionPage />
    </ClientProvider>,
  );
  await screen.findByText(BRIEF.text, {}, { timeout: 3000 });
  return fetch;
}

const speechCalls = (fetch: ReturnType<typeof vi.fn>) => fetch.mock.calls.map((c) => String(c[0])).filter((u) => u.includes("/voice/speech/"));

afterEach(() => {
  cleanup();
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  window.localStorage.clear();
  window.sessionStorage.clear();
  heard.length = 0;
});

describe("Work Companion read-aloud (API mode)", () => {
  it("reads a new session's opening brief once, and not again on reload", async () => {
    const fetch = await renderPage([BRIEF]);
    await waitFor(() => expect(speechCalls(fetch)).toEqual(["/api/work-sessions/ws1/voice/speech/b1/stream?part=0"]));
    await waitFor(() => expect(heard.length).toBe(1));
    cleanup();
    const again = await renderPage([BRIEF]);
    await new Promise((r) => setTimeout(r, 50));
    expect(speechCalls(again)).toEqual([]); // the brief is history now
  });

  it("never replays history, but each reply can be heard with Listen", async () => {
    const fetch = await renderPage([BRIEF, ASKED, FOCUS]);
    await new Promise((r) => setTimeout(r, 50));
    expect(speechCalls(fetch)).toEqual([]);
    fireEvent.click(screen.getAllByRole("button", { name: "Listen to this reply" })[1]!);
    await waitFor(() => expect(speechCalls(fetch)).toEqual(["/api/work-sessions/ws1/voice/speech/r1/stream?part=0"]));
  });

  it("waits for a tap when the browser hasn't allowed sound yet", async () => {
    const fetch = await renderPage([BRIEF], { activated: false });
    const hear = await screen.findByRole("button", { name: "Hear the brief" });
    expect(speechCalls(fetch)).toEqual([]); // nothing spent on audio that couldn't play
    fireEvent.click(hear);
    await waitFor(() => expect(speechCalls(fetch)).toEqual(["/api/work-sessions/ws1/voice/speech/b1/stream?part=0"]));
  });

  it("stays quiet when read-aloud is off", async () => {
    const fetch = await renderPage([BRIEF], { readAloud: false });
    await new Promise((r) => setTimeout(r, 50));
    expect(speechCalls(fetch)).toEqual([]);
    expect(screen.getByRole("switch", { name: "Read replies aloud" })).not.toBeChecked();
  });
});
