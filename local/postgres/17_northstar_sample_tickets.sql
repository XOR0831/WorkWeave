-- Northstar sample tickets for testing the AI Work Companion's guidance flow (ADR-033).
-- Local-only test data: NOT in app/ops/baseline.py SCRIPTS, so disposable test databases and
-- fresh cloud setups don't get it. Apply to the local dev database only, with approval.
--
-- One ticket per embedded SOP-001 v3.4 section (the only Northstar knowledge with chunks and
-- embeddings). Each ticket describes a situation that section answers, is ASSIGNED (the engine
-- loads ASSIGNED/ACCEPTED work only) and records the section it should retrieve in
-- metadata.expected_knowledge, so a test can compare the engine's choice with the intended one.
-- No ingestion, chunks or embeddings are touched.
--
-- Times are relative to the scenario's existing "now" (the newest non-historical ticket's
-- created_at), so the demo copy's time shift (work_anchors) is unchanged: original tickets keep
-- "due in ~2 h / ~6 h". Fresh demos copy these tickets with everything else.
--
-- Idempotent (fixed IDs, ON CONFLICT DO NOTHING); the guard at the end checks all six exist.
BEGIN;

DO $sample$
DECLARE
    o  constant uuid := '00000001-0000-4000-8000-000000000001';
    w  constant uuid := '00000001-0000-4000-8000-000000000002';
    alex constant uuid := '00000001-0000-4000-8000-000000000009';
    anchor timestamptz;
    t record;
BEGIN
    SELECT max(created_at) INTO anchor FROM workweave.work_items
     WHERE organization_id = o AND workspace_id = w AND coalesce(metadata->>'historical_only', 'false') <> 'true'
       AND work_item_id::text NOT LIKE '00000001-0000-4000-8000-0000000097%';
    IF anchor IS NULL THEN
        RAISE EXCEPTION 'Northstar baseline work items are missing; apply the baseline scripts first';
    END IF;

    FOR t IN
        SELECT * FROM (VALUES
            ('00000001-0000-4000-8000-000000009701'::uuid, '00000001-0000-4000-8000-000000009711'::uuid, '00000001-0000-4000-8000-000000009721'::uuid,
             'Ticket #934', 'Machine #31 calibration prep: confirm the applicable procedure',
             'Two printed copies of the calibration instructions were found at the Machine #31 station with different version numbers. Confirm which approved version applies before the scheduled calibration.',
             'HIGH', interval '3 hours', '00000001-0000-4000-8000-000000000010'::uuid, 'document_review',
             'Fundamentals', 'Find the current procedure'),
            ('00000001-0000-4000-8000-000000009702'::uuid, '00000001-0000-4000-8000-000000009712'::uuid, '00000001-0000-4000-8000-000000009722'::uuid,
             'Ticket #941', 'Machine #14 vibration: correct the shift summary',
             'The night-shift summary says today''s Machine #14 vibration is caused by the loose mounting found in Ticket #492. The cause for the open ticket is not verified. Correct the summary before handover.',
             'MEDIUM', interval '5 hours', '00000001-0000-4000-8000-000000000010'::uuid, 'evidence_reporting',
             'Fundamentals', 'Separate history from evidence'),
            ('00000001-0000-4000-8000-000000009703'::uuid, '00000001-0000-4000-8000-000000009713'::uuid, '00000001-0000-4000-8000-000000009723'::uuid,
             'Ticket #947', 'Machine #18 bracket: torque value not in the current SOP',
             'A requester asked for the Machine #18 bracket torque value. The current SOP does not state it. Ask the document owner for the applicable approved source instead of using a remembered value.',
             'MEDIUM', interval '6 hours', '00000001-0000-4000-8000-000000000008'::uuid, 'procedure_control',
             'Fundamentals', 'Ask a clearer question'),
            ('00000001-0000-4000-8000-000000009704'::uuid, '00000001-0000-4000-8000-000000009714'::uuid, '00000001-0000-4000-8000-000000009724'::uuid,
             'Ticket #952', 'Machine #7 calibration record: complete the source reference',
             'The Machine #7 calibration record cites only "SOP" with no document code, version or section. Complete the source reference before the record is filed.',
             'LOW', interval '8 hours', '00000001-0000-4000-8000-000000000008'::uuid, 'document_review',
             'Reference aids', 'Source-selection checklist'),
            ('00000001-0000-4000-8000-000000009705'::uuid, '00000001-0000-4000-8000-000000009715'::uuid, '00000001-0000-4000-8000-000000009725'::uuid,
             'Ticket #958', 'Machine #22 inspection findings: write the evidence note',
             'Inspection findings for Machine #22 were shared verbally at the shift meeting. Record them in the work record with the observation time, the source consulted and what is verified or only reported.',
             'MEDIUM', interval '4 hours', alex, 'evidence_reporting',
             'Reference aids', 'Work-evidence note template'),
            ('00000001-0000-4000-8000-000000009706'::uuid, '00000001-0000-4000-8000-000000009716'::uuid, '00000001-0000-4000-8000-000000009726'::uuid,
             'Ticket #963', 'Shared search link ranks SOP-001 v3.3 first',
             'A search link shared with the team shows SOP-001 v3.3 above v3.4 for calibration questions. Confirm which version is current and correct the shared link.',
             'LOW', interval '10 hours', '00000001-0000-4000-8000-000000009002'::uuid, 'document_review',
             'Reference aids', 'Training checks')
        ) AS v(work_item_id, assignment_id, requirement_id, external_id, title, description, priority, due_in, assignee, competency, topic, subtopic)
    LOOP
        INSERT INTO workweave.work_items (work_item_id, organization_id, workspace_id, external_system, external_id, work_item_type, title, description,
                                          priority, status, due_at, metadata, created_at, updated_at)
        VALUES (t.work_item_id, o, w, 'synthetic_seed', t.external_id, 'TICKET', t.title, t.description, t.priority, 'ACTIVE', anchor + t.due_in,
                jsonb_build_object('synthetic', true, 'fixture', 'northstar-sample-tickets-v1', 'not_real_employee_evidence', true,
                                   'expected_knowledge', jsonb_build_object('document_code', 'SOP-001', 'version', '3.4', 'topic', t.topic, 'subtopic', t.subtopic)),
                anchor, anchor)
        ON CONFLICT DO NOTHING;

        INSERT INTO workweave.work_item_competency_requirements (id, organization_id, workspace_id, work_item_id, competency_id, required_level, created_at, updated_at)
        SELECT t.requirement_id, o, w, t.work_item_id, c.competency_id, 1, anchor, anchor
          FROM workweave.competencies c WHERE c.organization_id = o AND c.workspace_id = w AND c.code = t.competency
        ON CONFLICT DO NOTHING;

        INSERT INTO workweave.work_item_assignments (assignment_id, organization_id, workspace_id, work_item_id, employee_id, assigned_by_employee_id,
                                                     assignment_source, status, assigned_at, created_at, updated_at)
        VALUES (t.assignment_id, o, w, t.work_item_id, t.assignee, alex, 'MANUAL', 'ASSIGNED', anchor - interval '30 minutes', anchor, anchor)
        ON CONFLICT DO NOTHING;
    END LOOP;

    IF (SELECT count(*) FROM workweave.work_items WHERE workspace_id = w AND metadata->>'fixture' = 'northstar-sample-tickets-v1') <> 6
       OR (SELECT count(*) FROM workweave.work_item_assignments WHERE workspace_id = w AND assignment_id::text LIKE '00000001-0000-4000-8000-0000000097%' AND status = 'ASSIGNED') <> 6
       OR (SELECT count(*) FROM workweave.work_item_competency_requirements WHERE workspace_id = w AND id::text LIKE '00000001-0000-4000-8000-0000000097%') <> 6 THEN
        RAISE EXCEPTION 'Northstar sample tickets incomplete; nothing was applied';
    END IF;
END
$sample$;

COMMIT;
