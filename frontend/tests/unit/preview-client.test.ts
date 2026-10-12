import { describe, expect, it } from "vitest";
import { PreviewClient } from "@/lib/clients/preview/PreviewClient";
import { PACKS } from "@/fixtures";
import { UI_ACTIONS, WorkWeaveError } from "@/types/contracts";

const k = (s = "") => ({ idempotency_key: `t-${s}-${Math.random()}` });
const turn = (text: string, preview_prompt_id?: string, expected_revision?: number) => ({ ...k("turn"), client_turn_id: `ct-${Math.random()}`, text, input_kind: "TEXT" as const, preview_prompt_id, expected_revision });

async function client(company: "northstar" | "acme" | "harbor", persona?: string) {
  const c = new PreviewClient(null, 0);
  await c.startDemoSession(company, true);
  if (persona) await c.switchPersona(persona);
  return c;
}
async function code(p: Promise<unknown>) {
  try {
    await p;
    return "OK";
  } catch (e) {
    return e instanceof WorkWeaveError ? e.error.code : String(e);
  }
}

describe("fixtures stay honest (docs/28 negative claims)", () => {
  const all = JSON.stringify(PACKS.northstar);
  it("contains no fabricated Northstar facts", () => {
    expect(all).not.toMatch(/45\s*PSI|50\s*PSI|Machine #12|seven incidents/i);
  });
  it("v3.4 is current and older versions superseded", () => {
    const docs = PACKS.northstar.documents;
    expect(docs.find((d) => d.version === "3.4")?.temporal_status).toBe("CURRENT");
    expect(docs.filter((d) => d.version !== "3.4").every((d) => d.temporal_status === "SUPERSEDED")).toBe(true);
  });
  it("every scripted companion ui_action is allowlisted", () => {
    for (const pack of Object.values(PACKS))
      for (const s of pack.companion_scripts) for (const step of s.steps) expect(UI_ACTIONS).toContain(step.ui_action.type);
  });
  it("Harbor never borrows manufacturing nouns", () => {
    expect(JSON.stringify(PACKS.harbor)).not.toMatch(/Machine #|SOP-001 v3/);
  });
});

describe("onboarding", () => {
  it("free text is not interpreted and never changes progress", async () => {
    const c = await client("northstar");
    const s = await c.startOnboardingSession();
    expect(s.transcript[0]!.sender).toBe("AI");
    const after = await c.sendOnboardingTurn(turn("I already know all this", undefined, s.revision));
    expect(after.transcript.at(-1)!.kind).toBe("NOT_INTERPRETED");
    expect(after.overview.topics[0]!.subtopics.every((x) => x.status !== "COMPLETED")).toBe(true);
  });
  it("completion requires the correct check; pause leaves next NOT_STARTED", async () => {
    const c = await client("northstar");
    let s = await c.startOnboardingSession();
    for (const id of ["ns-1-a", "ns-1-ready", "ns-1-hint", "ns-1-partial"]) s = await c.sendOnboardingTurn(turn("x", id, s.revision));
    expect(s.overview.topics[0]!.subtopics[0]!.status).toBe("IN_PROGRESS");
    s = await c.sendOnboardingTurn(turn("x", "ns-1-correct", s.revision));
    expect(s.overview.topics[0]!.subtopics[0]!.status).toBe("COMPLETED");
    expect(s.awaiting_continue).toBe(true);
    s = await c.pauseOnboarding({ ...k(), expected_revision: s.revision });
    expect(s.overview.topics[0]!.subtopics[1]!.status).toBe("NOT_STARTED");
  });
  it("continuing before the objective is met is refused", async () => {
    const c = await client("northstar");
    const s = await c.startOnboardingSession();
    expect(await code(c.continueOnboarding({ ...k(), expected_revision: s.revision }))).toBe("GUARD_FAILED");
  });
  it("stale revision conflicts", async () => {
    const c = await client("northstar");
    const s = await c.startOnboardingSession();
    expect(await code(c.sendOnboardingTurn(turn("x", "ns-1-a", s.revision - 1)))).toBe("REVISION_CONFLICT");
  });
});

describe("companion and delegation", () => {
  it("rejects a non-allowlisted ui_action and keeps the canvas", async () => {
    const c = await client("acme");
    await c.startWorkSession();
    let v = await c.sendWorkMessage(turn("x", "ac-c-tickets"));
    expect(v.canvas.view).toBe("WORK_ITEMS");
    v = await c.sendWorkMessage(turn("x", "ac-c-invalid"));
    expect(v.canvas.view).toBe("WORK_ITEMS");
    expect(v.transcript.at(-1)!.rejected_action).toBe("OPEN_ADMIN_CONSOLE");
  });
  it("editing preserves the recommendation; confirm assigns once; replay is a no-op", async () => {
    const c = await client("acme");
    await c.startWorkSession();
    await c.sendWorkMessage(turn("x", "ac-c-edit"));
    const p = await c.getProposal("ac-dp-126");
    const it203 = p.items.find((i) => i.work_item_id === "ac-wi-203")!;
    expect(it203.recommended_employee_id).toBe("ac-john");
    expect(it203.final_employee_id).toBe("ac-maria");
    expect((await c.listWorkItems()).find((i) => i.work_item_id === "ac-wi-203")!.assignee_id).toBeUndefined();
    const done = await c.confirmProposal("ac-dp-126", { ...k(), expected_revision: p.revision });
    expect(done.status).toBe("CONFIRMED");
    const again = await c.confirmProposal("ac-dp-126", { ...k(), expected_revision: p.revision });
    expect(again.revision).toBe(done.revision);
    expect((await c.listWorkItems()).find((i) => i.work_item_id === "ac-wi-203")!.assignee_id).toBe("ac-maria");
  });
  it("members can't view or confirm proposals", async () => {
    const c = await client("acme", "ac-john");
    expect(await code(c.getProposal("ac-dp-126"))).toBe("FORBIDDEN");
    expect(await code(c.confirmProposal("ac-dp-126", k()))).toBe("FORBIDDEN");
  });
  it("a member report is not official completion", async () => {
    const c = await client("acme");
    const p = await c.getProposal("ac-dp-126");
    await c.confirmProposal("ac-dp-126", { ...k(), expected_revision: p.revision });
    await c.switchPersona("ac-john");
    const ev = await c.reportWorkEvent("ac-wi-203", "REPORTED_COMPLETE", "done", k());
    expect(ev.sync_status).toBe("AWAITING_SOURCE"); // waits for the ticket system (ADR-033)
    const item = (await c.listWorkItems()).find((i) => i.work_item_id === "ac-wi-203")!;
    expect(item.status).toBe("IN_PROGRESS");
    expect(item.report).toMatchObject({ reported_status: "DONE", sync_status: "AWAITING_SOURCE" });
  });
});

describe("shift handover", () => {
  it("lead publishes directly; members can't; required sections guard", async () => {
    const member = await client("acme", "ac-john");
    expect(await code(member.publishHandover(k()))).toBe("FORBIDDEN");
    const lead = await client("acme");
    let w = await lead.getHandoverWorkspace();
    w = await lead.editDraftSection("sec-summary", "", {}, { ...k(), expected_revision: w.revision });
    expect(await code(lead.publishHandover({ ...k(), expected_revision: w.revision }))).toBe("GUARD_FAILED");
    w = await lead.editDraftSection("sec-summary", "", { kind: "UNKNOWN_WITH_FOLLOW_UP", reason: "follow up" }, { ...k(), expected_revision: w.revision });
    w = await lead.publishHandover({ ...k(), expected_revision: w.revision });
    expect(w.status).toBe("PUBLISHED");
    expect(w.publications).toHaveLength(2);
  });
  it("published snapshots don't change when work completes", async () => {
    const c = await client("acme");
    let w = await c.getHandoverWorkspace();
    w = await c.acceptSuggestion("ac-sg-153", "VALIDATE_COMPLETION", { ...k(), expected_revision: w.revision });
    const item = w.items.find((i) => i.handover_item_id === "ac-hi-144")!;
    expect([item.work_status, item.acknowledgement_status]).toEqual(["COMPLETED", "PENDING"]);
    expect(w.publications[0]!.entries.find((e) => e.handover_item_id === "ac-hi-144")!.snapshot_work_status).toBe("IN_PROGRESS");
  });
  it("dispute reopens; a stale cycle can't close the recompleted item", async () => {
    const c = await client("acme");
    let w = await c.getHandoverWorkspace();
    w = await c.acceptSuggestion("ac-sg-153", "VALIDATE_COMPLETION", { ...k(), expected_revision: w.revision });
    const c1 = w.cycles[0]!.completion_cycle_id;
    w = await c.acknowledgeCompletion(c1, "DISPUTE", "still failing", k());
    expect(w.items.find((i) => i.handover_item_id === "ac-hi-144")!.work_status).toBe("IN_PROGRESS");
    w = await c.confirmItemCompletion("ac-hi-144", { ...k(), expected_revision: w.revision });
    expect(await code(c.acknowledgeCompletion(c1, "ACKNOWLEDGE", "", k()))).toBe("GUARD_FAILED");
    const c2 = w.cycles[1]!.completion_cycle_id;
    w = await c.acknowledgeCompletion(c2, "ACKNOWLEDGE", "", k());
    expect(w.items.find((i) => i.handover_item_id === "ac-hi-144")!.work_status).toBe("CLOSED");
  });
  it("members don't receive lead drafts or suggestions", async () => {
    const c = await client("acme", "ac-john");
    const w = await c.getHandoverWorkspace();
    expect(w.draft_sections).toHaveLength(0);
    expect(w.suggestions).toHaveLength(0);
  });
});

describe("exit KT", () => {
  it("no self-approval; exact revision; promotion is idempotent with index pending", async () => {
    const c = await client("northstar", "ns-alex");
    let kt = (await c.getExitKtCase())!;
    kt = await c.submitArtifact("ns-art-135", "ns-artr-136", "TEAM", { ...k(), expected_revision: kt.revision });
    expect(await code(c.decideArtifact("ns-art-135", "ns-artr-136", "APPROVE", "", k()))).toBe("FORBIDDEN");
    await c.switchPersona("ns-morgan");
    kt = (await c.getExitKtCase())!;
    expect(await code(c.decideArtifact("ns-art-135", "wrong-rev", "APPROVE", "", { ...k(), expected_revision: kt.revision }))).toBe("REVISION_CONFLICT");
    kt = await c.decideArtifact("ns-art-135", "ns-artr-136", "APPROVE", "", { ...k(), expected_revision: kt.revision });
    kt = await c.promoteArtifact("ns-art-135", "ns-artr-136", { ...k(), expected_revision: kt.revision });
    kt = await c.promoteArtifact("ns-art-135", "ns-artr-136", { ...k(), expected_revision: kt.revision });
    expect(kt.artifacts[0]!.promotion?.index_status).toBe("PENDING");
    expect((await c.listDocumentVersions()).filter((d) => d.document_type === "KT_ARTIFACT")).toHaveLength(1);
    expect((await c.listDocumentVersions()).find((d) => d.document_code === "SOP-001" && d.version === "3.4")?.temporal_status).toBe("CURRENT");
  });
  it("editing an approved artifact creates a new revision that needs new review", async () => {
    const c = await client("northstar", "ns-alex");
    let kt = (await c.getExitKtCase())!;
    kt = await c.submitArtifact("ns-art-135", "ns-artr-136", "TEAM", { ...k(), expected_revision: kt.revision });
    await c.switchPersona("ns-morgan");
    kt = await c.decideArtifact("ns-art-135", "ns-artr-136", "APPROVE", "", { ...k(), expected_revision: kt.revision });
    await c.switchPersona("ns-alex");
    kt = await c.editArtifact("ns-art-135", "changed", { ...k(), expected_revision: kt.revision });
    const a = kt.artifacts[0]!;
    expect(a.revisions).toHaveLength(2);
    expect(a.revisions.find((r) => r.artifact_revision_id === a.current_revision_id)!.status).toBe("DRAFT");
  });
  it("transfer needs current approved receipt and effective time; receipt alone transfers nothing", async () => {
    const c = await client("northstar", "ns-alex");
    let kt = (await c.getExitKtCase())!;
    kt = await c.submitPackage({ ...k(), expected_revision: kt.revision });
    await c.switchPersona("ns-morgan");
    expect(await code(c.confirmTransfer("ns-rt-138", k()))).toBe("GUARD_FAILED");
    kt = (await c.getExitKtCase())!;
    kt = await c.decidePackage("APPROVE", "", { ...k(), expected_revision: kt.revision });
    await c.switchPersona("ns-jamie");
    kt = await c.receivePackage(kt.package.current_approved_version_id!, k());
    expect(kt.responsibilities.find((r) => r.responsibility_id === "ns-resp-137")!.owner_employee_id).toBe("ns-alex");
    await c.switchPersona("ns-morgan");
    expect(await code(c.confirmTransfer("ns-rt-138", k()))).toBe("GUARD_FAILED"); // future effective time
    kt = (await c.getExitKtCase())!;
    kt = await c.reviewEffectiveTime("ns-rt-138", { ...k(), expected_revision: kt.revision });
    kt = await c.confirmTransfer("ns-rt-138", k());
    expect(kt.responsibilities.find((r) => r.responsibility_id === "ns-resp-137")!.owner_employee_id).toBe("ns-jamie");
  });
  it("successor view hides private interviews, drafts and findings", async () => {
    const c = await client("northstar", "ns-jamie");
    const kt = (await c.getExitKtCase())!;
    expect(kt.interviews).toHaveLength(0);
    expect(kt.artifacts).toHaveLength(0);
    expect(kt.findings).toHaveLength(0);
  });
  it("discovery and drafting report unavailable capability", async () => {
    const c = await client("northstar", "ns-alex");
    expect(await code(c.runDiscovery())).toBe("CAPABILITY_UNAVAILABLE");
    expect(await code(c.draftArtifactFromInterview("ns-int-132"))).toBe("CAPABILITY_UNAVAILABLE");
  });
  it("departure requires a final working date", async () => {
    const c = await client("northstar", "ns-morgan");
    expect(await code(c.createExitKtCase({ employee_id: "ns-jamie", case_kind: "DEPARTURE", reviewer_employee_id: "ns-morgan" }, k()))).toBe("MALFORMED_INPUT");
    expect(await code(c.createExitKtCase({ employee_id: "ns-jamie", case_kind: "ROLE_TRANSITION", reviewer_employee_id: "ns-morgan" }, k()))).toBe("OK");
  });
});

describe("demo entry (ADR-024)", () => {
  it("a new run needs an explicit persona choice; switching records it", async () => {
    const c = new PreviewClient(null, 0);
    const s = await c.startDemoSession("acme", false);
    expect(s.persona_selected).toBe(false);
    expect((await c.getLocalDemoRun("acme"))!.persona_selected).toBe(false);
    const after = await c.switchPersona("ac-john");
    expect(after.persona_selected).toBe(true);
    expect((await c.getLocalDemoRun("acme"))!.persona?.employee_id).toBe("ac-john");
  });
  it("fresh replaces only the selected company's run", async () => {
    const c = new PreviewClient(null, 0);
    await c.startDemoSession("northstar", false);
    const ns = (await c.getLocalDemoRun("northstar"))!.workspace_id;
    const a1 = await c.startDemoSession("acme", false);
    const p = await c.getProposal("ac-dp-126");
    await c.confirmProposal("ac-dp-126", { idempotency_key: "x", expected_revision: p.revision });
    const a2 = await c.startDemoSession("acme", true);
    expect(a2.workspace_id).not.toBe(a1.workspace_id);
    expect((await c.getProposal("ac-dp-126")).status).toBe("PROPOSED");
    expect((await c.getLocalDemoRun("northstar"))!.workspace_id).toBe(ns);
  });
  it("a failed fresh start leaves the existing run untouched", async () => {
    const c = new PreviewClient(null, 0);
    const a1 = await c.startDemoSession("acme", false);
    await c.switchPersona("ac-alex");
    c.setFailureMode("fail_next");
    expect(await code(c.startDemoSession("acme", true))).toBe("DEPENDENCY_UNAVAILABLE");
    const run = (await c.getLocalDemoRun("acme"))!;
    expect(run.workspace_id).toBe(a1.workspace_id);
    expect(run.persona?.employee_id).toBe("ac-alex");
  });
  it("resume keeps the run; unknown companies are refused", async () => {
    const c = new PreviewClient(null, 0);
    const a = await c.startDemoSession("harbor", false);
    expect((await c.startDemoSession("harbor", false)).workspace_id).toBe(a.workspace_id);
    expect(await code(c.startDemoSession("nope" as "acme", false))).toBe("NOT_FOUND");
  });
});

describe("curricula & sources guards (proposed coordinator contract)", () => {
  const draftId = "northstar-curr-draft-1-1";
  it("only coordinators can open the workspace", async () => {
    expect(await code((await client("northstar", "ns-sam")).listCurricula())).toBe("FORBIDDEN");
    expect(await code((await client("northstar", "ns-morgan")).listCurricula())).toBe("OK");
  });
  it("a filename-only upload is staged but can't be parsed", async () => {
    const c = await client("northstar", "ns-morgan");
    const cur = await c.stageCurriculumSource(draftId, { document_code: "X-1", title: "Fictional", version: "1", file: { name: "x.md", size: 10 }, use_sample: false }, k());
    const src = cur.sources[0]!;
    expect(src.origin).toBe("FILENAME_ONLY");
    expect(await code(c.parseCurriculumSource(draftId, src.curriculum_source_id, k()))).toBe("CAPABILITY_UNAVAILABLE");
    expect(await code(c.stageCurriculumSource(draftId, { document_code: "X-2", title: "Fictional", version: "1", file: { name: "x.pdf", size: 10 }, use_sample: false }, k()))).toBe("MALFORMED_INPUT");
  });
  it("source approval doesn't publish; publication needs the readiness gate", async () => {
    const c = await client("northstar", "ns-morgan");
    let cur = await c.stageCurriculumSource(draftId, { document_code: "", title: "", version: "", use_sample: true }, k());
    const sid = cur.sources[0]!.curriculum_source_id;
    cur = await c.parseCurriculumSource(draftId, sid, k());
    // H4 headings stay inside H3 sections; reference aids default to reference-only.
    expect(cur.sources[0]!.sections).toHaveLength(7);
    expect(cur.sources[0]!.sections[0]!.nested_headings.length).toBeGreaterThan(0);
    expect(await code(c.submitSourceForReview(draftId, sid, k()))).toBe("GUARD_FAILED");
    expect(await code(c.publishCurriculum(draftId, k()))).toBe("GUARD_FAILED");
    const mappings = Object.fromEntries(cur.sources[0]!.sections.map((s) => [s.section_id, s.mapping]));
    await c.saveSourceMappings(draftId, sid, mappings, true, k());
    await c.submitSourceForReview(draftId, sid, k());
    cur = await c.reviewSourceVersion(draftId, sid, "APPROVED", "", k());
    expect(cur.status).toBe("DRAFT");
    expect(cur.sources[0]!.stage).toBe("APPROVED");
    expect((await c.publishCurriculum(draftId, k())).status).toBe("PUBLISHED");
    expect(await code(c.stageCurriculumSource(draftId, { document_code: "", title: "", version: "", use_sample: true }, k()))).toBe("GUARD_FAILED");
  });
  it("rejection purges the source and keeps a non-content receipt; a reason is required", async () => {
    const c = await client("northstar", "ns-morgan");
    let cur = await c.stageCurriculumSource(draftId, { document_code: "", title: "", version: "", use_sample: true }, k());
    const sid = cur.sources[0]!.curriculum_source_id;
    cur = await c.parseCurriculumSource(draftId, sid, k());
    await c.saveSourceMappings(draftId, sid, {}, true, k());
    await c.submitSourceForReview(draftId, sid, k());
    expect(await code(c.reviewSourceVersion(draftId, sid, "REJECTED", " ", k()))).toBe("MALFORMED_INPUT");
    cur = await c.reviewSourceVersion(draftId, sid, "REJECTED", "Remap section 3", k());
    expect(cur.sources).toHaveLength(0);
    const receipts = (await c.listCurricula()).receipts;
    expect(receipts[0]).toMatchObject({ decision: "REJECTED", document_code: "SOP-001", reason: "Remap section 3" });
    expect(JSON.stringify(receipts)).not.toMatch(/Use this section when preparing/);
  });
});
