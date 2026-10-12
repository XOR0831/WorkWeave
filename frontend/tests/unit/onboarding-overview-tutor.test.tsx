import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

vi.mock("next/navigation", () => ({
  usePathname: () => "/onboarding/",
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

const PERSONA = { employee_id: "p", first_name: "Sam", last_name: "Kim", role_name: "Technician", team_name: "Maintenance", team_role: "MEMBER", employment_status: "ACTIVE", scenario_note: "", grants: ["onboarding.learn"] };
const SESSION = { session_id: "s", scenario: { scenario_id: "x", key: "northstar", company_name: "Northstar Manufacturing", industry: "manufacturing" }, workspace_id: "w", pack_version: "v", persona: PERSONA, persona_selected: true, expires_at: "2099-01-01T00:00:00Z" };
const OVERVIEW = {
  learning_assignment_id: "la",
  curriculum_name: "Machine Fundamentals",
  curriculum_version: "1.1",
  source_versions: [],
  topics: [{ topic_id: "t1", name: "Fundamentals", order_index: 1, subtopics: [{ subtopic_id: "s1", name: "Find the current procedure", order_index: 1, objective: "o", status: "NOT_STARTED", optional: false }] }],
  current_subtopic_id: "s1",
  session_status: null,
  learning_session_id: null,
  saved_at: null,
};
const json = (data: unknown) => new Response(JSON.stringify({ request_id: "r", data }), { status: 200, headers: { "content-type": "application/json" } });

async function renderOverview(engine: "AVAILABLE" | "UNAVAILABLE") {
  vi.stubEnv("NEXT_PUBLIC_WORKWEAVE_MODE", "http");
  vi.resetModules();
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const u = String(url);
      if (u.endsWith("/demo-sessions/current")) return json(SESSION);
      if (u.endsWith("/personas")) return json([PERSONA]);
      if (u.endsWith("/capabilities")) return json({ conversation_engine: engine, voice_adapter: "AVAILABLE" });
      if (u.endsWith("/onboarding")) return json(OVERVIEW);
      return json(null);
    }),
  );
  const { ClientProvider } = await import("@/lib/preview/client-context");
  const { default: OnboardingPage } = await import("@/app/onboarding/page");
  render(
    <ClientProvider>
      <OnboardingPage />
    </ClientProvider>,
  );
  await screen.findByRole("button", { name: /(Start|Resume) conversation/ }, { timeout: 3000 });
  await new Promise((r) => setTimeout(r, 50));
}

afterEach(() => {
  cleanup();
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("onboarding overview: is the tutor connected?", () => {
  it("asks the server: with the engine connected, no 'not connected' notice", async () => {
    await renderOverview("AVAILABLE");
    expect(screen.queryByText("The tutor isn't connected yet")).toBeNull();
  });

  it("says so when the server reports no engine", async () => {
    await renderOverview("UNAVAILABLE");
    expect(await screen.findByText("The tutor isn't connected yet")).toBeInTheDocument();
  });
});
