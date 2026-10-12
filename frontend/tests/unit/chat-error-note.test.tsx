import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { ChatErrorNote } from "@/components/chat";

afterEach(cleanup);

describe("chat error note (why, what happened, what next)", () => {
  it("says the server's reason, that nothing changed, and that the typed text is kept", () => {
    render(<ChatErrorNote error={{ code: "DEPENDENCY_UNAVAILABLE", message: "The knowledge-transfer assistant is still working on your previous request.", retryable: true }} />);
    expect(screen.getByRole("alert")).toHaveTextContent(
      "The knowledge-transfer assistant is still working on your previous request. Nothing was changed. What you typed is still in the box.",
    );
  });

  it("doesn't repeat 'nothing changed' when the reason already says it, and gives a limit's reset time", () => {
    render(<ChatErrorNote error={{ code: "LIMIT_REACHED", message: "This demo workspace has used its assistant messages for today. Your work is saved; nothing was sent.", retryable: false, limit: { kind: "TUTOR_TURN", scope: "RUN", resets_at: "2026-10-12T00:00:00+00:00" } }} />);
    const text = screen.getByRole("alert").textContent ?? "";
    expect(text).not.toContain("Nothing was changed");
    expect(text).toMatch(/It resets at /);
    expect(text).not.toContain("still in the box"); // nothing to retry until the reset
  });

  it("doesn't repeat what the server already said about the typed text", () => {
    render(<ChatErrorNote error={{ code: "DEPENDENCY_UNAVAILABLE", message: "The work assistant couldn't reply. Nothing was saved; your message is still in the box, so you can try again.", retryable: true }} />);
    expect(screen.getByRole("alert")).toHaveTextContent(/^WorkWeaveThe work assistant couldn't reply\. Nothing was saved; your message is still in the box, so you can try again\.$/);
  });

  it("recognises other ways of saying it", () => {
    render(<ChatErrorNote error={{ code: "DEPENDENCY_UNAVAILABLE", message: "The save didn't go through. Nothing was committed; your input is kept, so you can retry.", retryable: true }} />);
    const text = screen.getByRole("alert").textContent ?? "";
    expect(text).not.toContain("Nothing was changed");
    expect(text).not.toContain("still in the box");
  });

  it("offers Reload latest for a stale view and Dismiss", () => {
    const retry = vi.fn();
    const dismiss = vi.fn();
    render(<ChatErrorNote error={{ code: "REVISION_CONFLICT", message: "The view changed since you opened it.", retryable: false }} onRetry={retry} onDismiss={dismiss} />);
    fireEvent.click(screen.getByRole("button", { name: "Reload latest" }));
    fireEvent.click(screen.getByRole("button", { name: "Dismiss" }));
    expect(retry).toHaveBeenCalledOnce();
    expect(dismiss).toHaveBeenCalledOnce();
  });
});
