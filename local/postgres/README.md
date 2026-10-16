# PostgreSQL schema and synthetic scenario fixtures

The base schema and seed were applied to the local `workweave` database after explicit user approval. These files remain **review fixtures**, not Alembic migrations or a deployed application. Check the verification section for the additive Northstar alignment's application status. The SOP/curriculum schema migration below was applied locally on 2026-09-29.

## Files and application order

| File | Purpose | Writes data? |
| --- | --- | --- |
| [01_schema.sql](01_schema.sql) | 86 shared-domain tables, scoped foreign keys, indexes, revision/history guards and two administrative views | Creates schema objects |
| [02_seed.sql](02_seed.sql) | 480 base synthetic rows across three companies | Yes |
| [04_northstar_scenario_alignment.sql](04_northstar_scenario_alignment.sql) | Adds one historical Northstar ticket, its source and event; no existing rows overwritten | Yes; additive and repeatable |
| [05_northstar_full_sop_approved_test.sql](05_northstar_full_sop_approved_test.sql) | **Applied locally 2026-09-28:** inserts full synthetic approved SOP-001 v3.4, maps three subtopics, switches Northstar's current pointer from v3.3; leaves chunks for ingestion code | Yes; reviewed test overlay only |
| [07_sop_curriculum_links.sql](07_sop_curriculum_links.sql) | **Applied locally 2026-09-29:** adds three scoped, FK-connected SOP ingestion tables and a nullable source-section link on chunks; no fixture rows or embeddings | Schema only |
| [08_document_scoped_curriculum_topics.sql](08_document_scoped_curriculum_topics.sql) | **Applied locally 2026-09-30:** makes topic order local to a curriculum document source, adds deterministic source order and a source H2 key; preserves legacy topic IDs and their NULL source | Schema migration; backfills only existing source order |
| [09_direct_document_topic_link.sql](09_direct_document_topic_link.sql) | **Applied locally 2026-09-30:** replaces topic source UUID/H2 key with direct `document_version_id`; keeps source ordering and legacy topic IDs | Schema migration |
| [10_remove_curriculum_source_order.sql](10_remove_curriculum_source_order.sql) | **Applied locally 2026-09-30:** removes `curriculum_sources.order_index` and its two constraints; preserves source and topic rows | Schema migration; discards one stored source-order value locally |
| [11_onboarding_supervision_grants.sql](11_onboarding_supervision_grants.sql) | Additive, idempotent: `learning:supervise` for Morgan (Northstar), Morgan (Acme) and Ravi (Harbor), scope copied from their `knowledge:review` grants. **Applied locally 2026-10-03** (packs re-synced and re-activated afterwards); also applied to disposable test databases | Yes; additive |
| [14_sop001_v34_ingestion.sql](14_sop001_v34_ingestion.sql) | SOP-001 v3.4 ingestion output exported verbatim from local dev (read-only, 2026-10-04): 7 sections, 17 chunks with their `gemini-embedding-2` 768-dimension vectors, the 1.0 curriculum source link, 2 document-bound topics, 7 subtopics, 7 section links. Keeps dev IDs with `ON CONFLICT DO NOTHING`, so it is a no-op on dev; gives disposable test databases the same sample. Nothing regenerated. | Already present in dev (no-op) |
| [15_machine_fundamentals_v11.sql](15_machine_fundamentals_v11.sql) | Machine Fundamentals 1.1 from the v3.4 topics: Fundamentals (3 required) and Reference aids (4 optional), each linked to its own v3.4 section; objectives drafted from the SOP text (`sop001-v3.4-criteria-draft-1`, **review draft**); prerequisites in SOP order; Sam and Jamie reassigned (Jamie's 1.0 progress carried over by subtopic name). 1.0 archived, its assignments cancelled; nothing deleted. Guarded and idempotent. **Applied locally 2026-10-04** after a read-only preflight (1.1 PUBLISHED, 1.0 ARCHIVED; pack fingerprints unchanged, no re-activation) | Additive + status changes on 1.0 |
| [17_northstar_sample_tickets.sql](17_northstar_sample_tickets.sql) | **Baseline since 2026-10-13** (owner; applied to dev 2026-10-08). Six assigned Northstar sample tickets, one per embedded SOP-001 v3.4 section, for the AI Work Companion's guidance flow; each records its intended section in `metadata.expected_knowledge`. In the baseline script list, so fresh databases (cloud setup, tests) get it. |
| [16_distinct_shift_rosters.sql](16_distinct_shift_rosters.sql) | **Applied locally 2026-10-08** after a read-only roster preflight. Adds distinct Morning and Evening lead personas for all three companies. Preserves completed Morning and active Afternoon history; changes only the unstarted Evening roster to one new lead and one existing member, then creates the following Morning with one new lead and one existing member. All three catalogs were re-synced and re-activated, then verified READY with matching fingerprints; existing visitor runs end at their next request, so start fresh demos. Recovery of the removed scheduled memberships requires restoring a pre-application dev backup or reseeding a disposable database. | Yes; deletes only excess scheduled Evening memberships, retains all employees |
| [20_northstar_829_owner.sql](20_northstar_829_owner.sql) | Additive baseline fix (owner, 2026-10-11): Alex Rivera's current assignment on Ticket #829, so the scenario's open ticket stays his and automatic assignment (ADR-035) leaves it alone. In the baseline script list; run `activate northstar --confirm-reviewed` afterwards. | Yes; idempotent, additive |
| [21_acme_harbor_procedures.sql](21_acme_harbor_procedures.sql) | **Applied by Alembic 0020** (owner, 2026-10-16), not by the baseline list: Acme OPS-RB-007 and Harbor BPO-PRC-004 v1.0 (approved, current; Markdown in `seed/sources/`) with 12 sections and 23 chunks from the AI engineer's unchanged ingestion, run in the disposable `workweave_scratch_kb` database; vectors for the 6 existing chunks of OPS-SOP-001 v1.1 and BPO-SOP-001 v1.1 (same text, same model); a TEACHES link from each company's curriculum to both documents so visitor demos copy them. No topics, subtopics or objectives: learning paths unchanged. Fixed IDs, `ON CONFLICT DO NOTHING`. | Not yet in local `workweave` dev (0020 applies it on the next local migrate) |
| [22_acme_harbor_sop_v12.sql](22_acme_harbor_sop_v12.sql) | **Applied by Alembic 0021** (owner, 2026-10-16, option A): OPS-SOP-001 v1.2 (Acme) and BPO-SOP-001 v1.2 (Harbor), fuller approved versions (Markdown in `seed/sources/`), with 10 sections and 29 chunks from the AI engineer's unchanged ingestion in the disposable `workweave_scratch_kb` database. v1.1 becomes approved history; each curriculum TEACHES v1.2 instead of v1.1; its existing subtopics are linked to their v1.2 sections, as 12 did for Northstar. Subtopic names, objectives and progress unchanged; the ingestion's own topics are not exported. Fixed IDs, idempotent. | Not yet in local `workweave` dev (0021 applies it on the next local migrate) |
| [13_curriculum_read_grants.sql](13_curriculum_read_grants.sql) | Additive, idempotent: explicit workspace-scoped `curriculum:read` grants (`{"scope": "WORKSPACE"}`) for the pack coordinators (Northstar/Acme Morgan Lee, Harbor Ravi Patel), copied validity/grantor from their `knowledge:review` grant; guarded to exactly three. Needed by `GET /curricula`. Changes the packs' identity hash, so `activate <packs> --confirm-reviewed` must follow (`sync-catalog` isn't needed: catalog.json is unchanged). **Applied locally 2026-10-03** after a read-only preflight (3 grants added; northstar/acme/harbor re-activated, still READY); also used by disposable test databases | Yes; additive |
| [12_reconcile_sop001_v34_sections.sql](12_reconcile_sop001_v34_sections.sql) | Guarded, idempotent: adds three `curriculum_source_sections` links from SOP-001 v3.4 sections `h2:1/h3:1..3` to the existing "Machine Fundamentals" learner subtopics; never updates or deletes; fails on missing, ambiguous, unapproved, superseded, revoked or unembedded state. Needs the v3.4 ingestion output, which only the local dev database holds. **Applied locally 2026-10-03** (typed links 7 → 10; objectives/progress/prerequisites unchanged); also tested on disposable clones | Yes; additive |
| [10_curriculum_topic_review.sql](10_curriculum_topic_review.sql) | Read-only check for the current curriculum/document/topic layout | No |
| [09_direct_document_topic_review.sql](09_direct_document_topic_review.sql) | Historical review for the intermediate migration 09 schema; **do not run after 10** | No |
| [08_document_scoped_review.sql](08_document_scoped_review.sql) | Historical read-only check for the intermediate migration 08 schema; **do not run after 09** | No |
| [06_northstar_full_sop_review.sql](06_northstar_full_sop_review.sql) | Read-only check of source/version status, mappings, chunk/embedding counts and current projection | No |
| [03_review_queries.sql](03_review_queries.sql) | Inspect tenants, learning, sources, proposals, handovers and KT outcomes | No; transaction is read-only |
| [init/01-extensions.sql](init/01-extensions.sql) | Existing Compose bootstrap for pgvector | Already part of the local stack; no business tables |

The business scripts sit **outside `init/`**. Compose only mounts `postgres/init`,
so starting Docker will not automatically create business tables or ingest these fixtures.
No Compose mount was changed.

For a **new empty database**, apply `01_schema.sql`, `02_seed.sql`, `04_northstar_scenario_alignment.sql`, and the optional v3.4 overlay (`05`) if that scenario is desired. After reviewing it, apply `07_sop_curriculum_links.sql`, `08_document_scoped_curriculum_topics.sql`, `09_direct_document_topic_link.sql`, then `10_remove_curriculum_source_order.sql`; use `10_curriculum_topic_review.sql` for the current topic layout. `03_review_queries.sql` does not display document-local topic ordering. For the **already seeded local database**, do not rerun the one-shot base scripts. The optional v3.4 test overlay (`05`) was applied after user approval on 2026-09-28; do not apply it to other workspaces without the same explicit test intent. `07` was applied locally on 2026-09-29; `08`, `09`, and `10` were applied on 2026-09-30. Do not rerun them there. Read-only `06` inspects source/version status, mappings and chunks. The alignment script preserves all existing approved SOP content.

## Application migrations (Alembic)

New business-schema changes are Alembic migrations in [`../../backend/migrations`](../../backend/migrations), applied on top of these reviewed scripts with `uv run alembic upgrade head` (see the [backend README](../../backend/README.md)). Migration `0001` (applied locally 2026-10-03) is additive: `scenario_catalog.presentation`, `employees.baseline_employee_id`, and new `scenario_personas` and `demo_visitor_sessions` tables. The baseline's `demo_sessions` and `demo_persona_grants` are unused because their composite keys pin a session to the pack's baseline workspace rather than a visitor's isolated copy.

Migration `0002` (tested on disposable databases, then **applied locally 2026-10-03** after a passing read-only preflight) drops those two empty legacy tables (it aborts if either has rows), adds `UNIQUE (organization_id, workspace_id, kind)` on `workspaces`, and gives `demo_visitor_sessions` a `workspace_kind` column fixed to `DEMO` with a three-column FK to `workspaces`, so a demo session can't attach to an `OPERATIONAL` workspace. `01_schema.sql` stays the immutable historical baseline: a fresh database applies it (with the scripts above), then `0001`, then `0002`; `0002`'s downgrade recreates the legacy tables exactly as defined here.

## SOP ingestion relationship added by migration 07

`knowledge_document_versions` owns approved/draft source content. The importer parses each H2/H3 pair into `knowledge_sections`; H4 and deeper headings remain in chunk content. `knowledge_chunks.source_section_id` points to that exact same-version section. `curriculum_sources` connects an exact document version to an explicitly chosen or newly drafted curriculum. `curriculum_source_sections` connects a source section to a subtopic and enforces, through composite foreign keys, that the section belongs to the linked version, the topic belongs to the linked curriculum, and the subtopic belongs to that topic. One source may support multiple curricula, and one curriculum may use multiple sources.

These three tables are the typed onboarding path; existing polymorphic `knowledge_mappings` remain for historical fixtures and non-curriculum links. A new importer should write the typed links and should not infer curriculum identity from a heading alone. Legacy rows are **not** silently backfilled: SOP-001 v3.4's three existing `knowledge_mappings` do not yet create `knowledge_sections`/`curriculum_sources`/`curriculum_source_sections` rows. The AI engineer's importer must create those during ingestion. The old v3.3 chunks retain a NULL `source_section_id`; newly parsed H3 chunks should supply it. Existing approved chunks cannot be reassigned to a section in place after migration.

Immediately after schema migration 07, the three new tables contained **zero rows**; ingestion work since then may have added rows, so do not use that initial count as the current database state. The importer creates one `knowledge_sections` row per H3 (including reference-aid H3s), one `curriculum_sources` row per chosen curriculum/document version, and one `curriculum_source_sections` row per reviewed instructional section/subtopic link. New H3 chunks must reference the correct `section_id`; a database trigger checks that `section_path` equals the H2 heading and `heading` equals the H3 heading. Reference-aid chunks may have a source section without any curriculum mapping.

The review flow still needs application code: a draft upload must not become the current approved pointer or enter authorized retrieval before approval. A rejected candidate requires explicit cleanup of any draft child rows and stored file bytes; FK constraints intentionally do not cascade-delete them. Keep only the permitted minimal decision/notification receipt, not rejected SOP content. This schema migration alone does not implement admin notifications, approval commands, or cleanup.

## Direct document-version H2 topics (migrations 09–10, applied locally)

`curriculum_sources` is a curriculum/document-version link without an order column. `curriculum_topics.document_version_id` identifies the exact linked document version; `document_id` is available by joining to `knowledge_document_versions` or `curriculum_sources`. For document-bound topics, `curriculum_topics.order_index` is the H2 order **within that document version**. Its uniqueness is scoped to `(curriculum_id, document_version_id)`, so two documents in the same curriculum may each contain H2 positions 1 and 2. No explicit cross-document learning order is stored; a display may use source creation time plus source ID as a stable fallback, but that is not an approved curriculum sequence. Source H2 order in `knowledge_sections.topic_order_index` remains independent provenance. Supplemental sections from other documents can still map to a topic via `curriculum_source_sections`.

Existing fixture topics are intentionally left with `document_version_id = NULL`: they keep their IDs and curriculum-local order. The previously inserted unlinked `Reference aids` duplicate was deleted locally on 2026-09-30 after confirming it had no dependents; the SOP-001 v3.4-bound `Reference aids` topic remains. This migration does not guess whether the existing `Machine Fundamentals` topic should be owned by SOP-001 v3.4 or whether its H2 `Fundamentals` should become a separate learning topic. That is a coordinator mapping decision.

The importer must use the post-10 schema. Creating a `curriculum_sources` row requires only the curriculum and exact document version, not an `order_index`. Creating a new H2 topic must include `curriculum_id`, the same exact `document_version_id` as the linked source, and the H2's document-local `order_index`; neither `curriculum_source_id` nor `source_topic_key` belongs on `curriculum_topics`. The old `ON CONFLICT (organization_id, workspace_id, curriculum_id, order_index)` is no longer a valid target. Check for an existing topic by `(curriculum_id, document_version_id, order_index)` and compare its stored heading rather than silently accepting a mismatch. For a replacement approved document version, preserve historical mappings and use an explicit curriculum revision/review rather than silently repointing published topics.

## Architectural alignment

Sources: the project's data model, implementation contracts, scenario-pack contracts
and build specification (design notes kept outside this repository).

PostgreSQL is authoritative for organizations/employees, permissions, curriculum,
employee-specific progress, competency evidence, work, confirmed assignments,
handover publications/items, KT drafts/approvals/ownership, audit, consent and the
transactional outbox.

Firestore remains the planned authenticated realtime inbox and presentation
projection. It does not receive duplicate business tables here. No Firestore
documents, Firebase identities, credentials or live sessions are seeded.
AI checkpoint storage is separately owned; these scripts do not create a
LangGraph implementation, call Gemini, generate embeddings or simulate a
successful notification delivery.

All business rows except organization/workspace roots include
`organization_id` and `workspace_id`. Composite foreign keys prevent linked
records from silently crossing those boundaries. They are **not read-access
policies**: application authentication, audience checks, approved competency
sharing and permission enforcement still need implementation.

UUIDs identify internal records. Ticket codes such as INC-203 remain
`external_id` values. Timestamps use `TIMESTAMPTZ`; flexible metadata uses
`JSONB`. Versioned publications and evidence histories are protected against
updates/deletes. Mutable records carry a revision counter for future optimistic
concurrency checks.

## Synthetic companies and demo starting states

| Company | Scenario | Key employees |
| --- | --- | --- |
| Northstar Manufacturing | Current SOP-001 v3.3 vs superseded v3.2; Machine #14 open Ticket #829, historical closed Ticket #492, Machine #22 open Ticket #910; role-transition KT | Sam Kim, Alex Rivera, Jamie Chen, Morgan Lee |
| Harbor Support (BPO) | Account support and escalation; case documentation; role-transition KT | Nora Santos, Leo Cruz, Mia Reyes, Ravi Patel |
| Acme Infrastructure Operations | Payment/network/database operations; three shifts; departure KT | Alex Chen, John Tan, Maria Garcia, Sam Lim, Pat Reyes, Morgan Lee |

Each company has one isolated DEMO workspace, organizational structure,
explicit permission grants, availability, Morning/Afternoon/Evening shifts,
approved current and superseded SOP fixtures, a deterministic curriculum,
proposed delegation, published historical handover plus an unpublished next
draft, pending copilot suggestions, and incomplete KT work.

The Northstar scenario contract (a project design note) controls all demo claims. Standalone Markdown copies of seeded [SOP-001 v3.3](../../seed/sources/northstar/SOP-001-v3.3.md) and [historical v3.2](../../seed/sources/northstar/SOP-001-v3.2.md) are available. The [full v3.4 synthetic test document](../../seed/sources/northstar/SOP-001-v3.4-TEST.md) was inserted into the local database; v3.4 is now synthetic approved/current and v3.3 is superseded. There are **zero v3.4 chunks and embeddings** until the ingestion code creates them. None specifies a coolant-pressure target. Ticket #492's older loose-mounting record is context, not a diagnosis for #829. The local SQL fixture has no real audio recording, Machine #12 record or seven-incident history.

Specific review cases:

- New learners have NOT_STARTED progress. Northstar's Jamie has separate
  historical evidence: first subtopic COMPLETED, second IN_PROGRESS, third
  NOT_STARTED, plus an example request and paused session. Its thread identifier
  is a fixture marker, **not an actual checkpointer thread**.
- Delegation stays PROPOSED with no final assignee. The three manual assignments
  are historical and CANCELLED; no proposed assignment was executed.
- John reports INC-203 complete, but INC-203 remains officially IN_PROGRESS.
  A pending handover status suggestion requires the authorized lead's decision.
- Synthetic email suggestions demonstrate an upcoming activity. They are
  provider-adapter fixtures, not evidence of working Gmail/Outlook integrations.
- Historical handovers are published by the shift lead directly. There is no
  secondary reviewer requirement. The current draft remains unpublished.
- KT contains documented, outdated and undocumented knowledge; OPEN findings;
  a paused targeted interview; a DRAFT structured checklist; a PROPOSED successor
  transfer; and a second responsibility without a successor. No KT knowledge is
  promoted, no ownership is transferred and no exit case is marked complete.

Approved SOPs, baseline competencies, the historical publication and Jamie's
prior completion are **pre-existing synthetic history**, not outcomes generated
by running the app. Fixture metadata explicitly distinguishes these from real
employee evidence. SOP text is intentionally safe illustrative training content,
not a production-quality procedure for operating machinery, handling customer
accounts or deploying software.

## Time and fixture limitations

Dates are relative to the import transaction and each workspace's
`clock_anchor`, rather than a fixed hackathon date. DEMO workspaces expire
after seven days. Shift phases are a deliberate scenario preset (Morning
completed, Afternoon active, Evening scheduled), **not inferred live from the
current wall clock**.

Catalog entries remain DRAFT. `content_hash` is an explicit placeholder, not a
validated scenario-pack SHA-256 hash. No import run is falsely marked successful.
These hand-authored SQL fixtures are not a substitute for the planned scenario
generator, validation, preview, consent policy or ingestion service.

Embeddings are NULL. The schema permits pgvector storage but deliberately does
not choose a model/dimension or build an ANN index. The AI engineer must finalize
the embedding contract and retrieval evaluation before creating a matching
index. A simple lexical GIN index is provided. Approved/current source views
exclude revoked/expired sources and non-ready KT promotions, but do **not**
implement complete retrieval authorization.

## Decisions before building production services

1. Confirm the baseline's table/field contracts and the scope of the 86 tables.
   Several reliability and review tables start empty by design.
2. Confirm permissions and least-privilege application DB roles. No production
   RLS policy or GRANT statements are supplied; the Compose user is a local
   administrator, not a safe production application identity.
3. Implement human-authorized business commands, deterministic objective gates,
   context-revision checks and idempotency transactions. Presence of reviewer
   columns/CHECK constraints alone does not authenticate a reviewer. Services
   must enforce exact artifact revision approvals, lead membership, assignment
   confirmation, ownership timing and linked operational status consistency.
4. Implement outbox delivery, notification projection, consent revocation and
   retention workers. Empty delivery tables do not demonstrate those systems.
5. Finalize embedding dimensions/model and the dedicated AI checkpoint contract.
6. Convert the agreed baseline into versioned application migrations before production.
   The Northstar alignment is a narrow additive local fixture migration, not a general upgrade framework.

The base schema and seed are one-shot and transactional. Existing schema/duplicate
fixture keys cause failure instead of overwriting data. The Northstar alignment is
additive and idempotent only for its exact three fixture IDs. There is no DROP,
TRUNCATE, reset or automatic cleanup script. Apply in the order above to a fresh
database; on the existing local database, do not rerun the base files.

## Table inventory

Fixture row counts below total **483 rows**: 480 base inserts plus three Northstar alignment rows. Final pointer updates do not add rows.
A count of zero means a defined future runtime table, not a missing implementation
silently filled with fake outcomes.

### Shared organization, permissions and shifts

| Table | Primary key | Seed rows |
| --- | --- | ---: |
| `organizations` | `organization_id` | 3 |
| `workspaces` | `workspace_id` | 3 |
| `departments` | `department_id` | 3 |
| `teams` | `team_id` | 3 |
| `roles` | `role_id` | 6 |
| `employees` | `employee_id` | 14 |
| `employee_team_memberships` | `membership_id` | 14 |
| `auth_identity_links` | `identity_link_id` | 0 |
| `permission_grants` | `grant_id` | 59 |
| `shifts` | `shift_id` | 9 |
| `shift_instances` | `shift_instance_id` | 9 |
| `shift_instance_memberships` | `shift_membership_id` | 33 |
| `employee_availability` | `availability_id` | 14 |

### Consent, sources and knowledge

| Table | Primary key | Seed rows |
| --- | --- | ---: |
| `consent_sessions` | `consent_session_id` | 3 |
| `source_records` | `source_id` | 10 (9 base + 1 alignment) |
| `knowledge_documents` | `document_id` | 3 |
| `knowledge_document_versions` | `document_version_id` | 6 |
| `knowledge_chunks` | `chunk_id` | 9 |
| `knowledge_mappings` | `mapping_id` | 9 |
| `memory_drafts` | `draft_id` | 0 |
| `memory_records` | `memory_id` | 0 |

### Competency evidence

| Table | Primary key | Seed rows |
| --- | --- | ---: |
| `competencies` | `competency_id` | 11 |
| `role_competency_requirements` | `requirement_id` | 11 |
| `employee_competency_evidence` | `evidence_id` | 12 |
| `employee_competency_state` | `employee_competency_state_id` | 12 |

### Adaptive onboarding

| Table | Primary key | Seed rows |
| --- | --- | ---: |
| `curricula` | `curriculum_id` | 3 |
| `curriculum_assignments` | `assignment_id` | 4 |
| `learning_assignments` | `learning_assignment_id` | 4 |
| `curriculum_topics` | `topic_id` | 3 |
| `curriculum_subtopics` | `subtopic_id` | 9 |
| `curriculum_prerequisites` | `prerequisite_id` | 6 |
| `learning_objectives` | `objective_id` | 9 |
| `employee_learning_progress` | `progress_id` | 12 |
| `learning_sessions` | `learning_session_id` | 1 |
| `learning_turns` | `turn_id` | 1 |
| `employee_learning_events` | `learning_event_id` | 3 |
| `learning_assessment_attempts` | `attempt_id` | 1 |
| `objective_evidence` | `objective_evidence_id` | 1 |

### Work companion and delegation

| Table | Primary key | Seed rows |
| --- | --- | ---: |
| `work_sessions` | `work_session_id` | 3 |
| `work_items` | `work_item_id` | 8 (7 base + 1 alignment) |
| `work_item_competency_requirements` | `id` | 7 |
| `delegation_proposals` | `delegation_proposal_id` | 3 |
| `delegation_proposal_items` | `proposal_item_id` | 7 |
| `work_item_assignments` | `assignment_id` | 3 |
| `work_events` | `work_event_id` | 4 (3 base + 1 alignment) |
| `employee_work_state` | `employee_work_state_id` | 3 |
| `productivity_observations` | `observation_id` | 0 |

### Shift handover

| Table | Primary key | Seed rows |
| --- | --- | ---: |
| `handover_templates` | `template_id` | 3 |
| `handover_template_versions` | `template_version_id` | 3 |
| `handover_template_sections` | `section_id` | 18 |
| `shift_handovers` | `handover_id` | 6 |
| `handover_publications` | `publication_id` | 3 |
| `handover_items` | `handover_item_id` | 7 |
| `handover_entries` | `handover_entry_id` | 7 |
| `handover_suggestions` | `suggestion_id` | 6 |
| `handover_item_sources` | `source_id` | 13 |
| `handover_completion_cycles` | `completion_cycle_id` | 0 |
| `handover_item_events` | `event_id` | 0 |
| `handover_acknowledgements` | `acknowledgement_id` | 0 |
| `handover_receipts` | `receipt_id` | 0 |

### Exit knowledge transfer

| Table | Primary key | Seed rows |
| --- | --- | ---: |
| `exit_kt_cases` | `exit_kt_case_id` | 3 |
| `exit_kt_knowledge_items` | `kt_item_id` | 9 |
| `exit_kt_sources` | `source_id` | 3 |
| `exit_kt_findings` | `finding_id` | 9 |
| `exit_kt_interviews` | `interview_id` | 3 |
| `exit_kt_interview_messages` | `message_id` | 6 |
| `exit_kt_artifacts` | `artifact_id` | 3 |
| `exit_kt_artifact_revisions` | `artifact_revision_id` | 3 |
| `knowledge_approvals` | `approval_id` | 0 |
| `knowledge_promotions` | `promotion_id` | 0 |
| `responsibilities` | `responsibility_id` | 6 |
| `responsibility_transfers` | `transfer_id` | 3 |
| `exit_kt_packages` | `package_id` | 3 |
| `exit_kt_package_responsibilities` | `package_responsibility_id` | 3 |
| `exit_kt_package_versions` | `package_version_id` | 0 |
| `successor_receipts` | `receipt_id` | 0 |
| `kt_checklist_items` | `checklist_item_id` | 6 |

### Reliability, audit and scenario administration

| Table | Primary key | Seed rows |
| --- | --- | ---: |
| `command_receipts` | `command_receipt_id` | 0 |
| `audit_events` | `audit_event_id` | 3 |
| `outbox_events` | `event_id` | 0 |
| `delivery_attempts` | `delivery_attempt_id` | 0 |
| `operations` | `operation_id` | 0 |
| `scenario_catalog` | `scenario_id` | 3 |
| `import_runs` | `import_run_id` | 0 |
| `demo_sessions` | `demo_session_id` | 0 (baseline only; superseded by `demo_visitor_sessions`, removed by Alembic 0002) |
| `demo_persona_grants` | `demo_persona_grant_id` | 0 (baseline only; superseded by `scenario_personas` + scoped `permission_grants`, removed by Alembic 0002) |

## Verification evidence

Static validation on 2026-09-27 and local runtime verification on 2026-09-28:

- PostgreSQL syntax parser accepted schema, seed and review-query scripts.
- Schema has 86 tables and 269 foreign keys, including scope constraints.
- Offline checks found no missing declared required seed fields, invalid declared
  enum values, duplicate declared table unique keys or mismatched fixture FK
  references. FK targets have unconditional primary/unique keys.
- Review queries were checked against declared table/column names.
- The base schema and 480-row seed were applied to localhost after explicit user
  approval on 2026-09-27; review queries completed without error.
- The additive Northstar alignment was applied on 2026-09-28 in one transaction:
  one `source_records`, one closed historical `work_items` row and one `work_events`
  row. Read-only verification found one Ticket #492, one related event, 86 tables,
  483 total fixture rows, and the unchanged SOP-001 v3.2 `APPROVED/SUPERSEDED`
  and v3.3 `APPROVED/CURRENT`. A second application inserted zero rows;
  the updated read-only review queries completed successfully.
- The full synthetic Northstar SOP v3.4 insert was applied on 2026-09-28 in one
  transaction. Read-only verification found v3.4 `APPROVED/CURRENT`, v3.3
  `APPROVED/SUPERSEDED`, source checksum matching the Markdown, three subtopic
  mappings, and zero v3.4 chunks/embeddings. Chunk generation remains owned by
  the separate ingestion automation; current Northstar source excerpts will be
  absent until it populates v3.4 chunks.
- Document chunks remain unembedded. Application permissions, retrieval, AI,
  Firestore delivery, production migrations and deployed behavior are not tested
  by this local SQL verification.

The syntax parser was installed into a temporary tooling directory only; no
project dependency or lockfile was changed.
