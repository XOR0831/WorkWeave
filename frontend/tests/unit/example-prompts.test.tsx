import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { ExamplePrompts } from "@/components/chat";
import { companionExamples, handoverExamples, ktExamples, ONBOARDING_EXAMPLES, ticketOf } from "@/features/chat/examples";

afterEach(() => {
  cleanup();
  localStorage.clear();
});

describe("example prompts: what to say", () => {
  it("takes the ticket from a dashboard priority line", () => {
    expect(ticketOf("Ticket #829 · Machine #14 inspection · Due in 1 h")).toBe("Ticket #829");
    expect(ticketOf("INC-203 · Disk alert · Due in 2 h")).toBe("INC-203");
    expect(ticketOf("Nothing urgent")).toBeUndefined();
    expect(ticketOf(undefined)).toBeUndefined();
  });

  it("gives the shift lead delegation with a real teammate, and members their own work", () => {
    const lead = companionExamples({ lead: true, ticket: "Ticket #910", teammate: "Jamie" }).map((e) => e.text);
    expect(lead).toContain("Assign Ticket #910 to Jamie");
    expect(lead).toContain("Who should take Ticket #910?");
    const member = companionExamples({ lead: false, ticket: "Ticket #947" }).map((e) => e.text);
    expect(member.some((t) => t.startsWith("Assign"))).toBe(false); // members can't delegate
    expect(member).toContain("I'm blocked on Ticket #947");
    // Without a ticket or teammate, nothing names one.
    expect(companionExamples({ lead: true }).map((e) => e.text).join(" ")).not.toMatch(/undefined|Assign/);
  });

  it("covers the other chats", () => {
    expect(ONBOARDING_EXAMPLES.map((e) => e.text)).toContain("Let's take a break");
    expect(handoverExamples({ outgoing: true, item: "Machine #14 inspection" })[0]!.text).toBe("What's missing from this handover?");
    expect(handoverExamples({ outgoing: false }).map((e) => e.text)).toContain("What do I need to know for my shift?");
    expect(ktExamples({ responsibility: "Machine #14 maintenance" }).map((e) => e.text)).toContain("Who could take over Machine #14 maintenance?");
  });
});

describe("ExamplePrompts", () => {
  const examples = ["One", "Two", "Three", "Four"].map((text) => ({ text }));

  it("sends the clicked example and shows the rest on request", () => {
    const pick = vi.fn();
    render(<ExamplePrompts examples={examples} onPick={pick} />);
    expect(screen.queryByRole("button", { name: "Four" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "More (1)" }));
    fireEvent.click(screen.getByRole("button", { name: "Four" }));
    expect(pick).toHaveBeenCalledWith("Four");
  });

  it("can be hidden, and stays hidden in this browser", () => {
    const { unmount } = render(<ExamplePrompts examples={examples} onPick={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: "Hide" }));
    expect(screen.queryByRole("button", { name: "One" })).toBeNull();
    unmount();
    render(<ExamplePrompts examples={examples} onPick={() => {}} />);
    expect(screen.getByRole("button", { name: "Show examples" })).toHaveAttribute("aria-expanded", "false");
  });

  it("is disabled while a message is being sent", () => {
    render(<ExamplePrompts examples={examples} onPick={() => {}} disabled />);
    expect(screen.getByRole("button", { name: "One" })).toBeDisabled();
  });
});
