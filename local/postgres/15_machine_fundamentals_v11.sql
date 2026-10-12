-- Machine Fundamentals 1.1: the Northstar learning path built from SOP-001 v3.4's ingested topics.
-- Approved 2026-10-04 (product owner): switch the demo's learning path to the v3.4 document-bound
-- topics as a NEW curriculum version; 1.0 stays frozen with its history; the four Reference aids are
-- on the path but optional. Synthetic test data, not validated for real machine operations.
--
-- Requires 14_sop001_v34_ingestion.sql (v3.4 sections and links) and the 1.0 seed.
--
-- What it does (additive except two status changes on 1.0, nothing deleted):
--   * curricula: Machine Fundamentals 1.1 (PUBLISHED, completion policy mvp-objective-evidence-1)
--   * curriculum_sources: 1.1 TEACHES SOP-001 v3.4
--   * curriculum_topics/subtopics: "Fundamentals" (3) and "Reference aids" (4), bound to v3.4, in SOP order
--   * curriculum_source_sections: each subtopic linked to its own v3.4 section (by section_key)
--   * learning_objectives: one per subtopic, drafted from the v3.4 section text (REVIEW DRAFT);
--     Fundamentals required, Reference aids optional (required = false)
--   * curriculum_prerequisites: each subtopic requires the one before it, in SOP order
--   * curriculum_assignments + learning_assignments: Sam and Jamie, assigned by Morgan Lee
--   * employee_learning_progress: Sam all NOT_STARTED; Jamie's 1.0 state carried over by subtopic
--     name (Find the current procedure COMPLETED, Separate history from evidence IN_PROGRESS).
--     Jamie's 1.0 evidence stays attached to 1.0; the carried-over completion is seeded scenario state.
--   * 1.0: status ARCHIVED; its curriculum and learning assignments CANCELLED (rows kept).
--
-- Idempotent: fixed IDs with ON CONFLICT DO NOTHING; the guards fail on missing or ambiguous input.
BEGIN;
SET CONSTRAINTS ALL DEFERRED;

DO $v11$
DECLARE
    o   constant uuid := '00000001-0000-4000-8000-000000000001';
    w   constant uuid := '00000001-0000-4000-8000-000000000002';
    v34 constant uuid := '00000001-0000-4000-8000-000000000951';
    sop constant uuid := '00000001-0000-4000-8000-000000000065';  -- SOP-001 document
    c10 constant uuid := '00000001-0000-4000-8000-000000000068';  -- Machine Fundamentals 1.0
    c11 constant uuid := '00000001-0000-4000-8000-000000001101';
    cs11 constant uuid := '00000001-0000-4000-8000-000000001102';
    t_fun constant uuid := '00000001-0000-4000-8000-000000001111';
    t_ref constant uuid := '00000001-0000-4000-8000-000000001112';
    morgan constant uuid := '00000001-0000-4000-8000-000000000011';
    sam constant uuid := '00000001-0000-4000-8000-000000000008';
    jamie constant uuid := '00000001-0000-4000-8000-000000000010';
    n bigint;
    s record;
    prev uuid := NULL;
    i int := 0;
BEGIN
    -- Preconditions -----------------------------------------------------------------------------
    SELECT count(*) INTO n FROM workweave.knowledge_document_versions v
      JOIN workweave.knowledge_documents d ON d.document_id = v.document_id
      JOIN workweave.source_records r ON r.source_id = v.source_id
     WHERE v.document_version_id = v34 AND v.workspace_id = w AND d.document_id = sop AND v.approval_status = 'APPROVED'
       AND v.temporal_status = 'CURRENT' AND d.current_version_id = v34 AND r.revoked_at IS NULL;
    IF n <> 1 THEN RAISE EXCEPTION '15_v11: SOP-001 v3.4 must be approved, current and unrevoked'; END IF;
    SELECT count(*) INTO n FROM workweave.knowledge_sections WHERE workspace_id = w AND document_version_id = v34;
    IF n <> 7 THEN RAISE EXCEPTION '15_v11: expected 7 v3.4 sections (run 14 first), found %', n; END IF;
    SELECT count(*) INTO n FROM workweave.curricula WHERE workspace_id = w AND curriculum_id = c10 AND name = 'Machine Fundamentals' AND version = '1.0';
    IF n <> 1 THEN RAISE EXCEPTION '15_v11: Machine Fundamentals 1.0 not found'; END IF;

    -- Curriculum 1.1 and its exact source ----------------------------------------------------------
    INSERT INTO workweave.curricula (curriculum_id, organization_id, workspace_id, name, description, version, status, published_at, completion_policy_version)
    VALUES (c11, o, w, 'Machine Fundamentals',
            'Built from SOP-001 v3.4 (synthetic test fixture): Fundamentals, plus optional Reference aids.',
            '1.1', 'PUBLISHED', now(), 'mvp-objective-evidence-1')
    ON CONFLICT (curriculum_id) DO NOTHING;
    INSERT INTO workweave.curriculum_sources (curriculum_source_id, organization_id, workspace_id, curriculum_id, document_id, document_version_id, relationship_type)
    VALUES (cs11, o, w, c11, sop, v34, 'TEACHES') ON CONFLICT (curriculum_source_id) DO NOTHING;
    INSERT INTO workweave.curriculum_topics (topic_id, organization_id, workspace_id, curriculum_id, name, description, order_index, active, document_version_id) VALUES
        (t_fun, o, w, c11, 'Fundamentals', 'SOP-001 v3.4 §1: find the current instruction, separate evidence from history, and ask clear questions.', 1, true, v34),
        (t_ref, o, w, c11, 'Reference aids', 'SOP-001 v3.4 §2: checklists and templates that support the fundamentals. Optional.', 2, true, v34)
    ON CONFLICT (topic_id) DO NOTHING;

    -- Subtopics, section links, objectives and prerequisites, in SOP order ----------------------------
    FOR s IN
        SELECT * FROM (VALUES
          (1, t_fun, 1, 'h2:1/h3:1', 'Find the current procedure', true,
           'Identify the approved, current controlled instruction for a work item before relying on it, and record its exact reference.',
           '{"synthetic": true, "source": "SOP-001 v3.4 section 1 (h2:1/h3:1)", "review_status": "DRAFT",
             "required_checks": ["verify_approved_current_version", "match_scope_to_question", "record_exact_source_reference", "escalate_missing_or_conflicting_source"],
             "check_descriptions": {
               "verify_approved_current_version": "Chooses the version the controlled registry marks approved and current, not a newer-looking file, search hit, bookmark or earlier attachment (1.2 step 3).",
               "match_scope_to_question": "Checks the document covers the question; does not take calibration parameters, repair steps or limits from an evidence-handling source (1.2 step 4).",
               "record_exact_source_reference": "Records document code, version and section alongside the work item and asset identifiers (1.2 step 5, 1.4).",
               "escalate_missing_or_conflicting_source": "Treats a missing or conflicting instruction as a document-control gap for the authorized owner; does not fall back to a superseded version or an AI-filled value (1.3)."}}'),
          (2, t_fun, 2, 'h2:1/h3:2', 'Separate history from evidence', true,
           'Label each claim in a work update as reported, verified, historical, unknown or proposed, and keep earlier cases from being presented as the current cause.',
           '{"synthetic": true, "source": "SOP-001 v3.4 section 2 (h2:1/h3:2)", "review_status": "DRAFT",
             "required_checks": ["label_claims_by_evidence_status", "keep_historical_cases_historical", "keep_unknowns_explicit", "preserve_work_item_boundaries"],
             "check_descriptions": {
               "label_claims_by_evidence_status": "Marks each statement as reported, verified, historical, unknown or proposed (2.1).",
               "keep_historical_cases_historical": "Uses a prior incident (e.g. Ticket #492) only as historical context, never as the diagnosis of the current item (e.g. Ticket #829) (2.3).",
               "keep_unknowns_explicit": "Leaves an unknown cause or observation time as unknown; does not backfill or infer it (2.2).",
               "preserve_work_item_boundaries": "Ties claims to the exact work item and asset; does not merge separate assets or tickets (2.2, 2.3)."}}'),
          (3, t_fun, 3, 'h2:1/h3:3', 'Ask a clearer question', true,
           'Write a clarification request that names the context, the current source consulted, the known evidence, the exact gap and the specific response needed from an authorized reviewer.',
           '{"synthetic": true, "source": "SOP-001 v3.4 section 3 (h2:1/h3:3)", "review_status": "DRAFT",
             "required_checks": ["state_context", "cite_current_source", "separate_known_evidence", "name_exact_gap", "request_specific_response"],
             "check_descriptions": {
               "state_context": "States the organization, asset, work item and relevant role or shift (3.2 part 1).",
               "cite_current_source": "Gives the approved document, version and section consulted, or says no applicable approved source was found (3.2 part 2).",
               "separate_known_evidence": "Keeps reported facts, verified facts and labelled historical context apart (3.2 part 3).",
               "name_exact_gap": "Names the specific missing instruction, contradiction, unverified observation or authority decision (3.2 part 4).",
               "request_specific_response": "Asks a named authorized reviewer for a specific decision or source, and keeps the status open meanwhile (3.2 part 5, 3.4)."}}'),
          (4, t_ref, 1, 'h2:2/h3:1', 'Source-selection checklist', false,
           'Apply the source-selection checklist before relying on a document.',
           '{"synthetic": true, "source": "SOP-001 v3.4 reference aid A (h2:2/h3:1)", "review_status": "DRAFT",
             "required_checks": ["open_controlled_record", "exclude_superseded_and_draft", "send_discrepancy_to_reviewer"],
             "check_descriptions": {
               "open_controlled_record": "Opens the controlled document record rather than relying on a copied excerpt or search snippet.",
               "exclude_superseded_and_draft": "Keeps superseded and draft versions out of current operational guidance.",
               "send_discrepancy_to_reviewer": "Sends any discrepancy or unavailable source to an authorized reviewer."}}'),
          (5, t_ref, 2, 'h2:2/h3:2', 'Work-evidence note template', false,
           'Complete a work-evidence note with exact identifiers, separate recorded and observation times, an evidence status and the remaining gap.',
           '{"synthetic": true, "source": "SOP-001 v3.4 reference aid B (h2:2/h3:2)", "review_status": "DRAFT",
             "required_checks": ["exact_identifiers", "separate_observation_time", "state_evidence_status", "state_remaining_gap"],
             "check_descriptions": {
               "exact_identifiers": "Uses exact work item and asset identifiers, not an approximate title.",
               "separate_observation_time": "Keeps the observation time separate from the recorded time, or says it is not known.",
               "state_evidence_status": "States whether the claim is reported, verified, historical, unknown or proposed.",
               "state_remaining_gap": "Says what is not yet established and who reviews next."}}'),
          (6, t_ref, 3, 'h2:2/h3:3', 'Training checks', false,
           'Reason through the training scenarios: search rank versus current status, a prior cause versus a current symptom, a value missing from the source, and a partial completion report.',
           '{"synthetic": true, "source": "SOP-001 v3.4 reference aid C (h2:2/h3:3)", "review_status": "DRAFT",
             "required_checks": ["current_status_over_rank", "prior_case_as_history", "no_invented_values", "partial_report_not_closure"],
             "check_descriptions": {
               "current_status_over_rank": "Retrieval rank does not override approved/current status; v3.4 is current.",
               "prior_case_as_history": "A prior documented cause is cited as history, not proof of today''s cause.",
               "no_invented_values": "A value absent from the approved source is reported as unavailable, not invented.",
               "partial_report_not_closure": "A partial completion report is preserved and reviewed; it does not close the ticket."}}'),
          (7, t_ref, 4, 'h2:2/h3:4', 'Version and publication boundary', false,
           'Explain why a content change needs a new approved version rather than an in-place edit, and why search eligibility follows approval and status.',
           '{"synthetic": true, "source": "SOP-001 v3.4 reference aid D (h2:2/h3:4)", "review_status": "DRAFT",
             "required_checks": ["new_version_for_changes", "eligibility_follows_approval_status"],
             "check_descriptions": {
               "new_version_for_changes": "A later content change requires a new version, not an edit of the approved one.",
               "eligibility_follows_approval_status": "Search eligibility follows approval, temporal status, permissions and index readiness."}}')
        ) AS x(seq, topic_id, order_index, section_key, name, required, objective, criteria)
    LOOP
        i := i + 1;
        INSERT INTO workweave.curriculum_subtopics (subtopic_id, organization_id, workspace_id, topic_id, name, order_index, active)
        VALUES (('00000001-0000-4000-8000-00000000112' || s.seq)::uuid, o, w, s.topic_id, s.name, s.order_index, true)
        ON CONFLICT (subtopic_id) DO NOTHING;

        SELECT count(*) INTO n FROM workweave.knowledge_sections WHERE workspace_id = w AND document_version_id = v34 AND section_key = s.section_key;
        IF n <> 1 THEN RAISE EXCEPTION '15_v11: expected 1 v3.4 section %, found %', s.section_key, n; END IF;
        INSERT INTO workweave.curriculum_source_sections (curriculum_source_section_id, organization_id, workspace_id, curriculum_source_id, curriculum_id,
                document_version_id, section_id, topic_id, subtopic_id, relationship_type)
        SELECT ('00000001-0000-4000-8000-00000000113' || s.seq)::uuid, o, w, cs11, c11, v34, ks.section_id, s.topic_id,
               ('00000001-0000-4000-8000-00000000112' || s.seq)::uuid, 'TEACHES'
        FROM workweave.knowledge_sections ks WHERE ks.workspace_id = w AND ks.document_version_id = v34 AND ks.section_key = s.section_key
        ON CONFLICT (curriculum_source_section_id) DO NOTHING;

        -- Competency: inherited from the 1.0 objective of the same-named learner subtopic, if any.
        INSERT INTO workweave.learning_objectives (objective_id, organization_id, workspace_id, subtopic_id, description, assessment_criteria, criteria_version, required, competency_id)
        VALUES (('00000001-0000-4000-8000-00000000114' || s.seq)::uuid, o, w, ('00000001-0000-4000-8000-00000000112' || s.seq)::uuid,
                s.objective, s.criteria::jsonb, 'sop001-v3.4-criteria-draft-1', s.required,
                (SELECT lo0.competency_id FROM workweave.learning_objectives lo0
                   JOIN workweave.curriculum_subtopics s0 ON s0.subtopic_id = lo0.subtopic_id
                   JOIN workweave.curriculum_topics t0 ON t0.topic_id = s0.topic_id
                  WHERE t0.curriculum_id = c10 AND t0.document_version_id IS NULL AND s0.name = s.name LIMIT 1))
        ON CONFLICT (objective_id) DO NOTHING;

        IF prev IS NOT NULL THEN
            INSERT INTO workweave.curriculum_prerequisites (prerequisite_id, organization_id, workspace_id, subtopic_id, prerequisite_subtopic_id)
            VALUES (('00000001-0000-4000-8000-00000000115' || s.seq)::uuid, o, w, ('00000001-0000-4000-8000-00000000112' || s.seq)::uuid, prev)
            ON CONFLICT (prerequisite_id) DO NOTHING;
        END IF;
        prev := ('00000001-0000-4000-8000-00000000112' || s.seq)::uuid;
    END LOOP;

    -- Assignments: Sam and Jamie move to 1.1; their 1.0 assignments are cancelled, not deleted --------
    INSERT INTO workweave.curriculum_assignments (assignment_id, organization_id, workspace_id, curriculum_id, employee_id, assigned_by_employee_id, status) VALUES
        ('00000001-0000-4000-8000-000000001161', o, w, c11, sam, morgan, 'ACTIVE'),
        ('00000001-0000-4000-8000-000000001162', o, w, c11, jamie, morgan, 'ACTIVE')
    ON CONFLICT (assignment_id) DO NOTHING;
    INSERT INTO workweave.learning_assignments (learning_assignment_id, organization_id, workspace_id, employee_id, curriculum_id, originating_assignment_id, assignment_kind, status) VALUES
        ('00000001-0000-4000-8000-000000001171', o, w, sam, c11, '00000001-0000-4000-8000-000000001161', 'INITIAL', 'ACTIVE'),
        ('00000001-0000-4000-8000-000000001172', o, w, jamie, c11, '00000001-0000-4000-8000-000000001162', 'INITIAL', 'ACTIVE')
    ON CONFLICT (learning_assignment_id) DO NOTHING;

    -- Progress: one row per assignment and subtopic. Jamie's 1.0 state carried over by subtopic name.
    INSERT INTO workweave.employee_learning_progress (progress_id, organization_id, workspace_id, employee_id, learning_assignment_id, subtopic_id, status, started_at, completed_at)
    SELECT ('00000001-0000-4000-8000-0000000011' || CASE WHEN a.who = 'sam' THEN '8' ELSE '9' END || st.seq)::uuid, o, w, a.employee_id, a.la, st.subtopic_id,
           COALESCE(old.status, 'NOT_STARTED'), old.started_at, old.completed_at
    FROM (VALUES ('sam', sam, '00000001-0000-4000-8000-000000001171'::uuid), ('jamie', jamie, '00000001-0000-4000-8000-000000001172'::uuid)) AS a(who, employee_id, la)
    CROSS JOIN (SELECT subtopic_id, name, right(subtopic_id::text, 1) AS seq FROM workweave.curriculum_subtopics
                WHERE workspace_id = w AND topic_id IN (t_fun, t_ref)) st
    LEFT JOIN LATERAL (
        SELECT p.status, p.started_at, p.completed_at FROM workweave.employee_learning_progress p
        JOIN workweave.curriculum_subtopics s0 ON s0.subtopic_id = p.subtopic_id
        JOIN workweave.curriculum_topics t0 ON t0.topic_id = s0.topic_id
        WHERE p.workspace_id = w AND p.employee_id = a.employee_id AND t0.curriculum_id = c10 AND t0.document_version_id IS NULL AND s0.name = st.name
    ) old ON true
    ON CONFLICT (progress_id) DO NOTHING;

    -- Retire 1.0 (status changes only; rows, progress and evidence are kept) -------------------------
    UPDATE workweave.learning_assignments SET status = 'CANCELLED' WHERE workspace_id = w AND curriculum_id = c10 AND status <> 'CANCELLED';
    UPDATE workweave.curriculum_assignments SET status = 'CANCELLED' WHERE workspace_id = w AND curriculum_id = c10 AND status <> 'CANCELLED';
    UPDATE workweave.curricula SET status = 'ARCHIVED' WHERE curriculum_id = c10 AND status <> 'ARCHIVED';

    -- Postconditions ---------------------------------------------------------------------------------
    SELECT count(*) INTO n FROM workweave.curriculum_subtopics WHERE topic_id IN (t_fun, t_ref) AND active;
    IF n <> 7 THEN RAISE EXCEPTION '15_v11: expected 7 subtopics, found %', n; END IF;
    SELECT count(*) INTO n FROM workweave.curriculum_source_sections WHERE curriculum_id = c11;
    IF n <> 7 THEN RAISE EXCEPTION '15_v11: expected 7 section links, found %', n; END IF;
    SELECT count(*) INTO n FROM workweave.learning_objectives lo JOIN workweave.curriculum_subtopics cs_sub ON cs_sub.subtopic_id = lo.subtopic_id WHERE cs_sub.topic_id IN (t_fun, t_ref);
    IF n <> 7 THEN RAISE EXCEPTION '15_v11: expected 7 objectives, found %', n; END IF;
    SELECT count(*) INTO n FROM workweave.employee_learning_progress WHERE learning_assignment_id IN ('00000001-0000-4000-8000-000000001171', '00000001-0000-4000-8000-000000001172');
    IF n <> 14 THEN RAISE EXCEPTION '15_v11: expected 14 progress rows, found %', n; END IF;
END
$v11$;

COMMIT;
