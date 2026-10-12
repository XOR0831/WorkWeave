-- Additive, idempotent review fixture: permission to author curricula (owner decision 2026-10-10,
-- ADR-040). The manager (Northstar/Acme: Morgan Lee; Harbor: Ravi Patel) creates curricula, uploads
-- Markdown sources and approves them; there is no separate learning team in these packs, so the
-- manager may approve their own upload after confirming they reviewed that exact version (audited).
--
-- Workspace scope is explicit, like curriculum:read (13_curriculum_read_grants.sql). Grantor and
-- validity are copied from each persona's curriculum:read grant. Changes no existing row.
-- Afterwards run `activate <packs> --confirm-reviewed`: the pack identity hash includes grants.
BEGIN;

INSERT INTO workweave.permission_grants (organization_id, workspace_id, actor_id, resource_scope, action, valid_from, valid_until, granted_by)
SELECT g.organization_id, g.workspace_id, g.actor_id, g.resource_scope, 'curriculum:manage', g.valid_from, g.valid_until, g.granted_by
FROM workweave.permission_grants g
WHERE g.action = 'curriculum:read'
  AND g.actor_id IN (
    '00000001-0000-4000-8000-000000000011', -- Northstar: Morgan Lee
    '00000003-0000-4000-8000-000000000013', -- Acme: Morgan Lee
    '00000002-0000-4000-8000-000000000011'  -- Harbor: Ravi Patel
  )
  AND NOT EXISTS (
    SELECT 1 FROM workweave.permission_grants x
    WHERE x.organization_id = g.organization_id AND x.workspace_id = g.workspace_id
      AND x.actor_id = g.actor_id AND x.action = 'curriculum:manage'
  );

COMMIT;
