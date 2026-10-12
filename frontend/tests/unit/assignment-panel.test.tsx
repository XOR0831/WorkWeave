import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

vi.mock("next/navigation", () => ({
  usePathname: () => "/companion/",
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

// Labelled test data shaped like the API (ADR-035).
const ITEM = { work_item_id: "w829", external_id: "Ticket #829", work_item_type: "TICKET", title: "Machine #14 inspection", description: "", priority: "HIGH", status: "IN_PROGRESS", due_label: "Due in 2 h", assignee_id: "jamie", revision: 3, assignment_source: "AUTOMATIC" } as const;
const WHY = {
  work_item_id: "w829",
  assigned: true,
  summary: "Assigned automatically to Jamie Chen by the competency rule: no validated evidence yet for Procedure control.",
  assignee_name: "Jamie Chen",
  source: "AUTOMATIC",
  requirements: [{ name: "Procedure control", required_level: 1, met: false }],
  compared: [
    { name: "Jamie Chen", gaps: 1, open_work: 0, availability: "AVAILABLE" },
    { name: "Sam Kim", gaps: 1, open_work: 1, availability: "AVAILABLE" },
  ],
};
const CANDIDATES = [
  { employee_id: "jamie", name: "Jamie Chen", gaps: ["Procedure control"], open_work: 1, availability: "AVAILABLE" },
  { employee_id: "sam", name: "Sam Kim", gaps: [], open_work: 1, availability: "AVAILABLE" },
];
const json = (data: unknown) => new Response(JSON.stringify({ request_id: "r", data }), { status: 200, headers: { "content-type": "application/json" } });

async function renderPanel(isLead: boolean) {
  vi.stubEnv("NEXT_PUBLIC_WORKWEAVE_MODE", "http");
  vi.resetModules();
  const fetch = vi.fn(async (url: string, init?: RequestInit) => {
    const u = String(url);
    if (u.endsWith("/work-items/w829/assignment")) return json(WHY);
    if (u.endsWith("/assignment-candidates")) return json(CANDIDATES);
    if (u.endsWith("/work-items/w829/assignee") && init?.method === "POST") return json({ ...WHY, source: "MANUAL", assignee_name: "Sam Kim" });
    return json(null);
  });
  vi.stubGlobal("fetch", fetch);
  const { ClientProvider } = await import("@/lib/preview/client-context");
  const { AssignmentPanel } = await import("@/features/companion/Assignment");
  render(
    <ClientProvider>
      <AssignmentPanel item={ITEM} isLead={isLead} />
    </ClientProvider>,
  );
  return fetch;
}

afterEach(() => {
  cleanup();
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("ticket assignment panel (API mode)", () => {
  it("shows the lead why, with how the members compared", async () => {
    await renderPanel(true);
    fireEvent.click(await screen.findByRole("button", { name: "Why this person?" }));
    expect(await screen.findByText(/Assigned automatically to Jamie Chen/)).toBeInTheDocument();
    expect(screen.getByRole("listitem")).toHaveTextContent("Procedure control (level 1): no validated evidence yet");
    expect(screen.getByRole("table", { name: /How the members on the shift compared/ })).toBeInTheDocument();
  });

  it("lets the lead change the assignee to a member on the shift", async () => {
    const fetch = await renderPanel(true);
    fireEvent.click(await screen.findByRole("button", { name: "Change assignee" }));
    const select = await screen.findByRole("combobox", { name: /Give it to someone on your shift/ });
    expect(screen.queryByRole("option", { name: /Jamie Chen/ })).toBeNull(); // the current assignee isn't offered
    fireEvent.change(select, { target: { value: "sam" } });
    fireEvent.click(screen.getAllByRole("button", { name: "Change assignee" }).at(-1)!);
    await waitFor(() => {
      const call = fetch.mock.calls.find((c) => String(c[0]).endsWith("/assignee"));
      expect(call).toBeTruthy();
      expect(JSON.parse(String((call![1] as RequestInit).body))).toMatchObject({ employee_id: "sam", expected_revision: 3 });
    });
  });

  it("gives other members only the label, no reasons or controls", async () => {
    await renderPanel(false);
    expect(await screen.findByText("Assigned automatically by competency")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Why this person?" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Change assignee" })).toBeNull();
  });
});
