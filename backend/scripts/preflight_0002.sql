-- Read-only preflight for Alembic 0002. Changes nothing: the transaction is READ ONLY.
-- Every row must show ok = true before applying 0002.
BEGIN TRANSACTION READ ONLY;

SELECT check_name, detail, ok FROM (
  SELECT 1 AS n, 'alembic at 0001' AS check_name,
         (SELECT string_agg(version_num, ',') FROM workweave.alembic_version) AS detail,
         (SELECT bool_and(version_num = '0001') FROM workweave.alembic_version) AS ok
  UNION ALL
  SELECT 2, 'demo_persona_grants is empty',
         (SELECT count(*)::text FROM workweave.demo_persona_grants) || ' row(s)',
         NOT EXISTS (SELECT 1 FROM workweave.demo_persona_grants)
  UNION ALL
  SELECT 3, 'demo_sessions is empty',
         (SELECT count(*)::text FROM workweave.demo_sessions) || ' row(s)',
         NOT EXISTS (SELECT 1 FROM workweave.demo_sessions)
  UNION ALL
  SELECT 4, 'every visitor session is on a DEMO workspace',
         (SELECT count(*)::text FROM workweave.demo_visitor_sessions s
            JOIN workweave.workspaces w ON w.organization_id = s.organization_id AND w.workspace_id = s.workspace_id
           WHERE w.kind <> 'DEMO') || ' on non-DEMO',
         NOT EXISTS (SELECT 1 FROM workweave.demo_visitor_sessions s
            JOIN workweave.workspaces w ON w.organization_id = s.organization_id AND w.workspace_id = s.workspace_id
           WHERE w.kind <> 'DEMO')
  UNION ALL
  SELECT 5, 'no other table references the legacy tables',
         COALESCE((SELECT string_agg(conrelid::regclass || '.' || conname, ', ') FROM pg_constraint
                    WHERE contype = 'f'
                      AND confrelid IN ('workweave.demo_sessions'::regclass, 'workweave.demo_persona_grants'::regclass)
                      AND conrelid NOT IN ('workweave.demo_sessions'::regclass, 'workweave.demo_persona_grants'::regclass)), 'none'),
         NOT EXISTS (SELECT 1 FROM pg_constraint
                      WHERE contype = 'f'
                        AND confrelid IN ('workweave.demo_sessions'::regclass, 'workweave.demo_persona_grants'::regclass)
                        AND conrelid NOT IN ('workweave.demo_sessions'::regclass, 'workweave.demo_persona_grants'::regclass))
  UNION ALL
  SELECT 6, 'no views/rules depend on the legacy tables',
         COALESCE((SELECT string_agg(DISTINCT v.oid::regclass::text, ', ') FROM pg_depend d
                     JOIN pg_rewrite r ON r.oid = d.objid JOIN pg_class v ON v.oid = r.ev_class
                    WHERE d.refobjid IN ('workweave.demo_sessions'::regclass, 'workweave.demo_persona_grants'::regclass)
                      AND v.oid NOT IN ('workweave.demo_sessions'::regclass, 'workweave.demo_persona_grants'::regclass)), 'none'),
         NOT EXISTS (SELECT 1 FROM pg_depend d JOIN pg_rewrite r ON r.oid = d.objid
                      WHERE d.refobjid IN ('workweave.demo_sessions'::regclass, 'workweave.demo_persona_grants'::regclass)
                        AND r.ev_class NOT IN ('workweave.demo_sessions'::regclass, 'workweave.demo_persona_grants'::regclass))
  UNION ALL
  SELECT 7, '0001 workspace FK present under the expected name',
         'demo_visitor_sessions_organization_id_workspace_id_fkey',
         EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid = 'workweave.demo_visitor_sessions'::regclass
                    AND conname = 'demo_visitor_sessions_organization_id_workspace_id_fkey')
  UNION ALL
  SELECT 8, 'new names are free',
         'workspaces_scope_kind_key, demo_visitor_sessions_demo_workspace_fkey, workspace_kind',
         NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname IN ('workspaces_scope_kind_key', 'demo_visitor_sessions_demo_workspace_fkey'))
         AND NOT EXISTS (SELECT 1 FROM information_schema.columns
                          WHERE table_schema = 'workweave' AND table_name = 'demo_visitor_sessions' AND column_name = 'workspace_kind')
) checks ORDER BY n;

ROLLBACK;
