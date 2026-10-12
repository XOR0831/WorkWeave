import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

vi.mock("next/navigation", () => ({
  usePathname: () => "/onboarding/session/",
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

// Labelled test data shaped like the API (GET /onboarding, /onboarding/sessions/{id}, /capabilities).
const PERSONA = { employee_id: "test-jamie", first_name: "Jamie", last_name: "Chen", role_name: "Technician", team_name: "Maintenance", team_role: "MEMBER", employment_status: "ACTIVE", scenario_note: "", grants: ["onboarding.learn"] };
const SESSION = { session_id: "s", scenario: { scenario_id: "x", key: "northstar", company_name: "Northstar Manufacturing", industry: "manufacturing" }, workspace_id: "w", pack_version: "v", persona: PERSONA, persona_selected: true, expires_at: "2099-01-01T00:00:00Z" };
const sub = (id: string, name: string, status: string, optional = false) => ({ subtopic_id: id, name, order_index: 1, objective: "o", status, optional });
const OVERVIEW = {
  learning_assignment_id: "la",
  curriculum_name: "Machine Fundamentals",
  curriculum_version: "1.1",
  source_versions: [],
  topics: [{ topic_id: "t1", name: "Fundamentals", order_index: 1, subtopics: [sub("s1", "Find the current procedure", "COMPLETED"), sub("s2", "Separate history from evidence", "IN_PROGRESS"), sub("s3", "Ask a clearer question", "NOT_STARTED")] },
           { topic_id: "t2", name: "Reference aids", order_index: 2, subtopics: [sub("s4", "Training checks", "NOT_STARTED", true)] }],
  current_subtopic_id: "s2",
  session_status: "ACTIVE",
  learning_session_id: "ls",
  saved_at: "Progress saved 03 Oct 2026",
};
const REPLY = { message_id: "turn1:out", sender: "AI", kind: "TEACHING", text: "Use the current approved version.", citations: [], provenance: "TUTOR_ENGINE", created_at: "2026-10-03T10:00:00Z" };
const VIEW = {
  learning_session_id: "ls",
  revision: 3,
  overview: OVERVIEW,
  transcript: [{ message_id: "turn1:in", sender: "EMPLOYEE", input_kind: "TEXT", kind: "TEACHING", text: "Which version?", citations: [], provenance: "EMPLOYEE_INPUT", created_at: "2026-10-03T10:00:00Z" }, REPLY],
  pending_check: { question_id: "q", objective_id: "o", text: "Which version do you follow?" },
  awaiting_continue: false,
  script_prompts: [],
  status: "ACTIVE",
  tutor: { status: "ok", message: "" },
};

const json = (data: unknown) => new Response(JSON.stringify({ request_id: "r", data }), { status: 200, headers: { "content-type": "application/json" } });
const played: { src: string; rate: number }[] = [];

/** Web Audio stand-in: a reply counts as "played" once its first streamed chunk starts. */
class FakeAudioContext {
  currentTime = 0;
  state = "running";
  destination = {};
  async resume() {}
  createBuffer(_channels: number, length: number, rate: number) {
    return { duration: length / rate, copyToChannel: () => undefined };
  }
  createBufferSource() {
    const src = {
      buffer: null as unknown,
      playbackRate: { value: 1 },
      onended: null as null | (() => void),
      connect: () => undefined,
      stop: () => undefined,
      // Each test reply is one chunk, so one started source = one reply heard. It keeps "playing"
      // until stopped, like real audio, so the Stop control stays visible.
      start: () => {
        started.add(src);
        played.push({ src: "stream", rate: src.playbackRate.value });
      },
    };
    return src;
  }
}
const started = new Set<object>();
const pcmResponse = () =>
  new Response(
    new ReadableStream<Uint8Array>({
      start(c) {
        c.enqueue(new Uint8Array([1, 0, 2, 0]));
        c.close();
      },
    }),
    { status: 200, headers: { "content-type": "audio/L16;rate=24000;channels=1", "x-sample-rate": "24000" } },
  );

class FakeAudio {
  playbackRate = 1;
  onended: (() => void) | null = null;
  onerror: (() => void) | null = null;
  constructor(public src: string) {}
  play() {
    played.push({ src: this.src, rate: this.playbackRate });
    return Promise.resolve();
  }
  pause() {}
}

async function renderPage(onTurn?: () => Promise<Response>) {
  vi.stubEnv("NEXT_PUBLIC_WORKWEAVE_MODE", "http");
  vi.resetModules();
  vi.stubGlobal("Audio", FakeAudio);
  vi.stubGlobal("AudioContext", FakeAudioContext);
  vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: () => "blob:reply", revokeObjectURL: () => undefined }));
  const fetch = vi.fn(async (url: string) => {
    const u = String(url);
    if (u.endsWith("/demo-sessions/current")) return json(SESSION);
    if (u.endsWith("/personas")) return json([PERSONA]);
    if (u.endsWith("/capabilities")) return json({ voice_adapter: "AVAILABLE", conversation_engine: "AVAILABLE" });
    if (u.endsWith("/onboarding")) return json(OVERVIEW);
    if (u.endsWith("/onboarding/sessions/ls")) return json(VIEW);
    if (u.includes("/voice/speech/") && u.endsWith("/stream")) return pcmResponse();
    if (u.includes("/voice/speech/")) return new Response(new TextEncoder().encode("RIFF"), { status: 200, headers: { "content-type": "audio/wav" } });
    if (u.endsWith("/turns/stream") && onTurn) return onTurn();
    return json(null);
  });
  vi.stubGlobal("fetch", fetch);
  const { ClientProvider } = await import("@/lib/preview/client-context");
  const { default: TutorPage } = await import("@/app/onboarding/session/page");
  render(
    <ClientProvider>
      <TutorPage />
    </ClientProvider>,
  );
  await screen.findByText("Use the current approved version.", {}, { timeout: 3000 });
  return fetch;
}

afterEach(() => {
  cleanup();
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  window.localStorage.clear();
  played.length = 0;
  started.clear();
});

describe("onboarding session voice and flow polish (API mode)", () => {
  it("welcomes a returning learner from saved data, and can be dismissed", async () => {
    await renderPage();
    const card = screen.getByText("Welcome back").closest(".notice")!;
    expect(card).toHaveTextContent("You're on Separate history from evidence.");
    expect(card).toHaveTextContent("1 of 3 required subtopics complete · 1 optional.");
    expect(card).toHaveTextContent("Your open question: Which version do you follow?");
    fireEvent.click(screen.getByRole("button", { name: "Got it" }));
    expect(screen.queryByText("Welcome back")).toBeNull();
  });

  it("shows the tutor is thinking while a reply is generated", async () => {
    let release!: (r: Response) => void;
    await renderPage(() => new Promise<Response>((r) => (release = r)));
    fireEvent.change(screen.getByLabelText("Ask, answer, or tell me what you need"), { target: { value: "Which one?" } });
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Send" })));
    expect(await screen.findByText(/Tutor is thinking…/)).toBeInTheDocument();
    await act(async () => release(json(VIEW)));
    await waitFor(() => expect(screen.queryByText(/Tutor is thinking…/)).toBeNull());
  });

  it("shows what the tutor is doing while it works, then the reply", async () => {
    let push!: (text: string) => void;
    let close!: () => void;
    const enc = new TextEncoder();
    await renderPage(
      async () =>
        new Response(
          new ReadableStream<Uint8Array>({
            start(c) {
              push = (t) => c.enqueue(enc.encode(t));
              close = () => c.close();
            },
          }),
          { status: 200, headers: { "content-type": "text/event-stream" } },
        ),
    );
    fireEvent.change(screen.getByLabelText("Ask, answer, or tell me what you need"), { target: { value: "Which one?" } });
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Send" })));
    expect(await screen.findByText(/Tutor is thinking…/)).toBeInTheDocument();
    await act(async () => push('event: progress\ndata: {"label":"Finding the right part of the procedure…"}\n\n'));
    expect(await screen.findByText(/Finding the right part of the procedure…/)).toBeInTheDocument();
    await act(async () => push('event: progress\ndata: {"label":"Writing a reply…"}\n\n'));
    expect(await screen.findByText(/Writing a reply…/)).toBeInTheDocument();
    await act(async () => {
      push(`event: done\ndata: ${JSON.stringify({ request_id: "r", data: VIEW })}\n\n`);
      close();
    });
    await waitFor(() => expect(screen.queryByText(/Writing a reply…/)).toBeNull());
  });

  it("Listen plays a reply at the remembered speed", async () => {
    window.localStorage.setItem("ww.voice.prefs.v1", JSON.stringify({ speed: 1.25 }));
    const fetch = await renderPage();
    expect(screen.getByRole("combobox", { name: "Speed" })).toHaveValue("1.25");
    await act(async () => fireEvent.click(await screen.findByRole("button", { name: "Listen to this reply" })));
    // Streamed read-aloud: sound starts with the first chunk, at the remembered speed.
    expect(fetch.mock.calls.some(([u]) => String(u).endsWith("/onboarding/sessions/ls/voice/speech/turn1%3Aout/stream"))).toBe(true);
    await waitFor(() => expect(played).toEqual([{ src: "stream", rate: 1.25 }]));
    expect(screen.getByRole("button", { name: "Stop reading this reply" })).toBeInTheDocument();
  });

  it("remembers read-aloud and speed in this browser", async () => {
    await renderPage();
    fireEvent.click(await screen.findByRole("switch", { name: "Read replies aloud" }));
    fireEvent.change(screen.getByRole("combobox", { name: "Speed" }), { target: { value: "0.9" } });
    expect(JSON.parse(window.localStorage.getItem("ww.voice.prefs.v1")!)).toMatchObject({ readAloud: true, speed: 0.9 });
  });
});

describe("hearing the tutor (read aloud offer and fresh openings)", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
    window.localStorage.clear();
    window.sessionStorage.clear();
    played.length = 0;
  started.clear();
  });

  it("offers spoken replies once; turning them on reads the latest reply and remembers it", async () => {
    await renderPage();
    const offer = await screen.findByTestId("read-aloud-offer");
    expect(offer).toHaveTextContent("Hear the tutor?");
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Turn on spoken replies" })));
    await waitFor(() => expect(played).toHaveLength(1));
    expect(JSON.parse(window.localStorage.getItem("ww.voice.prefs.v1")!)).toMatchObject({ readAloud: true, readAloudOffered: true });
    expect(screen.queryByTestId("read-aloud-offer")).toBeNull();
    expect(screen.getByRole("switch", { name: "Read replies aloud" })).toBeChecked();
  });

  it("\"Not now\" hides the offer for good, without sound", async () => {
    await renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Not now" }));
    expect(screen.queryByTestId("read-aloud-offer")).toBeNull();
    expect(played).toHaveLength(0);
    cleanup();
    await renderPage();
    await act(async () => new Promise((r) => setTimeout(r, 50)));
    expect(screen.queryByTestId("read-aloud-offer")).toBeNull();
  });

  it("reads the opening of a conversation the learner just started (read-aloud on)", async () => {
    window.localStorage.setItem("ww.voice.prefs.v1", JSON.stringify({ readAloud: true }));
    window.sessionStorage.setItem("ww.voice.fresh-start", "ls");
    await renderPage();
    await waitFor(() => expect(played).toHaveLength(1));
    expect(window.sessionStorage.getItem("ww.voice.fresh-start")).toBeNull(); // only once
  });

  it("never replays history on a plain load, or for another conversation", async () => {
    window.localStorage.setItem("ww.voice.prefs.v1", JSON.stringify({ readAloud: true }));
    await renderPage();
    await act(async () => new Promise((r) => setTimeout(r, 100)));
    expect(played).toHaveLength(0);
    cleanup();
    window.sessionStorage.setItem("ww.voice.fresh-start", "some-other-session");
    await renderPage();
    await act(async () => new Promise((r) => setTimeout(r, 100)));
    expect(played).toHaveLength(0);
  });
});

