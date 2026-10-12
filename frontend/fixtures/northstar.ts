/**
 * Northstar Manufacturing — primary demo fixture (UI preview only).
 *
 * Facts follow docs/28-northstar-scenario-contract.md: SOP-001 v3.4 is current (local test
 * overlay), v3.3/v3.2 are superseded; Ticket #829 is open with cause UNKNOWN; Ticket #492 is
 * closed history; no coolant target, no Machine #12, no recorded audio, no pre-eligible
 * transfer time. Excerpts quote src/seed/sources/northstar/SOP-001-v3.4-TEST.md verbatim.
 */
import type { PackFixture } from "./types";

const SOP34 = "ns-dv-sop001-34";
const SOP33 = "ns-dv-sop001-33";
const SOP32 = "ns-dv-sop001-32";

const ex = (key: string, heading: string[], text: string, document_version_id = SOP34) => ({
  [key]: { source_id: `ns-src-${key}`, document_version_id, heading_path: heading, text, evidence_type: "OBSERVED" as const },
});

const excerpts = {
  ...ex(
    "sop-1.2",
    ["1. Find the current procedure", "1.2 Resolve the source in order"],
    "3. Confirm that the selected version is approved and current for the work context. A downloaded copy, old bookmark, prior shift attachment, or search hit may be historical even when its content looks useful.\n\nIn the Northstar test scenario after the v3.4 fixture is activated, SOP-001 v3.4 is approved/current; v3.3 and v3.2 remain approved but superseded history. The status of a version is determined by the controlled registry, not by which Markdown file happens to be newest on disk.",
  ),
  ...ex(
    "sop-1.3",
    ["1. Find the current procedure", "1.3 If the source is missing or conflicting"],
    "Treat a missing, inaccessible, expired, or contradictory instruction as a document-control gap. Record what was searched and the versions found. Ask the authorized document owner or supervisor to identify the applicable instruction. Do not decide that a superseded version is safe because it resembles the current task. Do not have an AI assistant fill in a missing numeric value or operational step.",
  ),
  ...ex(
    "sop-1.4",
    ["1. Find the current procedure", "1.4 Evidence of correct source selection"],
    "For example: “For Ticket #829 on Machine #14, SOP-001 v3.4 is the current document-control reference in this synthetic test workspace. It does not state a vibration cause or a coolant-pressure target. The applicable machine-operation instruction still needs confirmation.” This is a training example, not a new live observation or operating instruction.",
  ),
  ...ex(
    "sop-2.1",
    ["2. Separate history from evidence", "2.1 Use explicit evidence labels"],
    "Reported — someone described an observation or action; it has not necessarily been independently verified. Verified — an authorized person or system confirmed a specific fact, with a traceable source. Historical — the fact belongs to an earlier event or superseded document. Unknown — the available evidence does not establish the answer. Proposed — a next step, hypothesis, or AI suggestion awaits human review.\n\nThese labels describe the status of a specific claim, not the overall quality of an employee.",
  ),
  ...ex(
    "sop-2.2",
    ["2. Separate history from evidence", "2.2 Record the minimum useful work context"],
    "“Steps 1–4 were reported complete” does not mean that the complete inspection passed, that a cause was found, or that the ticket can be closed. A work event can inform a handover suggestion without automatically modifying the published handover or changing the official work status.",
  ),
  ...ex(
    "sop-2.3",
    ["2. Separate history from evidence", "2.3 Compare prior cases without copying conclusions"],
    "Historical incidents can suggest questions to ask, records to inspect, or expertise to seek. They do not prove a current cause. In the seeded training scenario, Ticket #492 is a closed prior Machine #14 vibration incident whose recorded cause was a loose mounting assembly. Ticket #829 is a separate open Machine #14 inspection with abnormal vibration reported and current cause unknown.",
  ),
  ...ex(
    "sop-2.4",
    ["2. Separate history from evidence", "2.4 Make uncertainty visible at handover and transfer"],
    "If an AI system proposes a missing handover item or a status correction based on a member report, the shift lead reviews its source and accepts or rejects the suggestion. The suggestion remains distinct from the official published handover until accepted and published.",
  ),
  ...ex(
    "sop-3.1",
    ["3. Ask a clearer question", "3.1 When clarification is needed"],
    "Ask for clarification when the approved source is missing, out of scope, ambiguous, inaccessible, or contradicted by another source; when an observation cannot support the proposed conclusion; when the actor lacks authority to approve or publish a change; or when a work item lacks the evidence needed for the next decision.",
  ),
  ...ex(
    "sop-3.2",
    ["3. Ask a clearer question", "3.2 Build the question from five parts"],
    "1. Context: state the organization, asset, work item, and relevant role or shift. 2. Current source: give the approved document code, version, and section consulted. 3. Known evidence: distinguish reported facts, verified facts, and historical context. 4. Exact gap: name the missing instruction, contradictory statement, unverified observation, or authority decision. 5. Requested response: ask a specific reviewer to identify the controlling source, validate a fact, approve a revision, or assign an owner.",
  ),
  ...ex(
    "sop-3.3",
    ["3. Ask a clearer question", "3.3 Worked training example"],
    "Weak question: “Is the vibration caused by the same thing as before?” It hides which ticket is current, which event is historical, and what evidence is missing.",
  ),
  ...ex(
    "sop-C3",
    ["2. Reference aids", "C. Training checks"],
    "3. A coworker asks for the coolant-pressure target, but the approved evidence-handling fixture contains no target. What should be said? Expected reasoning: the value is unavailable from this source; locate the applicable approved operational instruction or authorized reviewer. Do not invent a number.",
  ),
  ...ex(
    "v33-1",
    ["1. Fundamentals", "1. Find the current procedure"],
    "Use the current approved source, not a familiar historical version. This text is a synthetic training fixture.",
    SOP33,
  ),
  ...ex("v32", ["Historical synthetic reference"], "Superseded; not current instructions.", SOP32),
  "ticket-492": {
    source_id: "ns-src-492",
    document_version_id: "",
    heading_path: ["Work history", "Ticket #492 (closed)"],
    text: "Closed prior Machine #14 vibration incident. Loose mounting assembly was recorded for that earlier incident only; current Ticket #829 cause remains unknown.",
    evidence_type: "REPORTED" as const,
  },
  "pub-1": {
    source_id: "ns-src-pub-1",
    document_version_id: "",
    heading_path: ["Shift handover", "Publication #1 (Morning → Afternoon)"],
    text: "Ticket #829: IN_PROGRESS. Reported vibration; steps 1–4 recorded complete. Cause remains unverified. Ticket #910: IN_PROGRESS. Current document reference needs confirmation.",
    evidence_type: "REPORTED" as const,
  },
};

export const northstar: PackFixture = {
  card: {
    scenario_id: "northstar-machine14",
    key: "northstar",
    company_name: "Northstar Manufacturing",
    industry: "Manufacturing maintenance",
    story:
      "Sam learns to tell current procedure from history, Alex captures a missing reporting practice during a role transition, and Morgan approves the Machine #14 handover to Jamie.",
    pack_version: "review-only-v1",
    status: "READY",
    role_in_review: "Primary recorded demo",
    terminology: { workItem: "ticket", workItems: "tickets", team: "maintenance team", asset: "machine" },
  },
  personas: [
    {
      employee_id: "ns-sam",
      first_name: "Sam",
      last_name: "Kim",
      role_name: "Maintenance technician",
      team_name: "Maintenance",
      team_role: "MEMBER",
      employment_status: "ONBOARDING",
      scenario_note: "New learner assigned Machine Fundamentals",
      grants: ["onboarding.learn", "work.report", "handover.receive"],
    },
    {
      employee_id: "ns-alex",
      first_name: "Alex",
      last_name: "Rivera",
      role_name: "Maintenance technician",
      team_name: "Maintenance",
      team_role: "SHIFT_LEAD",
      employment_status: "ACTIVE",
      scenario_note: "Machine #14 owner, shift lead, role transition in progress",
      grants: ["work.report", "work.validate", "delegation.confirm", "handover.publish", "handover.receive", "exitkt.subject"],
    },
    {
      employee_id: "ns-jamie",
      first_name: "Jamie",
      last_name: "Chen",
      role_name: "Maintenance technician",
      team_name: "Maintenance",
      team_role: "MEMBER",
      employment_status: "ACTIVE",
      scenario_note: "Proposed Machine #14 successor; returning learner",
      grants: ["onboarding.learn", "work.report", "handover.receive", "exitkt.successor"],
    },
    {
      employee_id: "ns-morgan",
      first_name: "Morgan",
      last_name: "Lee",
      role_name: "Knowledge reviewer / manager",
      team_name: "Maintenance",
      team_role: "MANAGER",
      employment_status: "ACTIVE",
      scenario_note: "Reviews knowledge and KT packages; confirms ownership transfer",
      grants: ["onboarding.supervise", "curriculum.manage", "knowledge.review", "responsibility.confirm"],
    },
    { employee_id: "ns-priya", first_name: "Priya", last_name: "Nair", role_name: "Maintenance technician", team_name: "Maintenance", team_role: "SHIFT_LEAD", employment_status: "ACTIVE", scenario_note: "Lead for the next Morning shift, with Sam Kim", grants: ["work.report", "delegation.confirm", "handover.publish", "handover.receive"] },
    { employee_id: "ns-dana", first_name: "Dana", last_name: "Brooks", role_name: "Maintenance technician", team_name: "Maintenance", team_role: "SHIFT_LEAD", employment_status: "ACTIVE", scenario_note: "Evening shift lead after Alex Rivera, with Jamie Chen", grants: ["work.report", "delegation.confirm", "handover.publish", "handover.receive"] },
  ],
  documents: [
    {
      document_version_id: SOP34,
      document_id: "ns-doc-sop001",
      document_code: "SOP-001",
      title: "Calibration and evidence handling",
      version: "3.4",
      approval_status: "APPROVED",
      temporal_status: "CURRENT",
      approved_by: "Morgan Lee (synthetic fixture reviewer)",
      effective_label: "Current in this workspace (local test overlay)",
      document_type: "SOP",
      index_status: "PENDING",
    },
    {
      document_version_id: SOP33,
      document_id: "ns-doc-sop001",
      document_code: "SOP-001",
      title: "Calibration and evidence handling",
      version: "3.3",
      approval_status: "APPROVED",
      temporal_status: "SUPERSEDED",
      approved_by: "Morgan Lee (synthetic fixture reviewer)",
      effective_label: "Superseded by v3.4",
      document_type: "SOP",
    },
    {
      document_version_id: SOP32,
      document_id: "ns-doc-sop001",
      document_code: "SOP-001",
      title: "Historical synthetic reference",
      version: "3.2",
      approval_status: "APPROVED",
      temporal_status: "SUPERSEDED",
      approved_by: "Morgan Lee (synthetic fixture reviewer)",
      effective_label: "Superseded; not current instructions",
      document_type: "SOP",
    },
  ],
  excerpts,
  full_text: {
    [SOP34]: [
      "sop-1.2", "sop-1.3", "sop-1.4", "sop-2.1", "sop-2.2", "sop-2.3", "sop-2.4", "sop-3.1", "sop-3.2", "sop-3.3", "sop-C3",
    ].map((k) => `## ${excerpts[k as keyof typeof excerpts].heading_path.join(" › ")}\n\n${excerpts[k as keyof typeof excerpts].text}`).join("\n\n"),
    [SOP33]:
      "## 1. Find the current procedure\n\nUse the current approved source, not a familiar historical version. This text is a synthetic training fixture.\n\n## 2. Separate history from evidence\n\nKeep reported and verified facts separate. An earlier incident cannot prove a current cause. No operational action is authorized by this fixture.\n\n## 3. Ask a clearer question\n\nName the current work item and approved source version. State missing evidence and ask the authorized reviewer for clarification. Do not invent company procedures.",
    [SOP32]: "# Historical synthetic reference\n\nSuperseded; not current instructions.",
  },
  onboarding: {
    curriculum_name: "Machine Fundamentals",
    curriculum_version: "1.0",
    source_version_ids: [SOP34],
    topics: [
      {
        topic_id: "ns-topic-1",
        name: "Machine Fundamentals",
        order_index: 1,
        subtopics: [
          { subtopic_id: "ns-st-1", name: "Find the current procedure", order_index: 1, objective: "Identify and cite the approved, current procedure version.", status: "NOT_STARTED" },
          { subtopic_id: "ns-st-2", name: "Separate history from evidence", order_index: 2, objective: "Keep historical context separate from current, verified evidence.", status: "NOT_STARTED" },
          { subtopic_id: "ns-st-3", name: "Ask a clearer question", order_index: 3, objective: "Ask a reviewer a specific question that keeps unknowns explicit.", status: "NOT_STARTED" },
        ],
      },
    ],
    learners: [
      { employee_id: "ns-sam", learning_assignment_id: "ns-la-sam", completed: [] },
      { employee_id: "ns-jamie", learning_assignment_id: "ns-la-jamie", completed: ["ns-st-1"], in_progress: "ns-st-2" },
    ],
    new_learner_greeting: "Welcome, {name}.",
    curriculum_complete_text:
      "You've completed every required subtopic in Machine Fundamentals. Finishing onboarding doesn't authorize operating equipment; your supervisor confirms operational readiness separately.",
    scripts: [
      {
        subtopic_id: "ns-st-1",
        opening: [
          {
            kind: "OPENING",
            text: "Welcome, {name}. We'll start Machine Fundamentals with finding the current procedure. Have you used an approved procedure to investigate an issue before?",
            excerpt_keys: ["sop-1.2"],
          },
        ],
        resume: [
          {
            kind: "OPENING",
            text: "Welcome back, {name}. We were working on finding the current procedure. Want to pick up where we left off?",
            excerpt_keys: ["sop-1.2"],
          },
        ],
        steps: [
          {
            stage: 0,
            advances: true,
            prompt: { prompt_id: "ns-1-a", label: "Answer the opening question", text: "I have, but I'm not always sure which version is the current one." },
            responses: [
              {
                kind: "TEACHING",
                text: "That's the right thing to be unsure about. A copy that looks useful — a bookmark, an old attachment, a search hit — can still be history. Currentness comes from the controlled document registry: here, SOP-001 v3.4 is approved and current, and v3.3 and v3.2 are superseded.",
                excerpt_keys: ["sop-1.2"],
              },
            ],
          },
          {
            stage: 1,
            prompt: { prompt_id: "ns-1-ex", label: "Ask for an example", text: "Give me an example." },
            responses: [
              {
                kind: "EXAMPLE",
                text: "Training example from the SOP: a source-selection note for Ticket #829 names SOP-001 v3.4 as the current reference, says it doesn't state a vibration cause or coolant-pressure target, and says the machine-operation instruction still needs confirmation.",
                excerpt_keys: ["sop-1.4"],
              },
            ],
          },
          {
            stage: 1,
            prompt: { prompt_id: "ns-1-hist", label: "Ask about the older version", text: "Why did the older version say something different?" },
            responses: [
              {
                kind: "TEACHING",
                text: "v3.3 was approved before v3.4 replaced it, so it's labelled superseded history. Older text can explain why a practice changed, but it doesn't supply current guidance. This doesn't move your place in the curriculum.",
                excerpt_keys: ["v33-1", "sop-1.2"],
              },
            ],
          },
          {
            stage: 1,
            advances: true,
            prompt: { prompt_id: "ns-1-ready", label: "Ask to be checked", text: "I think I've got it. Can you check me?" },
            responses: [
              {
                kind: "CHECK",
                text: "A search returns SOP-001 v3.3 above v3.4 because its wording matches your query. Which version supplies current guidance for Ticket #829, and why?",
                excerpt_keys: ["sop-1.2"],
                check: { question_id: "ns-q-1", objective_id: "ns-obj-1" },
              },
            ],
          },
          {
            stage: 2,
            prompt: { prompt_id: "ns-1-hint", label: "Ask for a hint", text: "Can I have a hint?" },
            responses: [
              {
                kind: "HINT",
                text: "Look at what decides currentness in step 3: the registry's approval and effective status, not search ranking. A hint doesn't count as an answer — the question is still open.",
                excerpt_keys: ["sop-1.2"],
              },
            ],
          },
          {
            stage: 2,
            prompt: { prompt_id: "ns-1-partial", label: "Give a partial answer", text: "Probably v3.4, because it's the newest file." },
            responses: [
              {
                kind: "FEEDBACK",
                text: "v3.4 is right, but not because it's newest — the SOP says file age doesn't decide. What makes v3.4 the one to use?",
                excerpt_keys: ["sop-1.2"],
                assessment: { outcome: "PARTIAL", note: "Correct version, missing the registry-status reason." },
              },
            ],
          },
          {
            stage: 2,
            advances: true,
            completes_subtopic: true,
            prompt: {
              prompt_id: "ns-1-correct",
              label: "Give a complete answer",
              text: "v3.4. The controlled registry marks it approved and current. Search rank doesn't change that, and v3.3 is superseded history.",
            },
            responses: [
              {
                kind: "FEEDBACK",
                text: "Yes. You used the registry status, kept search rank out of it, and labelled v3.3 as history.",
                excerpt_keys: ["sop-1.2"],
                assessment: { outcome: "CORRECT", note: "Meets use_current_approved_evidence and keep_unknowns_explicit." },
              },
            ],
          },
        ],
      },
      {
        subtopic_id: "ns-st-2",
        opening: [
          {
            kind: "TEACHING",
            text: "Next: separating history from evidence. Ticket #492 and today's Ticket #829 both involve vibration on Machine #14. Before comparing them, what would you want to know about each one?",
            excerpt_keys: ["sop-2.3"],
          },
        ],
        resume: [
          {
            kind: "OPENING",
            text: "Welcome back, {name}. We were distinguishing historical incidents from current evidence, and we hadn't finished the scenario. Continue there, or review the explanation first?",
            excerpt_keys: ["sop-2.3"],
          },
        ],
        steps: [
          {
            stage: 0,
            advances: true,
            prompt: { prompt_id: "ns-2-a", label: "Answer the question", text: "Whether each one is open or closed, and what was actually verified." },
            responses: [
              {
                kind: "TEACHING",
                text: "Exactly the right questions. The SOP gives each claim a label: reported, verified, historical, unknown, or proposed. Ticket #492 is closed history. For #829, vibration is reported and the cause is unknown.",
                excerpt_keys: ["sop-2.1", "sop-2.3"],
              },
            ],
          },
          {
            stage: 1,
            prompt: { prompt_id: "ns-2-cross", label: "Ask about a later section", text: "What happens in the 'Ask a clearer question' section?" },
            responses: [
              {
                kind: "TEACHING",
                text: "That section builds a question from five parts: context, current source, known evidence, the exact gap, and the response you need. We'll cover it next. Your place stays on 'Separate history from evidence'.",
                excerpt_keys: ["sop-3.2"],
              },
            ],
          },
          {
            stage: 1,
            prompt: { prompt_id: "ns-2-cause", label: "Ask what caused the vibration", text: "So what caused today's vibration?" },
            responses: [
              {
                kind: "TEACHING",
                text: "The current cause of #829 isn't verified. #492's loose mounting assembly was recorded for that earlier incident only, so it can suggest what to inspect, but it can't be cited as today's diagnosis.",
                excerpt_keys: ["sop-2.3", "ticket-492"],
              },
            ],
          },
          {
            stage: 1,
            advances: true,
            prompt: { prompt_id: "ns-2-ready", label: "Ask to be checked", text: "Okay, check my understanding." },
            responses: [
              {
                kind: "CHECK",
                text: "Ticket #492 looks similar to today's Ticket #829. What can we conclude about today's cause?",
                excerpt_keys: ["sop-2.3"],
                check: { question_id: "ns-q-2", objective_id: "ns-obj-2" },
              },
            ],
          },
          {
            stage: 2,
            prompt: { prompt_id: "ns-2-claim", label: "Say you understand", text: "I get it." },
            responses: [
              {
                kind: "TEACHING",
                text: "Good to hear. To record progress, I still need your answer to the question above — saying you understand isn't evidence on its own.",
                excerpt_keys: [],
              },
            ],
          },
          {
            stage: 2,
            advances: true,
            completes_subtopic: true,
            prompt: {
              prompt_id: "ns-2-correct",
              label: "Give a complete answer",
              text: "It may be useful context, but today's cause still needs verification. #492's loose mounting assembly belongs to that earlier incident.",
            },
            responses: [
              {
                kind: "FEEDBACK",
                text: "Right. You kept #492 as historical context and left today's cause unknown until it's verified.",
                excerpt_keys: ["sop-2.3"],
                assessment: { outcome: "CORRECT", note: "Meets keep_unknowns_explicit; history not cited as current cause." },
              },
            ],
          },
        ],
      },
      {
        subtopic_id: "ns-st-3",
        opening: [
          {
            kind: "TEACHING",
            text: "Last subtopic: asking a clearer question. When the approved source doesn't answer something, how would you ask for help today?",
            excerpt_keys: ["sop-3.1"],
          },
        ],
        resume: [
          {
            kind: "OPENING",
            text: "Welcome back, {name}. We were working on asking a clearer question. Ready to continue?",
            excerpt_keys: ["sop-3.1"],
          },
        ],
        steps: [
          {
            stage: 0,
            advances: true,
            prompt: { prompt_id: "ns-3-a", label: "Answer the question", text: "I'd ask my lead if it's the same problem as before." },
            responses: [
              {
                kind: "TEACHING",
                text: "That's the SOP's own example of a weak question: it hides which ticket is current, which is history, and what's missing. A clearer question names the context, the current source, the known evidence, the exact gap, and the response you need.",
                excerpt_keys: ["sop-3.3", "sop-3.2"],
              },
            ],
          },
          {
            stage: 1,
            prompt: { prompt_id: "ns-3-coolant", label: "Ask about coolant pressure", text: "What coolant pressure should I use?" },
            responses: [
              {
                kind: "TEACHING",
                text: "SOP-001 v3.4 doesn't specify a coolant-pressure target, so I can't give you one. Find the applicable approved operating instruction or ask an authorized reviewer.",
                excerpt_keys: ["sop-C3"],
              },
            ],
          },
          {
            stage: 1,
            advances: true,
            prompt: { prompt_id: "ns-3-ready", label: "Offer to write one", text: "Let me try writing one." },
            responses: [
              {
                kind: "CHECK",
                text: "Write the question you would send to Morgan about Ticket #829.",
                excerpt_keys: ["sop-3.2"],
                check: { question_id: "ns-q-3", objective_id: "ns-obj-3" },
              },
            ],
          },
          {
            stage: 2,
            advances: true,
            completes_subtopic: true,
            prompt: {
              prompt_id: "ns-3-correct",
              label: "Give a complete answer",
              text: "For open Ticket #829 on Machine #14, I checked SOP-001 v3.4. Vibration was reported; today's cause isn't verified, and #492 is history only. Morgan, which inspection record can establish the current cause, and should #829 stay open meanwhile?",
            },
            responses: [
              {
                kind: "FEEDBACK",
                text: "That covers all five parts, and it keeps the cause marked unknown.",
                excerpt_keys: ["sop-3.2"],
                assessment: { outcome: "CORRECT", note: "All five question parts present; unknown kept explicit." },
              },
            ],
          },
        ],
      },
    ],
  },
  supervisor_ids: ["ns-morgan"],
  work_items: [
    {
      work_item_id: "ns-wi-829",
      external_id: "Ticket #829",
      work_item_type: "INCIDENT",
      title: "Machine #14 inspection",
      description: "Reported vibration; steps 1–4 recorded complete. Cause remains unverified.",
      priority: "HIGH",
      status: "IN_PROGRESS",
      due_label: "Due in 2 h",
      assignee_id: "ns-alex",
      revision: 3,
    },
    {
      work_item_id: "ns-wi-910",
      external_id: "Ticket #910",
      work_item_type: "TASK",
      title: "Machine #22 document check",
      description: "Current document reference needs confirmation.",
      priority: "MEDIUM",
      status: "IN_PROGRESS",
      due_label: "Due in 6 h",
      revision: 2,
    },
    {
      work_item_id: "ns-wi-492",
      external_id: "Ticket #492",
      work_item_type: "INCIDENT",
      title: "Historical Machine #14 vibration incident",
      description: "Closed after a loose mounting assembly was recorded in that prior incident. Not evidence about Ticket #829.",
      priority: "LOW",
      status: "CLOSED",
      due_label: "Closed",
      revision: 5,
      historical: true,
    },
  ],
  work_events: [
    {
      work_event_id: "ns-ev-98",
      work_item_id: "ns-wi-829",
      employee_id: "ns-alex",
      event_type: "COMMENTED",
      description: "Partial progress was reported; missing evidence and current cause remain unknown.",
      evidence_type: "REPORTED",
      observed_label: "1 hour ago",
    },
    {
      work_event_id: "ns-ev-492",
      work_item_id: "ns-wi-492",
      employee_id: "ns-alex",
      event_type: "COMPLETED",
      description: "Historical: loose mounting assembly recorded for this earlier incident only.",
      evidence_type: "REPORTED",
      observed_label: "Historical record",
    },
  ],
  companion_scripts: [
    {
      employee_id: "ns-alex",
      opening:
        "Good afternoon, Alex. You're leading the Afternoon maintenance shift. Two open tickets need follow-up: Ticket #829 (Machine #14 inspection, cause still unverified) and Ticket #910 (Machine #22 document check, not yet assigned). What would you like to focus on?",
      steps: [
        { prompt: { prompt_id: "nc-tickets", label: "Focus on tickets", text: "I want to focus on tickets." }, reply: "Here are the open tickets for your team.", excerpt_keys: [], ui_action: { type: "SHOW_WORK_ITEMS", filters: { status: ["ACTIVE", "IN_PROGRESS", "BLOCKED"] } } },
        { prompt: { prompt_id: "nc-blocked", label: "Only blocked tickets", text: "Only show the blocked ones." }, reply: "No tickets are blocked right now. I've kept the filter on so you can see that.", excerpt_keys: [], ui_action: { type: "SHOW_WORK_ITEMS", filters: { status: ["BLOCKED"] } } },
        { prompt: { prompt_id: "nc-829", label: "Show Ticket #829", text: "Show Ticket #829." }, reply: "Ticket #829 is open. Steps 1–4 are reported complete; the cause isn't verified.", excerpt_keys: [], ui_action: { type: "SHOW_WORK_ITEMS", resource_refs: ["ns-wi-829"] } },
        { prompt: { prompt_id: "nc-cause", label: "Ask what caused the vibration", text: "What caused today's vibration?" }, reply: "The cause of Ticket #829 isn't verified. Ticket #492 is historical context only. Details are on the left.", excerpt_keys: ["sop-2.3"], ui_action: { type: "SHOW_GUIDANCE", resource_refs: ["g-ns-cause"] } },
        { prompt: { prompt_id: "nc-current", label: "Ask which SOP is current", text: "Which SOP is current?" }, reply: "SOP-001 v3.4 is the approved, current version here.", excerpt_keys: ["sop-1.2"], ui_action: { type: "SHOW_GUIDANCE", resource_refs: ["g-ns-current"] } },
        { prompt: { prompt_id: "nc-coolant", label: "Ask for a coolant target", text: "What coolant pressure should I use?" }, reply: "The approved source doesn't give a coolant-pressure target, so I won't suggest one.", excerpt_keys: ["sop-C3"], ui_action: { type: "SHOW_GUIDANCE", resource_refs: ["g-ns-coolant"] } },
        { prompt: { prompt_id: "nc-updates", label: "Show recent updates", text: "Show recent updates." }, reply: "Here are the permitted work updates. Reports are labelled separately from validated changes.", excerpt_keys: [], ui_action: { type: "SHOW_WORK_UPDATES" } },
        { prompt: { prompt_id: "nc-focus", label: "Ask what to focus on", text: "What should I focus on?" }, reply: "Based on deadlines and open work, here's a focus plan.", excerpt_keys: [], ui_action: { type: "SHOW_FOCUS_PLAN" } },
        { prompt: { prompt_id: "nc-delegate", label: "Recommend assignments", text: "Recommend assignments for this shift." }, reply: "Here's a proposed set of assignments. Nothing is assigned until you confirm.", excerpt_keys: [], ui_action: { type: "SHOW_DELEGATION_PROPOSAL", resource_refs: ["ns-dp-94"] } },
        { prompt: { prompt_id: "nc-edit", label: "Give #910 to Jamie too", text: "Give Ticket #910 to Jamie as well." }, reply: "I've changed Ticket #910 to Jamie. The original recommendation is still shown. Confirm when you're ready, or keep editing.", excerpt_keys: [], ui_action: { type: "SHOW_DELEGATION_PROPOSAL", resource_refs: ["ns-dp-94"] }, effect: { kind: "EDIT_PROPOSAL", edits: [{ work_item_id: "ns-wi-910", final_employee_id: "ns-jamie" }] } },
        { prompt: { prompt_id: "nc-report", label: "Report progress on #829", text: "I want to report progress on Ticket #829." }, reply: "Here's a draft work report. Review it before you submit.", excerpt_keys: ["sop-2.2"], ui_action: { type: "NO_VIEW_CHANGE" }, effect: { kind: "OPEN_REPORT", work_item_id: "ns-wi-829", draft: "Abnormal vibration is still present after steps 1–4. Cause not verified. Further inspection is still required." } },
        { prompt: { prompt_id: "nc-ambiguous", label: "Ask about \"that one\"", text: "Open that one." }, reply: "Which ticket do you mean: Ticket #829 or Ticket #910? I've kept the current view.", excerpt_keys: [], ui_action: { type: "REQUEST_CLARIFICATION" } },
        { prompt: { prompt_id: "nc-invalid", label: "Preview: invalid ui_action", text: "(Preview) Return a ui_action outside the allowlist." }, reply: "", excerpt_keys: [], ui_action: { type: "NO_VIEW_CHANGE" }, effect: { kind: "INVALID_ACTION", attempted: "RENDER_GENERATED_HTML" } },
        { prompt: { prompt_id: "nc-brief", label: "Back to my briefing", text: "Back to my briefing." }, reply: "Here's your briefing again. The conversation is unchanged.", excerpt_keys: [], ui_action: { type: "SHOW_BRIEFING" } },
      ],
    },
    {
      employee_id: "ns-jamie",
      opening:
        "Hi Jamie. Alex is preparing this shift's assignments, so nothing is assigned to you yet. You also have one onboarding subtopic in progress. What would you like to do?",
      steps: [
        { prompt: { prompt_id: "nj-tickets", label: "Show team tickets", text: "Show the team's tickets." }, reply: "Here are the open team tickets you can see.", excerpt_keys: [], ui_action: { type: "SHOW_WORK_ITEMS", filters: { status: ["ACTIVE", "IN_PROGRESS", "BLOCKED"] } } },
        { prompt: { prompt_id: "nj-report", label: "Report progress on #829", text: "I want to report progress on Ticket #829." }, reply: "Here's a draft work report. Review it before you submit.", excerpt_keys: ["sop-2.2"], ui_action: { type: "NO_VIEW_CHANGE" }, effect: { kind: "OPEN_REPORT", work_item_id: "ns-wi-829", draft: "Reviewed steps 1–4 records. Vibration still reported; cause not verified." } },
        { prompt: { prompt_id: "nj-brief", label: "Back to my briefing", text: "Back to my briefing." }, reply: "Here's your briefing again.", excerpt_keys: [], ui_action: { type: "SHOW_BRIEFING" } },
      ],
    },
  ],
  guidance: [
    {
      guidance_id: "g-ns-cause",
      question: "What caused today's vibration?",
      answer:
        "Ticket #829's cause isn't verified. Abnormal vibration was reported and steps 1–4 are reported complete. Ticket #492 recorded a loose mounting assembly, but that was an earlier, closed incident and isn't evidence about today.",
      answer_status: "ANSWERED",
      citations: [],
      unknowns: ["Current cause of the Ticket #829 vibration"],
      related_work_item_id: "ns-wi-829",
    },
    {
      guidance_id: "g-ns-current",
      question: "Which SOP is current?",
      answer: "SOP-001 v3.4 is approved and current in this workspace. v3.3 and v3.2 are superseded history and shouldn't be used as current guidance.",
      answer_status: "ANSWERED",
      citations: [],
      unknowns: [],
    },
    {
      guidance_id: "g-ns-coolant",
      question: "What coolant pressure should I use?",
      answer:
        "The approved SOP-001 v3.4 doesn't specify a coolant-pressure target. Find the applicable approved operating instruction or ask an authorized reviewer.",
      answer_status: "INSUFFICIENT_EVIDENCE",
      citations: [],
      unknowns: ["Coolant-pressure target: no approved source in scope"],
    },
  ],
  proposal: {
    delegation_proposal_id: "ns-dp-94",
    status: "PROPOSED",
    revision: 1,
    origin: "SYNTHETIC_SEED",
    items: [
      {
        proposal_item_id: "ns-dpi-95",
        work_item_id: "ns-wi-829",
        recommended_employee_id: "ns-jamie",
        recommendation_reason: "Declared available this shift; validated document-review evidence.",
        evidence: ["Document review: supervisor validation (synthetic baseline)"],
        uncertainty: "No validated evidence for physical inspection work in this pack.",
      },
      {
        proposal_item_id: "ns-dpi-96",
        work_item_id: "ns-wi-910",
        recommended_employee_id: "ns-alex",
        recommendation_reason: "Validated procedure-control and evidence-reporting evidence; declared available.",
        evidence: ["Procedure control: supervisor validation (synthetic baseline)", "Evidence reporting: supervisor validation (synthetic baseline)"],
      },
    ],
  },
  priorities: {
    "ns-alex": ["Ticket #829: due in 2 h, cause unverified", "Ticket #910: due in 6 h, needs an owner", "Prepare the Afternoon → Evening handover"],
    "ns-jamie": ["Finish onboarding: Separate history from evidence", "Wait for Alex's shift assignments"],
    "ns-sam": ["Start Machine Fundamentals"],
    "ns-morgan": ["Review submitted knowledge", "Machine #14 role-transition package"],
  },
  handover: {
    template_name: "Maintenance shift handover",
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
      { shift_instance_id: "ns-si-morning", name: "Morning", window_label: "07:00–15:00 Asia/Manila", lead_employee_id: "ns-alex", member_ids: ["ns-sam", "ns-jamie"], status: "COMPLETED" },
      { shift_instance_id: "ns-si-afternoon", name: "Afternoon", window_label: "15:00–23:00 Asia/Manila", lead_employee_id: "ns-alex", member_ids: ["ns-sam", "ns-jamie"], status: "ACTIVE" },
      { shift_instance_id: "ns-si-evening", name: "Evening", window_label: "23:00–07:00 Asia/Manila", lead_employee_id: "ns-dana", member_ids: ["ns-jamie"], status: "SCHEDULED" },
      { shift_instance_id: "ns-si-next-morning", name: "Morning", window_label: "07:00–15:00 Asia/Manila", lead_employee_id: "ns-priya", member_ids: ["ns-sam"], status: "SCHEDULED" },
    ],
    source_shift_id: "ns-si-afternoon",
    target_shift_id: "ns-si-evening",
    items: [
      {
        handover_item_id: "ns-hi-111",
        display_id: "HI-111",
        work_item_id: "ns-wi-829",
        title: "Machine #14 inspection",
        description: "Reported vibration; steps 1–4 recorded complete. Cause remains unverified.",
        originating_shift_instance_id: "ns-si-morning",
        work_status: "IN_PROGRESS",
        acknowledgement_status: "NOT_REQUIRED",
        section_id: "sec-active",
        evidence_type: "REPORTED",
        source_label: "Ticket #829 work events",
      },
      {
        handover_item_id: "ns-hi-114",
        display_id: "HI-114",
        work_item_id: "ns-wi-910",
        title: "Machine #22 document check",
        description: "Current document reference needs confirmation.",
        originating_shift_instance_id: "ns-si-morning",
        work_status: "IN_PROGRESS",
        acknowledgement_status: "NOT_REQUIRED",
        section_id: "sec-active",
        evidence_type: "REPORTED",
        source_label: "Ticket #910",
      },
    ],
    draft_sections: [
      { section_id: "sec-summary", content: "Open work requires follow-up. Ticket #829 cause remains unverified." },
      { section_id: "sec-active", content: "Ticket #829 and Ticket #910 carry over from the Morning shift." },
      { section_id: "sec-incidents", content: "" },
      { section_id: "sec-scheduled", content: "" },
      { section_id: "sec-blockers", content: "" },
      { section_id: "sec-notes", content: "" },
    ],
    suggestions: [
      {
        suggestion_id: "ns-sg-117",
        suggestion_type: "STALE_INFORMATION",
        handover_item_id: "ns-hi-111",
        title: "Add Alex's partial progress report to HI-111",
        reason: "A work event from 1 hour ago isn't reflected in the draft. Review the report before adding it.",
        before: "Reported vibration; steps 1–4 recorded complete. Cause remains unverified.",
        proposed: "Reported vibration; steps 1–4 recorded complete. Partial progress reported 1 hour ago; missing evidence and current cause remain unknown.",
        source_label: "Work event · Ticket #829 · reported",
        evidence_type: "REPORTED",
        status: "PENDING",
      },
      {
        suggestion_id: "ns-sg-120",
        suggestion_type: "MISSING_ITEM",
        title: "Upcoming team briefing",
        reason: "A synthetic email mentions a team activity in about 6 hours that isn't in Scheduled Activities. The time still needs confirming.",
        proposed: "Upcoming team briefing (time to be confirmed).",
        source_label: "Synthetic email fixture, not an integration",
        evidence_type: "REPORTED",
        status: "PENDING",
      },
    ],
    publications: [
      {
        publication_id: "ns-pub-109",
        publication_number: 1,
        source_shift_instance_id: "ns-si-morning",
        target_shift_instance_id: "ns-si-afternoon",
        template_version: "1",
        sections: [
          { section_id: "sec-summary", content: "Synthetic shift summary. Open work requires follow-up." },
          { section_id: "sec-active", content: "Ticket #829: IN_PROGRESS. Ticket #910: IN_PROGRESS." },
        ],
        entries: [
          { handover_item_id: "ns-hi-111", display_id: "HI-111", title: "Machine #14 inspection", section_id: "sec-active", snapshot_work_status: "IN_PROGRESS", snapshot_acknowledgement_status: "NOT_REQUIRED", snapshot_description: "Reported vibration; steps 1–4 recorded complete. Cause remains unverified." },
          { handover_item_id: "ns-hi-114", display_id: "HI-114", title: "Machine #22 document check", section_id: "sec-active", snapshot_work_status: "IN_PROGRESS", snapshot_acknowledgement_status: "NOT_REQUIRED", snapshot_description: "Current document reference needs confirmation." },
        ],
        published_by: "ns-alex",
        published_label: "Today, end of Morning shift",
        receipts: [{ employee_id: "ns-jamie", received_label: "Start of Afternoon shift" }],
      },
    ],
    copilot_opening:
      "Since the Morning publication I've grouped two updates for review: one work report and one synthetic email activity. Neither changes the draft until you accept it.",
    copilot_steps: [
      { audience: "LEAD", prompt: { prompt_id: "nh-changed", label: "What changed since Morning?", text: "What changed since the Morning handover?" }, reply: "Ticket #829 has a new partial progress report; the cause is still unknown. A synthetic email mentions an upcoming team briefing. Both are waiting in the suggestions below.", excerpt_keys: ["sop-2.4"] },
      { audience: "LEAD", prompt: { prompt_id: "nh-missing", label: "Is anything required missing?", text: "Is anything required still missing?" }, reply: "Shift Summary and Active / Ongoing Items are required and both have content. The optional sections are empty; that won't block publishing.", excerpt_keys: [] },
      { audience: "INCOMING", prompt: { prompt_id: "nh-open", label: "What's still open for us?", text: "What's still open for us?" }, reply: "In the published snapshot, Ticket #829 and Ticket #910 are both in progress. #829's cause is unverified, so don't treat it as diagnosed.", excerpt_keys: ["pub-1"] },
    ],
  },
  exit_kt: {
    case: {
      exit_kt_case_id: "ns-kt-124",
      employee_id: "ns-alex",
      case_kind: "ROLE_TRANSITION",
      status: "IN_PROGRESS",
      reviewer_employee_id: "ns-morgan",
      revision: 1,
      knowledge_items: [
        { kt_item_id: "ns-kti-125", title: "Calibration and evidence handling", description: "Current approved SOP already exists.", documentation_status: "DOCUMENTED", kt_status: "EXISTING_KNOWLEDGE", risk_level: "MEDIUM", origin: "SYNTHETIC_SEED", linked_source: "SOP-001 v3.4" },
        { kt_item_id: "ns-kti-126", title: "Historical procedure references", description: "Historical version appears in older notes; compare against the current source.", documentation_status: "OUTDATED", kt_status: "NOT_STARTED", risk_level: "MEDIUM", origin: "SYNTHETIC_SEED" },
        { kt_item_id: "ns-kti-127", title: "Evidence-based escalation practice", description: "Alex's reporting practice isn't approved reusable knowledge yet.", documentation_status: "MISSING", kt_status: "DRAFT_CREATED", risk_level: "HIGH", origin: "SYNTHETIC_SEED", artifact_id: "ns-art-135" },
      ],
      findings: [
        { finding_id: "ns-ktf-129", kt_item_id: "ns-kti-126", finding_type: "OUTDATED_DOCUMENTATION", description: "Older notes still reference SOP-001 v3.3. Review them; this isn't proof that current instructions are wrong.", evidence: ["SOP-001 v3.3 (superseded)"], status: "OPEN", origin: "SYNTHETIC_SEED" },
        { finding_id: "ns-ktf-130", kt_item_id: "ns-kti-127", finding_type: "UNDOCUMENTED_KNOWLEDGE", description: "Alex's reporting practice needs employee review and knowledge approval.", evidence: ["Consented interview (private)"], status: "OPEN", origin: "SYNTHETIC_SEED" },
        { finding_id: "ns-ktf-131", kt_item_id: "ns-kti-127", finding_type: "MISSING_SUCCESSOR", description: "Recurring source-reference review has no proposed successor. A proposed successor is not a completed transfer.", evidence: ["Responsibility record: recurring source-reference review"], status: "OPEN", origin: "SYNTHETIC_SEED" },
      ],
      interviews: [
        {
          interview_id: "ns-int-132",
          kt_item_id: "ns-kti-127",
          status: "PAUSED",
          consent_accepted: true,
          messages: [
            { message_id: "ns-im-133", sender_type: "AI", content: "Which current work item and approved source do you include when requesting missing evidence?", provenance: "SCRIPTED_FIXTURE" },
            { message_id: "ns-im-134", sender_type: "EMPLOYEE", content: "I include the work item and source version, keep the cause unknown, and ask the reviewer to verify the missing evidence.", provenance: "EMPLOYEE_INPUT" },
          ],
          script_prompts: [],
        },
      ],
      artifacts: [
        {
          artifact_id: "ns-art-135",
          kt_item_id: "ns-kti-127",
          artifact_type: "CHECKLIST",
          title: "Requesting evidence-based clarification",
          current_revision_id: "ns-artr-136",
          revisions: [
            {
              artifact_revision_id: "ns-artr-136",
              version: 1,
              content: "1. Identify the current work item.\n2. Cite the approved source version.\n3. State missing evidence and ask the reviewer.",
              status: "DRAFT",
              audience: "PRIVATE",
            },
          ],
        },
      ],
      responsibilities: [
        { responsibility_id: "ns-resp-137", responsibility_type: "PROCESS", title: "Machine #14 maintenance responsibility", owner_employee_id: "ns-alex", ownership_revision: 1 },
        { responsibility_id: "ns-resp-139", responsibility_type: "RECURRING_TASK", title: "Recurring source-reference review", owner_employee_id: "ns-alex", ownership_revision: 1 },
      ],
      transfers: [
        { transfer_id: "ns-rt-138", responsibility_id: "ns-resp-137", current_owner_employee_id: "ns-alex", recommended_owner_employee_id: "ns-jamie", recommendation_reason: "Proposed successor from the seeded scenario. Package receipt and manager confirmation are still required.", status: "PROPOSED", effective_label: "Tomorrow 07:00 (future)", effective_reached: false, expected_owner_revision: 1, origin: "SYNTHETIC_SEED" },
        { transfer_id: "ns-rt-139", responsibility_id: "ns-resp-139", current_owner_employee_id: "ns-alex", status: "DISCOVERED", effective_label: "Not set", effective_reached: false, expected_owner_revision: 1, origin: "SYNTHETIC_SEED" },
      ],
      package: {
        package_id: "ns-pkg-140",
        successor_employee_id: "ns-jamie",
        status: "DRAFT",
        revision: 1,
        draft_sections: [
          { title: "Responsibilities", content: "Machine #14 maintenance responsibility" },
          { title: "Current procedure", content: "SOP-001 v3.4 (approved, current)", evidence_type: "OBSERVED" },
          { title: "Open work", content: "Ticket #829 is open. Steps 1–4 reported complete; cause unknown.", evidence_type: "REPORTED" },
          { title: "History", content: "Ticket #492 (closed): loose mounting assembly recorded for that incident only.", evidence_type: "REPORTED" },
          { title: "Knowledge gaps", content: "Private checklist awaits employee review and knowledge approval.", evidence_type: "UNKNOWN" },
        ],
        versions: [],
        receipts: [],
      },
      checklist: [
        { checklist_item_id: "ns-ktc-142", label: "Evidence-based escalation practice documented and approved", required: true, status: "OPEN", evidence_refs: [] },
        { checklist_item_id: "ns-ktc-143", label: "Machine #14 maintenance responsibility transferred or explicitly retained", required: true, status: "OPEN", evidence_refs: [] },
      ],
      open_work_note: "Ticket #829 stays open with cause unknown. Completing KT doesn't close it.",
      successor_prompts: [],
      successor_qa: [],
    },
    interview_opening: "Which current work item and approved source do you include when requesting missing evidence?",
    interview_steps: [
      { prompt: { prompt_id: "ni-1", label: "Name who verifies", text: "Morgan or the assigned reviewer verifies it. I record their response on the ticket and keep the cause marked unknown until then." }, ai_follow_up: "Thanks. Is there anything you check before asking, so the reviewer isn't asked to reconstruct the whole case?" },
      { prompt: { prompt_id: "ni-2", label: "Describe what you check", text: "I check the current SOP version and the latest work events, then list exactly what's missing." }, ai_follow_up: "That's enough for a checklist. You'll review any draft privately before anyone else sees it." },
    ],
    successor_steps: [
      { prompt: { prompt_id: "ns-s-open", label: "What's still open on Machine #14?", text: "What's still open on Machine #14?" }, reply: "In the approved package, Ticket #829 is open. Steps 1–4 are reported complete and the cause is unknown.", excerpt_keys: ["sop-2.3"] },
      { prompt: { prompt_id: "ns-s-492", label: "Did #492 cause today's issue?", text: "Did the #492 problem cause today's vibration?" }, reply: "No. #492's loose mounting assembly is historical context for that earlier incident only. Today's cause isn't verified.", excerpt_keys: ["ticket-492"] },
    ],
    draft_artifact_template: "",
  },
  timeline: [
    { entry_id: "ns-tl-1", label: "SOP-001 v3.4 approved and current", detail: "Calibration and evidence handling. Local test overlay; semantic index pending.", kind: "DOCUMENT_VERSION", temporal: "CURRENT", evidence_type: "OBSERVED", document_version_id: SOP34 },
    { entry_id: "ns-tl-2", label: "SOP-001 v3.3 superseded", detail: "Approved earlier; superseded by v3.4.", kind: "DOCUMENT_VERSION", temporal: "HISTORICAL", evidence_type: "OBSERVED", document_version_id: SOP33 },
    { entry_id: "ns-tl-3", label: "SOP-001 v3.2 superseded", detail: "Historical synthetic reference; not current instructions.", kind: "DOCUMENT_VERSION", temporal: "HISTORICAL", evidence_type: "OBSERVED", document_version_id: SOP32 },
    { entry_id: "ns-tl-4", label: "Ticket #492 closed", detail: "Loose mounting assembly recorded for that prior incident only.", kind: "WORK_HISTORY", temporal: "HISTORICAL", evidence_type: "REPORTED" },
    { entry_id: "ns-tl-5", label: "Ticket #829 open", detail: "Vibration reported; steps 1–4 reported complete; cause unknown.", kind: "WORK_HISTORY", temporal: "CURRENT", evidence_type: "REPORTED" },
  ],
};
