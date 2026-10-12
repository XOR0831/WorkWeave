/**
 * Harbor Support (BPO) — portability fixture across all four modules (UI preview only).
 *
 * From src/local/postgres/02_seed.sql: Customer Support team; Nora (learner), Leo (shift lead,
 * role transition owner of priority account escalation), Mia (proposed successor), Ravi
 * (reviewer/manager); CASE-104 and ACT-105; BPO-SOP-001 v1.1 current, v1.0 superseded.
 * Conversation wording beyond the seed is preview copy written for screen review.
 */
import type { PackFixture } from "./types";
import { simpleSubtopic } from "./script-helpers";

const BPO11 = "hb-dv-bpo001-11";
const BPO10 = "hb-dv-bpo001-10";

const ex = (key: string, heading: string[], text: string, document_version_id = BPO11) => ({
  [key]: { source_id: `hb-src-${key}`, document_version_id, heading_path: heading, text, evidence_type: "OBSERVED" as const },
});

const excerpts = {
  ...ex("bpo-1", ["1. Fundamentals", "1. Use the approved account guide"], "Use the current approved source, not a familiar historical version. This text is a synthetic training fixture."),
  ...ex("bpo-2", ["1. Fundamentals", "2. Separate customer reports from verified facts"], "Keep reported and verified facts separate. An earlier incident cannot prove a current cause. No operational action is authorized by this fixture."),
  ...ex("bpo-3", ["1. Fundamentals", "3. Escalate without exposing private data"], "Name the current work item and approved source version. State missing evidence and ask the authorized reviewer for clarification. Do not invent company procedures."),
  ...ex("bpo-10", ["Historical synthetic reference"], "Superseded; not current instructions.", BPO10),
  "case-104": {
    source_id: "hb-src-case-104",
    document_version_id: "",
    heading_path: ["Case", "CASE-104 Billing clarification"],
    text: "Customer reports a disputed amount. Verification is pending; do not assert a confirmed billing fault.",
    evidence_type: "REPORTED" as const,
  },
  "pub-1": {
    source_id: "hb-src-pub-1",
    document_version_id: "",
    heading_path: ["Queue handover", "Publication #1 (Morning → Afternoon)"],
    text: "CASE-104: IN_PROGRESS. Customer-reported disputed amount; verification pending. ACT-105: ACTIVE, refresher time to be confirmed.",
    evidence_type: "REPORTED" as const,
  },
};

const members = ["hb-nora", "hb-mia"];

export const harbor: PackFixture = {
  card: {
    scenario_id: "harbor-account-queue",
    key: "harbor",
    company_name: "Harbor Support",
    industry: "Customer support BPO",
    story:
      "Nora learns the approved account guide, Leo hands the support queue across shifts and prepares to move off priority-account escalation, and Ravi approves the hand-off to Mia.",
    pack_version: "review-only-v1",
    status: "READY",
    role_in_review: "Portability across industries",
    terminology: { workItem: "case", workItems: "cases", team: "support queue", asset: "account", queue: "support queue" },
  },
  personas: [
    { employee_id: "hb-nora", first_name: "Nora", last_name: "Santos", role_name: "Support specialist", team_name: "Customer Support", team_role: "MEMBER", employment_status: "ONBOARDING", scenario_note: "New learner assigned Account Support Fundamentals", grants: ["onboarding.learn", "work.report", "handover.receive"] },
    { employee_id: "hb-leo", first_name: "Leo", last_name: "Cruz", role_name: "Support specialist", team_name: "Customer Support", team_role: "SHIFT_LEAD", employment_status: "ACTIVE", scenario_note: "Queue shift lead; moving off priority-account escalation", grants: ["work.report", "work.validate", "delegation.confirm", "handover.publish", "handover.receive", "exitkt.subject"] },
    { employee_id: "hb-mia", first_name: "Mia", last_name: "Reyes", role_name: "Support specialist", team_name: "Customer Support", team_role: "MEMBER", employment_status: "ACTIVE", scenario_note: "Proposed successor for priority-account escalation", grants: ["work.report", "handover.receive", "exitkt.successor"] },
    { employee_id: "hb-ravi", first_name: "Ravi", last_name: "Patel", role_name: "Knowledge reviewer / manager", team_name: "Customer Support", team_role: "MANAGER", employment_status: "ACTIVE", scenario_note: "Reviews knowledge and packages; confirms transfers", grants: ["onboarding.supervise", "curriculum.manage", "knowledge.review", "responsibility.confirm"] },
    { employee_id: "hb-cora", first_name: "Cora", last_name: "Mendoza", role_name: "Support specialist", team_name: "Customer Support", team_role: "SHIFT_LEAD", employment_status: "ACTIVE", scenario_note: "Lead for the next Morning shift, with Nora Santos", grants: ["work.report", "delegation.confirm", "handover.publish", "handover.receive"] },
    { employee_id: "hb-tessa", first_name: "Tessa", last_name: "Lim", role_name: "Support specialist", team_name: "Customer Support", team_role: "SHIFT_LEAD", employment_status: "ACTIVE", scenario_note: "Evening shift lead after Leo Cruz, with Mia Reyes", grants: ["work.report", "delegation.confirm", "handover.publish", "handover.receive"] },
  ],
  documents: [
    { document_version_id: BPO11, document_id: "hb-doc-bpo001", document_code: "BPO-SOP-001", title: "Customer account escalation", version: "1.1", approval_status: "APPROVED", temporal_status: "CURRENT", approved_by: "Ravi Patel (synthetic fixture reviewer)", effective_label: "Current", document_type: "SOP", index_status: "PENDING" },
    { document_version_id: BPO10, document_id: "hb-doc-bpo001", document_code: "BPO-SOP-001", title: "Historical synthetic reference", version: "1.0", approval_status: "APPROVED", temporal_status: "SUPERSEDED", approved_by: "Ravi Patel (synthetic fixture reviewer)", effective_label: "Superseded by v1.1", document_type: "SOP" },
  ],
  excerpts,
  full_text: {
    [BPO11]: ["bpo-1", "bpo-2", "bpo-3"].map((k) => `## ${excerpts[k as keyof typeof excerpts].heading_path.join(" › ")}\n\n${excerpts[k as keyof typeof excerpts].text}`).join("\n\n"),
    [BPO10]: "# Historical synthetic reference\n\nSuperseded; not current instructions.",
  },
  onboarding: {
    curriculum_name: "Account Support Fundamentals",
    curriculum_version: "1.0",
    source_version_ids: [BPO11],
    topics: [
      {
        topic_id: "hb-topic-1",
        name: "Account Support Fundamentals",
        order_index: 1,
        subtopics: [
          { subtopic_id: "hb-st-1", name: "Use the approved account guide", order_index: 1, objective: "Use and cite the current approved account guide.", status: "NOT_STARTED" },
          { subtopic_id: "hb-st-2", name: "Separate customer reports from verified facts", order_index: 2, objective: "Keep customer-reported claims separate from verified facts.", status: "NOT_STARTED" },
          { subtopic_id: "hb-st-3", name: "Escalate without exposing private data", order_index: 3, objective: "Escalate with the minimum necessary account information.", status: "NOT_STARTED" },
        ],
      },
    ],
    learners: [{ employee_id: "hb-nora", learning_assignment_id: "hb-la-nora", completed: [] }],
    new_learner_greeting: "Welcome, {name}.",
    curriculum_complete_text: "You've completed Account Support Fundamentals. That doesn't grant priority-account access; your lead confirms that separately.",
    scripts: [
      simpleSubtopic({
        id: "hb-st-1",
        excerpt: "bpo-1",
        opening: "Welcome, {name}. We'll start with the approved account guide. Have you worked from an account guide on another support queue?",
        answerPrompt: "Yes, but each account kept its own copy.",
        teaching: "Local copies drift. For escalation, BPO-SOP-001 v1.1 is the approved, current guide; v1.0 is superseded.",
        check: "A teammate pastes guidance from BPO-SOP-001 v1.0 into a case note. What do you do?",
        partial: "Use it, since it's from the same guide.",
        partialFeedback: "It is the same guide, but which version is approved and current?",
        correct: "Check the current version. v1.1 is approved and current, so I follow v1.1 and treat v1.0 as history.",
        correctFeedback: "Yes. You checked the version status before reusing the text.",
        hint: "Compare the two versions' status.",
      }),
      simpleSubtopic({
        id: "hb-st-2",
        excerpt: "bpo-2",
        opening: "Next: separating customer reports from verified facts. CASE-104's customer says they were overcharged. What do we actually know?",
        answerPrompt: "That the billing system charged them wrong.",
        teaching: "Not yet. The customer reported a disputed amount; nobody has verified a billing fault. Keep those separate in the case note.",
        check: "How would you summarise CASE-104 in a handover note?",
        partial: "Customer was overcharged; refund pending.",
        partialFeedback: "That states the fault as fact. How would you keep it accurate?",
        correct: "Customer reports a disputed amount. Verification is pending; no billing fault is confirmed.",
        correctFeedback: "Exactly. The report stays a report until it's verified.",
        hint: "Which parts are reported, and which are verified?",
      }),
      simpleSubtopic({
        id: "hb-st-3",
        excerpt: "bpo-3",
        opening: "Last subtopic: escalating without exposing private data. What would you include when escalating CASE-104?",
        answerPrompt: "The customer's full account history so they have everything.",
        teaching: "Share only what the reviewer needs: the case ID, the source version, what's missing, and the decision you need. Full account history isn't necessary.",
        check: "Write the escalation you'd send to Ravi for CASE-104.",
        partial: "Ravi, can you look at CASE-104?",
        partialFeedback: "Good start. Add the source you checked and the exact gap.",
        correct: "Ravi, for CASE-104 I checked BPO-SOP-001 v1.1. The customer reports a disputed amount; it isn't verified. Who can confirm the billing record? The case stays open until then.",
        correctFeedback: "Clear and minimal: case, source, gap and the response you need.",
        hint: "Include the case ID, the source version and the gap, but no extra account data.",
      }),
    ],
  },
  supervisor_ids: ["hb-ravi"],
  work_items: [
    { work_item_id: "hb-wi-104", external_id: "CASE-104", work_item_type: "TICKET", title: "Billing clarification", description: "Customer reports a disputed amount. Verification is pending; do not assert a confirmed billing fault.", priority: "HIGH", status: "IN_PROGRESS", due_label: "SLA in 2 h", assignee_id: "hb-leo", revision: 2 },
    { work_item_id: "hb-wi-105", external_id: "ACT-105", work_item_type: "ACTIVITY", title: "Account escalation refresher", description: "A team refresher is scheduled; the session time needs confirmation.", priority: "MEDIUM", status: "ACTIVE", due_label: "In 6 h", revision: 1 },
  ],
  work_events: [
    { work_event_id: "hb-ev-98", work_item_id: "hb-wi-104", employee_id: "hb-leo", event_type: "COMMENTED", description: "Partial progress was reported; missing evidence remains unknown.", evidence_type: "REPORTED", observed_label: "1 hour ago" },
  ],
  companion_scripts: [
    {
      employee_id: "hb-leo",
      opening:
        "Good afternoon, Leo. You're leading the Afternoon support queue. CASE-104 has a customer-reported billing dispute that isn't verified yet, and the escalation refresher (ACT-105) still needs a time. What would you like to focus on?",
      steps: [
        { prompt: { prompt_id: "hb-c-cases", label: "Focus on cases", text: "Show my queue's cases." }, reply: "Here are the open cases and activities for the queue.", excerpt_keys: [], ui_action: { type: "SHOW_WORK_ITEMS", filters: { status: ["ACTIVE", "IN_PROGRESS", "BLOCKED"] } } },
        { prompt: { prompt_id: "hb-c-104", label: "Show CASE-104", text: "Show CASE-104." }, reply: "CASE-104 is in progress. The disputed amount is customer-reported, not verified.", excerpt_keys: ["case-104"], ui_action: { type: "SHOW_WORK_ITEMS", resource_refs: ["hb-wi-104"] } },
        { prompt: { prompt_id: "hb-c-guide", label: "Ask how to escalate it", text: "How should I escalate CASE-104?" }, reply: "Here's what the approved guide says, with the gap marked.", excerpt_keys: ["bpo-3"], ui_action: { type: "SHOW_GUIDANCE", resource_refs: ["g-hb-escalate"] } },
        { prompt: { prompt_id: "hb-c-updates", label: "Show recent updates", text: "Show recent updates." }, reply: "Here are the permitted case updates.", excerpt_keys: [], ui_action: { type: "SHOW_WORK_UPDATES" } },
        { prompt: { prompt_id: "hb-c-focus", label: "Ask what to focus on", text: "What should I focus on?" }, reply: "Here's a focus plan from SLAs and open cases.", excerpt_keys: [], ui_action: { type: "SHOW_FOCUS_PLAN" } },
        { prompt: { prompt_id: "hb-c-delegate", label: "Recommend assignments", text: "Recommend assignments for the queue." }, reply: "Here's a proposal. Nothing is assigned until you confirm.", excerpt_keys: [], ui_action: { type: "SHOW_DELEGATION_PROPOSAL", resource_refs: ["hb-dp-94"] } },
        { prompt: { prompt_id: "hb-c-edit", label: "Give ACT-105 to Mia", text: "Give the refresher to Mia instead." }, reply: "Updated: ACT-105 → Mia. The original recommendation is kept. Confirm when you're ready.", excerpt_keys: [], ui_action: { type: "SHOW_DELEGATION_PROPOSAL", resource_refs: ["hb-dp-94"] }, effect: { kind: "EDIT_PROPOSAL", edits: [{ work_item_id: "hb-wi-105", final_employee_id: "hb-mia" }] } },
        { prompt: { prompt_id: "hb-c-ambiguous", label: "Ask about \"that account\"", text: "What happened with that account?" }, reply: "Which case do you mean? CASE-104 is the only open account case, but I'd rather confirm than guess.", excerpt_keys: [], ui_action: { type: "REQUEST_CLARIFICATION" } },
        { prompt: { prompt_id: "hb-c-brief", label: "Back to my briefing", text: "Back to my briefing." }, reply: "Here's your briefing again.", excerpt_keys: [], ui_action: { type: "SHOW_BRIEFING" } },
      ],
    },
    {
      employee_id: "hb-mia",
      opening: "Hi Mia. Leo is preparing queue assignments. You're also the proposed successor for priority-account escalation; that package isn't approved yet.",
      steps: [
        { prompt: { prompt_id: "hb-m-cases", label: "Show queue cases", text: "Show the queue's cases." }, reply: "Here are the open queue cases you can see.", excerpt_keys: [], ui_action: { type: "SHOW_WORK_ITEMS", filters: { status: ["ACTIVE", "IN_PROGRESS", "BLOCKED"] } } },
        { prompt: { prompt_id: "hb-m-report", label: "Report progress on CASE-104", text: "I want to report progress on CASE-104." }, reply: "Here's a draft case report. Review it before you submit.", excerpt_keys: ["bpo-2"], ui_action: { type: "NO_VIEW_CHANGE" }, effect: { kind: "OPEN_REPORT", work_item_id: "hb-wi-104", draft: "Requested the billing record for the disputed amount. Not verified yet." } },
        { prompt: { prompt_id: "hb-m-brief", label: "Back to my briefing", text: "Back to my briefing." }, reply: "Here's your briefing again.", excerpt_keys: [], ui_action: { type: "SHOW_BRIEFING" } },
      ],
    },
  ],
  guidance: [
    {
      guidance_id: "g-hb-escalate",
      question: "How should I escalate CASE-104?",
      answer: "BPO-SOP-001 v1.1 says to name the case and source version, state the missing evidence, and ask the authorized reviewer. It doesn't name which billing team owns disputed amounts.",
      answer_status: "ANSWERED",
      citations: [],
      unknowns: ["Which billing team verifies disputed amounts"],
      related_work_item_id: "hb-wi-104",
    },
  ],
  proposal: {
    delegation_proposal_id: "hb-dp-94",
    status: "PROPOSED",
    revision: 1,
    origin: "SYNTHETIC_SEED",
    items: [
      { proposal_item_id: "hb-dpi-95", work_item_id: "hb-wi-104", recommended_employee_id: "hb-mia", recommendation_reason: "Customer-privacy evidence; declared available.", evidence: ["Customer privacy: supervisor validation (synthetic)"] },
      { proposal_item_id: "hb-dpi-96", work_item_id: "hb-wi-105", recommended_employee_id: "hb-leo", recommendation_reason: "Account escalation and case documentation evidence; declared available.", evidence: ["Account escalation: supervisor validation (synthetic)", "Case documentation: supervisor validation (synthetic)"] },
    ],
  },
  priorities: {
    "hb-leo": ["CASE-104: SLA in 2 h, verification pending", "Confirm the ACT-105 refresher time", "Prepare the Afternoon → Evening queue handover"],
    "hb-mia": ["Wait for Leo's queue assignments"],
    "hb-nora": ["Start Account Support Fundamentals"],
    "hb-ravi": ["Review submitted knowledge", "Priority-account escalation package"],
  },
  handover: {
    template_name: "Support queue shift handover",
    template_version: "1",
    sections: [
      { section_id: "sec-summary", name: "Shift Summary", order_index: 1, is_required: true },
      { section_id: "sec-active", name: "Active / Ongoing Items", order_index: 2, is_required: true },
      { section_id: "sec-incidents", name: "Incidents / Issues", order_index: 3, is_required: false },
      { section_id: "sec-scheduled", name: "Scheduled Activities", order_index: 4, is_required: false },
      { section_id: "sec-blockers", name: "Blockers / Risks", order_index: 5, is_required: false },
      { section_id: "sec-notes", name: "Important Notes", order_index: 6, is_required: false },
    ],
    occurrences: [
      { shift_instance_id: "hb-si-morning", name: "Morning", window_label: "07:00–15:00 Asia/Manila", lead_employee_id: "hb-leo", member_ids: members, status: "COMPLETED" },
      { shift_instance_id: "hb-si-afternoon", name: "Afternoon", window_label: "15:00–23:00 Asia/Manila", lead_employee_id: "hb-leo", member_ids: members, status: "ACTIVE" },
      { shift_instance_id: "hb-si-evening", name: "Evening", window_label: "23:00–07:00 Asia/Manila", lead_employee_id: "hb-tessa", member_ids: ["hb-mia"], status: "SCHEDULED" },
      { shift_instance_id: "hb-si-next-morning", name: "Morning", window_label: "07:00–15:00 Asia/Manila", lead_employee_id: "hb-cora", member_ids: ["hb-nora"], status: "SCHEDULED" },
    ],
    source_shift_id: "hb-si-afternoon",
    target_shift_id: "hb-si-evening",
    items: [
      { handover_item_id: "hb-hi-111", display_id: "HI-111", work_item_id: "hb-wi-104", title: "Billing clarification (CASE-104)", description: "Customer reports a disputed amount. Verification is pending; do not assert a confirmed billing fault.", originating_shift_instance_id: "hb-si-morning", work_status: "IN_PROGRESS", acknowledgement_status: "NOT_REQUIRED", section_id: "sec-active", evidence_type: "REPORTED", source_label: "CASE-104 case events" },
      { handover_item_id: "hb-hi-114", display_id: "HI-114", work_item_id: "hb-wi-105", title: "Account escalation refresher (ACT-105)", description: "A team refresher is scheduled; the session time needs confirmation.", originating_shift_instance_id: "hb-si-morning", work_status: "ACTIVE", acknowledgement_status: "NOT_REQUIRED", section_id: "sec-scheduled", evidence_type: "REPORTED", source_label: "ACT-105" },
    ],
    draft_sections: [
      { section_id: "sec-summary", content: "CASE-104 billing dispute is still unverified." },
      { section_id: "sec-active", content: "CASE-104 carries over from the Morning queue." },
      { section_id: "sec-incidents", content: "" },
      { section_id: "sec-scheduled", content: "ACT-105 refresher; time to be confirmed." },
      { section_id: "sec-blockers", content: "" },
      { section_id: "sec-notes", content: "" },
    ],
    suggestions: [
      { suggestion_id: "hb-sg-117", suggestion_type: "STALE_INFORMATION", handover_item_id: "hb-hi-111", title: "Add Leo's partial progress report to HI-111", reason: "A case event from 1 hour ago isn't reflected in the draft.", before: "Customer reports a disputed amount. Verification is pending.", proposed: "Customer reports a disputed amount. Partial progress reported 1 hour ago; verification still pending.", source_label: "Case event · CASE-104 · reported", evidence_type: "REPORTED", status: "PENDING" },
      { suggestion_id: "hb-sg-120", suggestion_type: "MISSING_ITEM", title: "Upcoming team briefing", reason: "A synthetic email mentions a team activity in about 6 hours that isn't in the draft.", proposed: "Upcoming team briefing (time to be confirmed).", source_label: "Synthetic email fixture, not an integration", evidence_type: "REPORTED", status: "PENDING" },
    ],
    publications: [
      {
        publication_id: "hb-pub-109",
        publication_number: 1,
        source_shift_instance_id: "hb-si-morning",
        target_shift_instance_id: "hb-si-afternoon",
        template_version: "1",
        sections: [
          { section_id: "sec-summary", content: "Synthetic shift summary. Open cases require follow-up." },
          { section_id: "sec-active", content: "CASE-104: IN_PROGRESS." },
        ],
        entries: [
          { handover_item_id: "hb-hi-111", display_id: "HI-111", title: "Billing clarification (CASE-104)", section_id: "sec-active", snapshot_work_status: "IN_PROGRESS", snapshot_acknowledgement_status: "NOT_REQUIRED", snapshot_description: "Customer reports a disputed amount. Verification is pending." },
          { handover_item_id: "hb-hi-114", display_id: "HI-114", title: "Account escalation refresher (ACT-105)", section_id: "sec-scheduled", snapshot_work_status: "ACTIVE", snapshot_acknowledgement_status: "NOT_REQUIRED", snapshot_description: "Session time needs confirmation." },
        ],
        published_by: "hb-leo",
        published_label: "Today, end of Morning shift",
        receipts: [],
      },
    ],
    copilot_opening: "Since the Morning queue publication I've grouped two updates: a case event on CASE-104 and a synthetic email. Review each before it changes the draft.",
    copilot_steps: [
      { audience: "LEAD", prompt: { prompt_id: "hb-h-changed", label: "What changed since Morning?", text: "What changed since the Morning handover?" }, reply: "CASE-104 has a partial progress report; the dispute is still unverified. A synthetic email mentions a team briefing.", excerpt_keys: ["case-104"] },
      { audience: "INCOMING", prompt: { prompt_id: "hb-h-open", label: "What's still open for us?", text: "What's still open for us?" }, reply: "In the published snapshot, CASE-104 is in progress with verification pending, and the ACT-105 time isn't confirmed.", excerpt_keys: ["pub-1"] },
    ],
  },
  exit_kt: {
    case: {
      exit_kt_case_id: "hb-kt-124",
      employee_id: "hb-leo",
      case_kind: "ROLE_TRANSITION",
      status: "IN_PROGRESS",
      reviewer_employee_id: "hb-ravi",
      revision: 1,
      knowledge_items: [
        { kt_item_id: "hb-kti-125", title: "Customer account escalation", description: "Current approved SOP already exists.", documentation_status: "DOCUMENTED", kt_status: "EXISTING_KNOWLEDGE", risk_level: "MEDIUM", origin: "SYNTHETIC_SEED", linked_source: "BPO-SOP-001 v1.1" },
        { kt_item_id: "hb-kti-126", title: "Historical procedure references", description: "Historical version appears in older notes; compare against the current source.", documentation_status: "OUTDATED", kt_status: "NOT_STARTED", risk_level: "MEDIUM", origin: "SYNTHETIC_SEED" },
        { kt_item_id: "hb-kti-127", title: "Evidence-based escalation practice", description: "Leo's escalation practice isn't approved reusable knowledge yet.", documentation_status: "MISSING", kt_status: "DRAFT_CREATED", risk_level: "HIGH", origin: "SYNTHETIC_SEED", artifact_id: "hb-art-135" },
      ],
      findings: [
        { finding_id: "hb-ktf-129", kt_item_id: "hb-kti-126", finding_type: "OUTDATED_DOCUMENTATION", description: "Older account notes reference BPO-SOP-001 v1.0. Review them; this isn't proof that current guidance is wrong.", evidence: ["BPO-SOP-001 v1.0 (superseded)"], status: "OPEN", origin: "SYNTHETIC_SEED" },
        { finding_id: "hb-ktf-130", kt_item_id: "hb-kti-127", finding_type: "UNDOCUMENTED_KNOWLEDGE", description: "Leo's escalation practice needs employee review and knowledge approval.", evidence: ["Consented interview (private)"], status: "OPEN", origin: "SYNTHETIC_SEED" },
        { finding_id: "hb-ktf-131", finding_type: "MISSING_SUCCESSOR", description: "Recurring source-reference review has no proposed successor.", evidence: ["Responsibility record: recurring source-reference review"], status: "OPEN", origin: "SYNTHETIC_SEED" },
      ],
      interviews: [
        {
          interview_id: "hb-int-132",
          kt_item_id: "hb-kti-127",
          status: "PAUSED",
          consent_accepted: true,
          messages: [
            { message_id: "hb-im-133", sender_type: "AI", content: "Which current work item and approved source do you include when requesting missing evidence?", provenance: "SCRIPTED_FIXTURE" },
            { message_id: "hb-im-134", sender_type: "EMPLOYEE", content: "I include the work item and source version, keep the cause unknown, and ask the reviewer to verify the missing evidence.", provenance: "EMPLOYEE_INPUT" },
          ],
          script_prompts: [],
        },
      ],
      artifacts: [
        {
          artifact_id: "hb-art-135",
          kt_item_id: "hb-kti-127",
          artifact_type: "CHECKLIST",
          title: "Requesting evidence-based clarification",
          current_revision_id: "hb-artr-136",
          revisions: [{ artifact_revision_id: "hb-artr-136", version: 1, content: "1. Identify the current case.\n2. Cite the approved source version.\n3. State missing evidence and ask the reviewer.", status: "DRAFT", audience: "PRIVATE" }],
        },
      ],
      responsibilities: [
        { responsibility_id: "hb-resp-137", responsibility_type: "PROCESS", title: "Priority customer account escalation", owner_employee_id: "hb-leo", ownership_revision: 1 },
        { responsibility_id: "hb-resp-139", responsibility_type: "RECURRING_TASK", title: "Recurring source-reference review", owner_employee_id: "hb-leo", ownership_revision: 1 },
      ],
      transfers: [
        { transfer_id: "hb-rt-138", responsibility_id: "hb-resp-137", current_owner_employee_id: "hb-leo", recommended_owner_employee_id: "hb-mia", recommendation_reason: "Proposed successor from the seeded scenario. Package receipt and manager confirmation are still required.", status: "PROPOSED", effective_label: "Tomorrow 07:00 (future)", effective_reached: false, expected_owner_revision: 1, origin: "SYNTHETIC_SEED" },
        { transfer_id: "hb-rt-139", responsibility_id: "hb-resp-139", current_owner_employee_id: "hb-leo", status: "DISCOVERED", effective_label: "Not set", effective_reached: false, expected_owner_revision: 1, origin: "SYNTHETIC_SEED" },
      ],
      package: {
        package_id: "hb-pkg-140",
        successor_employee_id: "hb-mia",
        status: "DRAFT",
        revision: 1,
        draft_sections: [
          { title: "Responsibilities", content: "Priority customer account escalation" },
          { title: "Current guide", content: "BPO-SOP-001 v1.1 (approved, current)", evidence_type: "OBSERVED" },
          { title: "Open cases", content: "CASE-104: customer-reported disputed amount; verification pending.", evidence_type: "REPORTED" },
          { title: "Knowledge gaps", content: "Private checklist awaits employee review and knowledge approval.", evidence_type: "UNKNOWN" },
        ],
        versions: [],
        receipts: [],
      },
      checklist: [
        { checklist_item_id: "hb-ktc-142", label: "Evidence-based escalation practice documented and approved", required: true, status: "OPEN", evidence_refs: [] },
        { checklist_item_id: "hb-ktc-143", label: "Priority account escalation transferred or explicitly retained", required: true, status: "OPEN", evidence_refs: [] },
      ],
      open_work_note: "CASE-104 stays open until the disputed amount is verified. Completing KT doesn't close it.",
      successor_prompts: [],
      successor_qa: [],
    },
    interview_opening: "Which current work item and approved source do you include when requesting missing evidence?",
    interview_steps: [
      { prompt: { prompt_id: "hi-1", label: "Name who verifies", text: "Ravi or the billing reviewer verifies it. I note their answer on the case and keep the dispute marked unverified until then." }, ai_follow_up: "Thanks. What account details do you leave out of an escalation?" },
      { prompt: { prompt_id: "hi-2", label: "Describe what you leave out", text: "Anything the reviewer doesn't need: full history, contact details beyond the case owner, and payment data." }, ai_follow_up: "That covers the privacy boundary. You'll review any draft privately before anyone else sees it." },
    ],
    successor_steps: [
      { prompt: { prompt_id: "hb-s-open", label: "What's still open for me?", text: "What's still open for me?" }, reply: "In the approved package, CASE-104's disputed amount is customer-reported and still unverified.", excerpt_keys: ["case-104"] },
    ],
    draft_artifact_template: "",
  },
  timeline: [
    { entry_id: "hb-tl-1", label: "BPO-SOP-001 v1.1 approved and current", detail: "Customer account escalation. Semantic index pending.", kind: "DOCUMENT_VERSION", temporal: "CURRENT", evidence_type: "OBSERVED", document_version_id: BPO11 },
    { entry_id: "hb-tl-2", label: "BPO-SOP-001 v1.0 superseded", detail: "Historical synthetic reference.", kind: "DOCUMENT_VERSION", temporal: "HISTORICAL", evidence_type: "OBSERVED", document_version_id: BPO10 },
    { entry_id: "hb-tl-3", label: "CASE-104 opened", detail: "Customer-reported disputed amount; unverified.", kind: "WORK_HISTORY", temporal: "CURRENT", evidence_type: "REPORTED" },
  ],
};
