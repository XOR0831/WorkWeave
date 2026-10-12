import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

const nav = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock("next/navigation", () => ({
  usePathname: () => "/demo/",
  useRouter: () => ({ push: nav.push, replace: vi.fn(), back: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

// jsdom has no modal <dialog>; a minimal stand-in for the shared Dialog component.
beforeAll(() => {
  HTMLDialogElement.prototype.showModal ??= function (this: HTMLDialogElement) {
    this.setAttribute("open", "");
  };
  HTMLDialogElement.prototype.close ??= function (this: HTMLDialogElement) {
    this.removeAttribute("open");
  };
});

const EXPIRES = "2026-10-31T23:59:59+00:00";
const VALID = "WW-7K4Q-M9TX-2PLR-ABCD";
const json = (data: unknown, status = 200) =>
  new Response(JSON.stringify(status === 200 ? { request_id: "r", data } : { request_id: "r", error: data }), { status, headers: { "content-type": "application/json" } });

/** A tiny fake API: the browser's tier changes only when a valid code is posted. */
function api() {
  let tier: "PUBLIC" | "EVALUATOR" = "PUBLIC";
  const posted: string[] = [];
  const fetch = vi.fn(async (url: string, init?: RequestInit) => {
    const u = String(url);
    if (u.endsWith("/demo-access") && init?.method === "POST") {
      const code = JSON.parse(String(init.body)).code as string;
      posted.push(code);
      if (code !== VALID) return json({ code: "MALFORMED_INPUT", message: "That access code isn't valid, or it has expired. Check it and try again.", retryable: false }, 422);
      tier = "EVALUATOR";
      return json({ tier, expires_at: EXPIRES });
    }
    if (u.endsWith("/demo-access") && init?.method === "DELETE") {
      tier = "PUBLIC";
      return json({ tier, expires_at: null });
    }
    if (u.endsWith("/demo-access")) return json({ tier, expires_at: tier === "EVALUATOR" ? EXPIRES : null });
    if (u.endsWith("/demo-usage"))
      return json({ tier, resets_at: "2026-10-12T00:00:00+00:00", run_open: true, new_workspaces_per_day: null,
        items: [{ kind: "TUTOR_TURN", limit: 120, used: 12, shared_full: false }, { kind: "VOICE_LISTEN", limit: 60, used: 3, shared_full: false }, { kind: "VOICE_SPEECH", limit: null, used: 0, shared_full: false }] });
    return json(null);
  });
  return { fetch, posted };
}

async function renderControl(mode: "http" | "preview", fake = api(), props: { variant?: "entry" | "band"; prompt?: boolean } = {}) {
  vi.stubEnv("NEXT_PUBLIC_WORKWEAVE_MODE", mode);
  vi.resetModules();
  vi.stubGlobal("fetch", fake.fetch);
  const { ClientProvider } = await import("@/lib/preview/client-context");
  const { EvaluatorAccess } = await import("@/features/demo/EvaluatorAccess");
  render(
    <ClientProvider>
      <header>
        <EvaluatorAccess {...props} />
      </header>
    </ClientProvider>,
  );
  return fake;
}

afterEach(() => {
  cleanup();
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  window.history.replaceState(null, "", "/");
});

describe("evaluator access in the demo header", () => {
  it("a judge opens it from the header; a wrong code is explained, the right one turns access on", async () => {
    const fake = await renderControl("http");
    await waitFor(() => expect(screen.getByRole("button", { name: "Evaluator access" })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: "Evaluator access" }));
    fireEvent.change(screen.getByLabelText("Access code"), { target: { value: "WW-0000-0000-0000-0000" } });
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Use code" })));
    expect(await screen.findByText(/isn't valid, or it has expired/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Access code"), { target: { value: VALID } });
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Use code" })));
    expect(await screen.findByTestId("evaluator-access-on")).toHaveTextContent(/higher daily limits for judging, until (31 Oct|Oct 31)/);
    const chip = await screen.findByTestId("evaluator-access");
    expect(chip).toHaveTextContent("Evaluator access");
    expect(chip).toHaveTextContent(/until (31 Oct|Oct 31)/); // the UTC expiry day, not the next local day
    expect(document.body).not.toHaveTextContent("WW-7K4Q"); // the code is never shown back
    expect(fake.posted).toEqual(["WW-0000-0000-0000-0000", VALID]);
  });

  it("a link with ?access= applies the code, confirms it, and removes it from the address bar", async () => {
    window.history.replaceState(null, "", `/demo/?access=${VALID}&x=1`);
    const fake = await renderControl("http");
    expect(await screen.findByTestId("evaluator-access-on")).toBeInTheDocument();
    expect(fake.posted).toEqual([VALID]);
    expect(window.location.search).toBe("?x=1");
  });

  it("a bad link explains the problem in the dialog", async () => {
    window.history.replaceState(null, "", "/demo/?access=WW-0000-0000-0000-0000");
    await renderControl("http");
    expect(await screen.findByText(/isn't valid, or it has expired/)).toBeInTheDocument();
    expect(screen.getByLabelText("Access code")).toBeInTheDocument();
  });

  it("access can be turned off again from the chip", async () => {
    window.history.replaceState(null, "", `/demo/?access=${VALID}`);
    await renderControl("http");
    await screen.findByTestId("evaluator-access-on");
    await waitFor(() => expect(screen.getByRole("button", { name: "Stop using code" })).toBeEnabled());
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Stop using code" })));
    await waitFor(() => expect(screen.queryByTestId("evaluator-access")).toBeNull());
    expect(screen.getAllByRole("button", { name: "Evaluator access" }).length).toBeGreaterThan(0);
  });

  it("the UI preview has no limits, so nothing is shown", async () => {
    await renderControl("preview");
    await act(async () => new Promise((r) => setTimeout(r, 50)));
    expect(screen.queryByRole("button", { name: "Evaluator access" })).toBeNull();
  });
});

describe("the landing prompt and the limits chip", () => {
  it("asks public visitors on the landing page, shows the limits, and continues to the catalog without a code", async () => {
    nav.push.mockClear();
    await renderControl("http", api(), { prompt: true });
    const dialog = await screen.findByRole("dialog", { name: "Do you have evaluator access?" });
    expect(dialog).toBeInTheDocument();
    expect(await screen.findByText("Assistant messages (all AI assistants)")).toBeInTheDocument();
    expect(screen.getByText("12 / 120")).toBeInTheDocument();
    expect(screen.queryByText(/Replies read aloud/)).not.toBeInTheDocument(); // uncapped kinds aren't listed
    fireEvent.click(screen.getByRole("button", { name: "Continue without evaluator access" }));
    expect(nav.push).toHaveBeenCalledWith("/demo/");
  });

  it("asks again on every visit, but never someone who already has evaluator access", async () => {
    const fake = api();
    await renderControl("http", fake, { prompt: true });
    fireEvent.click(await screen.findByRole("button", { name: "Continue without evaluator access" }));
    cleanup();
    await renderControl("http", fake, { prompt: true }); // still public: asked again
    expect(await screen.findByRole("dialog", { name: "Do you have evaluator access?" })).toBeInTheDocument();
    cleanup();
    await fake.fetch("/api/demo-access", { method: "POST", body: JSON.stringify({ code: VALID }) });
    await renderControl("http", fake, { prompt: true });
    expect(await screen.findByTestId("evaluator-access")).toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: "Do you have evaluator access?" })).not.toBeInTheDocument();
  });

  it("the header chip shows this run's use of each limit", async () => {
    await renderControl("http", api(), { variant: "band" });
    await waitFor(() => expect(screen.getByRole("button", { name: "Public demo · limits" })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: "Public demo · limits" }));
    expect(await screen.findByText("3 / 60")).toBeInTheDocument();
    expect(screen.getByText(/used by this demo workspace today/)).toBeInTheDocument();
    expect(screen.getByLabelText("Access code")).toBeInTheDocument(); // a code can still be entered here
  });
});
