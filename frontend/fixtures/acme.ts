/**
 * Acme Infrastructure Operations — operational acceptance fixture (UI preview only).
 *
 * From src/local/postgres/02_seed.sql: Alex Chen leads Platform Operations; John, Maria and
 * Sam Lim have synthetic supervisor-validated evidence; INC-203 / INC-221 / ACT-101; John's
 * REPORTED_COMPLETE event awaits lead validation; Pat Reyes has a DEPARTURE case.
 * The certificate-renewal knowledge item is a labelled preview addition taken from the
 * example in docs/16-exit-knowledge-transfer-user-flow.md (origin PREVIEW_FIXTURE).
 */
import type { PackFixture } from "./types";
import { simpleSubtopic } from "./script-helpers";

const OPS11 = "ac-dv-ops001-11";
const OPS10 = "ac-dv-ops001-10";

const ex = (key: string, heading: string[], text: string, document_version_id = OPS11) => ({
  [key]: { source_id: `ac-src-${key}`, document_version_id, heading_path: heading, text, evidence_type: "OBSERVED" as const },
});

const excerpts = {
  ...ex("ops-1", ["1. Fundamentals", "1. Introduction"], "Use the current approved source, not a familiar historical version. This text is a synthetic training fixture."),
  ...ex("ops-2", ["1. Fundamentals", "2. Deployment Process"], "Keep reported and verified facts separate. An earlier incident cannot prove a current cause. No operational action is authorized by this fixture."),
  ...ex("ops-3", ["1. Fundamentals", "3. Rollback"], "Name the current work item and approved source version. State missing evidence and ask the authorized reviewer for clarification. Do not invent company procedures."),
  ...ex("ops-10", ["Historical synthetic reference"], "Superseded; not current instructions.", OPS10),
  "ev-131": {
    source_id: "ac-src-ev-131",
    document_version_id: "",
    heading_path: ["Work event", "INC-203 · REPORTED_COMPLETE"],
    text: "John reported correcting the gateway configuration and validating transactions. Lead verification is still pending.",
    evidence_type: "REPORTED" as const,
  },
  "pub-1": {
    source_id: "ac-src-pub-1",
    document_version_id: "",
    heading_path: ["Shift handover", "Publication #1 (Morning → Afternoon)"],
    text: "INC-203: IN_PROGRESS. INC-221: BLOCKED, waiting for approved network diagnostic evidence. ACT-101: ACTIVE, maintenance tonight; approved window must be confirmed.",
    evidence_type: "REPORTED" as const,
  },
};

const sections = [
  { section_id: "sec-summary", name: "Shift Summary", order_index: 1, is_required: true },
  { section_id: "sec-active", name: "Active / Ongoing Items", order_index: 2, is_required: true },
  { section_id: "sec-incidents", name: "Incidents / Issues", order_index: 3, is_required: false },
  { section_id: "sec-scheduled", name: "Scheduled Activities", order_index: 4, is_required: false },
  { section_id: "sec-blockers", name: "Blockers / Risks", order_index: 5, is_required: false },
  { section_id: "sec-notes", name: "Important Notes", order_index: 6, is_required: false },
];

const members = ["ac-john", "ac-maria", "ac-sam", "ac-pat"];

export const acme: PackFixture = {
  card: {
    scenario_id: "acme-platform-ops",
    key: "acme",
    company_name: "Acme Infrastructure Operations",
    industry: "Infrastructure operations",
    story:
      "Alex delegates INC-203, INC-221 and ACT-101, validates John's completion report, and carries the same items through three shifts while Pat prepares a departure handover.",
    pack_version: "review-only-v1",
    status: "READY",
    role_in_review: "Delegation and three-shift acceptance",
    terminology: { workItem: "incident", workItems: "incidents and activities", team: "platform team", asset: "service" },
  },
  personas: [
    { employee_id: "ac-alex", first_name: "Alex", last_name: "Chen", role_name: "Operations engineer", team_name: "Platform Operations", team_role: "SHIFT_LEAD", employment_status: "ACTIVE", scenario_note: "Afternoon shift lead; led the completed earlier Morning shift", grants: ["work.report", "work.validate", "delegation.confirm", "handover.publish", "handover.receive"] },
    { employee_id: "ac-john", first_name: "John", last_name: "Tan", role_name: "Operations engineer", team_name: "Platform Operations", team_role: "MEMBER", employment_status: "ACTIVE", scenario_note: "Payment gateway evidence; reported INC-203 complete", grants: ["work.report", "handover.receive"] },
    { employee_id: "ac-maria", first_name: "Maria", last_name: "Garcia", role_name: "Operations engineer", team_name: "Platform Operations", team_role: "MEMBER", employment_status: "ACTIVE", scenario_note: "Network diagnostics evidence; proposed successor for Pat", grants: ["work.report", "handover.receive", "exitkt.successor"] },
    { employee_id: "ac-sam", first_name: "Sam", last_name: "Lim", role_name: "Operations engineer", team_name: "Platform Operations", team_role: "MEMBER", employment_status: "ACTIVE", scenario_note: "Database operations evidence; assigned Deployment Fundamentals", grants: ["onboarding.learn", "work.report", "handover.receive"] },
    { employee_id: "ac-pat", first_name: "Pat", last_name: "Reyes", role_name: "Operations engineer", team_name: "Platform Operations", team_role: "MEMBER", employment_status: "NOTICE_PERIOD", scenario_note: "Departing; owns payment gateway operations", grants: ["work.report", "handover.receive", "exitkt.subject"] },
    { employee_id: "ac-morgan", first_name: "Morgan", last_name: "Lee", role_name: "Knowledge reviewer / manager", team_name: "Platform Operations", team_role: "MANAGER", employment_status: "ACTIVE", scenario_note: "Reviews knowledge and packages; confirms transfers", grants: ["onboarding.supervise", "curriculum.manage", "knowledge.review", "responsibility.confirm"] },
    { employee_id: "ac-neha", first_name: "Neha", last_name: "Shah", role_name: "Operations engineer", team_name: "Platform Operations", team_role: "SHIFT_LEAD", employment_status: "ACTIVE", scenario_note: "Lead for the next Morning shift, with Sam Lim", grants: ["work.report", "delegation.confirm", "handover.publish", "handover.receive"] },
    { employee_id: "ac-aisha", first_name: "Aisha", last_name: "Rahman", role_name: "Operations engineer", team_name: "Platform Operations", team_role: "SHIFT_LEAD", employment_status: "ACTIVE", scenario_note: "Evening shift lead after Alex Chen, with Maria Garcia", grants: ["work.report", "delegation.confirm", "handover.publish", "handover.receive"] },
  ],
  documents: [
    { document_version_id: OPS11, document_id: "ac-doc-ops001", document_code: "OPS-SOP-001", title: "Deployment and rollback reporting", version: "1.1", approval_status: "APPROVED", temporal_status: "CURRENT", approved_by: "Morgan Lee (synthetic fixture reviewer)", effective_label: "Current", document_type: "SOP", index_status: "PENDING" },
    { document_version_id: OPS10, document_id: "ac-doc-ops001", document_code: "OPS-SOP-001", title: "Historical synthetic reference", version: "1.0", approval_status: "APPROVED", temporal_status: "SUPERSEDED", approved_by: "Morgan Lee (synthetic fixture reviewer)", effective_label: "Superseded by v1.1", document_type: "SOP" },
  ],
  excerpts,
  full_text: {
    [OPS11]: ["ops-1", "ops-2", "ops-3"].map((k) => `## ${excerpts[k as keyof typeof excerpts].heading_path.join(" › ")}\n\n${excerpts[k as keyof typeof excerpts].text}`).join("\n\n"),
    [OPS10]: "# Historical synthetic reference\n\nSuperseded; not current instructions.",
  },
  onboarding: {
    curriculum_name: "Deployment Fundamentals",
    curriculum_version: "1.0",
    source_version_ids: [OPS11],
    topics: [
      {
        topic_id: "ac-topic-1",
        name: "Deployment Fundamentals",
        order_index: 1,
        subtopics: [
          { subtopic_id: "ac-st-1", name: "Introduction", order_index: 1, objective: "Use the current approved deployment source.", status: "NOT_STARTED" },
          { subtopic_id: "ac-st-2", name: "Deployment Process", order_index: 2, objective: "Keep reported and verified deployment facts separate.", status: "NOT_STARTED" },
          { subtopic_id: "ac-st-3", name: "Rollback", order_index: 3, objective: "Ask a reviewer a specific rollback question with unknowns explicit.", status: "NOT_STARTED" },
        ],
      },
    ],
    learners: [{ employee_id: "ac-sam", learning_assignment_id: "ac-la-sam", completed: [] }],
    new_learner_greeting: "Welcome, {name}.",
    curriculum_complete_text: "You've completed Deployment Fundamentals. That doesn't grant production deployment access; your lead confirms that separately.",
    scripts: [
      simpleSubtopic({
        id: "ac-st-1",
        excerpt: "ops-1",
        opening: "Welcome, {name}. Deployment Fundamentals starts with which source to trust. Have you followed a deployment runbook before?",
        answerPrompt: "Yes, but I usually use whatever's bookmarked.",
        teaching: "Bookmarks can point at history. OPS-SOP-001 v1.1 is the approved, current version; v1.0 is superseded.",
        check: "A teammate shares OPS-SOP-001 v1.0 from a bookmark. Which version do you follow, and why?",
        partial: "v1.1, I think it's newer.",
        partialFeedback: "Right version. What makes it the one to follow, rather than being newer?",
        correct: "v1.1, because it's the approved current version. v1.0 is superseded history.",
        correctFeedback: "Yes. You used approval and current status, not recency.",
        hint: "Check the approval and temporal status of each version.",
      }),
      simpleSubtopic({
        id: "ac-st-2",
        excerpt: "ops-2",
        opening: "Next: the deployment process. When a deployment update comes in, what tells you whether it's verified?",
        answerPrompt: "If someone says it's done, I assume it's done.",
        teaching: "A report is valuable, but it isn't verification. Keep reported and verified facts separate, and don't let an earlier incident explain a current one.",
        check: "John reports that INC-203 is fixed. What should the handover say until the lead validates it?",
        partial: "That INC-203 is fixed.",
        partialFeedback: "That turns a report into a fact. How would you keep it accurate?",
        correct: "That John reported INC-203 fixed, and lead validation is still pending.",
        correctFeedback: "Exactly. The report stays a report until it's validated.",
        hint: "Look at the difference between 'reported' and 'verified'.",
      }),
      simpleSubtopic({
        id: "ac-st-3",
        excerpt: "ops-3",
        opening: "Last subtopic: rollback. If the approved source doesn't cover a rollback step, what do you do?",
        answerPrompt: "I'd look it up online.",
        teaching: "Don't invent company procedures. Name the work item and source version, state what's missing, and ask the authorized reviewer.",
        check: "Write the question you'd send to Morgan if the rollback step for ACT-101 isn't in OPS-SOP-001 v1.1.",
        partial: "Morgan, how do I roll back ACT-101?",
        partialFeedback: "Good start. Add the source you checked and what exactly is missing.",
        correct: "Morgan, for ACT-101 I checked OPS-SOP-001 v1.1 and it doesn't cover the rollback step. Which approved source or reviewer covers it? I'll hold until then.",
        correctFeedback: "That names the work item, the source, the gap and the response you need.",
        hint: "Include the work item, the source version and the exact gap.",
      }),
    ],
  },
  supervisor_ids: ["ac-morgan", "ac-alex"],
  work_items: [
    { work_item_id: "ac-wi-203", external_id: "INC-203", work_item_type: "INCIDENT", title: "Payment API Timeout", description: "Gateway investigation ongoing. A prior-shift member completion report requires lead verification.", priority: "HIGH", status: "IN_PROGRESS", due_label: "SLA in 2 h", revision: 4 },
    { work_item_id: "ac-wi-221", external_id: "INC-221", work_item_type: "INCIDENT", title: "Network Latency", description: "Waiting for approved network diagnostic evidence.", priority: "MEDIUM", status: "BLOCKED", due_label: "SLA in 6 h", revision: 2 },
    { work_item_id: "ac-wi-101", external_id: "ACT-101", work_item_type: "ACTIVITY", title: "Production Database Maintenance", description: "Maintenance tonight; approved window must be confirmed before execution.", priority: "MEDIUM", status: "ACTIVE", due_label: "Tonight", revision: 1 },
  ],
  work_events: [
    { work_event_id: "ac-ev-131", work_item_id: "ac-wi-203", employee_id: "ac-john", event_type: "REPORTED_COMPLETE", description: "John reported correcting the gateway configuration and validating transactions. Lead verification is still pending.", evidence_type: "REPORTED", observed_label: "1 hour ago", validation: "PENDING" },
    { work_event_id: "ac-ev-221", work_item_id: "ac-wi-221", employee_id: "ac-maria", event_type: "BLOCKED", description: "Waiting for approved network diagnostic evidence.", evidence_type: "REPORTED", observed_label: "3 hours ago" },
  ],
  companion_scripts: [
    {
      employee_id: "ac-alex",
      opening:
        "You have two active incidents and one scheduled activity. John reported INC-203 done, but it's still open in the incident system, and database maintenance is scheduled tonight. What would you like to focus on?",
      steps: [
        { prompt: { prompt_id: "ac-c-tickets", label: "Focus on tickets", text: "I want to focus on tickets." }, reply: "Here's the open work for Platform Operations.", excerpt_keys: [], ui_action: { type: "SHOW_WORK_ITEMS", filters: { status: ["ACTIVE", "IN_PROGRESS", "BLOCKED"] } } },
        { prompt: { prompt_id: "ac-c-blocked", label: "Only blocked tickets", text: "Only show the blocked ones." }, reply: "One item is blocked: INC-221.", excerpt_keys: [], ui_action: { type: "SHOW_WORK_ITEMS", filters: { status: ["BLOCKED"] } } },
        { prompt: { prompt_id: "ac-c-203", label: "Show INC-203", text: "Show INC-203." }, reply: "INC-203 is in progress. John reported it done; the incident system hasn't confirmed it yet.", excerpt_keys: [], ui_action: { type: "SHOW_WORK_ITEMS", resource_refs: ["ac-wi-203"] } },
        { prompt: { prompt_id: "ac-c-guide", label: "Ask how to troubleshoot it", text: "How do I troubleshoot that payment timeout?" }, reply: "The approved sources here don't include payment-timeout troubleshooting steps. I've shown what is approved and what's missing.", excerpt_keys: ["ops-2"], ui_action: { type: "SHOW_GUIDANCE", resource_refs: ["g-ac-timeout"] } },
        { prompt: { prompt_id: "ac-c-updates", label: "Show recent updates", text: "Show recent updates." }, reply: "Here are the permitted updates. John's report is labelled reported, separate from the incident system's status.", excerpt_keys: [], ui_action: { type: "SHOW_WORK_UPDATES" } },
        { prompt: { prompt_id: "ac-c-focus", label: "Ask what to focus on", text: "What should I focus on?" }, reply: "Here's a focus plan from deadlines, blockers and reports waiting for the incident system.", excerpt_keys: [], ui_action: { type: "SHOW_FOCUS_PLAN" } },
        { prompt: { prompt_id: "ac-c-delegate", label: "Recommend assignments", text: "Recommend assignments." }, reply: "Here's a proposal using validated evidence and declared availability. Nothing is assigned until you confirm.", excerpt_keys: [], ui_action: { type: "SHOW_DELEGATION_PROPOSAL", resource_refs: ["ac-dp-126"] } },
        { prompt: { prompt_id: "ac-c-edit", label: "Reassign INC-203 and ACT-101", text: "Give INC-203 to Maria and database maintenance to John." }, reply: "Updated: INC-203 → Maria, ACT-101 → John. The original recommendations are kept for reference. Confirm when you're ready.", excerpt_keys: [], ui_action: { type: "SHOW_DELEGATION_PROPOSAL", resource_refs: ["ac-dp-126"] }, effect: { kind: "EDIT_PROPOSAL", edits: [{ work_item_id: "ac-wi-203", final_employee_id: "ac-maria" }, { work_item_id: "ac-wi-101", final_employee_id: "ac-john" }] } },
        { prompt: { prompt_id: "ac-c-ambiguous", label: "Ask about \"that one\"", text: "What's the status of that one?" }, reply: "Which item do you mean: INC-203, INC-221 or ACT-101? I've kept the current view.", excerpt_keys: [], ui_action: { type: "REQUEST_CLARIFICATION" } },
        { prompt: { prompt_id: "ac-c-invalid", label: "Preview: invalid ui_action", text: "(Preview) Return a ui_action outside the allowlist." }, reply: "", excerpt_keys: [], ui_action: { type: "NO_VIEW_CHANGE" }, effect: { kind: "INVALID_ACTION", attempted: "OPEN_ADMIN_CONSOLE" } },
        { prompt: { prompt_id: "ac-c-brief", label: "Back to my briefing", text: "Back to my work briefing." }, reply: "Here's your briefing again.", excerpt_keys: [], ui_action: { type: "SHOW_BRIEFING" } },
      ],
    },
    {
      employee_id: "ac-john",
      opening: "Hi John. You reported INC-203 done; it stays on your list until the incident system shows it resolved. Any new assignments from this shift will appear here.",
      steps: [
        { prompt: { prompt_id: "ac-j-work", label: "Show my work", text: "Show my work." }, reply: "Here's the open team work you can see.", excerpt_keys: [], ui_action: { type: "SHOW_WORK_ITEMS", filters: { status: ["ACTIVE", "IN_PROGRESS", "BLOCKED"] } } },
        { prompt: { prompt_id: "ac-j-report", label: "Report INC-203 done", text: "INC-203 is done. The gateway configuration was incorrect; I corrected it and validated the transactions." }, reply: "Here's a work report draft. Submitting it records a completion report. It doesn't change the incident: resolve it in the incident system.", excerpt_keys: ["ops-2"], ui_action: { type: "NO_VIEW_CHANGE" }, effect: { kind: "OPEN_REPORT", work_item_id: "ac-wi-203", draft: "INC-203 is done. The gateway configuration was incorrect; I corrected it and validated the transactions." } },
        { prompt: { prompt_id: "ac-j-brief", label: "Back to my briefing", text: "Back to my briefing." }, reply: "Here's your briefing again.", excerpt_keys: [], ui_action: { type: "SHOW_BRIEFING" } },
      ],
    },
  ],
  guidance: [
    {
      guidance_id: "g-ac-timeout",
      question: "How do I troubleshoot that payment timeout?",
      answer:
        "OPS-SOP-001 v1.1 covers source selection and reporting, not payment-gateway troubleshooting. Keep John's report labelled as reported, and ask the authorized reviewer for the applicable runbook.",
      answer_status: "INSUFFICIENT_EVIDENCE",
      citations: [],
      unknowns: ["Approved payment-timeout troubleshooting procedure"],
      related_work_item_id: "ac-wi-203",
    },
  ],
  proposal: {
    delegation_proposal_id: "ac-dp-126",
    status: "PROPOSED",
    revision: 1,
    origin: "SYNTHETIC_SEED",
    items: [
      { proposal_item_id: "ac-dpi-127", work_item_id: "ac-wi-203", recommended_employee_id: "ac-john", recommendation_reason: "Payment gateway and incident response evidence; declared available.", evidence: ["Payment gateway: supervisor validation (synthetic)", "Incident response: supervisor validation (synthetic)"] },
      { proposal_item_id: "ac-dpi-128", work_item_id: "ac-wi-221", recommended_employee_id: "ac-maria", recommendation_reason: "Network diagnostics evidence; declared available.", evidence: ["Network diagnostics: supervisor validation (synthetic)"] },
      { proposal_item_id: "ac-dpi-129", work_item_id: "ac-wi-101", recommended_employee_id: "ac-sam", recommendation_reason: "Database operations evidence; declared available.", evidence: ["Database operations: supervisor validation (synthetic)", "Maintenance procedures: supervisor validation (synthetic)"], uncertainty: "Sam is still in onboarding for Deployment Fundamentals; that's separate from this evidence." },
    ],
  },
  priorities: {
    "ac-alex": ["INC-203 reported done: waiting for the incident system", "INC-221 blocked: diagnostic evidence pending", "Confirm ACT-101 maintenance window before tonight"],
    "ac-john": ["INC-203 reported done: waiting for the incident system"],
    "ac-maria": ["INC-221 network evidence"],
    "ac-sam": ["Start Deployment Fundamentals"],
    "ac-pat": ["Departure knowledge transfer"],
    "ac-morgan": ["Review submitted knowledge", "Pat's departure package"],
  },
  handover: {
    template_name: "Platform Operations shift handover",
    template_version: "1",
    sections,
    occurrences: [
      { shift_instance_id: "ac-si-morning", name: "Morning", window_label: "07:00–15:00 Asia/Manila", lead_employee_id: "ac-alex", member_ids: members, status: "COMPLETED" },
      { shift_instance_id: "ac-si-afternoon", name: "Afternoon", window_label: "15:00–23:00 Asia/Manila", lead_employee_id: "ac-alex", member_ids: members, status: "ACTIVE" },
      { shift_instance_id: "ac-si-evening", name: "Evening", window_label: "23:00–07:00 Asia/Manila", lead_employee_id: "ac-aisha", member_ids: ["ac-maria"], status: "SCHEDULED" },
      { shift_instance_id: "ac-si-next-morning", name: "Morning", window_label: "07:00–15:00 Asia/Manila", lead_employee_id: "ac-neha", member_ids: ["ac-sam"], status: "SCHEDULED" },
    ],
    source_shift_id: "ac-si-afternoon",
    target_shift_id: "ac-si-evening",
    items: [
      { handover_item_id: "ac-hi-144", display_id: "HI-144", work_item_id: "ac-wi-203", title: "Payment API Timeout (INC-203)", description: "Gateway investigation ongoing. A prior-shift member completion report requires lead verification.", originating_shift_instance_id: "ac-si-morning", work_status: "IN_PROGRESS", acknowledgement_status: "NOT_REQUIRED", section_id: "sec-active", evidence_type: "REPORTED", source_label: "INC-203 work events" },
      { handover_item_id: "ac-hi-147", display_id: "HI-147", work_item_id: "ac-wi-221", title: "Network Latency (INC-221)", description: "Waiting for approved network diagnostic evidence.", originating_shift_instance_id: "ac-si-morning", work_status: "BLOCKED", acknowledgement_status: "NOT_REQUIRED", section_id: "sec-blockers", evidence_type: "REPORTED", source_label: "INC-221 work events" },
      { handover_item_id: "ac-hi-150", display_id: "HI-150", work_item_id: "ac-wi-101", title: "Production Database Maintenance (ACT-101)", description: "Maintenance tonight; approved window must be confirmed before execution.", originating_shift_instance_id: "ac-si-morning", work_status: "ACTIVE", acknowledgement_status: "NOT_REQUIRED", section_id: "sec-active", evidence_type: "REPORTED", source_label: "ACT-101" },
    ],
    draft_sections: [
      { section_id: "sec-summary", content: "INC-203 has a completion report pending validation. INC-221 remains blocked." },
      { section_id: "sec-active", content: "INC-203 and ACT-101 carry over from the Morning shift." },
      { section_id: "sec-incidents", content: "" },
      { section_id: "sec-scheduled", content: "" },
      { section_id: "sec-blockers", content: "INC-221 is waiting for approved network diagnostic evidence." },
      { section_id: "sec-notes", content: "" },
    ],
    suggestions: [
      { suggestion_id: "ac-sg-153", suggestion_type: "STATUS_UPDATE", handover_item_id: "ac-hi-144", title: "INC-203 reported complete", reason: "INC-203 is listed as In Progress, but John reported completion 1 hour ago. Review the evidence and update?", before: "IN_PROGRESS", proposed: "COMPLETED (after your validation)", source_label: "Work event · John Tan · reported", evidence_type: "REPORTED", status: "PENDING", report_event_id: "ac-ev-131" },
      { suggestion_id: "ac-sg-156", suggestion_type: "MISSING_ITEM", handover_item_id: "ac-hi-150", title: "ACT-101 missing from Scheduled Activities", reason: "ACT-101 database maintenance tonight appears in a synthetic email but isn't under Scheduled Activities. The window time still needs confirming.", proposed: "List HI-150 under Scheduled Activities (window to be confirmed).", source_label: "Synthetic email fixture, not an integration", evidence_type: "REPORTED", status: "PENDING" },
    ],
    publications: [
      {
        publication_id: "ac-pub-142",
        publication_number: 1,
        source_shift_instance_id: "ac-si-morning",
        target_shift_instance_id: "ac-si-afternoon",
        template_version: "1",
        sections: [
          { section_id: "sec-summary", content: "Synthetic shift summary. Open work requires follow-up." },
          { section_id: "sec-active", content: "INC-203: IN_PROGRESS. ACT-101: ACTIVE, maintenance tonight." },
          { section_id: "sec-blockers", content: "INC-221: BLOCKED." },
        ],
        entries: [
          { handover_item_id: "ac-hi-144", display_id: "HI-144", title: "Payment API Timeout (INC-203)", section_id: "sec-active", snapshot_work_status: "IN_PROGRESS", snapshot_acknowledgement_status: "NOT_REQUIRED", snapshot_description: "Gateway investigation ongoing." },
          { handover_item_id: "ac-hi-147", display_id: "HI-147", title: "Network Latency (INC-221)", section_id: "sec-blockers", snapshot_work_status: "BLOCKED", snapshot_acknowledgement_status: "NOT_REQUIRED", snapshot_description: "Waiting for approved network diagnostic evidence." },
          { handover_item_id: "ac-hi-150", display_id: "HI-150", title: "Production Database Maintenance (ACT-101)", section_id: "sec-active", snapshot_work_status: "ACTIVE", snapshot_acknowledgement_status: "NOT_REQUIRED", snapshot_description: "Maintenance tonight; approved window must be confirmed before execution." },
        ],
        published_by: "ac-alex",
        published_label: "Today, end of Morning shift",
        receipts: [{ employee_id: "ac-john", received_label: "Start of Afternoon shift" }],
      },
    ],
    copilot_opening:
      "Since the Morning publication: John reported INC-203 complete, and a synthetic email mentions tonight's ACT-101 maintenance. Review each one; nothing changes the draft until you accept it.",
    copilot_steps: [
      { audience: "LEAD", prompt: { prompt_id: "ac-h-changed", label: "What changed since Morning?", text: "What changed since the Morning handover?" }, reply: "John reported INC-203 complete (not yet validated). INC-221 is still blocked. ACT-101 should probably be under Scheduled Activities.", excerpt_keys: ["ev-131"] },
      { audience: "LEAD", prompt: { prompt_id: "ac-h-missing", label: "Is anything required missing?", text: "Is anything required still missing?" }, reply: "Both required sections have content. Optional sections can stay empty.", excerpt_keys: [] },
      { audience: "INCOMING", prompt: { prompt_id: "ac-h-open", label: "What's still open for us?", text: "What's still open for us?" }, reply: "From the published snapshot: INC-221 is blocked and ACT-101 is tonight. Check the current state too, because items may have changed since publication.", excerpt_keys: ["pub-1"] },
    ],
  },
  exit_kt: {
    case: {
      exit_kt_case_id: "ac-kt-160",
      employee_id: "ac-pat",
      case_kind: "DEPARTURE",
      final_working_date: "In 14 days",
      status: "IN_PROGRESS",
      reviewer_employee_id: "ac-morgan",
      revision: 1,
      knowledge_items: [
        { kt_item_id: "ac-kti-161", title: "Deployment and rollback reporting", description: "Current approved SOP already exists.", documentation_status: "DOCUMENTED", kt_status: "EXISTING_KNOWLEDGE", risk_level: "MEDIUM", origin: "SYNTHETIC_SEED", linked_source: "OPS-SOP-001 v1.1" },
        { kt_item_id: "ac-kti-162", title: "Historical procedure references", description: "Historical version appears in older notes; compare against the current source.", documentation_status: "OUTDATED", kt_status: "NOT_STARTED", risk_level: "MEDIUM", origin: "SYNTHETIC_SEED" },
        { kt_item_id: "ac-kti-163", title: "Evidence-based escalation practice", description: "Pat's reporting practice isn't approved reusable knowledge yet.", documentation_status: "MISSING", kt_status: "DRAFT_CREATED", risk_level: "HIGH", origin: "SYNTHETIC_SEED", artifact_id: "ac-art-171" },
        { kt_item_id: "ac-kti-164", title: "Certificate renewal verification", description: "The renewal checklist covers issuance but not verification after renewal.", documentation_status: "MISSING", kt_status: "INTERVIEW_REQUIRED", risk_level: "HIGH", origin: "PREVIEW_FIXTURE" },
      ],
      findings: [
        { finding_id: "ac-ktf-165", kt_item_id: "ac-kti-162", finding_type: "OUTDATED_DOCUMENTATION", description: "Older notes reference OPS-SOP-001 v1.0. Review them; this isn't proof that current instructions are wrong.", evidence: ["OPS-SOP-001 v1.0 (superseded)"], status: "OPEN", origin: "SYNTHETIC_SEED" },
        { finding_id: "ac-ktf-166", kt_item_id: "ac-kti-163", finding_type: "UNDOCUMENTED_KNOWLEDGE", description: "Pat's reporting practice needs employee review and knowledge approval.", evidence: ["Consented interview (private)"], status: "OPEN", origin: "SYNTHETIC_SEED" },
        { finding_id: "ac-ktf-167", finding_type: "MISSING_SUCCESSOR", description: "Certificate renewal and vendor escalation has no proposed successor.", evidence: ["Responsibility record: certificate renewal and vendor escalation"], status: "OPEN", origin: "SYNTHETIC_SEED" },
      ],
      interviews: [
        {
          interview_id: "ac-int-168",
          kt_item_id: "ac-kti-163",
          status: "PAUSED",
          consent_accepted: true,
          messages: [
            { message_id: "ac-im-169", sender_type: "AI", content: "Which current work item and approved source do you include when requesting missing evidence?", provenance: "SCRIPTED_FIXTURE" },
            { message_id: "ac-im-170", sender_type: "EMPLOYEE", content: "I include the work item and source version, keep the cause unknown, and ask the reviewer to verify the missing evidence.", provenance: "EMPLOYEE_INPUT" },
          ],
          script_prompts: [],
        },
      ],
      artifacts: [
        {
          artifact_id: "ac-art-171",
          kt_item_id: "ac-kti-163",
          artifact_type: "CHECKLIST",
          title: "Requesting evidence-based clarification",
          current_revision_id: "ac-artr-172",
          revisions: [{ artifact_revision_id: "ac-artr-172", version: 1, content: "1. Identify the current work item.\n2. Cite the approved source version.\n3. State missing evidence and ask the reviewer.", status: "DRAFT", audience: "PRIVATE" }],
        },
      ],
      responsibilities: [
        { responsibility_id: "ac-resp-173", responsibility_type: "PROCESS", title: "Payment gateway operations", owner_employee_id: "ac-pat", ownership_revision: 1 },
        { responsibility_id: "ac-resp-175", responsibility_type: "RECURRING_TASK", title: "Certificate renewal and vendor escalation", owner_employee_id: "ac-pat", ownership_revision: 1 },
      ],
      transfers: [
        { transfer_id: "ac-rt-174", responsibility_id: "ac-resp-173", current_owner_employee_id: "ac-pat", recommended_owner_employee_id: "ac-maria", recommendation_reason: "Proposed successor from the seeded scenario. Package receipt and manager confirmation are still required.", status: "PROPOSED", effective_label: "Tomorrow 07:00 (future)", effective_reached: false, expected_owner_revision: 1, origin: "SYNTHETIC_SEED" },
        { transfer_id: "ac-rt-175", responsibility_id: "ac-resp-175", current_owner_employee_id: "ac-pat", status: "DISCOVERED", effective_label: "Not set", effective_reached: false, expected_owner_revision: 1, origin: "SYNTHETIC_SEED" },
      ],
      package: {
        package_id: "ac-pkg-176",
        successor_employee_id: "ac-maria",
        status: "DRAFT",
        revision: 1,
        draft_sections: [
          { title: "Responsibilities", content: "Payment gateway operations" },
          { title: "Current procedure", content: "OPS-SOP-001 v1.1 (approved, current)", evidence_type: "OBSERVED" },
          { title: "Open work", content: "INC-203 has a completion report awaiting lead validation.", evidence_type: "REPORTED" },
          { title: "Knowledge gaps", content: "Certificate renewal verification isn't documented. Private checklist awaits review.", evidence_type: "UNKNOWN" },
        ],
        versions: [],
        receipts: [],
      },
      checklist: [
        { checklist_item_id: "ac-ktc-178", label: "Evidence-based escalation practice documented and approved", required: true, status: "OPEN", evidence_refs: [] },
        { checklist_item_id: "ac-ktc-179", label: "Payment gateway operations transferred or explicitly retained", required: true, status: "OPEN", evidence_refs: [] },
      ],
      open_work_note: "INC-221 and any unvalidated INC-203 work stay open. Completing KT doesn't close them.",
      successor_prompts: [],
      successor_qa: [],
    },
    interview_opening: "The certificate-renewal checklist lists issuance but not verification. What checks do you perform after renewal, and where is the result recorded?",
    interview_steps: [
      { prompt: { prompt_id: "ai-1", label: "Describe your checks", text: "I check the new expiry date on every endpoint and confirm the vendor portal shows the renewal. I note the result on the renewal ticket." }, ai_follow_up: "Thanks. What do you do if one endpoint still shows the old certificate?" },
      { prompt: { prompt_id: "ai-2", label: "Describe the exception", text: "I open a vendor escalation and keep the renewal ticket open until every endpoint is verified." }, ai_follow_up: "That covers the exception path. You'll review any draft privately before anyone else sees it." },
    ],
    successor_steps: [
      { prompt: { prompt_id: "ac-s-open", label: "What's still open for me?", text: "What's still open for me?" }, reply: "In the approved package, INC-203 has a completion report awaiting validation, and certificate renewal verification is still an open knowledge gap.", excerpt_keys: ["ev-131"] },
    ],
    draft_artifact_template: "",
  },
  timeline: [
    { entry_id: "ac-tl-1", label: "OPS-SOP-001 v1.1 approved and current", detail: "Deployment and rollback reporting. Semantic index pending.", kind: "DOCUMENT_VERSION", temporal: "CURRENT", evidence_type: "OBSERVED", document_version_id: OPS11 },
    { entry_id: "ac-tl-2", label: "OPS-SOP-001 v1.0 superseded", detail: "Historical synthetic reference.", kind: "DOCUMENT_VERSION", temporal: "HISTORICAL", evidence_type: "OBSERVED", document_version_id: OPS10 },
    { entry_id: "ac-tl-3", label: "INC-203 completion reported", detail: "John's report awaits lead validation.", kind: "WORK_HISTORY", temporal: "CURRENT", evidence_type: "REPORTED" },
  ],
};
