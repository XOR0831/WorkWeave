import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

vi.mock("next/navigation", () => ({
  usePathname: () => "/onboarding/session/",
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

const citation = {
  citation_id: "t1:0",
  label: "SOP-001 v3.4 · h2:1/h3:1",
  excerpt: { source_id: "s", document_version_id: "", heading_path: ["Fundamentals", "Find the current procedure"], text: "#### 1.1 When this section applies\n\n" + "A long paragraph. ".repeat(200), evidence_type: "OBSERVED" },
};

async function renderPanel(bare: boolean) {
  vi.resetModules();
  const { ClientProvider } = await import("@/lib/preview/client-context");
  const { ReferencePanel } = await import("@/features/onboarding/ReferencePanel");
  render(
    <ClientProvider>
      <ReferencePanel citation={citation as never} pinned={false} onReturn={() => undefined} onOpen={() => undefined} bare={bare} />
    </ClientProvider>,
  );
  return screen.findByTestId("source-excerpt");
}

afterEach(cleanup);

describe("reference panel: long sources", () => {
  it("beside the conversation, the excerpt scrolls in its own box and is reachable by keyboard", async () => {
    const box = await renderPanel(false);
    expect(box).toHaveClass("excerpt-scroll");
    expect(box).toHaveAttribute("tabindex", "0");
    expect(box).toHaveAccessibleName("Source excerpt: SOP-001 v3.4 · h2:1/h3:1");
  });

  it("in the phone sheet, the sheet itself scrolls (no box inside a box)", async () => {
    const box = await renderPanel(true);
    expect(box).not.toHaveClass("excerpt-scroll");
    expect(box).not.toHaveAttribute("tabindex");
  });
});
