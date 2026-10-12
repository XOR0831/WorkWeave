-- Additive, idempotent review fixture: explicit permission to view team onboarding progress.
-- The UI preview already treats these personas as onboarding supervisors (frontend fixtures:
-- onboarding.supervise). Job roles/team labels never grant permissions by themselves
-- (src/CLAUDE.md), so the seed needs an explicit learning:supervise grant.
-- Scope and grantor are copied from each persona's existing knowledge:review grant.
-- Changes no existing row. Afterwards run `activate <packs> --confirm-reviewed` (catalog CLI):
-- the pack's baseline identity hash includes permission grants. sync-catalog is only needed when
-- a pack's catalog.json changes.
BEGIN;

INSERT INTO workweave.permission_grants (organization_id, workspace_id, actor_id, resource_scope, action, valid_from, valid_until, granted_by)
SELECT g.organization_id, g.workspace_id, g.actor_id, g.resource_scope, 'learning:supervise', g.valid_from, g.valid_until, g.granted_by
FROM workweave.permission_grants g
JOIN workweave.employees e ON e.organization_id = g.organization_id AND e.workspace_id = g.workspace_id AND e.employee_id = g.actor_id
WHERE g.action = 'knowledge:review'
  AND e.employee_id IN (
    '00000001-0000-4000-8000-000000000011', -- Northstar: Morgan Lee
    '00000003-0000-4000-8000-000000000013', -- Acme: Morgan Lee
    '00000002-0000-4000-8000-000000000011'  -- Harbor: Ravi Patel
  )
  AND NOT EXISTS (
    SELECT 1 FROM workweave.permission_grants x
    WHERE x.organization_id = g.organization_id AND x.workspace_id = g.workspace_id
      AND x.actor_id = g.actor_id AND x.action = 'learning:supervise'
  );

COMMIT;
