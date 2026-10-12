-- Additive, idempotent review fixture: labelled synthetic work history for Exit KT discovery
-- (owner decision 2026-10-11, docs/32). Each pack's departing or transitioning employee gets closed
-- past tickets, their completed assignment and their own work updates, so "historical expertise",
-- recurring cases and knowledge-at-risk factors have real records to cite.
--
-- Every row is synthetic: metadata.synthetic = true, historical_only = true (never current work, never
-- in queues), not_real_employee_evidence = true. Dates are relative to the workspace clock_anchor.
-- Scenario contract limits hold (docs/28): no Machine #12, no coolant or pressure values, no
-- "seven incidents"; no record states or implies the cause of Ticket #829. SOP versions are named
-- only as the version in force at that time.
--
-- Changes no existing row. Afterwards run `activate <packs> --confirm-reviewed` (the pack identity
-- hash includes this baseline data).
BEGIN;

WITH history (ws, org, employee, item_suffix, external_id, kind, title, description, priority, days_ago, events) AS (
    VALUES
    -- Northstar Manufacturing: Alex Rivera (Machine #14 maintenance; recurring source-reference review)
    ('00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000009', 'a00000000001',
     'Ticket #431', 'WORK_ORDER', 'Machine #14 belt tension check', 'Scheduled belt tension check on Machine #14.', 'MEDIUM', 75,
     '[["INVESTIGATED", "Belt tension was outside the check range in SOP-001 v3.2, the version in force then. Adjusted and rechecked."], ["COMPLETED", "Rechecked after the adjustment and logged in the maintenance record."]]'),
    ('00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000009', 'a00000000002',
     'Ticket #458', 'INCIDENT', 'Machine #14 dust alarm', 'Dust alarm on Machine #14 during the Afternoon shift.', 'HIGH', 52,
     '[["INVESTIGATED", "The alarm cleared after cleaning the optical sensor. No part was replaced."], ["COMPLETED", "Sensor cleaning added as a note on the next scheduled check."]]'),
    ('00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000009', 'a00000000003',
     'Ticket #476', 'WORK_ORDER', 'Machine #14 lubrication overdue', 'Lubrication on Machine #14 was past its schedule.', 'MEDIUM', 30,
     '[["COMPLETED", "Lubrication done. Added a reminder to the shift checklist so it is not missed again."]]'),
    ('00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000009', 'a00000000004',
     'Ticket #487', 'TASK', 'Quarterly source-reference review: SOP-001 links', 'Check that work instructions point at the current SOP-001 version.', 'LOW', 21,
     '[["COMMENTED", "Updated the work instructions to point at SOP-001 v3.3 after its approval."], ["COMPLETED", "Review done; no other outdated links found."]]'),
    -- Acme Infrastructure: Pat Reyes (payment gateway operations; certificate renewal and vendor escalation)
    ('00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000012', 'a00000000001',
     'CHG-150', 'CHANGE', 'Payment gateway certificate renewal', 'Planned renewal of the payment gateway TLS certificate.', 'HIGH', 80,
     '[["COMMENTED", "Coordinated the renewal window with the vendor contact."], ["COMPLETED", "Certificate renewed; checked the gateway health page after the change."]]'),
    ('00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000012', 'a00000000002',
     'INC-171', 'INCIDENT', 'Payment gateway retry storm after deploy', 'Retries spiked after a gateway client deploy.', 'CRITICAL', 45,
     '[["INVESTIGATED", "Retries came from the new client setting in that deploy."], ["ESCALATED", "Escalated to the vendor to confirm their side was healthy."], ["COMPLETED", "Rolled back the client setting and added an alert on retry volume."]]'),
    ('00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000012', 'a00000000003',
     'ACT-090', 'ACTIVITY', 'Quarterly payment gateway failover drill', 'Planned failover drill for the payment gateway.', 'MEDIUM', 25,
     '[["COMPLETED", "Drill done. The runbook step for switching DNS needed a clearer order; noted for the next runbook revision."]]'),
    -- Harbor Support: Leo Cruz (priority customer account escalation)
    ('00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000009', 'a00000000001',
     'CASE-061', 'TICKET', 'Priority account: duplicate charge escalation', 'A priority customer reported a duplicate charge.', 'HIGH', 60,
     '[["ESCALATED", "Escalated to billing using the priority-account path."], ["COMPLETED", "Refund confirmed by billing; customer informed the same day."]]'),
    ('00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000009', 'a00000000002',
     'CASE-074', 'TICKET', 'Priority account: missed response target', 'A priority account case passed its response target.', 'HIGH', 38,
     '[["INVESTIGATED", "The case had been routed to the general queue instead of the priority queue."], ["COMPLETED", "Rerouted and answered; asked for the routing rule to be checked."]]'),
    ('00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000009', 'a00000000003',
     'CASE-088', 'TASK', 'Escalation contacts update after team change', 'Update the escalation contact list after a team change.', 'MEDIUM', 18,
     '[["COMMENTED", "Updated the contact list; the escalation guide still names the previous billing contact."], ["COMPLETED", "List updated; guide update left for review."]]')
),
rows AS (
    SELECT h.*, (substr(h.ws, 1, 24) || h.item_suffix)::uuid AS work_item_id, w.clock_anchor
    FROM history h JOIN workweave.workspaces w ON w.workspace_id = h.ws::uuid
),
items AS (
    INSERT INTO workweave.work_items (work_item_id, organization_id, workspace_id, external_system, external_id, work_item_type, title, description, priority, status, metadata,
                                      created_at, updated_at)
    SELECT work_item_id, org::uuid, ws::uuid, 'synthetic_seed', external_id, kind, title, description, priority, 'CLOSED',
           jsonb_build_object('fixture', 'exit-kt-history-v1', 'synthetic', true, 'historical_only', true, 'not_real_employee_evidence', true),
           clock_anchor - make_interval(days => days_ago), clock_anchor - make_interval(days => days_ago - 1)
    FROM rows
    ON CONFLICT DO NOTHING
    RETURNING work_item_id
),
assignments AS (
    INSERT INTO workweave.work_item_assignments (organization_id, workspace_id, work_item_id, employee_id, assignment_source, status, assigned_at, completed_at, created_at, updated_at)
    SELECT r.org::uuid, r.ws::uuid, r.work_item_id, r.employee::uuid, 'EXTERNAL_SYSTEM', 'COMPLETED',
           r.clock_anchor - make_interval(days => r.days_ago), r.clock_anchor - make_interval(days => r.days_ago - 1),
           r.clock_anchor - make_interval(days => r.days_ago), r.clock_anchor - make_interval(days => r.days_ago - 1)
    FROM rows r JOIN items i ON i.work_item_id = r.work_item_id
    RETURNING work_item_id
)
INSERT INTO workweave.work_events (organization_id, workspace_id, work_item_id, employee_id, event_type, description, event_data, observed_at, created_at)
SELECT r.org::uuid, r.ws::uuid, r.work_item_id, r.employee::uuid, ev.value->>0, ev.value->>1,
       jsonb_build_object('fixture', 'exit-kt-history-v1', 'synthetic', true, 'not_real_employee_evidence', true),
       r.clock_anchor - make_interval(days => r.days_ago) + make_interval(hours => ev.ordinality::int),
       r.clock_anchor - make_interval(days => r.days_ago) + make_interval(hours => ev.ordinality::int)
FROM rows r JOIN items i ON i.work_item_id = r.work_item_id
CROSS JOIN LATERAL jsonb_array_elements(r.events::jsonb) WITH ORDINALITY AS ev(value, ordinality);

COMMIT;
