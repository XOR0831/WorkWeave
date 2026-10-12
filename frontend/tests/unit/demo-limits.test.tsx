import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { VoiceComposer, type Listener } from "@/features/onboarding/VoiceComposer";
import { VoiceError, type ListenerEvents, type ListenMode, type VoiceGrant } from "@/lib/voice/live-listener";
import { blockedFrom, resetTime } from "@/lib/limits";
import { WorkWeaveError, type DemoLimits } from "@/types/contracts";

vi.mock("next/navigation", () => ({
  usePathname: () => "/onboarding/session/",
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

const RESETS = "2099-01-02T00:00:00+00:00";
const limitError = (kind: string, scope: "RUN" | "GLOBAL", message: string) =>
  new WorkWeaveError({ code: "LIMIT_REACHED", message, retryable: false, limit: { kind: kind as "TUTOR_TURN", scope, resets_at: RESETS } }, "r");

// ---------------------------------------------------------------- composer
class StubListener implements Listener {
  constructor(
    public mode: ListenMode,
    public events: ListenerEvents,
    private failWith?: unknown,
  ) {}
  async start() {
    if (this.failWith) throw this.failWith;
  }
  async finish() {}
  pause() {}
  resume() {}
  discardPending() {}
  close() {}
}

function composer(props: Partial<Parameters<typeof VoiceComposer>[0]> = {}, failWith?: unknown) {
  const onSend = vi.fn(async () => true);
  const getGrant = vi.fn(async (mode: ListenMode) => ({ mode }) as VoiceGrant);
  render(
    <VoiceComposer
      label="Message"
      onSend={onSend}
      voiceAvailable
      prefs={{ sounds: false, handsFree: false, micExplained: true }}
      getGrant={getGrant}
      createListener={(g, e) => new StubListener(g.mode, e, failWith)}
      {...props}
    />,
  );
  return { onSend, getGrant };
}

describe("voice input caps in the composer", () => {
  afterEach(cleanup);

  it("a capped mic says why and when, and typing still works", async () => {
    const { onSend } = composer({ voiceBlocked: { scope: "RUN", resets_at: RESETS } });
    const note = screen.getByTestId("voice-limit");
    expect(note).toHaveTextContent("Voice input is paused for today");
    expect(note).toHaveTextContent("This demo workspace has used its voice inputs.");
    expect(note).toHaveTextContent("Voice is back at");
    expect(screen.getByRole("button", { name: "Tap to talk" })).toBeDisabled();
    expect(screen.getByRole("switch", { name: "Hands-free" })).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Message"), { target: { value: "Typed answer" } });
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Send" })));
    expect(onSend).toHaveBeenCalledWith("Typed answer", "TEXT");
  });

  it("a refused listening grant hands the limit to the page instead of showing an error line", async () => {
    const onLimit = vi.fn();
    composer({ onLimit, getGrant: async () => Promise.reject(limitError("VOICE_LISTEN", "GLOBAL", "Voice input has reached today's shared demo limit.")) });
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Tap to talk" })));
    expect(onLimit).toHaveBeenCalledWith(expect.objectContaining({ kind: "VOICE_LISTEN", scope: "GLOBAL" }));
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("a busy free voice service is explained, and voice can be tried again later", async () => {
    composer({}, new VoiceError("BUSY", "busy"));
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Tap to talk" })));
    expect(screen.getByTestId("voice-busy")).toHaveTextContent("Voice is busy right now");
    expect(screen.getByRole("button", { name: "Tap to talk" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Try voice again" }));
    expect(screen.queryByTestId("voice-busy")).toBeNull();
    expect(screen.getByRole("button", { name: "Tap to talk" })).toBeEnabled();
  });
});

describe("limit helpers", () => {
  it("shows the reset in the visitor's time, with the weekday only when it isn't today", () => {
    const at = "2026-10-05T00:00:00Z";
    expect(resetTime(at, new Date(at))).not.toMatch(/^[A-Z][a-z]{2} /);
    expect(resetTime(at, new Date("2026-10-01T00:00:00Z"))).toMatch(/^[A-Z][a-z]{2} /);
    expect(resetTime("not a date")).toBe("tomorrow");
  });

  it("a refusal blocks immediately; otherwise the server's view decides", () => {
    const limits = { resets_at: RESETS, tutor_turn: { available: true, scope: null, remaining: 5 }, voice_listen: { available: false, scope: "RUN", remaining: 0 }, voice_speech: { available: true, scope: null, remaining: null } } as DemoLimits;
    expect(blockedFrom(limits, "tutor_turn", null)).toBeNull();
    expect(blockedFrom(limits, "voice_listen", null)).toEqual({ scope: "RUN", resets_at: RESETS });
    expect(blockedFrom(limits, "tutor_turn", { kind: "TUTOR_TURN", scope: "GLOBAL", resets_at: RESETS })).toEqual({ scope: "GLOBAL", resets_at: RESETS });
  });
});

// ---------------------------------------------------------------- session page (API mode)
const PERSONA = { employee_id: "p", first_name: "Jamie", last_name: "Chen", role_name: "Technician", team_name: "Maintenance", team_role: "MEMBER", employment_status: "ACTIVE", scenario_note: "", grants: ["onboarding.learn"] };
const SESSION = { session_id: "s", scenario: { scenario_id: "sc-1", key: "northstar", company_name: "Northstar Manufacturing", industry: "manufacturing" }, workspace_id: "w", pack_version: "v", persona: PERSONA, persona_selected: true, expires_at: "2099-01-01T00:00:00Z" };
const OVERVIEW = {
  learning_assignment_id: "la",
  curriculum_name: "Machine Fundamentals",
  curriculum_version: "1.1",
  source_versions: [],
  topics: [{ topic_id: "t1", name: "Fundamentals", order_index: 1, subtopics: [{ subtopic_id: "s1", name: "Find the current procedure", order_index: 1, objective: "o", status: "IN_PROGRESS", optional: false }] }],
  current_subtopic_id: "s1",
  session_status: "ACTIVE",
  learning_session_id: "ls",
  saved_at: "Progress saved",
};
const REPLY = { message_id: "turn1:out", sender: "AI", kind: "TEACHING", text: "Use the current approved version.", citations: [], provenance: "TUTOR_ENGINE", created_at: "2026-10-03T10:00:00Z" };
const open = { available: true, scope: null, remaining: null };
const view = (limits: Partial<DemoLimits> = {}) => ({
  learning_session_id: "ls",
  revision: 3,
  overview: OVERVIEW,
  transcript: [REPLY],
  pending_check: null,
  awaiting_continue: false,
  script_prompts: [],
  status: "ACTIVE",
  tutor: { status: "ok", message: "" },
  demo_limits: { resets_at: RESETS, tutor_turn: open, voice_listen: open, voice_speech: open, ...limits },
});
const json = (data: unknown, status = 200) => new Response(JSON.stringify(status === 200 ? { request_id: "r", data } : { request_id: "r", error: data }), { status, headers: { "content-type": "application/json" } });

async function page(v: ReturnType<typeof view>, onTurn?: () => Response, onContinue?: (body: unknown) => Response) {
  vi.stubEnv("NEXT_PUBLIC_WORKWEAVE_MODE", "http");
  vi.resetModules();
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const u = String(url);
      if (u.endsWith("/demo-sessions/current")) return json(SESSION);
      if (u.endsWith("/personas")) return json([PERSONA]);
      if (u.endsWith("/capabilities")) return json({ voice_adapter: "AVAILABLE", conversation_engine: "AVAILABLE" });
      if (u.endsWith("/onboarding")) return json(OVERVIEW);
      if (u.endsWith("/onboarding/sessions/ls")) return json(v);
      if (u.endsWith("/turns/stream") && onTurn) return onTurn();
      if (u.endsWith("/continue") && onContinue) return onContinue(JSON.parse(String(init?.body)));
      return json(null);
    }),
  );
  const { ClientProvider } = await import("@/lib/preview/client-context");
  const { default: TutorPage } = await import("@/app/onboarding/session/page");
  render(
    <ClientProvider>
      <TutorPage />
    </ClientProvider>,
  );
  await screen.findByText("Use the current approved version.", {}, { timeout: 3000 });
  await act(async () => new Promise((r) => setTimeout(r, 50))); // capabilities settle
}

describe("demo caps on the tutor page", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
    window.localStorage.clear();
  });

  it("when this demo's messages are used up, the composer becomes a clear next step", async () => {
    await page(view({ tutor_turn: { available: false, scope: "RUN", remaining: 0 } }));
    const panel = screen.getByTestId("tutor-limit");
    expect(panel).toHaveTextContent("This demo has used today's assistant messages");
    expect(panel).toHaveTextContent("Your conversation and progress are saved.");
    expect(screen.getByRole("link", { name: "Start a fresh demo" })).toHaveAttribute("href", expect.stringMatching(/^\/demo\/company\/?\?company_key=northstar&scenario=sc-1$/));
    expect(screen.queryByLabelText("Ask, answer, or tell me what you need")).toBeNull();
  });

  it("the shared daily limit offers no fresh-demo workaround", async () => {
    await page(view({ tutor_turn: { available: false, scope: "GLOBAL", remaining: 0 } }));
    expect(screen.getByTestId("tutor-limit")).toHaveTextContent("The demo assistants have reached today's shared limit");
    expect(screen.queryByRole("link", { name: "Start a fresh demo" })).toBeNull();
  });

  it("a refused message swaps in the limit panel instead of a generic error", async () => {
    await page(view(), () => json({ code: "LIMIT_REACHED", message: "This demo workspace has used its tutor messages for today.", retryable: false, limit: { kind: "TUTOR_TURN", scope: "RUN", resets_at: RESETS } }, 429));
    fireEvent.change(screen.getByLabelText("Ask, answer, or tell me what you need"), { target: { value: "One more?" } });
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Send" })));
    expect(await screen.findByTestId("tutor-limit")).toBeInTheDocument();
    expect(screen.queryByText("Demo limit reached")).toBeNull(); // no error notice on top of the panel
  });

  it("when reading aloud is capped, replies are clearly text-only", async () => {
    await page(view({ voice_speech: { available: false, scope: "GLOBAL", remaining: 0 } }));
    expect(screen.getByTestId("speech-limit")).toHaveTextContent("Replies are text-only for now");
    expect(screen.queryByRole("button", { name: "Listen to this reply" })).toBeNull();
    expect(screen.getByRole("switch", { name: "Read replies aloud" })).toBeDisabled();
  });

  it("a gentle count appears only near the end of the allowance", async () => {
    await page(view({ tutor_turn: { available: true, scope: null, remaining: 3 } }));
    expect(screen.getByTestId("turns-left")).toHaveTextContent("3 assistant messages left in this demo today.");
  });

  it("no count while plenty is left", async () => {
    await page(view({ tutor_turn: { available: true, scope: null, remaining: 80 } }));
    expect(screen.queryByTestId("turns-left")).toBeNull();
  });
});

describe("next item with the connected tutor (ADR-030)", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  it("after a completed item, Continue asks the tutor to open the next one", async () => {
    const done = { ...view(), awaiting_continue: true, overview: { ...OVERVIEW, topics: [{ ...OVERVIEW.topics[0]!, subtopics: [{ ...OVERVIEW.topics[0]!.subtopics[0]!, status: "COMPLETED" }, { subtopic_id: "s2", name: "Separate history from evidence", order_index: 2, objective: "o", status: "NOT_STARTED", optional: false }] }] } };
    const bodies: unknown[] = [];
    await page(done as ReturnType<typeof view>, undefined, (b) => {
      bodies.push(b);
      return json(view());
    });
    const btn = screen.getByRole("button", { name: "Continue to Separate history from evidence" });
    expect(screen.queryByText(/isn't connected yet/)).toBeNull();
    await act(async () => fireEvent.click(btn));
    expect(bodies).toEqual([{ expected_revision: 3 }]);
  });

  it("without the tutor, the completion is saved and Continue isn't offered", async () => {
    await page({ ...view(), awaiting_continue: true, tutor: { status: "unavailable", message: "Not connected." } } as ReturnType<typeof view>);
    expect(screen.queryByRole("button", { name: /Continue to/ })).toBeNull();
    expect(screen.getByText(/isn't connected yet/)).toBeInTheDocument();
  });
});

