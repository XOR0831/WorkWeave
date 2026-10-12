-- Additive, idempotent alignment for the already-seeded Northstar demo workspace.
-- No existing document, approved version, work item, or user data is overwritten.
-- Apply after 02_seed.sql. Safe to rerun only when these exact fixture IDs/facts match.
BEGIN;
SET LOCAL search_path = workweave, public;

DO $guard$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM organizations WHERE organization_id = '00000001-0000-4000-8000-000000000001'
        AND name = 'Northstar Manufacturing'
    ) OR NOT EXISTS (
        SELECT 1 FROM workspaces WHERE organization_id = '00000001-0000-4000-8000-000000000001'
        AND workspace_id = '00000001-0000-4000-8000-000000000002' AND kind = 'DEMO'
    ) THEN
        RAISE EXCEPTION 'Northstar review fixture is missing or different; no alignment rows inserted';
    END IF;
    IF EXISTS (
        SELECT 1 FROM work_items
        WHERE organization_id = '00000001-0000-4000-8000-000000000001'
          AND workspace_id = '00000001-0000-4000-8000-000000000002'
          AND external_system = 'synthetic_seed' AND external_id = 'Ticket #492'
          AND work_item_id <> '00000001-0000-4000-8000-000000000915'
    ) THEN
        RAISE EXCEPTION 'Ticket #492 already exists with a different ID; inspect before proceeding';
    END IF;
END
$guard$;

INSERT INTO source_records
    (source_id, organization_id, workspace_id, source_type, owner_employee_id,
     evidence_type, access_partition, metadata)
VALUES
    ('00000001-0000-4000-8000-000000000914',
     '00000001-0000-4000-8000-000000000001',
     '00000001-0000-4000-8000-000000000002',
     'TICKET', '00000001-0000-4000-8000-000000000009', 'REPORTED', 'TEAM',
     '{"synthetic":true,"fixture":"northstar-alignment-v1","external_id":"Ticket #492","summary":"Closed prior Machine #14 vibration incident. Loose mounting assembly was recorded for that earlier incident only; current Ticket #829 cause remains unknown.","not_real_employee_evidence":true}'::jsonb)
ON CONFLICT (source_id) DO NOTHING;

INSERT INTO work_items
    (work_item_id, organization_id, workspace_id, external_system, external_id,
     work_item_type, title, description, priority, status, metadata)
VALUES
    ('00000001-0000-4000-8000-000000000915',
     '00000001-0000-4000-8000-000000000001',
     '00000001-0000-4000-8000-000000000002',
     'synthetic_seed', 'Ticket #492', 'INCIDENT', 'Historical Machine #14 vibration incident',
     'Closed prior incident: loose mounting assembly was recorded for that incident. This does not establish the cause of open Ticket #829.',
     'MEDIUM', 'CLOSED',
     '{"synthetic":true,"fixture":"northstar-alignment-v1","historical_only":true,"source_id":"00000001-0000-4000-8000-000000000914","not_real_employee_evidence":true}'::jsonb)
ON CONFLICT (work_item_id) DO NOTHING;

INSERT INTO work_events
    (work_event_id, organization_id, workspace_id, work_item_id, employee_id,
     event_type, description, event_data, evidence_refs, observed_at)
VALUES
    ('00000001-0000-4000-8000-000000000916',
     '00000001-0000-4000-8000-000000000001',
     '00000001-0000-4000-8000-000000000002',
     '00000001-0000-4000-8000-000000000915',
     '00000001-0000-4000-8000-000000000009',
     'COMPLETED',
     'Historical Ticket #492 was closed after a loose mounting assembly was recorded in that prior incident; Ticket #829 remains unverified.',
     '{"synthetic":true,"fixture":"northstar-alignment-v1","historical_only":true,"not_current_diagnosis":true}'::jsonb,
     '["00000001-0000-4000-8000-000000000914"]'::jsonb,
     (SELECT clock_anchor - interval '120 days' FROM workspaces
      WHERE workspace_id = '00000001-0000-4000-8000-000000000002'))
ON CONFLICT (work_event_id) DO NOTHING;

DO $verify$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM source_records
        WHERE source_id = '00000001-0000-4000-8000-000000000914'
          AND organization_id = '00000001-0000-4000-8000-000000000001'
          AND workspace_id = '00000001-0000-4000-8000-000000000002'
          AND source_type = 'TICKET' AND access_partition = 'TEAM'
          AND metadata->>'external_id' = 'Ticket #492'
    ) OR NOT EXISTS (
        SELECT 1 FROM work_items
        WHERE work_item_id = '00000001-0000-4000-8000-000000000915'
          AND organization_id = '00000001-0000-4000-8000-000000000001'
          AND workspace_id = '00000001-0000-4000-8000-000000000002'
          AND external_id = 'Ticket #492' AND status = 'CLOSED'
    ) OR NOT EXISTS (
        SELECT 1 FROM work_events
        WHERE work_event_id = '00000001-0000-4000-8000-000000000916'
          AND work_item_id = '00000001-0000-4000-8000-000000000915'
          AND event_data->>'not_current_diagnosis' = 'true'
    ) THEN
        RAISE EXCEPTION 'Northstar historical fixture differs from reviewed contract; transaction rolled back';
    END IF;
END
$verify$;
COMMIT;
