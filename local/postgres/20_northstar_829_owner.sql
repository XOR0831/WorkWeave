-- Additive, idempotent baseline fix (owner decision 2026-10-11): Ticket #829 stays with Alex Rivera.
-- The scenario contract (docs/28) has Alex open the Companion with #829 still in progress and keeps
-- permanent responsibility with him, but the baseline only held his earlier, cancelled assignment, so
-- automatic assignment (ADR-035) gave #829 to whoever fit best when the Companion opened. This adds
-- Alex's current assignment; automatic assignment only takes unassigned tickets, so it leaves #829 alone.
-- The cancelled row stays as history. Other packs are unchanged.
--
-- Changes no existing row. Afterwards run `activate northstar --confirm-reviewed` (the pack identity
-- hash includes this baseline data).
BEGIN;

INSERT INTO workweave.work_item_assignments (assignment_id, organization_id, workspace_id, work_item_id, employee_id, assigned_by_employee_id,
                                             assignment_source, status, assigned_at, created_at, updated_at)
SELECT '00000001-0000-4000-8000-000000000098', w.organization_id, w.workspace_id, '00000001-0000-4000-8000-000000000089',
       '00000001-0000-4000-8000-000000000009', '00000001-0000-4000-8000-000000000009', 'MANUAL', 'ASSIGNED',
       w.clock_anchor - interval '2 hours', w.clock_anchor, w.clock_anchor
  FROM workweave.workspaces w
 WHERE w.workspace_id = '00000001-0000-4000-8000-000000000002'
ON CONFLICT DO NOTHING;

DO $check$
BEGIN
    IF (SELECT count(*) FROM workweave.work_item_assignments a
          JOIN workweave.work_items i ON i.workspace_id = a.workspace_id AND i.work_item_id = a.work_item_id
         WHERE a.workspace_id = '00000001-0000-4000-8000-000000000002' AND i.external_id = 'Ticket #829'
           AND a.employee_id = '00000001-0000-4000-8000-000000000009' AND a.status = 'ASSIGNED') <> 1 THEN
        RAISE EXCEPTION 'Ticket #829 is not assigned to Alex Rivera; nothing was applied';
    END IF;
END
$check$;

COMMIT;
