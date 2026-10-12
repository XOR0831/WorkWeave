-- Additive, idempotent review fixture: explicit, workspace-scoped permission to read curricula.
-- Approved 2026-10-03 (option 2). The read-only Curricula screens (GET /curricula,
-- GET /curricula/{id}) require a currently valid `curriculum:read` grant whose scope is the
-- whole workspace; `knowledge:review` no longer authorizes them.
--
-- Workspace scope is explicit, never inferred: resource_scope.scope = "WORKSPACE" and no
-- narrowing key (team_id, department_id, employee_id). A grant without the marker, or with a
-- narrowing key, does not authorize curriculum reads.
--
-- Granted to the personas the UI preview treats as onboarding coordinators (frontend fixtures:
-- curriculum.manage). Grantor and validity are copied from each persona's knowledge:review grant.
-- Changes no existing row. Afterwards run `activate <packs> --confirm-reviewed` (catalog CLI): the
-- pack's baseline identity hash includes permission grants. sync-catalog is only needed when a
-- pack's catalog.json (presentation/personas) changes, and is not required here.
BEGIN;

INSERT INTO workweave.permission_grants (organization_id, workspace_id, actor_id, resource_scope, action, valid_from, valid_until, granted_by)
SELECT g.organization_id, g.workspace_id, g.actor_id, '{"scope": "WORKSPACE", "synthetic": true}'::jsonb, 'curriculum:read', g.valid_from, g.valid_until, g.granted_by
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
      AND x.actor_id = g.actor_id AND x.action = 'curriculum:read'
  );

-- Guard: exactly the three intended coordinators hold it, each once.
DO $guard$
DECLARE n bigint;
BEGIN
    SELECT count(*) INTO n FROM workweave.permission_grants
    WHERE action = 'curriculum:read'
      AND actor_id IN ('00000001-0000-4000-8000-000000000011', '00000003-0000-4000-8000-000000000013', '00000002-0000-4000-8000-000000000011');
    IF n <> 3 THEN
        RAISE EXCEPTION '13_curriculum_read_grants: expected 3 coordinator curriculum:read grants, found %', n;
    END IF;
END
$guard$;

COMMIT;
