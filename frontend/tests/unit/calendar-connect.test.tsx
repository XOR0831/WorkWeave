import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";

vi.mock("next/navigation", () => ({
  usePathname: () => "/companion/",
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

const CONNECT = { connect_url: "http://127.0.0.1:8001/auth/google", retry_text: "Do I have meetings today?" };
const json = (data: unknown) => new Response(JSON.stringify({ request_id: "r", data }), { status: 200, headers: { "content-type": "application/json" } });

async function renderConnect(statuses: boolean[], popup: { closed: boolean; close: () => void } | null) {
  vi.stubEnv("NEXT_PUBLIC_WORKWEAVE_MODE", "http");
  vi.resetModules();
  const fetch = vi.fn(async (url: string) => {
    if (String(url).endsWith("/calendar/status")) return json({ enabled: true, connected: statuses.shift() ?? true, reachable: true });
    return json(null);
  });
  vi.stubGlobal("fetch", fetch);
  const open = vi.fn(() => popup);
  vi.stubGlobal("open", open);
  const onConnected = vi.fn();
  const { ClientProvider } = await import("@/lib/preview/client-context");
  const { CalendarConnect } = await import("@/features/companion/CalendarConnect");
  render(
    <ClientProvider>
      <CalendarConnect connect={CONNECT} onConnected={onConnected} />
    </ClientProvider>,
  );
  return { open, onConnected, fetch };
}

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("Connect Google Calendar (API mode)", () => {
  it("opens the sign-in from the click, then closes it and asks again once connected", async () => {
    const popup = { closed: false, close: vi.fn() };
    const { open, onConnected } = await renderConnect([false, true], popup);
    const button = await screen.findByRole("button", { name: "Connect Google Calendar" });
    vi.useFakeTimers();
    fireEvent.click(button);
    expect(open).toHaveBeenCalledWith(CONNECT.connect_url, "ww-google-calendar", expect.stringContaining("popup"));
    expect(screen.getByRole("button", { name: "Waiting for Google…" })).toBeDisabled();
    await act(async () => void (await vi.advanceTimersByTimeAsync(2100)));
    expect(onConnected).not.toHaveBeenCalled(); // first check: not yet
    await act(async () => void (await vi.advanceTimersByTimeAsync(2100)));
    expect(popup.close).toHaveBeenCalled();
    expect(onConnected).toHaveBeenCalledWith(CONNECT.retry_text);
  });

  it("offers a plain link when the browser blocks the window", async () => {
    await renderConnect([], null);
    fireEvent.click(await screen.findByRole("button", { name: "Connect Google Calendar" }));
    const link = screen.getByRole("link", { name: "Open Google sign-in" });
    expect(link).toHaveAttribute("href", CONNECT.connect_url);
    expect(link).toHaveAttribute("target", "_blank");
  });

  it("says so when the window is closed before connecting", async () => {
    const popup = { closed: false, close: vi.fn() };
    const { onConnected } = await renderConnect([false, false], popup);
    const button = await screen.findByRole("button", { name: "Connect Google Calendar" });
    vi.useFakeTimers();
    fireEvent.click(button);
    popup.closed = true;
    await act(async () => void (await vi.advanceTimersByTimeAsync(2100)));
    expect(screen.getByText(/closed before Google Calendar was connected/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeEnabled();
    expect(onConnected).not.toHaveBeenCalled();
  });
});
