import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

vi.mock("next/navigation", () => ({
  usePathname: () => "/onboarding/session/",
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

// Labelled test data shaped like the API responses; the page renders through the real HttpClient.
const PERSONA = { employee_id: "test-sam", first_name: "Sam", last_name: "Kim", role_name: "Technician", team_name: "Maintenance", team_role: "MEMBER", employment_status: "ACTIVE", scenario_note: "", grants: ["onboarding.learn"] };
const SESSION = {
  session_id: "test-session",
  scenario: { scenario_id: "test-scn", key: "northstar", company_name: "Northstar Manufacturing", industry: "manufacturing" },
  workspace_id: "test-ws",
  pack_version: "review-only-v1",
  persona: PERSONA,
  persona_selected: true,
  expires_at: "2099-01-01T00:00:00Z",
};
const sub = (id: string, name: string, status: string) => ({ subtopic_id: id, name, order_index: 1, objective: `Demonstrate ${name.toLowerCase()}.`, status });
const OVERVIEW = {
  learning_assignment_id: "test-la",
  curriculum_name: "Machine Fundamentals",
  curriculum_version: "1.0",
  source_versions: [],
  topics: [{ topic_id: "test-t1", name: "Machine Fundamentals", order_index: 1, subtopics: [sub("test-s1", "Find the current procedure", "IN_PROGRESS"), sub("test-s2", "Separate history from evidence", "NOT_STARTED")] }],
  current_subtopic_id: "test-s1",
  session_status: "ACTIVE",
  learning_session_id: "test-ls",
};
const CITATION = {
  citation_id: "t1:0",
  label: "SOP-001 v3.4 · h2:1/h3:1",
  excerpt: { source_id: "test-src", document_version_id: "test-v34", heading_path: ["Fundamentals", "Find the current procedure"], text: "Confirm the current approved version before acting.", evidence_type: "OBSERVED" },
};
const VIEW = {
  learning_session_id: "test-ls",
  revision: 4,
  overview: OVERVIEW,
  transcript: [
    { message_id: "t1:in", sender: "EMPLOYEE", input_kind: "TEXT", kind: "TEACHING", text: "How do I know which procedure to use?", citations: [], provenance: "EMPLOYEE_INPUT", created_at: "2026-10-03T10:00:00Z" },
    { message_id: "t1:out", sender: "AI", kind: "TEACHING", text: "Use the current approved procedure version.", citations: [CITATION], provenance: "TUTOR_ENGINE", created_at: "2026-10-03T10:00:00Z" },
    { message_id: "t2:in", sender: "EMPLOYEE", input_kind: "TEXT", kind: "TEACHING", text: "Use the newest one.", citations: [], provenance: "EMPLOYEE_INPUT", created_at: "2026-10-03T10:01:00Z" },
    {
      message_id: "t2:out", sender: "AI", kind: "FEEDBACK", text: "Close. What do you do about the gap?", citations: [], provenance: "TUTOR_ENGINE", created_at: "2026-10-03T10:01:00Z",
      assessment: { outcome: "PARTIAL", criteria_version: "synthetic-criteria-v1", note: "Not counted yet: every reviewed criterion must be met without hints." },
    },
  ],
  pending_check: { question_id: "test-q1", objective_id: "test-o1", text: "Two procedure versions disagree. Which one do you follow?" },
  awaiting_continue: false,
  script_prompts: [],
  status: "ACTIVE",
  tutor: { status: "ok", message: "" },
};

const json = (data: unknown) => new Response(JSON.stringify({ request_id: "r", data }), { status: 200, headers: { "content-type": "application/json" } });

async function renderSession(view: unknown) {
  vi.stubEnv("NEXT_PUBLIC_WORKWEAVE_MODE", "http");
  vi.resetModules();
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const u = String(url);
      if (u.endsWith("/demo-sessions/current")) return json(SESSION);
      if (u.endsWith("/personas")) return json([PERSONA]);
      if (u.endsWith("/onboarding")) return json(OVERVIEW);
      if (u.endsWith("/onboarding/sessions/test-ls")) return json(view);
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
  await screen.findByText("Use the current approved procedure version.", {}, { timeout: 3000 });
}

afterEach(() => {
  cleanup();
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("onboarding session, API mode", () => {
  it("shows committed turns, citations, the recorded assessment and the open question", async () => {
    await renderSession(VIEW);
    expect(screen.getByText("How do I know which procedure to use?")).toBeInTheDocument();
    expect(screen.getAllByText(/SOP-001 v3\.4 · h2:1\/h3:1/).length).toBeGreaterThan(0);
    expect(screen.getByText("Assessed: Partial")).toBeInTheDocument();
    expect(screen.getByText(/Not counted yet: every reviewed criterion must be met without hints\. Criteria synthetic-criteria-v1\./)).toBeInTheDocument();
    expect(screen.queryByText(/Fixture outcome/)).toBeNull();
    expect(screen.getByText("Open question")).toBeInTheDocument();
    expect(screen.getByText("Two procedure versions disagree. Which one do you follow?")).toBeInTheDocument();
    expect(screen.getByText("Replies are saved only after their sources and answers are checked")).toBeInTheDocument();
    expect(screen.queryByText(/Scripted preview/)).toBeNull();
  });

  it("never offers an unconnected Continue after a completion; the completion is stated as saved", async () => {
    const done = {
      ...VIEW,
      tutor: { status: "unavailable", message: "The tutor isn't connected yet." },
      pending_check: null,
      awaiting_continue: true,
      transcript: [...VIEW.transcript, { message_id: "t3:done", sender: "SYSTEM", kind: "COMPLETION", text: "Find the current procedure is complete.", citations: [], provenance: "BACKEND_RECORD", created_at: "2026-10-03T10:02:00Z" }],
    };
    await renderSession(done);
    expect(screen.getByText("Find the current procedure is complete.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Continue to/ })).toBeNull();
    expect(screen.getByText(/isn't connected yet\. Your completion is saved\./)).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Take a break" }).length).toBeGreaterThan(0);
  });

  it("states honestly when the tutor isn't connected", async () => {
    await renderSession({ ...VIEW, tutor: { status: "unavailable", message: "The tutor isn't connected yet." } });
    expect(screen.getByText("Replies aren't available yet")).toBeInTheDocument();
    expect(screen.getByText("Tutor not connected · your place and breaks are saved")).toBeInTheDocument();
  });
});
