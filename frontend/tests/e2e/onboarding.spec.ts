import { expect, test } from "@playwright/test";
import { asPersona, btn, chip, startCompany } from "./helpers";

test.describe("Adaptive onboarding (screens/onboarding 01–12)", () => {
  test("AI opens first, inline check, hint is not an attempt, completion then break keeps next NOT_STARTED", async ({ page }) => {
    await startCompany(page, "Northstar");
    await page.goto("/onboarding/");
    await expect(page.getByRole("heading", { name: "Machine Fundamentals" })).toBeVisible();
    await btn(page, "Start conversation").click();
    await page.waitForURL("**/onboarding/session/");

    const log = page.getByRole("log", { name: "Tutor conversation" });
    // AI-initiated: first message is the tutor's, no employee message yet.
    await expect(log).toContainText("Welcome, Sam");
    await expect(log.locator(".msg-employee")).toHaveCount(0);

    // Visible tap-to-talk, disabled with explanation (no voice adapter).
    const mic = page.getByRole("button", { name: /Tap to talk/ });
    await expect(mic).toBeVisible();
    await expect(mic).toBeDisabled();
    await expect(page.getByText("Voice not connected")).toBeVisible();

    // Right panel: learning path + one cited excerpt.
    await expect(page.getByRole("heading", { name: "Reference for this explanation" })).toBeVisible();
    await expect(page.locator("aside")).toContainText("SOP-001 v3.4");

    // Free text is never interpreted and does not change progress.
    await page.getByLabel("Ask, answer, or tell me what you need").fill("I think I know this already");
    await btn(page, "Send").click();
    await expect(log).toContainText("Not interpreted");
    await expect(page.locator("aside")).toContainText("0 of 3 complete");

    await chip(page, "Answer the opening question");
    await chip(page, "Ask to be checked");
    // The open check lives only in the transcript (no duplicate notice outside it).
    await expect(log.locator(".msg-check").last()).toContainText("Comprehension check");
    await chip(page, "Ask for a hint");
    await expect(log).toContainText("A hint doesn't count as an answer");
    await chip(page, "Give a partial answer");
    await expect(log).toContainText("Evidence: Partial");
    await expect(page.locator("aside")).toContainText("0 of 3 complete");
    await chip(page, "Give a complete answer");
    await expect(log).toContainText("You've completed \"Find the current procedure\"");
    await expect(page.locator("aside")).toContainText("1 of 3 complete");

    // Break: next subtopic stays NOT_STARTED.
    await btn(page, "Take a break").click();
    await expect(log).toContainText("The next subtopic stays not started");
    await page.goto("/onboarding/");
    const path = page.getByRole("list", { name: "Subtopics" });
    await expect(path.locator("li").nth(0)).toContainText("Completed");
    await expect(path.locator("li").nth(1)).toContainText("Not started");

    // Resume after refresh preserves progress.
    await page.reload();
    await btn(page, "Resume conversation").click();
    await expect(page.getByRole("log", { name: "Tutor conversation" })).toContainText("Your completed work is saved");
    await btn(page, "Continue to Separate history from evidence").click();
    await expect(page.locator("aside")).toContainText("Separate history from evidence");
  });

  test("returning learner resumes the in-progress subtopic; cross-topic question keeps position", async ({ page }) => {
    await startCompany(page, "Northstar");
    await asPersona(page, "Jamie Chen");
    await page.goto("/onboarding/");
    await btn(page, "Resume conversation").click();
    const log = page.getByRole("log", { name: "Tutor conversation" });
    await expect(log).toContainText("Welcome back, Jamie");
    await chip(page, "Answer the question");
    await chip(page, "Ask about a later section");
    await expect(log).toContainText("Your place stays on 'Separate history from evidence'");
    await expect(page.getByRole("list", { name: "Subtopics" }).locator("li", { hasText: "Current position" })).toContainText("Separate history from evidence");
  });

  test("supervisor sees progress without private conversation; learners are denied", async ({ page }) => {
    await startCompany(page, "Northstar");
    await page.goto("/onboarding/progress/");
    await expect(page.getByText("This isn't available to your persona")).toBeVisible();
    await asPersona(page, "Morgan Lee");
    await page.goto("/onboarding/progress/");
    await expect(page.getByRole("table")).toContainText("Jamie Chen");
    await expect(page.getByRole("table")).not.toContainText("Welcome");
  });

  test("failed save keeps the typed text and claims no progress", async ({ page }) => {
    await startCompany(page, "Northstar");
    await page.goto("/onboarding/");
    await btn(page, "Start conversation").click();
    await page.waitForURL("**/onboarding/session/");
    await expect(page.getByLabel("Ask, answer, or tell me what you need")).toBeVisible();
    await page.getByRole("button", { name: "Review tools" }).click();
    await page.getByLabel(/Next save fails/).check();
    await page.getByRole("button", { name: "Close Review tools" }).click();
    await page.getByLabel("Ask, answer, or tell me what you need").fill("Keep this text");
    await btn(page, "Send").click();
    // Said inside the conversation: why, that nothing changed, and that the text is kept.
    await expect(page.getByTestId("chat-error")).toContainText(/didn't go through.*input is kept/);
    await expect(page.getByLabel("Ask, answer, or tell me what you need")).toHaveValue("Keep this text");
  });
});
