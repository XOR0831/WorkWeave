import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render } from "@testing-library/react";
import { RichText } from "@/lib/text/RichText";

afterEach(cleanup);

describe("tutor reply formatting", () => {
  it("renders bold, italics, paragraphs and numbered steps from the tutor's Markdown", () => {
    const { container } = render(
      <RichText text={"According to **SOP-001, Section 1.2**, check the *registry*.\n\n1. **Verify the status:** approved and current.\n2. **Match the scope:** check it.\n\nDoes that make sense?"} />,
    );
    expect(container.querySelectorAll("strong")[0]!.textContent).toBe("SOP-001, Section 1.2");
    expect(container.querySelector("em")!.textContent).toBe("registry");
    const items = container.querySelectorAll("ol > li");
    expect(items).toHaveLength(2);
    expect(items[0]!.textContent).toBe("Verify the status: approved and current.");
    expect(container.querySelectorAll("p")).toHaveLength(2);
    expect(container.textContent).not.toContain("**");
  });

  it("keeps bullets, numbering starts and line breaks", () => {
    const { container } = render(<RichText text={"Steps:\n3. third\n4. fourth\n\n- one\n* two\nline a\nline b"} />);
    expect(container.querySelector("ol")!.getAttribute("start")).toBe("3");
    expect(container.querySelectorAll("ul > li")).toHaveLength(2);
    expect(container.querySelectorAll("br").length).toBeGreaterThan(0);
  });

  it("shows source headings as headings, not hash marks", () => {
    const { container } = render(<RichText text={"#### 1.1 When this section applies\n\nUse this section when preparing."} />);
    expect(container.querySelector(".rich-h strong")!.textContent).toBe("1.1 When this section applies");
    expect(container.textContent).not.toContain("#");
  });

  it("never turns model output into markup", () => {
    const { container } = render(<RichText text={'<img src=x onerror="alert(1)"> **<b>hi</b>** [link](javascript:alert(1))'} />);
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("b")).toBeNull();
    expect(container.querySelector("a")).toBeNull();
    expect(container.textContent).toContain('<img src=x onerror="alert(1)">');
  });
});
