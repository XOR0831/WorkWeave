-- One-shot reviewed synthetic seed. Applied to the local WorkWeave database on 2026-09-27.
-- Do not rerun against a populated database; apply 04_northstar_scenario_alignment.sql afterward.
-- Synthetic fixtures; not actual employees, user validation, model outputs or company procedures.
-- PostgreSQL 16 + pgvector. Apply 01_schema.sql first ONLY after review.
-- One-shot seed: intentionally fails on duplicates; never overwrites existing data.
-- Entire seed is atomic. No Firestore, AI checkpoints, embeddings or external integration calls.
BEGIN;
SET LOCAL search_path = workweave, public;
SET CONSTRAINTS ALL DEFERRED;


-- NORTHSTAR synthetic fixtures
-- northstar.organization
INSERT INTO workweave.organizations (organization_id, name, industry, company_key)
VALUES ('00000001-0000-4000-8000-000000000001', 'Northstar Manufacturing', 'manufacturing', 'northstar');

-- northstar.workspace
INSERT INTO workweave.workspaces (workspace_id, organization_id, kind, pack_version, clock_anchor, expires_at)
VALUES ('00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000001', 'DEMO', 'review-only-v1', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP + interval '7 days');

-- northstar.scenario
INSERT INTO workweave.scenario_catalog (scenario_id, organization_id, workspace_id, company_key, name, industry, pack_version, content_hash, provenance, status)
VALUES ('00000001-0000-4000-8000-000000000003', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', 'northstar', 'Northstar Manufacturing — review fixture', 'manufacturing', 'review-only-v1', 'synthetic-sql-fixture-not-a-pack-hash', '{"synthetic":true,"fixture":"review-only-sql-v1","not_real_employee_evidence":true}'::jsonb, 'DRAFT');

-- northstar.department
INSERT INTO workweave.departments (department_id, organization_id, workspace_id, name)
VALUES ('00000001-0000-4000-8000-000000000004', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', 'Operations');

-- northstar.team
INSERT INTO workweave.teams (team_id, organization_id, workspace_id, department_id, name)
VALUES ('00000001-0000-4000-8000-000000000005', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000004', 'Maintenance');

-- northstar.worker-role
INSERT INTO workweave.roles (role_id, organization_id, workspace_id, name)
VALUES ('00000001-0000-4000-8000-000000000006', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', 'Maintenance technician');

-- northstar.manager-role
INSERT INTO workweave.roles (role_id, organization_id, workspace_id, name)
VALUES ('00000001-0000-4000-8000-000000000007', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', 'Knowledge reviewer / manager');

-- northstar.learner
INSERT INTO workweave.employees (employee_id, organization_id, workspace_id, role_id, first_name, last_name, email, employment_status, hire_date)
VALUES ('00000001-0000-4000-8000-000000000008', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000006', 'Sam', 'Kim', 'sam.kim@northstar.example', 'ONBOARDING', CURRENT_DATE - 180);

-- northstar.outgoing
INSERT INTO workweave.employees (employee_id, organization_id, workspace_id, role_id, first_name, last_name, email, employment_status, hire_date)
VALUES ('00000001-0000-4000-8000-000000000009', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000006', 'Alex', 'Rivera', 'alex.rivera@northstar.example', 'ACTIVE', CURRENT_DATE - 180);

-- northstar.incoming
INSERT INTO workweave.employees (employee_id, organization_id, workspace_id, role_id, first_name, last_name, email, employment_status, hire_date)
VALUES ('00000001-0000-4000-8000-000000000010', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000006', 'Jamie', 'Chen', 'jamie.chen@northstar.example', 'ACTIVE', CURRENT_DATE - 180);

-- northstar.reviewer
INSERT INTO workweave.employees (employee_id, organization_id, workspace_id, role_id, first_name, last_name, email, employment_status, hire_date)
VALUES ('00000001-0000-4000-8000-000000000011', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000007', 'Morgan', 'Lee', 'morgan.lee@northstar.example', 'ACTIVE', CURRENT_DATE - 180);

-- northstar.learner-membership
INSERT INTO workweave.employee_team_memberships (membership_id, organization_id, workspace_id, employee_id, team_id, team_role, start_date, is_active)
VALUES ('00000001-0000-4000-8000-000000000012', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000008', '00000001-0000-4000-8000-000000000005', 'MEMBER', CURRENT_DATE - 180, TRUE);

-- northstar.learner-work:read
INSERT INTO workweave.permission_grants (grant_id, organization_id, workspace_id, actor_id, resource_scope, action, valid_from, granted_by)
VALUES ('00000001-0000-4000-8000-000000000013', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000008', '{"team_id":"00000001-0000-4000-8000-000000000005","synthetic":true}'::jsonb, 'work:read', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000001-0000-4000-8000-000000000002') + interval '-1 day', '00000001-0000-4000-8000-000000000011');

-- northstar.learner-work:report
INSERT INTO workweave.permission_grants (grant_id, organization_id, workspace_id, actor_id, resource_scope, action, valid_from, granted_by)
VALUES ('00000001-0000-4000-8000-000000000014', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000008', '{"team_id":"00000001-0000-4000-8000-000000000005","synthetic":true}'::jsonb, 'work:report', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000001-0000-4000-8000-000000000002') + interval '-1 day', '00000001-0000-4000-8000-000000000011');

-- northstar.learner-learning:own
INSERT INTO workweave.permission_grants (grant_id, organization_id, workspace_id, actor_id, resource_scope, action, valid_from, granted_by)
VALUES ('00000001-0000-4000-8000-000000000015', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000008', '{"team_id":"00000001-0000-4000-8000-000000000005","synthetic":true}'::jsonb, 'learning:own', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000001-0000-4000-8000-000000000002') + interval '-1 day', '00000001-0000-4000-8000-000000000011');

-- northstar.learner-exit_kt:own
INSERT INTO workweave.permission_grants (grant_id, organization_id, workspace_id, actor_id, resource_scope, action, valid_from, granted_by)
VALUES ('00000001-0000-4000-8000-000000000016', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000008', '{"team_id":"00000001-0000-4000-8000-000000000005","synthetic":true}'::jsonb, 'exit_kt:own', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000001-0000-4000-8000-000000000002') + interval '-1 day', '00000001-0000-4000-8000-000000000011');

-- northstar.learner-availability
INSERT INTO workweave.employee_availability (availability_id, organization_id, workspace_id, employee_id, start_at, end_at, status, source_reference)
VALUES ('00000001-0000-4000-8000-000000000017', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000008', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000001-0000-4000-8000-000000000002') + interval '-8 hours', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000001-0000-4000-8000-000000000002') + interval '16 hours', 'AVAILABLE', 'Synthetic declared availability, not monitoring');

-- northstar.outgoing-membership
INSERT INTO workweave.employee_team_memberships (membership_id, organization_id, workspace_id, employee_id, team_id, team_role, start_date, is_active)
VALUES ('00000001-0000-4000-8000-000000000018', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000009', '00000001-0000-4000-8000-000000000005', 'SHIFT_LEAD', CURRENT_DATE - 180, TRUE);

-- northstar.outgoing-work:read
INSERT INTO workweave.permission_grants (grant_id, organization_id, workspace_id, actor_id, resource_scope, action, valid_from, granted_by)
VALUES ('00000001-0000-4000-8000-000000000019', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000009', '{"team_id":"00000001-0000-4000-8000-000000000005","synthetic":true}'::jsonb, 'work:read', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000001-0000-4000-8000-000000000002') + interval '-1 day', '00000001-0000-4000-8000-000000000011');

-- northstar.outgoing-work:report
INSERT INTO workweave.permission_grants (grant_id, organization_id, workspace_id, actor_id, resource_scope, action, valid_from, granted_by)
VALUES ('00000001-0000-4000-8000-000000000020', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000009', '{"team_id":"00000001-0000-4000-8000-000000000005","synthetic":true}'::jsonb, 'work:report', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000001-0000-4000-8000-000000000002') + interval '-1 day', '00000001-0000-4000-8000-000000000011');

-- northstar.outgoing-delegation:confirm
INSERT INTO workweave.permission_grants (grant_id, organization_id, workspace_id, actor_id, resource_scope, action, valid_from, granted_by)
VALUES ('00000001-0000-4000-8000-000000000021', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000009', '{"team_id":"00000001-0000-4000-8000-000000000005","synthetic":true}'::jsonb, 'delegation:confirm', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000001-0000-4000-8000-000000000002') + interval '-1 day', '00000001-0000-4000-8000-000000000011');

-- northstar.outgoing-handover:publish
INSERT INTO workweave.permission_grants (grant_id, organization_id, workspace_id, actor_id, resource_scope, action, valid_from, granted_by)
VALUES ('00000001-0000-4000-8000-000000000022', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000009', '{"team_id":"00000001-0000-4000-8000-000000000005","synthetic":true}'::jsonb, 'handover:publish', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000001-0000-4000-8000-000000000002') + interval '-1 day', '00000001-0000-4000-8000-000000000011');

-- northstar.outgoing-handover:suggestion:review
INSERT INTO workweave.permission_grants (grant_id, organization_id, workspace_id, actor_id, resource_scope, action, valid_from, granted_by)
VALUES ('00000001-0000-4000-8000-000000000023', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000009', '{"team_id":"00000001-0000-4000-8000-000000000005","synthetic":true}'::jsonb, 'handover:suggestion:review', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000001-0000-4000-8000-000000000002') + interval '-1 day', '00000001-0000-4000-8000-000000000011');

-- northstar.outgoing-availability
INSERT INTO workweave.employee_availability (availability_id, organization_id, workspace_id, employee_id, start_at, end_at, status, source_reference)
VALUES ('00000001-0000-4000-8000-000000000024', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000009', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000001-0000-4000-8000-000000000002') + interval '-8 hours', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000001-0000-4000-8000-000000000002') + interval '16 hours', 'AVAILABLE', 'Synthetic declared availability, not monitoring');

-- northstar.incoming-membership
INSERT INTO workweave.employee_team_memberships (membership_id, organization_id, workspace_id, employee_id, team_id, team_role, start_date, is_active)
VALUES ('00000001-0000-4000-8000-000000000025', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000010', '00000001-0000-4000-8000-000000000005', 'MEMBER', CURRENT_DATE - 180, TRUE);

-- northstar.incoming-work:read
INSERT INTO workweave.permission_grants (grant_id, organization_id, workspace_id, actor_id, resource_scope, action, valid_from, granted_by)
VALUES ('00000001-0000-4000-8000-000000000026', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000010', '{"team_id":"00000001-0000-4000-8000-000000000005","synthetic":true}'::jsonb, 'work:read', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000001-0000-4000-8000-000000000002') + interval '-1 day', '00000001-0000-4000-8000-000000000011');

-- northstar.incoming-work:report
INSERT INTO workweave.permission_grants (grant_id, organization_id, workspace_id, actor_id, resource_scope, action, valid_from, granted_by)
VALUES ('00000001-0000-4000-8000-000000000027', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000010', '{"team_id":"00000001-0000-4000-8000-000000000005","synthetic":true}'::jsonb, 'work:report', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000001-0000-4000-8000-000000000002') + interval '-1 day', '00000001-0000-4000-8000-000000000011');

-- northstar.incoming-learning:own
INSERT INTO workweave.permission_grants (grant_id, organization_id, workspace_id, actor_id, resource_scope, action, valid_from, granted_by)
VALUES ('00000001-0000-4000-8000-000000000028', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000010', '{"team_id":"00000001-0000-4000-8000-000000000005","synthetic":true}'::jsonb, 'learning:own', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000001-0000-4000-8000-000000000002') + interval '-1 day', '00000001-0000-4000-8000-000000000011');

-- northstar.incoming-exit_kt:own
INSERT INTO workweave.permission_grants (grant_id, organization_id, workspace_id, actor_id, resource_scope, action, valid_from, granted_by)
VALUES ('00000001-0000-4000-8000-000000000029', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000010', '{"team_id":"00000001-0000-4000-8000-000000000005","synthetic":true}'::jsonb, 'exit_kt:own', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000001-0000-4000-8000-000000000002') + interval '-1 day', '00000001-0000-4000-8000-000000000011');

-- northstar.incoming-availability
INSERT INTO workweave.employee_availability (availability_id, organization_id, workspace_id, employee_id, start_at, end_at, status, source_reference)
VALUES ('00000001-0000-4000-8000-000000000030', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000010', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000001-0000-4000-8000-000000000002') + interval '-8 hours', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000001-0000-4000-8000-000000000002') + interval '16 hours', 'AVAILABLE', 'Synthetic declared availability, not monitoring');

-- northstar.reviewer-membership
INSERT INTO workweave.employee_team_memberships (membership_id, organization_id, workspace_id, employee_id, team_id, team_role, start_date, is_active)
VALUES ('00000001-0000-4000-8000-000000000031', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000011', '00000001-0000-4000-8000-000000000005', 'MANAGER', CURRENT_DATE - 180, TRUE);

-- northstar.reviewer-work:read
INSERT INTO workweave.permission_grants (grant_id, organization_id, workspace_id, actor_id, resource_scope, action, valid_from, granted_by)
VALUES ('00000001-0000-4000-8000-000000000032', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000011', '{"team_id":"00000001-0000-4000-8000-000000000005","synthetic":true}'::jsonb, 'work:read', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000001-0000-4000-8000-000000000002') + interval '-1 day', '00000001-0000-4000-8000-000000000011');

-- northstar.reviewer-knowledge:review
INSERT INTO workweave.permission_grants (grant_id, organization_id, workspace_id, actor_id, resource_scope, action, valid_from, granted_by)
VALUES ('00000001-0000-4000-8000-000000000033', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000011', '{"team_id":"00000001-0000-4000-8000-000000000005","synthetic":true}'::jsonb, 'knowledge:review', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000001-0000-4000-8000-000000000002') + interval '-1 day', '00000001-0000-4000-8000-000000000011');

-- northstar.reviewer-exit_kt:review
INSERT INTO workweave.permission_grants (grant_id, organization_id, workspace_id, actor_id, resource_scope, action, valid_from, granted_by)
VALUES ('00000001-0000-4000-8000-000000000034', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000011', '{"team_id":"00000001-0000-4000-8000-000000000005","synthetic":true}'::jsonb, 'exit_kt:review', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000001-0000-4000-8000-000000000002') + interval '-1 day', '00000001-0000-4000-8000-000000000011');

-- northstar.reviewer-responsibility:transfer
INSERT INTO workweave.permission_grants (grant_id, organization_id, workspace_id, actor_id, resource_scope, action, valid_from, granted_by)
VALUES ('00000001-0000-4000-8000-000000000035', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000011', '{"team_id":"00000001-0000-4000-8000-000000000005","synthetic":true}'::jsonb, 'responsibility:transfer', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000001-0000-4000-8000-000000000002') + interval '-1 day', '00000001-0000-4000-8000-000000000011');

-- northstar.reviewer-availability
INSERT INTO workweave.employee_availability (availability_id, organization_id, workspace_id, employee_id, start_at, end_at, status, source_reference)
VALUES ('00000001-0000-4000-8000-000000000036', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000011', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000001-0000-4000-8000-000000000002') + interval '-8 hours', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000001-0000-4000-8000-000000000002') + interval '16 hours', 'AVAILABLE', 'Synthetic declared availability, not monitoring');

-- northstar.Morning-shift
INSERT INTO workweave.shifts (shift_id, organization_id, workspace_id, team_id, name, start_time, end_time, timezone)
VALUES ('00000001-0000-4000-8000-000000000037', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000005', 'Morning', '07:00', '15:00', 'Asia/Manila');

-- northstar.Morning-instance
INSERT INTO workweave.shift_instances (shift_instance_id, organization_id, workspace_id, shift_id, shift_date, scheduled_start_at, scheduled_end_at, shift_lead_employee_id, status)
VALUES ('00000001-0000-4000-8000-000000000038', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000037', ((SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000001-0000-4000-8000-000000000002') AT TIME ZONE 'Asia/Manila')::date, (date_trunc('day', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000001-0000-4000-8000-000000000002') AT TIME ZONE 'Asia/Manila') + time '07:00') AT TIME ZONE 'Asia/Manila', (date_trunc('day', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000001-0000-4000-8000-000000000002') AT TIME ZONE 'Asia/Manila') + time '15:00') AT TIME ZONE 'Asia/Manila', '00000001-0000-4000-8000-000000000009', 'COMPLETED');

-- northstar.Morning-learner
INSERT INTO workweave.shift_instance_memberships (shift_membership_id, organization_id, workspace_id, shift_instance_id, employee_id, membership_role, availability_status)
VALUES ('00000001-0000-4000-8000-000000000039', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000038', '00000001-0000-4000-8000-000000000008', 'MEMBER', 'AVAILABLE');

-- northstar.Morning-outgoing
INSERT INTO workweave.shift_instance_memberships (shift_membership_id, organization_id, workspace_id, shift_instance_id, employee_id, membership_role, availability_status)
VALUES ('00000001-0000-4000-8000-000000000040', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000038', '00000001-0000-4000-8000-000000000009', 'SHIFT_LEAD', 'AVAILABLE');

-- northstar.Morning-incoming
INSERT INTO workweave.shift_instance_memberships (shift_membership_id, organization_id, workspace_id, shift_instance_id, employee_id, membership_role, availability_status)
VALUES ('00000001-0000-4000-8000-000000000041', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000038', '00000001-0000-4000-8000-000000000010', 'MEMBER', 'AVAILABLE');

-- northstar.Afternoon-shift
INSERT INTO workweave.shifts (shift_id, organization_id, workspace_id, team_id, name, start_time, end_time, timezone)
VALUES ('00000001-0000-4000-8000-000000000042', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000005', 'Afternoon', '15:00', '23:00', 'Asia/Manila');

-- northstar.Afternoon-instance
INSERT INTO workweave.shift_instances (shift_instance_id, organization_id, workspace_id, shift_id, shift_date, scheduled_start_at, scheduled_end_at, shift_lead_employee_id, status)
VALUES ('00000001-0000-4000-8000-000000000043', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000042', ((SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000001-0000-4000-8000-000000000002') AT TIME ZONE 'Asia/Manila')::date, (date_trunc('day', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000001-0000-4000-8000-000000000002') AT TIME ZONE 'Asia/Manila') + time '15:00') AT TIME ZONE 'Asia/Manila', (date_trunc('day', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000001-0000-4000-8000-000000000002') AT TIME ZONE 'Asia/Manila') + time '23:00') AT TIME ZONE 'Asia/Manila', '00000001-0000-4000-8000-000000000009', 'ACTIVE');

-- northstar.Afternoon-learner
INSERT INTO workweave.shift_instance_memberships (shift_membership_id, organization_id, workspace_id, shift_instance_id, employee_id, membership_role, availability_status)
VALUES ('00000001-0000-4000-8000-000000000044', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000043', '00000001-0000-4000-8000-000000000008', 'MEMBER', 'AVAILABLE');

-- northstar.Afternoon-outgoing
INSERT INTO workweave.shift_instance_memberships (shift_membership_id, organization_id, workspace_id, shift_instance_id, employee_id, membership_role, availability_status)
VALUES ('00000001-0000-4000-8000-000000000045', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000043', '00000001-0000-4000-8000-000000000009', 'SHIFT_LEAD', 'AVAILABLE');

-- northstar.Afternoon-incoming
INSERT INTO workweave.shift_instance_memberships (shift_membership_id, organization_id, workspace_id, shift_instance_id, employee_id, membership_role, availability_status)
VALUES ('00000001-0000-4000-8000-000000000046', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000043', '00000001-0000-4000-8000-000000000010', 'MEMBER', 'AVAILABLE');

-- northstar.Evening-shift
INSERT INTO workweave.shifts (shift_id, organization_id, workspace_id, team_id, name, start_time, end_time, timezone)
VALUES ('00000001-0000-4000-8000-000000000047', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000005', 'Evening', '23:00', '07:00', 'Asia/Manila');

-- northstar.Evening-instance
INSERT INTO workweave.shift_instances (shift_instance_id, organization_id, workspace_id, shift_id, shift_date, scheduled_start_at, scheduled_end_at, shift_lead_employee_id, status)
VALUES ('00000001-0000-4000-8000-000000000048', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000047', ((SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000001-0000-4000-8000-000000000002') AT TIME ZONE 'Asia/Manila')::date, (date_trunc('day', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000001-0000-4000-8000-000000000002') AT TIME ZONE 'Asia/Manila') + time '23:00') AT TIME ZONE 'Asia/Manila', (date_trunc('day', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000001-0000-4000-8000-000000000002') AT TIME ZONE 'Asia/Manila') + interval '1 day' + time '07:00') AT TIME ZONE 'Asia/Manila', '00000001-0000-4000-8000-000000000009', 'SCHEDULED');

-- northstar.Evening-learner
INSERT INTO workweave.shift_instance_memberships (shift_membership_id, organization_id, workspace_id, shift_instance_id, employee_id, membership_role, availability_status)
VALUES ('00000001-0000-4000-8000-000000000049', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000048', '00000001-0000-4000-8000-000000000008', 'MEMBER', 'AVAILABLE');

-- northstar.Evening-outgoing
INSERT INTO workweave.shift_instance_memberships (shift_membership_id, organization_id, workspace_id, shift_instance_id, employee_id, membership_role, availability_status)
VALUES ('00000001-0000-4000-8000-000000000050', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000048', '00000001-0000-4000-8000-000000000009', 'SHIFT_LEAD', 'AVAILABLE');

-- northstar.Evening-incoming
INSERT INTO workweave.shift_instance_memberships (shift_membership_id, organization_id, workspace_id, shift_instance_id, employee_id, membership_role, availability_status)
VALUES ('00000001-0000-4000-8000-000000000051', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000048', '00000001-0000-4000-8000-000000000010', 'MEMBER', 'AVAILABLE');

-- northstar.procedure_control
INSERT INTO workweave.competencies (competency_id, organization_id, workspace_id, code, name, category)
VALUES ('00000001-0000-4000-8000-000000000052', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', 'procedure_control', 'procedure control', 'manufacturing');

-- northstar.evidence_reporting
INSERT INTO workweave.competencies (competency_id, organization_id, workspace_id, code, name, category)
VALUES ('00000001-0000-4000-8000-000000000053', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', 'evidence_reporting', 'evidence reporting', 'manufacturing');

-- northstar.document_review
INSERT INTO workweave.competencies (competency_id, organization_id, workspace_id, code, name, category)
VALUES ('00000001-0000-4000-8000-000000000054', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', 'document_review', 'document review', 'manufacturing');

-- northstar.role-00000001-0000-4000-8000-000000000052
INSERT INTO workweave.role_competency_requirements (requirement_id, organization_id, workspace_id, role_id, competency_id, required_level, is_mandatory)
VALUES ('00000001-0000-4000-8000-000000000055', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000006', '00000001-0000-4000-8000-000000000052', 1, TRUE);

-- northstar.role-00000001-0000-4000-8000-000000000053
INSERT INTO workweave.role_competency_requirements (requirement_id, organization_id, workspace_id, role_id, competency_id, required_level, is_mandatory)
VALUES ('00000001-0000-4000-8000-000000000056', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000006', '00000001-0000-4000-8000-000000000053', 1, TRUE);

-- northstar.role-00000001-0000-4000-8000-000000000054
INSERT INTO workweave.role_competency_requirements (requirement_id, organization_id, workspace_id, role_id, competency_id, required_level, is_mandatory)
VALUES ('00000001-0000-4000-8000-000000000057', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000006', '00000001-0000-4000-8000-000000000054', 1, TRUE);

-- northstar.evidence-00000001-0000-4000-8000-000000000009-0
INSERT INTO workweave.employee_competency_evidence (evidence_id, organization_id, workspace_id, employee_id, competency_id, evidence_type, source_type, description, metadata, observed_at, validation_status, validated_by)
VALUES ('00000001-0000-4000-8000-000000000058', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000009', '00000001-0000-4000-8000-000000000052', 'SUPERVISOR_VALIDATION', 'MANUAL', 'Synthetic baseline validation for scenario review; not a real assessment.', '{"synthetic":true,"fixture":"review-only-sql-v1","not_real_employee_evidence":true}'::jsonb, (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000001-0000-4000-8000-000000000002') + interval '-7 days', 'VALIDATED', '00000001-0000-4000-8000-000000000011');

-- northstar.state-00000001-0000-4000-8000-000000000009-0
INSERT INTO workweave.employee_competency_state (employee_competency_state_id, organization_id, workspace_id, employee_id, competency_id, current_level, last_evaluated_at, policy_version, evidence_refs)
VALUES ('00000001-0000-4000-8000-000000000059', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000009', '00000001-0000-4000-8000-000000000052', 2, (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000001-0000-4000-8000-000000000002') + interval '-7 days', 'synthetic-setup-v1', '["00000001-0000-4000-8000-000000000058"]'::jsonb);

-- northstar.evidence-00000001-0000-4000-8000-000000000009-1
INSERT INTO workweave.employee_competency_evidence (evidence_id, organization_id, workspace_id, employee_id, competency_id, evidence_type, source_type, description, metadata, observed_at, validation_status, validated_by)
VALUES ('00000001-0000-4000-8000-000000000060', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000009', '00000001-0000-4000-8000-000000000053', 'SUPERVISOR_VALIDATION', 'MANUAL', 'Synthetic baseline validation for scenario review; not a real assessment.', '{"synthetic":true,"fixture":"review-only-sql-v1","not_real_employee_evidence":true}'::jsonb, (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000001-0000-4000-8000-000000000002') + interval '-7 days', 'VALIDATED', '00000001-0000-4000-8000-000000000011');

-- northstar.state-00000001-0000-4000-8000-000000000009-1
INSERT INTO workweave.employee_competency_state (employee_competency_state_id, organization_id, workspace_id, employee_id, competency_id, current_level, last_evaluated_at, policy_version, evidence_refs)
VALUES ('00000001-0000-4000-8000-000000000061', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000009', '00000001-0000-4000-8000-000000000053', 2, (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000001-0000-4000-8000-000000000002') + interval '-7 days', 'synthetic-setup-v1', '["00000001-0000-4000-8000-000000000060"]'::jsonb);

-- northstar.evidence-00000001-0000-4000-8000-000000000010-2
INSERT INTO workweave.employee_competency_evidence (evidence_id, organization_id, workspace_id, employee_id, competency_id, evidence_type, source_type, description, metadata, observed_at, validation_status, validated_by)
VALUES ('00000001-0000-4000-8000-000000000062', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000010', '00000001-0000-4000-8000-000000000054', 'SUPERVISOR_VALIDATION', 'MANUAL', 'Synthetic baseline validation for scenario review; not a real assessment.', '{"synthetic":true,"fixture":"review-only-sql-v1","not_real_employee_evidence":true}'::jsonb, (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000001-0000-4000-8000-000000000002') + interval '-7 days', 'VALIDATED', '00000001-0000-4000-8000-000000000011');

-- northstar.state-00000001-0000-4000-8000-000000000010-2
INSERT INTO workweave.employee_competency_state (employee_competency_state_id, organization_id, workspace_id, employee_id, competency_id, current_level, last_evaluated_at, policy_version, evidence_refs)
VALUES ('00000001-0000-4000-8000-000000000063', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000010', '00000001-0000-4000-8000-000000000054', 2, (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000001-0000-4000-8000-000000000002') + interval '-7 days', 'synthetic-setup-v1', '["00000001-0000-4000-8000-000000000062"]'::jsonb);

-- northstar.sop-source
INSERT INTO workweave.source_records (source_id, organization_id, workspace_id, source_type, evidence_type, access_partition, metadata)
VALUES ('00000001-0000-4000-8000-000000000064', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', 'APPROVED_EXCERPT', 'REPORTED', 'ORGANIZATION', '{"synthetic":true,"fixture":"review-only-sql-v1","not_real_employee_evidence":true}'::jsonb);

-- northstar.sop
INSERT INTO workweave.knowledge_documents (document_id, organization_id, workspace_id, document_code, title, document_type)
VALUES ('00000001-0000-4000-8000-000000000065', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', 'SOP-001', 'Calibration and evidence handling', 'SOP');

-- northstar.sop-historical
INSERT INTO workweave.knowledge_document_versions (document_version_id, organization_id, workspace_id, document_id, version, content, source_id, approval_status, temporal_status, effective_at, approved_by_employee_id, approved_at)
VALUES ('00000001-0000-4000-8000-000000000066', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000065', '3.2', '# Historical synthetic reference
Superseded; not current instructions.', '00000001-0000-4000-8000-000000000064', 'APPROVED', 'SUPERSEDED', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000001-0000-4000-8000-000000000002') + interval '-60 days', '00000001-0000-4000-8000-000000000011', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000001-0000-4000-8000-000000000002') + interval '-61 days');

-- northstar.sop-current
INSERT INTO workweave.knowledge_document_versions (document_version_id, organization_id, workspace_id, document_id, version, content, source_id, approval_status, temporal_status, effective_at, approved_by_employee_id, approved_at)
VALUES ('00000001-0000-4000-8000-000000000067', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000065', '3.3', '# SOP-001: Calibration and evidence handling

## 1. Fundamentals

### 1. Find the current procedure
Use the current approved source, not a familiar historical version. This text is a synthetic training fixture.

### 2. Separate history from evidence
Keep reported and verified facts separate. An earlier incident cannot prove a current cause. No operational action is authorized by this fixture.

### 3. Ask a clearer question
Name the current work item and approved source version. State missing evidence and ask the authorized reviewer for clarification. Do not invent company procedures.', '00000001-0000-4000-8000-000000000064', 'APPROVED', 'CURRENT', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000001-0000-4000-8000-000000000002') + interval '-7 days', '00000001-0000-4000-8000-000000000011', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000001-0000-4000-8000-000000000002') + interval '-8 days');

-- northstar.curriculum
INSERT INTO workweave.curricula (curriculum_id, organization_id, workspace_id, name, version, status, published_at, completion_policy_version)
VALUES ('00000001-0000-4000-8000-000000000068', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', 'Machine Fundamentals', '1.0', 'PUBLISHED', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000001-0000-4000-8000-000000000002') + interval '-1 day', 'synthetic-objective-v1');

-- northstar.topic
INSERT INTO workweave.curriculum_topics (topic_id, organization_id, workspace_id, curriculum_id, name, order_index)
VALUES ('00000001-0000-4000-8000-000000000069', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000068', 'Machine Fundamentals', 1);

-- northstar.subtopic-0
INSERT INTO workweave.curriculum_subtopics (subtopic_id, organization_id, workspace_id, topic_id, name, order_index)
VALUES ('00000001-0000-4000-8000-000000000070', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000069', 'Find the current procedure', 1);

-- northstar.objective-0
INSERT INTO workweave.learning_objectives (objective_id, organization_id, workspace_id, subtopic_id, description, assessment_criteria, criteria_version, required, hint_policy, competency_id)
VALUES ('00000001-0000-4000-8000-000000000071', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000070', 'Demonstrate find the current procedure.', '{"required_checks":["use_current_approved_evidence","keep_unknowns_explicit"],"synthetic":true}'::jsonb, 'synthetic-criteria-v1', TRUE, '{"hinted_answers":"FORMATIVE_ONLY"}'::jsonb, '00000001-0000-4000-8000-000000000052');

-- northstar.chunk-0
INSERT INTO workweave.knowledge_chunks (chunk_id, organization_id, workspace_id, document_version_id, source_id, section_path, heading, content, chunk_index, source_span, metadata)
VALUES ('00000001-0000-4000-8000-000000000072', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000067', '00000001-0000-4000-8000-000000000064', '["Fundamentals","Find the current procedure"]'::jsonb, 'Find the current procedure', '### 1. Find the current procedure
Use the current approved source, not a familiar historical version. This text is a synthetic training fixture.', 0, '{"heading":"Find the current procedure","synthetic":true}'::jsonb, '{"synthetic":true,"fixture":"review-only-sql-v1","not_real_employee_evidence":true}'::jsonb);

-- northstar.mapping-0
INSERT INTO workweave.knowledge_mappings (mapping_id, organization_id, workspace_id, document_id, document_version_id, section_ref, entity_type, entity_id, relationship_type)
VALUES ('00000001-0000-4000-8000-000000000073', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000065', '00000001-0000-4000-8000-000000000067', 'Find the current procedure', 'CURRICULUM_SUBTOPIC', '00000001-0000-4000-8000-000000000070', 'TEACHES');

-- northstar.subtopic-1
INSERT INTO workweave.curriculum_subtopics (subtopic_id, organization_id, workspace_id, topic_id, name, order_index)
VALUES ('00000001-0000-4000-8000-000000000074', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000069', 'Separate history from evidence', 2);

-- northstar.objective-1
INSERT INTO workweave.learning_objectives (objective_id, organization_id, workspace_id, subtopic_id, description, assessment_criteria, criteria_version, required, hint_policy, competency_id)
VALUES ('00000001-0000-4000-8000-000000000075', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000074', 'Demonstrate separate history from evidence.', '{"required_checks":["use_current_approved_evidence","keep_unknowns_explicit"],"synthetic":true}'::jsonb, 'synthetic-criteria-v1', TRUE, '{"hinted_answers":"FORMATIVE_ONLY"}'::jsonb, '00000001-0000-4000-8000-000000000053');

-- northstar.chunk-1
INSERT INTO workweave.knowledge_chunks (chunk_id, organization_id, workspace_id, document_version_id, source_id, section_path, heading, content, chunk_index, source_span, metadata)
VALUES ('00000001-0000-4000-8000-000000000076', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000067', '00000001-0000-4000-8000-000000000064', '["Fundamentals","Separate history from evidence"]'::jsonb, 'Separate history from evidence', '### 2. Separate history from evidence
Keep reported and verified facts separate. An earlier incident cannot prove a current cause. No operational action is authorized by this fixture.', 1, '{"heading":"Separate history from evidence","synthetic":true}'::jsonb, '{"synthetic":true,"fixture":"review-only-sql-v1","not_real_employee_evidence":true}'::jsonb);

-- northstar.mapping-1
INSERT INTO workweave.knowledge_mappings (mapping_id, organization_id, workspace_id, document_id, document_version_id, section_ref, entity_type, entity_id, relationship_type)
VALUES ('00000001-0000-4000-8000-000000000077', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000065', '00000001-0000-4000-8000-000000000067', 'Separate history from evidence', 'CURRICULUM_SUBTOPIC', '00000001-0000-4000-8000-000000000074', 'TEACHES');

-- northstar.prereq-1
INSERT INTO workweave.curriculum_prerequisites (prerequisite_id, organization_id, workspace_id, subtopic_id, prerequisite_subtopic_id)
VALUES ('00000001-0000-4000-8000-000000000078', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000074', '00000001-0000-4000-8000-000000000070');

-- northstar.subtopic-2
INSERT INTO workweave.curriculum_subtopics (subtopic_id, organization_id, workspace_id, topic_id, name, order_index)
VALUES ('00000001-0000-4000-8000-000000000079', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000069', 'Ask a clearer question', 3);

-- northstar.objective-2
INSERT INTO workweave.learning_objectives (objective_id, organization_id, workspace_id, subtopic_id, description, assessment_criteria, criteria_version, required, hint_policy, competency_id)
VALUES ('00000001-0000-4000-8000-000000000080', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000079', 'Demonstrate ask a clearer question.', '{"required_checks":["use_current_approved_evidence","keep_unknowns_explicit"],"synthetic":true}'::jsonb, 'synthetic-criteria-v1', TRUE, '{"hinted_answers":"FORMATIVE_ONLY"}'::jsonb, '00000001-0000-4000-8000-000000000054');

-- northstar.chunk-2
INSERT INTO workweave.knowledge_chunks (chunk_id, organization_id, workspace_id, document_version_id, source_id, section_path, heading, content, chunk_index, source_span, metadata)
VALUES ('00000001-0000-4000-8000-000000000081', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000067', '00000001-0000-4000-8000-000000000064', '["Fundamentals","Ask a clearer question"]'::jsonb, 'Ask a clearer question', '### 3. Ask a clearer question
Name the current work item and approved source version. State missing evidence and ask the authorized reviewer for clarification. Do not invent company procedures.', 2, '{"heading":"Ask a clearer question","synthetic":true}'::jsonb, '{"synthetic":true,"fixture":"review-only-sql-v1","not_real_employee_evidence":true}'::jsonb);

-- northstar.mapping-2
INSERT INTO workweave.knowledge_mappings (mapping_id, organization_id, workspace_id, document_id, document_version_id, section_ref, entity_type, entity_id, relationship_type)
VALUES ('00000001-0000-4000-8000-000000000082', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000065', '00000001-0000-4000-8000-000000000067', 'Ask a clearer question', 'CURRICULUM_SUBTOPIC', '00000001-0000-4000-8000-000000000079', 'TEACHES');

-- northstar.prereq-2
INSERT INTO workweave.curriculum_prerequisites (prerequisite_id, organization_id, workspace_id, subtopic_id, prerequisite_subtopic_id)
VALUES ('00000001-0000-4000-8000-000000000083', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000079', '00000001-0000-4000-8000-000000000074');

-- northstar.learner-curriculum
INSERT INTO workweave.curriculum_assignments (assignment_id, organization_id, workspace_id, curriculum_id, employee_id, assigned_at, assigned_by_employee_id)
VALUES ('00000001-0000-4000-8000-000000000084', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000068', '00000001-0000-4000-8000-000000000008', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000001-0000-4000-8000-000000000002') + interval '0 seconds', '00000001-0000-4000-8000-000000000011');

-- northstar.learner-assignment
INSERT INTO workweave.learning_assignments (learning_assignment_id, organization_id, workspace_id, employee_id, curriculum_id, originating_assignment_id, assignment_kind)
VALUES ('00000001-0000-4000-8000-000000000085', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000008', '00000001-0000-4000-8000-000000000068', '00000001-0000-4000-8000-000000000084', 'INITIAL');

-- northstar.learner-progress-0
INSERT INTO workweave.employee_learning_progress (progress_id, organization_id, workspace_id, employee_id, learning_assignment_id, subtopic_id, status)
VALUES ('00000001-0000-4000-8000-000000000086', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000008', '00000001-0000-4000-8000-000000000085', '00000001-0000-4000-8000-000000000070', 'NOT_STARTED');

-- northstar.learner-progress-1
INSERT INTO workweave.employee_learning_progress (progress_id, organization_id, workspace_id, employee_id, learning_assignment_id, subtopic_id, status)
VALUES ('00000001-0000-4000-8000-000000000087', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000008', '00000001-0000-4000-8000-000000000085', '00000001-0000-4000-8000-000000000074', 'NOT_STARTED');

-- northstar.learner-progress-2
INSERT INTO workweave.employee_learning_progress (progress_id, organization_id, workspace_id, employee_id, learning_assignment_id, subtopic_id, status)
VALUES ('00000001-0000-4000-8000-000000000088', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000008', '00000001-0000-4000-8000-000000000085', '00000001-0000-4000-8000-000000000079', 'NOT_STARTED');

-- northstar.work-0
INSERT INTO workweave.work_items (work_item_id, organization_id, workspace_id, external_system, external_id, work_item_type, title, description, priority, status, due_at, metadata)
VALUES ('00000001-0000-4000-8000-000000000089', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', 'synthetic_seed', 'Ticket #829', 'INCIDENT', 'Machine #14 inspection', 'Reported vibration; steps 1–4 recorded complete. Cause remains unverified.', 'HIGH', 'IN_PROGRESS', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000001-0000-4000-8000-000000000002') + interval '2 hours', '{"synthetic":true,"fixture":"review-only-sql-v1","not_real_employee_evidence":true}'::jsonb);

-- northstar.requirement-0
INSERT INTO workweave.work_item_competency_requirements (id, organization_id, workspace_id, work_item_id, competency_id, required_level, importance)
VALUES ('00000001-0000-4000-8000-000000000090', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000089', '00000001-0000-4000-8000-000000000052', 1, 1);

-- northstar.work-1
INSERT INTO workweave.work_items (work_item_id, organization_id, workspace_id, external_system, external_id, work_item_type, title, description, priority, status, due_at, metadata)
VALUES ('00000001-0000-4000-8000-000000000091', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', 'synthetic_seed', 'Ticket #910', 'TASK', 'Machine #22 document check', 'Current document reference needs confirmation.', 'MEDIUM', 'IN_PROGRESS', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000001-0000-4000-8000-000000000002') + interval '6 hours', '{"synthetic":true,"fixture":"review-only-sql-v1","not_real_employee_evidence":true}'::jsonb);

-- northstar.requirement-1
INSERT INTO workweave.work_item_competency_requirements (id, organization_id, workspace_id, work_item_id, competency_id, required_level, importance)
VALUES ('00000001-0000-4000-8000-000000000092', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000091', '00000001-0000-4000-8000-000000000053', 1, 1);

-- northstar.work-session
INSERT INTO workweave.work_sessions (work_session_id, organization_id, workspace_id, employee_id, shift_instance_id, started_at, status)
VALUES ('00000001-0000-4000-8000-000000000093', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000009', '00000001-0000-4000-8000-000000000043', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000001-0000-4000-8000-000000000002') + interval '0 seconds', 'ACTIVE');

-- northstar.proposal
INSERT INTO workweave.delegation_proposals (delegation_proposal_id, organization_id, workspace_id, shift_instance_id, team_id, created_by, status, context_revisions)
VALUES ('00000001-0000-4000-8000-000000000094', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000043', '00000001-0000-4000-8000-000000000005', '00000001-0000-4000-8000-000000000009', 'PROPOSED', '{"synthetic":true,"team_revision":1}'::jsonb);

-- northstar.proposal-item-0
INSERT INTO workweave.delegation_proposal_items (proposal_item_id, organization_id, workspace_id, delegation_proposal_id, work_item_id, recommended_employee_id, recommendation_reason, match_data)
VALUES ('00000001-0000-4000-8000-000000000095', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000094', '00000001-0000-4000-8000-000000000089', '00000001-0000-4000-8000-000000000010', 'Synthetic proposed match from validated baseline evidence and declared availability; needs human confirmation.', '{"synthetic":true,"fixture":"review-only-sql-v1","not_real_employee_evidence":true}'::jsonb);

-- northstar.proposal-item-1
INSERT INTO workweave.delegation_proposal_items (proposal_item_id, organization_id, workspace_id, delegation_proposal_id, work_item_id, recommended_employee_id, recommendation_reason, match_data)
VALUES ('00000001-0000-4000-8000-000000000096', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000094', '00000001-0000-4000-8000-000000000091', '00000001-0000-4000-8000-000000000009', 'Synthetic proposed match from validated baseline evidence and declared availability; needs human confirmation.', '{"synthetic":true,"fixture":"review-only-sql-v1","not_real_employee_evidence":true}'::jsonb);

-- northstar.historical-assignment
INSERT INTO workweave.work_item_assignments (assignment_id, organization_id, workspace_id, work_item_id, employee_id, assigned_by_employee_id, assignment_source, status, assigned_at)
VALUES ('00000001-0000-4000-8000-000000000097', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000089', '00000001-0000-4000-8000-000000000009', '00000001-0000-4000-8000-000000000009', 'MANUAL', 'CANCELLED', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000001-0000-4000-8000-000000000002') + interval '-8 hours');

-- northstar.member-report
INSERT INTO workweave.work_events (work_event_id, organization_id, workspace_id, work_item_id, employee_id, shift_instance_id, event_type, description, event_data, evidence_refs, observed_at)
VALUES ('00000001-0000-4000-8000-000000000098', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000089', '00000001-0000-4000-8000-000000000009', '00000001-0000-4000-8000-000000000038', 'COMMENTED', 'Partial progress was reported; missing evidence and current cause remain unknown.', '{"synthetic":true,"fixture":"review-only-sql-v1","not_real_employee_evidence":true,"prior_assignment_ended":true}'::jsonb, '["00000001-0000-4000-8000-000000000064"]'::jsonb, (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000001-0000-4000-8000-000000000002') + interval '-1 hour');

-- northstar.lead-work-state
INSERT INTO workweave.employee_work_state (employee_work_state_id, organization_id, workspace_id, employee_id, shift_instance_id, work_context_key, workload_state, active_work_count, blocked_work_count, metadata)
VALUES ('00000001-0000-4000-8000-000000000099', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000009', '00000001-0000-4000-8000-000000000043', 'shift:00000001-0000-4000-8000-000000000043', 'NEEDS_FOCUS', 2, 0, '{"synthetic":true,"fixture":"review-only-sql-v1","not_real_employee_evidence":true,"derived_from_current_items":true}'::jsonb);

-- northstar.template
INSERT INTO workweave.handover_templates (template_id, organization_id, workspace_id, team_id, name, is_default)
VALUES ('00000001-0000-4000-8000-000000000100', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000005', 'Team continuity', TRUE);

-- northstar.template-v1
INSERT INTO workweave.handover_template_versions (template_version_id, organization_id, workspace_id, template_id, version, published_at)
VALUES ('00000001-0000-4000-8000-000000000101', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000100', 1, (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000001-0000-4000-8000-000000000002') + interval '-2 days');

-- northstar.section-0
INSERT INTO workweave.handover_template_sections (section_id, organization_id, workspace_id, template_version_id, name, order_index, is_required)
VALUES ('00000001-0000-4000-8000-000000000102', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000101', 'Shift Summary', 1, TRUE);

-- northstar.section-1
INSERT INTO workweave.handover_template_sections (section_id, organization_id, workspace_id, template_version_id, name, order_index, is_required)
VALUES ('00000001-0000-4000-8000-000000000103', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000101', 'Active / Ongoing Items', 2, TRUE);

-- northstar.section-2
INSERT INTO workweave.handover_template_sections (section_id, organization_id, workspace_id, template_version_id, name, order_index, is_required)
VALUES ('00000001-0000-4000-8000-000000000104', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000101', 'Incidents / Issues', 3, FALSE);

-- northstar.section-3
INSERT INTO workweave.handover_template_sections (section_id, organization_id, workspace_id, template_version_id, name, order_index, is_required)
VALUES ('00000001-0000-4000-8000-000000000105', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000101', 'Scheduled Activities', 4, FALSE);

-- northstar.section-4
INSERT INTO workweave.handover_template_sections (section_id, organization_id, workspace_id, template_version_id, name, order_index, is_required)
VALUES ('00000001-0000-4000-8000-000000000106', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000101', 'Blockers / Risks', 5, FALSE);

-- northstar.section-5
INSERT INTO workweave.handover_template_sections (section_id, organization_id, workspace_id, template_version_id, name, order_index, is_required)
VALUES ('00000001-0000-4000-8000-000000000107', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000101', 'Important Notes', 6, FALSE);

-- northstar.morning-handover
INSERT INTO workweave.shift_handovers (handover_id, organization_id, workspace_id, source_shift_instance_id, target_shift_instance_id, template_version_id, status, created_by_employee_id, context_as_of, context_revisions, draft_sections)
VALUES ('00000001-0000-4000-8000-000000000108', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000038', '00000001-0000-4000-8000-000000000043', '00000001-0000-4000-8000-000000000101', 'DRAFT', '00000001-0000-4000-8000-000000000009', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000001-0000-4000-8000-000000000002') + interval '-2 hours', '{"synthetic":true,"fixture":"review-only-sql-v1","not_real_employee_evidence":true}'::jsonb, '[{"section_id":"00000001-0000-4000-8000-000000000102","status":"DOCUMENTED","content":"Synthetic shift summary. Open work requires follow-up."},{"section_id":"00000001-0000-4000-8000-000000000103","status":"DOCUMENTED","content":"Ticket #829: IN_PROGRESS. Reported vibration; steps 1–4 recorded complete. Cause remains unverified.\nTicket #910: IN_PROGRESS. Current document reference needs confirmation."}]'::jsonb);

-- northstar.morning-publication
INSERT INTO workweave.handover_publications (publication_id, organization_id, workspace_id, handover_id, publication_number, content_revision, scope_snapshot, template_version_id, section_content, source_revisions, published_by, published_at)
VALUES ('00000001-0000-4000-8000-000000000109', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000108', 1, 1, '{"target_shift_instance_id":"00000001-0000-4000-8000-000000000043","synthetic":true}'::jsonb, '00000001-0000-4000-8000-000000000101', '[{"section_id":"00000001-0000-4000-8000-000000000102","status":"DOCUMENTED","content":"Synthetic shift summary. Open work requires follow-up."},{"section_id":"00000001-0000-4000-8000-000000000103","status":"DOCUMENTED","content":"Ticket #829: IN_PROGRESS. Reported vibration; steps 1–4 recorded complete. Cause remains unverified.\nTicket #910: IN_PROGRESS. Current document reference needs confirmation."}]'::jsonb, '{"source_id":"00000001-0000-4000-8000-000000000064","document_version_id":"00000001-0000-4000-8000-000000000067"}'::jsonb, '00000001-0000-4000-8000-000000000009', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000001-0000-4000-8000-000000000002') + interval '-2 hours');

-- northstar.afternoon-draft
INSERT INTO workweave.shift_handovers (handover_id, organization_id, workspace_id, source_shift_instance_id, target_shift_instance_id, template_version_id, status, created_by_employee_id, context_as_of, context_revisions, draft_sections)
VALUES ('00000001-0000-4000-8000-000000000110', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000043', '00000001-0000-4000-8000-000000000048', '00000001-0000-4000-8000-000000000101', 'DRAFT', '00000001-0000-4000-8000-000000000009', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000001-0000-4000-8000-000000000002') + interval '0 seconds', '{"synthetic":true,"fixture":"review-only-sql-v1","not_real_employee_evidence":true}'::jsonb, '[{"section_id":"00000001-0000-4000-8000-000000000102","status":"DOCUMENTED","content":"Synthetic shift summary. Open work requires follow-up."},{"section_id":"00000001-0000-4000-8000-000000000103","status":"DOCUMENTED","content":"Ticket #829: IN_PROGRESS. Reported vibration; steps 1–4 recorded complete. Cause remains unverified.\nTicket #910: IN_PROGRESS. Current document reference needs confirmation."}]'::jsonb);

-- northstar.handover-item-0
INSERT INTO workweave.handover_items (handover_item_id, organization_id, workspace_id, work_item_id, title, description, originating_shift_instance_id, originating_employee_id, current_owner_shift_instance_id, work_status, acknowledgement_status)
VALUES ('00000001-0000-4000-8000-000000000111', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000089', 'Machine #14 inspection', 'Reported vibration; steps 1–4 recorded complete. Cause remains unverified.', '00000001-0000-4000-8000-000000000038', '00000001-0000-4000-8000-000000000009', '00000001-0000-4000-8000-000000000043', 'IN_PROGRESS', 'NOT_REQUIRED');

-- northstar.morning-entry-0
INSERT INTO workweave.handover_entries (handover_entry_id, organization_id, workspace_id, publication_id, handover_item_id, section_id, snapshot_work_status, snapshot_acknowledgement_status, snapshot_description, snapshot_source_refs)
VALUES ('00000001-0000-4000-8000-000000000112', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000109', '00000001-0000-4000-8000-000000000111', '00000001-0000-4000-8000-000000000103', 'IN_PROGRESS', 'NOT_REQUIRED', 'Reported vibration; steps 1–4 recorded complete. Cause remains unverified.', '["00000001-0000-4000-8000-000000000064"]'::jsonb);

-- northstar.item-source-0
INSERT INTO workweave.handover_item_sources (source_id, organization_id, workspace_id, handover_item_id, source_type, external_system, external_id, source_reference, extracted_data, detected_by_ai, confirmed_by_employee_id)
VALUES ('00000001-0000-4000-8000-000000000113', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000111', 'TICKET', 'synthetic_seed', 'Ticket #829', 'Synthetic work item', '{"synthetic":true,"fixture":"review-only-sql-v1","not_real_employee_evidence":true}'::jsonb, FALSE, '00000001-0000-4000-8000-000000000009');

-- northstar.handover-item-1
INSERT INTO workweave.handover_items (handover_item_id, organization_id, workspace_id, work_item_id, title, description, originating_shift_instance_id, originating_employee_id, current_owner_shift_instance_id, work_status, acknowledgement_status)
VALUES ('00000001-0000-4000-8000-000000000114', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000091', 'Machine #22 document check', 'Current document reference needs confirmation.', '00000001-0000-4000-8000-000000000038', '00000001-0000-4000-8000-000000000009', '00000001-0000-4000-8000-000000000043', 'IN_PROGRESS', 'NOT_REQUIRED');

-- northstar.morning-entry-1
INSERT INTO workweave.handover_entries (handover_entry_id, organization_id, workspace_id, publication_id, handover_item_id, section_id, snapshot_work_status, snapshot_acknowledgement_status, snapshot_description, snapshot_source_refs)
VALUES ('00000001-0000-4000-8000-000000000115', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000109', '00000001-0000-4000-8000-000000000114', '00000001-0000-4000-8000-000000000103', 'IN_PROGRESS', 'NOT_REQUIRED', 'Current document reference needs confirmation.', '["00000001-0000-4000-8000-000000000064"]'::jsonb);

-- northstar.item-source-1
INSERT INTO workweave.handover_item_sources (source_id, organization_id, workspace_id, handover_item_id, source_type, external_system, external_id, source_reference, extracted_data, detected_by_ai, confirmed_by_employee_id)
VALUES ('00000001-0000-4000-8000-000000000116', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000114', 'TICKET', 'synthetic_seed', 'Ticket #910', 'Synthetic work item', '{"synthetic":true,"fixture":"review-only-sql-v1","not_real_employee_evidence":true}'::jsonb, FALSE, '00000001-0000-4000-8000-000000000009');

-- northstar.report-suggestion
INSERT INTO workweave.handover_suggestions (suggestion_id, organization_id, workspace_id, handover_id, handover_item_id, suggestion_type, suggested_data, reason, source_refs, context_revisions, status)
VALUES ('00000001-0000-4000-8000-000000000117', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000110', '00000001-0000-4000-8000-000000000111', 'STALE_INFORMATION', '{"work_event_id":"00000001-0000-4000-8000-000000000098","reported_complete":false,"synthetic":true}'::jsonb, 'Compare the prior-shift report with the draft. Human review required.', '["00000001-0000-4000-8000-000000000098"]'::jsonb, '{"synthetic":true,"fixture":"review-only-sql-v1","not_real_employee_evidence":true}'::jsonb, 'PENDING');

-- northstar.report-source
INSERT INTO workweave.handover_item_sources (source_id, organization_id, workspace_id, suggestion_id, source_type, source_reference, extracted_data, detected_by_ai)
VALUES ('00000001-0000-4000-8000-000000000118', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000117', 'WORK_EVENT', '00000001-0000-4000-8000-000000000098', '{"synthetic":true,"fixture":"review-only-sql-v1","not_real_employee_evidence":true}'::jsonb, FALSE);

-- northstar.email
INSERT INTO workweave.source_records (source_id, organization_id, workspace_id, source_type, owner_employee_id, evidence_type, access_partition, metadata)
VALUES ('00000001-0000-4000-8000-000000000119', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', 'EMAIL', '00000001-0000-4000-8000-000000000009', 'REPORTED', 'TEAM', '{"synthetic":true,"fixture":"review-only-sql-v1","not_real_employee_evidence":true,"subject":"Upcoming team activity","scheduled_at_relative":"+6 hours"}'::jsonb);

-- northstar.email-suggestion
INSERT INTO workweave.handover_suggestions (suggestion_id, organization_id, workspace_id, handover_id, suggestion_type, suggested_data, reason, source_refs, context_revisions, status)
VALUES ('00000001-0000-4000-8000-000000000120', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000110', 'MISSING_ITEM', '{"title":"Upcoming team briefing","section":"Scheduled Activities","time_confirmation":"PENDING","source_id":"00000001-0000-4000-8000-000000000119","synthetic":true}'::jsonb, 'Synthetic email activity does not appear in the draft; review before adding.', '["00000001-0000-4000-8000-000000000119"]'::jsonb, '{"synthetic":true,"fixture":"review-only-sql-v1","not_real_employee_evidence":true}'::jsonb, 'PENDING');

-- northstar.email-source
INSERT INTO workweave.handover_item_sources (source_id, organization_id, workspace_id, suggestion_id, source_type, external_system, external_id, source_reference, extracted_data, detected_by_ai)
VALUES ('00000001-0000-4000-8000-000000000121', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000120', 'EMAIL', 'synthetic_seed', 'MAIL-101', '00000001-0000-4000-8000-000000000119', '{"synthetic":true,"fixture":"review-only-sql-v1","not_real_employee_evidence":true}'::jsonb, FALSE);

-- northstar.kt-consent
INSERT INTO workweave.consent_sessions (consent_session_id, organization_id, workspace_id, purpose, owner_employee_id, notice_version, accepted_at, requested_audience, raw_retention, status)
VALUES ('00000001-0000-4000-8000-000000000122', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', 'EXIT_KT_INTERVIEW', '00000001-0000-4000-8000-000000000009', 'synthetic-notice-v1', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000001-0000-4000-8000-000000000002') + interval '-30 minutes', '{"draft":"OWNER_ONLY","submitted":"DESIGNATED_REVIEWER","approved":"AUTHORIZED_SUCCESSOR"}'::jsonb, '{"days":7,"synthetic":true}'::jsonb, 'ACTIVE');

-- northstar.interview-source
INSERT INTO workweave.source_records (source_id, organization_id, workspace_id, source_type, owner_employee_id, consent_session_id, evidence_type, access_partition, retention_until, metadata)
VALUES ('00000001-0000-4000-8000-000000000123', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', 'INTERVIEW', '00000001-0000-4000-8000-000000000009', '00000001-0000-4000-8000-000000000122', 'REPORTED', 'PRIVATE', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000001-0000-4000-8000-000000000002') + interval '7 days', '{"synthetic":true,"fixture":"review-only-sql-v1","not_real_employee_evidence":true}'::jsonb);

-- northstar.kt-case
INSERT INTO workweave.exit_kt_cases (exit_kt_case_id, organization_id, workspace_id, employee_id, case_kind, status, initiated_by_employee_id, reviewer_employee_id, started_at)
VALUES ('00000001-0000-4000-8000-000000000124', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000009', 'ROLE_TRANSITION', 'IN_PROGRESS', '00000001-0000-4000-8000-000000000011', '00000001-0000-4000-8000-000000000011', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000001-0000-4000-8000-000000000002') + interval '-1 day');

-- northstar.inventory-documented
INSERT INTO workweave.exit_kt_knowledge_items (kt_item_id, organization_id, workspace_id, exit_kt_case_id, title, description, documentation_status, kt_status, risk_level)
VALUES ('00000001-0000-4000-8000-000000000125', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000124', 'Calibration and evidence handling', 'Current approved SOP already exists.', 'DOCUMENTED', 'EXISTING_KNOWLEDGE', 'MEDIUM');

-- northstar.inventory-outdated
INSERT INTO workweave.exit_kt_knowledge_items (kt_item_id, organization_id, workspace_id, exit_kt_case_id, title, description, documentation_status, kt_status, risk_level)
VALUES ('00000001-0000-4000-8000-000000000126', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000124', 'Historical procedure references', 'Historical version appears in older notes; compare against current source.', 'OUTDATED', 'NOT_STARTED', 'MEDIUM');

-- northstar.inventory-missing
INSERT INTO workweave.exit_kt_knowledge_items (kt_item_id, organization_id, workspace_id, exit_kt_case_id, title, description, documentation_status, kt_status, risk_level)
VALUES ('00000001-0000-4000-8000-000000000127', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000124', 'Evidence-based escalation practice', 'Employee reporting practice is not yet approved reusable knowledge.', 'MISSING', 'DRAFT_CREATED', 'HIGH');

-- northstar.kt-doc-source
INSERT INTO workweave.exit_kt_sources (source_id, organization_id, workspace_id, kt_item_id, source_type, source_reference, relevance_data)
VALUES ('00000001-0000-4000-8000-000000000128', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000125', 'DOCUMENT', '00000001-0000-4000-8000-000000000067', '{"synthetic":true,"fixture":"review-only-sql-v1","not_real_employee_evidence":true}'::jsonb);

-- northstar.finding-OUTDATED_DOCUMENTATION
INSERT INTO workweave.exit_kt_findings (finding_id, organization_id, workspace_id, exit_kt_case_id, kt_item_id, finding_type, description, evidence_refs, status)
VALUES ('00000001-0000-4000-8000-000000000129', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000124', '00000001-0000-4000-8000-000000000126', 'OUTDATED_DOCUMENTATION', 'Review the old document reference; it is not proof that current instructions are wrong.', '["00000001-0000-4000-8000-000000000064"]'::jsonb, 'OPEN');

-- northstar.finding-UNDOCUMENTED_KNOWLEDGE
INSERT INTO workweave.exit_kt_findings (finding_id, organization_id, workspace_id, exit_kt_case_id, kt_item_id, finding_type, description, evidence_refs, status)
VALUES ('00000001-0000-4000-8000-000000000130', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000124', '00000001-0000-4000-8000-000000000127', 'UNDOCUMENTED_KNOWLEDGE', 'Reporting practice needs employee review and knowledge approval.', '["00000001-0000-4000-8000-000000000064"]'::jsonb, 'OPEN');

-- northstar.finding-MISSING_SUCCESSOR
INSERT INTO workweave.exit_kt_findings (finding_id, organization_id, workspace_id, exit_kt_case_id, kt_item_id, finding_type, description, evidence_refs, status)
VALUES ('00000001-0000-4000-8000-000000000131', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000124', '00000001-0000-4000-8000-000000000127', 'MISSING_SUCCESSOR', 'A proposed successor is not a completed ownership transfer.', '["00000001-0000-4000-8000-000000000064"]'::jsonb, 'OPEN');

-- northstar.interview
INSERT INTO workweave.exit_kt_interviews (interview_id, organization_id, workspace_id, kt_item_id, employee_id, consent_session_id, status, started_at)
VALUES ('00000001-0000-4000-8000-000000000132', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000127', '00000001-0000-4000-8000-000000000009', '00000001-0000-4000-8000-000000000122', 'PAUSED', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000001-0000-4000-8000-000000000002') + interval '-30 minutes');

-- northstar.interview-question
INSERT INTO workweave.exit_kt_interview_messages (message_id, organization_id, workspace_id, interview_id, sender_type, message_type, content, metadata, source_refs)
VALUES ('00000001-0000-4000-8000-000000000133', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000132', 'AI', 'SCRIPTED_FIXTURE', 'Which current work item and approved source do you include when requesting missing evidence?', '{"synthetic":true,"fixture":"review-only-sql-v1","not_real_employee_evidence":true,"no_model_was_called":true}'::jsonb, '["00000001-0000-4000-8000-000000000064"]'::jsonb);

-- northstar.interview-answer
INSERT INTO workweave.exit_kt_interview_messages (message_id, organization_id, workspace_id, interview_id, sender_type, content, metadata, source_refs)
VALUES ('00000001-0000-4000-8000-000000000134', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000132', 'EMPLOYEE', 'I include the work item and source version, keep the cause unknown, and ask the reviewer to verify the missing evidence.', '{"synthetic":true,"fixture":"review-only-sql-v1","not_real_employee_evidence":true}'::jsonb, '["00000001-0000-4000-8000-000000000123"]'::jsonb);

-- northstar.artifact
INSERT INTO workweave.exit_kt_artifacts (artifact_id, organization_id, workspace_id, kt_item_id, artifact_type, title, generated_from_interview_id)
VALUES ('00000001-0000-4000-8000-000000000135', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000127', 'CHECKLIST', 'Requesting evidence-based clarification', '00000001-0000-4000-8000-000000000132');

-- northstar.artifact-draft
INSERT INTO workweave.exit_kt_artifact_revisions (artifact_revision_id, organization_id, workspace_id, artifact_id, version, content, status, source_refs)
VALUES ('00000001-0000-4000-8000-000000000136', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000135', 1, '# Private synthetic checklist
1. Identify the current work item.
2. Cite the approved source version.
3. State missing evidence and ask the reviewer.

DRAFT: employee review and knowledge approval are pending.', 'DRAFT', '["00000001-0000-4000-8000-000000000123"]'::jsonb);

-- northstar.responsibility
INSERT INTO workweave.responsibilities (responsibility_id, organization_id, workspace_id, responsibility_type, title, owner_employee_id, ownership_revision, description)
VALUES ('00000001-0000-4000-8000-000000000137', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', 'PROCESS', 'Machine #14 maintenance responsibility', '00000001-0000-4000-8000-000000000009', 1, 'Synthetic role responsibility. No transfer has been completed.');

-- northstar.transfer
INSERT INTO workweave.responsibility_transfers (transfer_id, organization_id, workspace_id, exit_kt_case_id, responsibility_id, current_owner_employee_id, recommended_owner_employee_id, recommendation_reason, recommendation_data, status, effective_at, expected_owner_revision)
VALUES ('00000001-0000-4000-8000-000000000138', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000124', '00000001-0000-4000-8000-000000000137', '00000001-0000-4000-8000-000000000009', '00000001-0000-4000-8000-000000000010', 'Synthetic proposed successor; human confirmation and package receipt remain required.', '{"synthetic":true,"fixture":"review-only-sql-v1","not_real_employee_evidence":true}'::jsonb, 'PROPOSED', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000001-0000-4000-8000-000000000002') + interval '1 day', 1);

-- northstar.uncovered-responsibility
INSERT INTO workweave.responsibilities (responsibility_id, organization_id, workspace_id, responsibility_type, title, owner_employee_id, ownership_revision)
VALUES ('00000001-0000-4000-8000-000000000139', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', 'RECURRING_TASK', 'Recurring source-reference review', '00000001-0000-4000-8000-000000000009', 1);

-- northstar.kt-package
INSERT INTO workweave.exit_kt_packages (package_id, organization_id, workspace_id, exit_kt_case_id, successor_employee_id, status, effective_at, context_revisions, draft_sections)
VALUES ('00000001-0000-4000-8000-000000000140', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000124', '00000001-0000-4000-8000-000000000010', 'DRAFT', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000001-0000-4000-8000-000000000002') + interval '1 day', '{"synthetic":true,"fixture":"review-only-sql-v1","not_real_employee_evidence":true}'::jsonb, '[{"title":"Responsibilities","content":"Machine #14 maintenance responsibility"},{"title":"Knowledge gaps","content":"Private checklist awaits employee review and knowledge approval."}]'::jsonb);

-- northstar.package-responsibility
INSERT INTO workweave.exit_kt_package_responsibilities (package_responsibility_id, organization_id, workspace_id, package_id, responsibility_id)
VALUES ('00000001-0000-4000-8000-000000000141', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000140', '00000001-0000-4000-8000-000000000137');

-- northstar.knowledge-checklist
INSERT INTO workweave.kt_checklist_items (checklist_item_id, organization_id, workspace_id, exit_kt_case_id, knowledge_item_id, required, status, evidence_refs)
VALUES ('00000001-0000-4000-8000-000000000142', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000124', '00000001-0000-4000-8000-000000000127', TRUE, 'OPEN', '[]'::jsonb);

-- northstar.responsibility-checklist
INSERT INTO workweave.kt_checklist_items (checklist_item_id, organization_id, workspace_id, exit_kt_case_id, responsibility_id, required, status, evidence_refs)
VALUES ('00000001-0000-4000-8000-000000000143', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000124', '00000001-0000-4000-8000-000000000137', TRUE, 'OPEN', '[]'::jsonb);

-- northstar.seed-audit
INSERT INTO workweave.audit_events (audit_event_id, organization_id, workspace_id, actor_id, action, resource_type, resource_id, resource_revision, result, source_refs, request_id)
VALUES ('00000001-0000-4000-8000-000000000145', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000011', 'SYNTHETIC_FIXTURE_STAGED', 'workspace', '00000001-0000-4000-8000-000000000002', 1, 'REVIEW_ONLY_NO_LIVE_WORKFLOW_COMPLETED', '[]'::jsonb, '00000001-0000-4000-8000-000000000144');


-- HARBOR synthetic fixtures
-- harbor.organization
INSERT INTO workweave.organizations (organization_id, name, industry, company_key)
VALUES ('00000002-0000-4000-8000-000000000001', 'Harbor Support', 'bpo', 'harbor');

-- harbor.workspace
INSERT INTO workweave.workspaces (workspace_id, organization_id, kind, pack_version, clock_anchor, expires_at)
VALUES ('00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000001', 'DEMO', 'review-only-v1', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP + interval '7 days');

-- harbor.scenario
INSERT INTO workweave.scenario_catalog (scenario_id, organization_id, workspace_id, company_key, name, industry, pack_version, content_hash, provenance, status)
VALUES ('00000002-0000-4000-8000-000000000003', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', 'harbor', 'Harbor Support — review fixture', 'bpo', 'review-only-v1', 'synthetic-sql-fixture-not-a-pack-hash', '{"synthetic":true,"fixture":"review-only-sql-v1","not_real_employee_evidence":true}'::jsonb, 'DRAFT');

-- harbor.department
INSERT INTO workweave.departments (department_id, organization_id, workspace_id, name)
VALUES ('00000002-0000-4000-8000-000000000004', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', 'Customer Operations');

-- harbor.team
INSERT INTO workweave.teams (team_id, organization_id, workspace_id, department_id, name)
VALUES ('00000002-0000-4000-8000-000000000005', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000004', 'Customer Support');

-- harbor.worker-role
INSERT INTO workweave.roles (role_id, organization_id, workspace_id, name)
VALUES ('00000002-0000-4000-8000-000000000006', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', 'Support specialist');

-- harbor.manager-role
INSERT INTO workweave.roles (role_id, organization_id, workspace_id, name)
VALUES ('00000002-0000-4000-8000-000000000007', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', 'Knowledge reviewer / manager');

-- harbor.learner
INSERT INTO workweave.employees (employee_id, organization_id, workspace_id, role_id, first_name, last_name, email, employment_status, hire_date)
VALUES ('00000002-0000-4000-8000-000000000008', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000006', 'Nora', 'Santos', 'nora.santos@harbor.example', 'ONBOARDING', CURRENT_DATE - 180);

-- harbor.outgoing
INSERT INTO workweave.employees (employee_id, organization_id, workspace_id, role_id, first_name, last_name, email, employment_status, hire_date)
VALUES ('00000002-0000-4000-8000-000000000009', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000006', 'Leo', 'Cruz', 'leo.cruz@harbor.example', 'ACTIVE', CURRENT_DATE - 180);

-- harbor.incoming
INSERT INTO workweave.employees (employee_id, organization_id, workspace_id, role_id, first_name, last_name, email, employment_status, hire_date)
VALUES ('00000002-0000-4000-8000-000000000010', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000006', 'Mia', 'Reyes', 'mia.reyes@harbor.example', 'ACTIVE', CURRENT_DATE - 180);

-- harbor.reviewer
INSERT INTO workweave.employees (employee_id, organization_id, workspace_id, role_id, first_name, last_name, email, employment_status, hire_date)
VALUES ('00000002-0000-4000-8000-000000000011', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000007', 'Ravi', 'Patel', 'ravi.patel@harbor.example', 'ACTIVE', CURRENT_DATE - 180);

-- harbor.learner-membership
INSERT INTO workweave.employee_team_memberships (membership_id, organization_id, workspace_id, employee_id, team_id, team_role, start_date, is_active)
VALUES ('00000002-0000-4000-8000-000000000012', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000008', '00000002-0000-4000-8000-000000000005', 'MEMBER', CURRENT_DATE - 180, TRUE);

-- harbor.learner-work:read
INSERT INTO workweave.permission_grants (grant_id, organization_id, workspace_id, actor_id, resource_scope, action, valid_from, granted_by)
VALUES ('00000002-0000-4000-8000-000000000013', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000008', '{"team_id":"00000002-0000-4000-8000-000000000005","synthetic":true}'::jsonb, 'work:read', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000002-0000-4000-8000-000000000002') + interval '-1 day', '00000002-0000-4000-8000-000000000011');

-- harbor.learner-work:report
INSERT INTO workweave.permission_grants (grant_id, organization_id, workspace_id, actor_id, resource_scope, action, valid_from, granted_by)
VALUES ('00000002-0000-4000-8000-000000000014', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000008', '{"team_id":"00000002-0000-4000-8000-000000000005","synthetic":true}'::jsonb, 'work:report', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000002-0000-4000-8000-000000000002') + interval '-1 day', '00000002-0000-4000-8000-000000000011');

-- harbor.learner-learning:own
INSERT INTO workweave.permission_grants (grant_id, organization_id, workspace_id, actor_id, resource_scope, action, valid_from, granted_by)
VALUES ('00000002-0000-4000-8000-000000000015', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000008', '{"team_id":"00000002-0000-4000-8000-000000000005","synthetic":true}'::jsonb, 'learning:own', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000002-0000-4000-8000-000000000002') + interval '-1 day', '00000002-0000-4000-8000-000000000011');

-- harbor.learner-exit_kt:own
INSERT INTO workweave.permission_grants (grant_id, organization_id, workspace_id, actor_id, resource_scope, action, valid_from, granted_by)
VALUES ('00000002-0000-4000-8000-000000000016', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000008', '{"team_id":"00000002-0000-4000-8000-000000000005","synthetic":true}'::jsonb, 'exit_kt:own', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000002-0000-4000-8000-000000000002') + interval '-1 day', '00000002-0000-4000-8000-000000000011');

-- harbor.learner-availability
INSERT INTO workweave.employee_availability (availability_id, organization_id, workspace_id, employee_id, start_at, end_at, status, source_reference)
VALUES ('00000002-0000-4000-8000-000000000017', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000008', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000002-0000-4000-8000-000000000002') + interval '-8 hours', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000002-0000-4000-8000-000000000002') + interval '16 hours', 'AVAILABLE', 'Synthetic declared availability, not monitoring');

-- harbor.outgoing-membership
INSERT INTO workweave.employee_team_memberships (membership_id, organization_id, workspace_id, employee_id, team_id, team_role, start_date, is_active)
VALUES ('00000002-0000-4000-8000-000000000018', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000009', '00000002-0000-4000-8000-000000000005', 'SHIFT_LEAD', CURRENT_DATE - 180, TRUE);

-- harbor.outgoing-work:read
INSERT INTO workweave.permission_grants (grant_id, organization_id, workspace_id, actor_id, resource_scope, action, valid_from, granted_by)
VALUES ('00000002-0000-4000-8000-000000000019', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000009', '{"team_id":"00000002-0000-4000-8000-000000000005","synthetic":true}'::jsonb, 'work:read', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000002-0000-4000-8000-000000000002') + interval '-1 day', '00000002-0000-4000-8000-000000000011');

-- harbor.outgoing-work:report
INSERT INTO workweave.permission_grants (grant_id, organization_id, workspace_id, actor_id, resource_scope, action, valid_from, granted_by)
VALUES ('00000002-0000-4000-8000-000000000020', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000009', '{"team_id":"00000002-0000-4000-8000-000000000005","synthetic":true}'::jsonb, 'work:report', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000002-0000-4000-8000-000000000002') + interval '-1 day', '00000002-0000-4000-8000-000000000011');

-- harbor.outgoing-delegation:confirm
INSERT INTO workweave.permission_grants (grant_id, organization_id, workspace_id, actor_id, resource_scope, action, valid_from, granted_by)
VALUES ('00000002-0000-4000-8000-000000000021', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000009', '{"team_id":"00000002-0000-4000-8000-000000000005","synthetic":true}'::jsonb, 'delegation:confirm', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000002-0000-4000-8000-000000000002') + interval '-1 day', '00000002-0000-4000-8000-000000000011');

-- harbor.outgoing-handover:publish
INSERT INTO workweave.permission_grants (grant_id, organization_id, workspace_id, actor_id, resource_scope, action, valid_from, granted_by)
VALUES ('00000002-0000-4000-8000-000000000022', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000009', '{"team_id":"00000002-0000-4000-8000-000000000005","synthetic":true}'::jsonb, 'handover:publish', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000002-0000-4000-8000-000000000002') + interval '-1 day', '00000002-0000-4000-8000-000000000011');

-- harbor.outgoing-handover:suggestion:review
INSERT INTO workweave.permission_grants (grant_id, organization_id, workspace_id, actor_id, resource_scope, action, valid_from, granted_by)
VALUES ('00000002-0000-4000-8000-000000000023', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000009', '{"team_id":"00000002-0000-4000-8000-000000000005","synthetic":true}'::jsonb, 'handover:suggestion:review', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000002-0000-4000-8000-000000000002') + interval '-1 day', '00000002-0000-4000-8000-000000000011');

-- harbor.outgoing-availability
INSERT INTO workweave.employee_availability (availability_id, organization_id, workspace_id, employee_id, start_at, end_at, status, source_reference)
VALUES ('00000002-0000-4000-8000-000000000024', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000009', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000002-0000-4000-8000-000000000002') + interval '-8 hours', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000002-0000-4000-8000-000000000002') + interval '16 hours', 'AVAILABLE', 'Synthetic declared availability, not monitoring');

-- harbor.incoming-membership
INSERT INTO workweave.employee_team_memberships (membership_id, organization_id, workspace_id, employee_id, team_id, team_role, start_date, is_active)
VALUES ('00000002-0000-4000-8000-000000000025', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000010', '00000002-0000-4000-8000-000000000005', 'MEMBER', CURRENT_DATE - 180, TRUE);

-- harbor.incoming-work:read
INSERT INTO workweave.permission_grants (grant_id, organization_id, workspace_id, actor_id, resource_scope, action, valid_from, granted_by)
VALUES ('00000002-0000-4000-8000-000000000026', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000010', '{"team_id":"00000002-0000-4000-8000-000000000005","synthetic":true}'::jsonb, 'work:read', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000002-0000-4000-8000-000000000002') + interval '-1 day', '00000002-0000-4000-8000-000000000011');

-- harbor.incoming-work:report
INSERT INTO workweave.permission_grants (grant_id, organization_id, workspace_id, actor_id, resource_scope, action, valid_from, granted_by)
VALUES ('00000002-0000-4000-8000-000000000027', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000010', '{"team_id":"00000002-0000-4000-8000-000000000005","synthetic":true}'::jsonb, 'work:report', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000002-0000-4000-8000-000000000002') + interval '-1 day', '00000002-0000-4000-8000-000000000011');

-- harbor.incoming-learning:own
INSERT INTO workweave.permission_grants (grant_id, organization_id, workspace_id, actor_id, resource_scope, action, valid_from, granted_by)
VALUES ('00000002-0000-4000-8000-000000000028', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000010', '{"team_id":"00000002-0000-4000-8000-000000000005","synthetic":true}'::jsonb, 'learning:own', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000002-0000-4000-8000-000000000002') + interval '-1 day', '00000002-0000-4000-8000-000000000011');

-- harbor.incoming-exit_kt:own
INSERT INTO workweave.permission_grants (grant_id, organization_id, workspace_id, actor_id, resource_scope, action, valid_from, granted_by)
VALUES ('00000002-0000-4000-8000-000000000029', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000010', '{"team_id":"00000002-0000-4000-8000-000000000005","synthetic":true}'::jsonb, 'exit_kt:own', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000002-0000-4000-8000-000000000002') + interval '-1 day', '00000002-0000-4000-8000-000000000011');

-- harbor.incoming-availability
INSERT INTO workweave.employee_availability (availability_id, organization_id, workspace_id, employee_id, start_at, end_at, status, source_reference)
VALUES ('00000002-0000-4000-8000-000000000030', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000010', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000002-0000-4000-8000-000000000002') + interval '-8 hours', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000002-0000-4000-8000-000000000002') + interval '16 hours', 'AVAILABLE', 'Synthetic declared availability, not monitoring');

-- harbor.reviewer-membership
INSERT INTO workweave.employee_team_memberships (membership_id, organization_id, workspace_id, employee_id, team_id, team_role, start_date, is_active)
VALUES ('00000002-0000-4000-8000-000000000031', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000011', '00000002-0000-4000-8000-000000000005', 'MANAGER', CURRENT_DATE - 180, TRUE);

-- harbor.reviewer-work:read
INSERT INTO workweave.permission_grants (grant_id, organization_id, workspace_id, actor_id, resource_scope, action, valid_from, granted_by)
VALUES ('00000002-0000-4000-8000-000000000032', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000011', '{"team_id":"00000002-0000-4000-8000-000000000005","synthetic":true}'::jsonb, 'work:read', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000002-0000-4000-8000-000000000002') + interval '-1 day', '00000002-0000-4000-8000-000000000011');

-- harbor.reviewer-knowledge:review
INSERT INTO workweave.permission_grants (grant_id, organization_id, workspace_id, actor_id, resource_scope, action, valid_from, granted_by)
VALUES ('00000002-0000-4000-8000-000000000033', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000011', '{"team_id":"00000002-0000-4000-8000-000000000005","synthetic":true}'::jsonb, 'knowledge:review', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000002-0000-4000-8000-000000000002') + interval '-1 day', '00000002-0000-4000-8000-000000000011');

-- harbor.reviewer-exit_kt:review
INSERT INTO workweave.permission_grants (grant_id, organization_id, workspace_id, actor_id, resource_scope, action, valid_from, granted_by)
VALUES ('00000002-0000-4000-8000-000000000034', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000011', '{"team_id":"00000002-0000-4000-8000-000000000005","synthetic":true}'::jsonb, 'exit_kt:review', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000002-0000-4000-8000-000000000002') + interval '-1 day', '00000002-0000-4000-8000-000000000011');

-- harbor.reviewer-responsibility:transfer
INSERT INTO workweave.permission_grants (grant_id, organization_id, workspace_id, actor_id, resource_scope, action, valid_from, granted_by)
VALUES ('00000002-0000-4000-8000-000000000035', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000011', '{"team_id":"00000002-0000-4000-8000-000000000005","synthetic":true}'::jsonb, 'responsibility:transfer', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000002-0000-4000-8000-000000000002') + interval '-1 day', '00000002-0000-4000-8000-000000000011');

-- harbor.reviewer-availability
INSERT INTO workweave.employee_availability (availability_id, organization_id, workspace_id, employee_id, start_at, end_at, status, source_reference)
VALUES ('00000002-0000-4000-8000-000000000036', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000011', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000002-0000-4000-8000-000000000002') + interval '-8 hours', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000002-0000-4000-8000-000000000002') + interval '16 hours', 'AVAILABLE', 'Synthetic declared availability, not monitoring');

-- harbor.Morning-shift
INSERT INTO workweave.shifts (shift_id, organization_id, workspace_id, team_id, name, start_time, end_time, timezone)
VALUES ('00000002-0000-4000-8000-000000000037', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000005', 'Morning', '07:00', '15:00', 'Asia/Manila');

-- harbor.Morning-instance
INSERT INTO workweave.shift_instances (shift_instance_id, organization_id, workspace_id, shift_id, shift_date, scheduled_start_at, scheduled_end_at, shift_lead_employee_id, status)
VALUES ('00000002-0000-4000-8000-000000000038', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000037', ((SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000002-0000-4000-8000-000000000002') AT TIME ZONE 'Asia/Manila')::date, (date_trunc('day', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000002-0000-4000-8000-000000000002') AT TIME ZONE 'Asia/Manila') + time '07:00') AT TIME ZONE 'Asia/Manila', (date_trunc('day', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000002-0000-4000-8000-000000000002') AT TIME ZONE 'Asia/Manila') + time '15:00') AT TIME ZONE 'Asia/Manila', '00000002-0000-4000-8000-000000000009', 'COMPLETED');

-- harbor.Morning-learner
INSERT INTO workweave.shift_instance_memberships (shift_membership_id, organization_id, workspace_id, shift_instance_id, employee_id, membership_role, availability_status)
VALUES ('00000002-0000-4000-8000-000000000039', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000038', '00000002-0000-4000-8000-000000000008', 'MEMBER', 'AVAILABLE');

-- harbor.Morning-outgoing
INSERT INTO workweave.shift_instance_memberships (shift_membership_id, organization_id, workspace_id, shift_instance_id, employee_id, membership_role, availability_status)
VALUES ('00000002-0000-4000-8000-000000000040', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000038', '00000002-0000-4000-8000-000000000009', 'SHIFT_LEAD', 'AVAILABLE');

-- harbor.Morning-incoming
INSERT INTO workweave.shift_instance_memberships (shift_membership_id, organization_id, workspace_id, shift_instance_id, employee_id, membership_role, availability_status)
VALUES ('00000002-0000-4000-8000-000000000041', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000038', '00000002-0000-4000-8000-000000000010', 'MEMBER', 'AVAILABLE');

-- harbor.Afternoon-shift
INSERT INTO workweave.shifts (shift_id, organization_id, workspace_id, team_id, name, start_time, end_time, timezone)
VALUES ('00000002-0000-4000-8000-000000000042', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000005', 'Afternoon', '15:00', '23:00', 'Asia/Manila');

-- harbor.Afternoon-instance
INSERT INTO workweave.shift_instances (shift_instance_id, organization_id, workspace_id, shift_id, shift_date, scheduled_start_at, scheduled_end_at, shift_lead_employee_id, status)
VALUES ('00000002-0000-4000-8000-000000000043', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000042', ((SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000002-0000-4000-8000-000000000002') AT TIME ZONE 'Asia/Manila')::date, (date_trunc('day', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000002-0000-4000-8000-000000000002') AT TIME ZONE 'Asia/Manila') + time '15:00') AT TIME ZONE 'Asia/Manila', (date_trunc('day', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000002-0000-4000-8000-000000000002') AT TIME ZONE 'Asia/Manila') + time '23:00') AT TIME ZONE 'Asia/Manila', '00000002-0000-4000-8000-000000000009', 'ACTIVE');

-- harbor.Afternoon-learner
INSERT INTO workweave.shift_instance_memberships (shift_membership_id, organization_id, workspace_id, shift_instance_id, employee_id, membership_role, availability_status)
VALUES ('00000002-0000-4000-8000-000000000044', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000043', '00000002-0000-4000-8000-000000000008', 'MEMBER', 'AVAILABLE');

-- harbor.Afternoon-outgoing
INSERT INTO workweave.shift_instance_memberships (shift_membership_id, organization_id, workspace_id, shift_instance_id, employee_id, membership_role, availability_status)
VALUES ('00000002-0000-4000-8000-000000000045', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000043', '00000002-0000-4000-8000-000000000009', 'SHIFT_LEAD', 'AVAILABLE');

-- harbor.Afternoon-incoming
INSERT INTO workweave.shift_instance_memberships (shift_membership_id, organization_id, workspace_id, shift_instance_id, employee_id, membership_role, availability_status)
VALUES ('00000002-0000-4000-8000-000000000046', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000043', '00000002-0000-4000-8000-000000000010', 'MEMBER', 'AVAILABLE');

-- harbor.Evening-shift
INSERT INTO workweave.shifts (shift_id, organization_id, workspace_id, team_id, name, start_time, end_time, timezone)
VALUES ('00000002-0000-4000-8000-000000000047', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000005', 'Evening', '23:00', '07:00', 'Asia/Manila');

-- harbor.Evening-instance
INSERT INTO workweave.shift_instances (shift_instance_id, organization_id, workspace_id, shift_id, shift_date, scheduled_start_at, scheduled_end_at, shift_lead_employee_id, status)
VALUES ('00000002-0000-4000-8000-000000000048', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000047', ((SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000002-0000-4000-8000-000000000002') AT TIME ZONE 'Asia/Manila')::date, (date_trunc('day', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000002-0000-4000-8000-000000000002') AT TIME ZONE 'Asia/Manila') + time '23:00') AT TIME ZONE 'Asia/Manila', (date_trunc('day', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000002-0000-4000-8000-000000000002') AT TIME ZONE 'Asia/Manila') + interval '1 day' + time '07:00') AT TIME ZONE 'Asia/Manila', '00000002-0000-4000-8000-000000000009', 'SCHEDULED');

-- harbor.Evening-learner
INSERT INTO workweave.shift_instance_memberships (shift_membership_id, organization_id, workspace_id, shift_instance_id, employee_id, membership_role, availability_status)
VALUES ('00000002-0000-4000-8000-000000000049', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000048', '00000002-0000-4000-8000-000000000008', 'MEMBER', 'AVAILABLE');

-- harbor.Evening-outgoing
INSERT INTO workweave.shift_instance_memberships (shift_membership_id, organization_id, workspace_id, shift_instance_id, employee_id, membership_role, availability_status)
VALUES ('00000002-0000-4000-8000-000000000050', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000048', '00000002-0000-4000-8000-000000000009', 'SHIFT_LEAD', 'AVAILABLE');

-- harbor.Evening-incoming
INSERT INTO workweave.shift_instance_memberships (shift_membership_id, organization_id, workspace_id, shift_instance_id, employee_id, membership_role, availability_status)
VALUES ('00000002-0000-4000-8000-000000000051', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000048', '00000002-0000-4000-8000-000000000010', 'MEMBER', 'AVAILABLE');

-- harbor.account_escalation
INSERT INTO workweave.competencies (competency_id, organization_id, workspace_id, code, name, category)
VALUES ('00000002-0000-4000-8000-000000000052', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', 'account_escalation', 'account escalation', 'bpo');

-- harbor.case_documentation
INSERT INTO workweave.competencies (competency_id, organization_id, workspace_id, code, name, category)
VALUES ('00000002-0000-4000-8000-000000000053', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', 'case_documentation', 'case documentation', 'bpo');

-- harbor.customer_privacy
INSERT INTO workweave.competencies (competency_id, organization_id, workspace_id, code, name, category)
VALUES ('00000002-0000-4000-8000-000000000054', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', 'customer_privacy', 'customer privacy', 'bpo');

-- harbor.role-00000002-0000-4000-8000-000000000052
INSERT INTO workweave.role_competency_requirements (requirement_id, organization_id, workspace_id, role_id, competency_id, required_level, is_mandatory)
VALUES ('00000002-0000-4000-8000-000000000055', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000006', '00000002-0000-4000-8000-000000000052', 1, TRUE);

-- harbor.role-00000002-0000-4000-8000-000000000053
INSERT INTO workweave.role_competency_requirements (requirement_id, organization_id, workspace_id, role_id, competency_id, required_level, is_mandatory)
VALUES ('00000002-0000-4000-8000-000000000056', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000006', '00000002-0000-4000-8000-000000000053', 1, TRUE);

-- harbor.role-00000002-0000-4000-8000-000000000054
INSERT INTO workweave.role_competency_requirements (requirement_id, organization_id, workspace_id, role_id, competency_id, required_level, is_mandatory)
VALUES ('00000002-0000-4000-8000-000000000057', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000006', '00000002-0000-4000-8000-000000000054', 1, TRUE);

-- harbor.evidence-00000002-0000-4000-8000-000000000009-0
INSERT INTO workweave.employee_competency_evidence (evidence_id, organization_id, workspace_id, employee_id, competency_id, evidence_type, source_type, description, metadata, observed_at, validation_status, validated_by)
VALUES ('00000002-0000-4000-8000-000000000058', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000009', '00000002-0000-4000-8000-000000000052', 'SUPERVISOR_VALIDATION', 'MANUAL', 'Synthetic baseline validation for scenario review; not a real assessment.', '{"synthetic":true,"fixture":"review-only-sql-v1","not_real_employee_evidence":true}'::jsonb, (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000002-0000-4000-8000-000000000002') + interval '-7 days', 'VALIDATED', '00000002-0000-4000-8000-000000000011');

-- harbor.state-00000002-0000-4000-8000-000000000009-0
INSERT INTO workweave.employee_competency_state (employee_competency_state_id, organization_id, workspace_id, employee_id, competency_id, current_level, last_evaluated_at, policy_version, evidence_refs)
VALUES ('00000002-0000-4000-8000-000000000059', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000009', '00000002-0000-4000-8000-000000000052', 2, (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000002-0000-4000-8000-000000000002') + interval '-7 days', 'synthetic-setup-v1', '["00000002-0000-4000-8000-000000000058"]'::jsonb);

-- harbor.evidence-00000002-0000-4000-8000-000000000009-1
INSERT INTO workweave.employee_competency_evidence (evidence_id, organization_id, workspace_id, employee_id, competency_id, evidence_type, source_type, description, metadata, observed_at, validation_status, validated_by)
VALUES ('00000002-0000-4000-8000-000000000060', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000009', '00000002-0000-4000-8000-000000000053', 'SUPERVISOR_VALIDATION', 'MANUAL', 'Synthetic baseline validation for scenario review; not a real assessment.', '{"synthetic":true,"fixture":"review-only-sql-v1","not_real_employee_evidence":true}'::jsonb, (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000002-0000-4000-8000-000000000002') + interval '-7 days', 'VALIDATED', '00000002-0000-4000-8000-000000000011');

-- harbor.state-00000002-0000-4000-8000-000000000009-1
INSERT INTO workweave.employee_competency_state (employee_competency_state_id, organization_id, workspace_id, employee_id, competency_id, current_level, last_evaluated_at, policy_version, evidence_refs)
VALUES ('00000002-0000-4000-8000-000000000061', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000009', '00000002-0000-4000-8000-000000000053', 2, (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000002-0000-4000-8000-000000000002') + interval '-7 days', 'synthetic-setup-v1', '["00000002-0000-4000-8000-000000000060"]'::jsonb);

-- harbor.evidence-00000002-0000-4000-8000-000000000010-2
INSERT INTO workweave.employee_competency_evidence (evidence_id, organization_id, workspace_id, employee_id, competency_id, evidence_type, source_type, description, metadata, observed_at, validation_status, validated_by)
VALUES ('00000002-0000-4000-8000-000000000062', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000010', '00000002-0000-4000-8000-000000000054', 'SUPERVISOR_VALIDATION', 'MANUAL', 'Synthetic baseline validation for scenario review; not a real assessment.', '{"synthetic":true,"fixture":"review-only-sql-v1","not_real_employee_evidence":true}'::jsonb, (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000002-0000-4000-8000-000000000002') + interval '-7 days', 'VALIDATED', '00000002-0000-4000-8000-000000000011');

-- harbor.state-00000002-0000-4000-8000-000000000010-2
INSERT INTO workweave.employee_competency_state (employee_competency_state_id, organization_id, workspace_id, employee_id, competency_id, current_level, last_evaluated_at, policy_version, evidence_refs)
VALUES ('00000002-0000-4000-8000-000000000063', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000010', '00000002-0000-4000-8000-000000000054', 2, (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000002-0000-4000-8000-000000000002') + interval '-7 days', 'synthetic-setup-v1', '["00000002-0000-4000-8000-000000000062"]'::jsonb);

-- harbor.sop-source
INSERT INTO workweave.source_records (source_id, organization_id, workspace_id, source_type, evidence_type, access_partition, metadata)
VALUES ('00000002-0000-4000-8000-000000000064', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', 'APPROVED_EXCERPT', 'REPORTED', 'ORGANIZATION', '{"synthetic":true,"fixture":"review-only-sql-v1","not_real_employee_evidence":true}'::jsonb);

-- harbor.sop
INSERT INTO workweave.knowledge_documents (document_id, organization_id, workspace_id, document_code, title, document_type)
VALUES ('00000002-0000-4000-8000-000000000065', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', 'BPO-SOP-001', 'Customer account escalation', 'SOP');

-- harbor.sop-historical
INSERT INTO workweave.knowledge_document_versions (document_version_id, organization_id, workspace_id, document_id, version, content, source_id, approval_status, temporal_status, effective_at, approved_by_employee_id, approved_at)
VALUES ('00000002-0000-4000-8000-000000000066', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000065', '1.0', '# Historical synthetic reference
Superseded; not current instructions.', '00000002-0000-4000-8000-000000000064', 'APPROVED', 'SUPERSEDED', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000002-0000-4000-8000-000000000002') + interval '-60 days', '00000002-0000-4000-8000-000000000011', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000002-0000-4000-8000-000000000002') + interval '-61 days');

-- harbor.sop-current
INSERT INTO workweave.knowledge_document_versions (document_version_id, organization_id, workspace_id, document_id, version, content, source_id, approval_status, temporal_status, effective_at, approved_by_employee_id, approved_at)
VALUES ('00000002-0000-4000-8000-000000000067', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000065', '1.1', '# BPO-SOP-001: Customer account escalation

## 1. Fundamentals

### 1. Use the approved account guide
Use the current approved source, not a familiar historical version. This text is a synthetic training fixture.

### 2. Separate customer reports from verified facts
Keep reported and verified facts separate. An earlier incident cannot prove a current cause. No operational action is authorized by this fixture.

### 3. Escalate without exposing private data
Name the current work item and approved source version. State missing evidence and ask the authorized reviewer for clarification. Do not invent company procedures.', '00000002-0000-4000-8000-000000000064', 'APPROVED', 'CURRENT', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000002-0000-4000-8000-000000000002') + interval '-7 days', '00000002-0000-4000-8000-000000000011', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000002-0000-4000-8000-000000000002') + interval '-8 days');

-- harbor.curriculum
INSERT INTO workweave.curricula (curriculum_id, organization_id, workspace_id, name, version, status, published_at, completion_policy_version)
VALUES ('00000002-0000-4000-8000-000000000068', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', 'Account Support Fundamentals', '1.0', 'PUBLISHED', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000002-0000-4000-8000-000000000002') + interval '-1 day', 'synthetic-objective-v1');

-- harbor.topic
INSERT INTO workweave.curriculum_topics (topic_id, organization_id, workspace_id, curriculum_id, name, order_index)
VALUES ('00000002-0000-4000-8000-000000000069', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000068', 'Account Support Fundamentals', 1);

-- harbor.subtopic-0
INSERT INTO workweave.curriculum_subtopics (subtopic_id, organization_id, workspace_id, topic_id, name, order_index)
VALUES ('00000002-0000-4000-8000-000000000070', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000069', 'Use the approved account guide', 1);

-- harbor.objective-0
INSERT INTO workweave.learning_objectives (objective_id, organization_id, workspace_id, subtopic_id, description, assessment_criteria, criteria_version, required, hint_policy, competency_id)
VALUES ('00000002-0000-4000-8000-000000000071', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000070', 'Demonstrate use the approved account guide.', '{"required_checks":["use_current_approved_evidence","keep_unknowns_explicit"],"synthetic":true}'::jsonb, 'synthetic-criteria-v1', TRUE, '{"hinted_answers":"FORMATIVE_ONLY"}'::jsonb, '00000002-0000-4000-8000-000000000052');

-- harbor.chunk-0
INSERT INTO workweave.knowledge_chunks (chunk_id, organization_id, workspace_id, document_version_id, source_id, section_path, heading, content, chunk_index, source_span, metadata)
VALUES ('00000002-0000-4000-8000-000000000072', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000067', '00000002-0000-4000-8000-000000000064', '["Fundamentals","Use the approved account guide"]'::jsonb, 'Use the approved account guide', '### 1. Use the approved account guide
Use the current approved source, not a familiar historical version. This text is a synthetic training fixture.', 0, '{"heading":"Use the approved account guide","synthetic":true}'::jsonb, '{"synthetic":true,"fixture":"review-only-sql-v1","not_real_employee_evidence":true}'::jsonb);

-- harbor.mapping-0
INSERT INTO workweave.knowledge_mappings (mapping_id, organization_id, workspace_id, document_id, document_version_id, section_ref, entity_type, entity_id, relationship_type)
VALUES ('00000002-0000-4000-8000-000000000073', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000065', '00000002-0000-4000-8000-000000000067', 'Use the approved account guide', 'CURRICULUM_SUBTOPIC', '00000002-0000-4000-8000-000000000070', 'TEACHES');

-- harbor.subtopic-1
INSERT INTO workweave.curriculum_subtopics (subtopic_id, organization_id, workspace_id, topic_id, name, order_index)
VALUES ('00000002-0000-4000-8000-000000000074', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000069', 'Separate customer reports from verified facts', 2);

-- harbor.objective-1
INSERT INTO workweave.learning_objectives (objective_id, organization_id, workspace_id, subtopic_id, description, assessment_criteria, criteria_version, required, hint_policy, competency_id)
VALUES ('00000002-0000-4000-8000-000000000075', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000074', 'Demonstrate separate customer reports from verified facts.', '{"required_checks":["use_current_approved_evidence","keep_unknowns_explicit"],"synthetic":true}'::jsonb, 'synthetic-criteria-v1', TRUE, '{"hinted_answers":"FORMATIVE_ONLY"}'::jsonb, '00000002-0000-4000-8000-000000000053');

-- harbor.chunk-1
INSERT INTO workweave.knowledge_chunks (chunk_id, organization_id, workspace_id, document_version_id, source_id, section_path, heading, content, chunk_index, source_span, metadata)
VALUES ('00000002-0000-4000-8000-000000000076', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000067', '00000002-0000-4000-8000-000000000064', '["Fundamentals","Separate customer reports from verified facts"]'::jsonb, 'Separate customer reports from verified facts', '### 2. Separate customer reports from verified facts
Keep reported and verified facts separate. An earlier incident cannot prove a current cause. No operational action is authorized by this fixture.', 1, '{"heading":"Separate customer reports from verified facts","synthetic":true}'::jsonb, '{"synthetic":true,"fixture":"review-only-sql-v1","not_real_employee_evidence":true}'::jsonb);

-- harbor.mapping-1
INSERT INTO workweave.knowledge_mappings (mapping_id, organization_id, workspace_id, document_id, document_version_id, section_ref, entity_type, entity_id, relationship_type)
VALUES ('00000002-0000-4000-8000-000000000077', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000065', '00000002-0000-4000-8000-000000000067', 'Separate customer reports from verified facts', 'CURRICULUM_SUBTOPIC', '00000002-0000-4000-8000-000000000074', 'TEACHES');

-- harbor.prereq-1
INSERT INTO workweave.curriculum_prerequisites (prerequisite_id, organization_id, workspace_id, subtopic_id, prerequisite_subtopic_id)
VALUES ('00000002-0000-4000-8000-000000000078', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000074', '00000002-0000-4000-8000-000000000070');

-- harbor.subtopic-2
INSERT INTO workweave.curriculum_subtopics (subtopic_id, organization_id, workspace_id, topic_id, name, order_index)
VALUES ('00000002-0000-4000-8000-000000000079', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000069', 'Escalate without exposing private data', 3);

-- harbor.objective-2
INSERT INTO workweave.learning_objectives (objective_id, organization_id, workspace_id, subtopic_id, description, assessment_criteria, criteria_version, required, hint_policy, competency_id)
VALUES ('00000002-0000-4000-8000-000000000080', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000079', 'Demonstrate escalate without exposing private data.', '{"required_checks":["use_current_approved_evidence","keep_unknowns_explicit"],"synthetic":true}'::jsonb, 'synthetic-criteria-v1', TRUE, '{"hinted_answers":"FORMATIVE_ONLY"}'::jsonb, '00000002-0000-4000-8000-000000000054');

-- harbor.chunk-2
INSERT INTO workweave.knowledge_chunks (chunk_id, organization_id, workspace_id, document_version_id, source_id, section_path, heading, content, chunk_index, source_span, metadata)
VALUES ('00000002-0000-4000-8000-000000000081', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000067', '00000002-0000-4000-8000-000000000064', '["Fundamentals","Escalate without exposing private data"]'::jsonb, 'Escalate without exposing private data', '### 3. Escalate without exposing private data
Name the current work item and approved source version. State missing evidence and ask the authorized reviewer for clarification. Do not invent company procedures.', 2, '{"heading":"Escalate without exposing private data","synthetic":true}'::jsonb, '{"synthetic":true,"fixture":"review-only-sql-v1","not_real_employee_evidence":true}'::jsonb);

-- harbor.mapping-2
INSERT INTO workweave.knowledge_mappings (mapping_id, organization_id, workspace_id, document_id, document_version_id, section_ref, entity_type, entity_id, relationship_type)
VALUES ('00000002-0000-4000-8000-000000000082', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000065', '00000002-0000-4000-8000-000000000067', 'Escalate without exposing private data', 'CURRICULUM_SUBTOPIC', '00000002-0000-4000-8000-000000000079', 'TEACHES');

-- harbor.prereq-2
INSERT INTO workweave.curriculum_prerequisites (prerequisite_id, organization_id, workspace_id, subtopic_id, prerequisite_subtopic_id)
VALUES ('00000002-0000-4000-8000-000000000083', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000079', '00000002-0000-4000-8000-000000000074');

-- harbor.learner-curriculum
INSERT INTO workweave.curriculum_assignments (assignment_id, organization_id, workspace_id, curriculum_id, employee_id, assigned_at, assigned_by_employee_id)
VALUES ('00000002-0000-4000-8000-000000000084', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000068', '00000002-0000-4000-8000-000000000008', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000002-0000-4000-8000-000000000002') + interval '0 seconds', '00000002-0000-4000-8000-000000000011');

-- harbor.learner-assignment
INSERT INTO workweave.learning_assignments (learning_assignment_id, organization_id, workspace_id, employee_id, curriculum_id, originating_assignment_id, assignment_kind)
VALUES ('00000002-0000-4000-8000-000000000085', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000008', '00000002-0000-4000-8000-000000000068', '00000002-0000-4000-8000-000000000084', 'INITIAL');

-- harbor.learner-progress-0
INSERT INTO workweave.employee_learning_progress (progress_id, organization_id, workspace_id, employee_id, learning_assignment_id, subtopic_id, status)
VALUES ('00000002-0000-4000-8000-000000000086', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000008', '00000002-0000-4000-8000-000000000085', '00000002-0000-4000-8000-000000000070', 'NOT_STARTED');

-- harbor.learner-progress-1
INSERT INTO workweave.employee_learning_progress (progress_id, organization_id, workspace_id, employee_id, learning_assignment_id, subtopic_id, status)
VALUES ('00000002-0000-4000-8000-000000000087', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000008', '00000002-0000-4000-8000-000000000085', '00000002-0000-4000-8000-000000000074', 'NOT_STARTED');

-- harbor.learner-progress-2
INSERT INTO workweave.employee_learning_progress (progress_id, organization_id, workspace_id, employee_id, learning_assignment_id, subtopic_id, status)
VALUES ('00000002-0000-4000-8000-000000000088', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000008', '00000002-0000-4000-8000-000000000085', '00000002-0000-4000-8000-000000000079', 'NOT_STARTED');

-- harbor.work-0
INSERT INTO workweave.work_items (work_item_id, organization_id, workspace_id, external_system, external_id, work_item_type, title, description, priority, status, due_at, metadata)
VALUES ('00000002-0000-4000-8000-000000000089', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', 'synthetic_seed', 'CASE-104', 'TICKET', 'Billing clarification', 'Customer reports a disputed amount. Verification is pending; do not assert a confirmed billing fault.', 'HIGH', 'IN_PROGRESS', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000002-0000-4000-8000-000000000002') + interval '2 hours', '{"synthetic":true,"fixture":"review-only-sql-v1","not_real_employee_evidence":true}'::jsonb);

-- harbor.requirement-0
INSERT INTO workweave.work_item_competency_requirements (id, organization_id, workspace_id, work_item_id, competency_id, required_level, importance)
VALUES ('00000002-0000-4000-8000-000000000090', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000089', '00000002-0000-4000-8000-000000000052', 1, 1);

-- harbor.work-1
INSERT INTO workweave.work_items (work_item_id, organization_id, workspace_id, external_system, external_id, work_item_type, title, description, priority, status, due_at, metadata)
VALUES ('00000002-0000-4000-8000-000000000091', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', 'synthetic_seed', 'ACT-105', 'ACTIVITY', 'Account escalation refresher', 'A team refresher is scheduled; the session time needs confirmation.', 'MEDIUM', 'ACTIVE', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000002-0000-4000-8000-000000000002') + interval '6 hours', '{"synthetic":true,"fixture":"review-only-sql-v1","not_real_employee_evidence":true}'::jsonb);

-- harbor.requirement-1
INSERT INTO workweave.work_item_competency_requirements (id, organization_id, workspace_id, work_item_id, competency_id, required_level, importance)
VALUES ('00000002-0000-4000-8000-000000000092', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000091', '00000002-0000-4000-8000-000000000053', 1, 1);

-- harbor.work-session
INSERT INTO workweave.work_sessions (work_session_id, organization_id, workspace_id, employee_id, shift_instance_id, started_at, status)
VALUES ('00000002-0000-4000-8000-000000000093', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000009', '00000002-0000-4000-8000-000000000043', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000002-0000-4000-8000-000000000002') + interval '0 seconds', 'ACTIVE');

-- harbor.proposal
INSERT INTO workweave.delegation_proposals (delegation_proposal_id, organization_id, workspace_id, shift_instance_id, team_id, created_by, status, context_revisions)
VALUES ('00000002-0000-4000-8000-000000000094', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000043', '00000002-0000-4000-8000-000000000005', '00000002-0000-4000-8000-000000000009', 'PROPOSED', '{"synthetic":true,"team_revision":1}'::jsonb);

-- harbor.proposal-item-0
INSERT INTO workweave.delegation_proposal_items (proposal_item_id, organization_id, workspace_id, delegation_proposal_id, work_item_id, recommended_employee_id, recommendation_reason, match_data)
VALUES ('00000002-0000-4000-8000-000000000095', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000094', '00000002-0000-4000-8000-000000000089', '00000002-0000-4000-8000-000000000010', 'Synthetic proposed match from validated baseline evidence and declared availability; needs human confirmation.', '{"synthetic":true,"fixture":"review-only-sql-v1","not_real_employee_evidence":true}'::jsonb);

-- harbor.proposal-item-1
INSERT INTO workweave.delegation_proposal_items (proposal_item_id, organization_id, workspace_id, delegation_proposal_id, work_item_id, recommended_employee_id, recommendation_reason, match_data)
VALUES ('00000002-0000-4000-8000-000000000096', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000094', '00000002-0000-4000-8000-000000000091', '00000002-0000-4000-8000-000000000009', 'Synthetic proposed match from validated baseline evidence and declared availability; needs human confirmation.', '{"synthetic":true,"fixture":"review-only-sql-v1","not_real_employee_evidence":true}'::jsonb);

-- harbor.historical-assignment
INSERT INTO workweave.work_item_assignments (assignment_id, organization_id, workspace_id, work_item_id, employee_id, assigned_by_employee_id, assignment_source, status, assigned_at)
VALUES ('00000002-0000-4000-8000-000000000097', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000089', '00000002-0000-4000-8000-000000000009', '00000002-0000-4000-8000-000000000009', 'MANUAL', 'CANCELLED', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000002-0000-4000-8000-000000000002') + interval '-8 hours');

-- harbor.member-report
INSERT INTO workweave.work_events (work_event_id, organization_id, workspace_id, work_item_id, employee_id, shift_instance_id, event_type, description, event_data, evidence_refs, observed_at)
VALUES ('00000002-0000-4000-8000-000000000098', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000089', '00000002-0000-4000-8000-000000000009', '00000002-0000-4000-8000-000000000038', 'COMMENTED', 'Partial progress was reported; missing evidence and current cause remain unknown.', '{"synthetic":true,"fixture":"review-only-sql-v1","not_real_employee_evidence":true,"prior_assignment_ended":true}'::jsonb, '["00000002-0000-4000-8000-000000000064"]'::jsonb, (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000002-0000-4000-8000-000000000002') + interval '-1 hour');

-- harbor.lead-work-state
INSERT INTO workweave.employee_work_state (employee_work_state_id, organization_id, workspace_id, employee_id, shift_instance_id, work_context_key, workload_state, active_work_count, blocked_work_count, metadata)
VALUES ('00000002-0000-4000-8000-000000000099', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000009', '00000002-0000-4000-8000-000000000043', 'shift:00000002-0000-4000-8000-000000000043', 'NEEDS_FOCUS', 2, 0, '{"synthetic":true,"fixture":"review-only-sql-v1","not_real_employee_evidence":true,"derived_from_current_items":true}'::jsonb);

-- harbor.template
INSERT INTO workweave.handover_templates (template_id, organization_id, workspace_id, team_id, name, is_default)
VALUES ('00000002-0000-4000-8000-000000000100', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000005', 'Team continuity', TRUE);

-- harbor.template-v1
INSERT INTO workweave.handover_template_versions (template_version_id, organization_id, workspace_id, template_id, version, published_at)
VALUES ('00000002-0000-4000-8000-000000000101', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000100', 1, (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000002-0000-4000-8000-000000000002') + interval '-2 days');

-- harbor.section-0
INSERT INTO workweave.handover_template_sections (section_id, organization_id, workspace_id, template_version_id, name, order_index, is_required)
VALUES ('00000002-0000-4000-8000-000000000102', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000101', 'Shift Summary', 1, TRUE);

-- harbor.section-1
INSERT INTO workweave.handover_template_sections (section_id, organization_id, workspace_id, template_version_id, name, order_index, is_required)
VALUES ('00000002-0000-4000-8000-000000000103', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000101', 'Active / Ongoing Items', 2, TRUE);

-- harbor.section-2
INSERT INTO workweave.handover_template_sections (section_id, organization_id, workspace_id, template_version_id, name, order_index, is_required)
VALUES ('00000002-0000-4000-8000-000000000104', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000101', 'Incidents / Issues', 3, FALSE);

-- harbor.section-3
INSERT INTO workweave.handover_template_sections (section_id, organization_id, workspace_id, template_version_id, name, order_index, is_required)
VALUES ('00000002-0000-4000-8000-000000000105', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000101', 'Scheduled Activities', 4, FALSE);

-- harbor.section-4
INSERT INTO workweave.handover_template_sections (section_id, organization_id, workspace_id, template_version_id, name, order_index, is_required)
VALUES ('00000002-0000-4000-8000-000000000106', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000101', 'Blockers / Risks', 5, FALSE);

-- harbor.section-5
INSERT INTO workweave.handover_template_sections (section_id, organization_id, workspace_id, template_version_id, name, order_index, is_required)
VALUES ('00000002-0000-4000-8000-000000000107', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000101', 'Important Notes', 6, FALSE);

-- harbor.morning-handover
INSERT INTO workweave.shift_handovers (handover_id, organization_id, workspace_id, source_shift_instance_id, target_shift_instance_id, template_version_id, status, created_by_employee_id, context_as_of, context_revisions, draft_sections)
VALUES ('00000002-0000-4000-8000-000000000108', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000038', '00000002-0000-4000-8000-000000000043', '00000002-0000-4000-8000-000000000101', 'DRAFT', '00000002-0000-4000-8000-000000000009', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000002-0000-4000-8000-000000000002') + interval '-2 hours', '{"synthetic":true,"fixture":"review-only-sql-v1","not_real_employee_evidence":true}'::jsonb, '[{"section_id":"00000002-0000-4000-8000-000000000102","status":"DOCUMENTED","content":"Synthetic shift summary. Open work requires follow-up."},{"section_id":"00000002-0000-4000-8000-000000000103","status":"DOCUMENTED","content":"CASE-104: IN_PROGRESS. Customer reports a disputed amount. Verification is pending; do not assert a confirmed billing fault.\nACT-105: ACTIVE. A team refresher is scheduled; the session time needs confirmation."}]'::jsonb);

-- harbor.morning-publication
INSERT INTO workweave.handover_publications (publication_id, organization_id, workspace_id, handover_id, publication_number, content_revision, scope_snapshot, template_version_id, section_content, source_revisions, published_by, published_at)
VALUES ('00000002-0000-4000-8000-000000000109', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000108', 1, 1, '{"target_shift_instance_id":"00000002-0000-4000-8000-000000000043","synthetic":true}'::jsonb, '00000002-0000-4000-8000-000000000101', '[{"section_id":"00000002-0000-4000-8000-000000000102","status":"DOCUMENTED","content":"Synthetic shift summary. Open work requires follow-up."},{"section_id":"00000002-0000-4000-8000-000000000103","status":"DOCUMENTED","content":"CASE-104: IN_PROGRESS. Customer reports a disputed amount. Verification is pending; do not assert a confirmed billing fault.\nACT-105: ACTIVE. A team refresher is scheduled; the session time needs confirmation."}]'::jsonb, '{"source_id":"00000002-0000-4000-8000-000000000064","document_version_id":"00000002-0000-4000-8000-000000000067"}'::jsonb, '00000002-0000-4000-8000-000000000009', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000002-0000-4000-8000-000000000002') + interval '-2 hours');

-- harbor.afternoon-draft
INSERT INTO workweave.shift_handovers (handover_id, organization_id, workspace_id, source_shift_instance_id, target_shift_instance_id, template_version_id, status, created_by_employee_id, context_as_of, context_revisions, draft_sections)
VALUES ('00000002-0000-4000-8000-000000000110', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000043', '00000002-0000-4000-8000-000000000048', '00000002-0000-4000-8000-000000000101', 'DRAFT', '00000002-0000-4000-8000-000000000009', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000002-0000-4000-8000-000000000002') + interval '0 seconds', '{"synthetic":true,"fixture":"review-only-sql-v1","not_real_employee_evidence":true}'::jsonb, '[{"section_id":"00000002-0000-4000-8000-000000000102","status":"DOCUMENTED","content":"Synthetic shift summary. Open work requires follow-up."},{"section_id":"00000002-0000-4000-8000-000000000103","status":"DOCUMENTED","content":"CASE-104: IN_PROGRESS. Customer reports a disputed amount. Verification is pending; do not assert a confirmed billing fault.\nACT-105: ACTIVE. A team refresher is scheduled; the session time needs confirmation."}]'::jsonb);

-- harbor.handover-item-0
INSERT INTO workweave.handover_items (handover_item_id, organization_id, workspace_id, work_item_id, title, description, originating_shift_instance_id, originating_employee_id, current_owner_shift_instance_id, work_status, acknowledgement_status)
VALUES ('00000002-0000-4000-8000-000000000111', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000089', 'Billing clarification', 'Customer reports a disputed amount. Verification is pending; do not assert a confirmed billing fault.', '00000002-0000-4000-8000-000000000038', '00000002-0000-4000-8000-000000000009', '00000002-0000-4000-8000-000000000043', 'IN_PROGRESS', 'NOT_REQUIRED');

-- harbor.morning-entry-0
INSERT INTO workweave.handover_entries (handover_entry_id, organization_id, workspace_id, publication_id, handover_item_id, section_id, snapshot_work_status, snapshot_acknowledgement_status, snapshot_description, snapshot_source_refs)
VALUES ('00000002-0000-4000-8000-000000000112', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000109', '00000002-0000-4000-8000-000000000111', '00000002-0000-4000-8000-000000000103', 'IN_PROGRESS', 'NOT_REQUIRED', 'Customer reports a disputed amount. Verification is pending; do not assert a confirmed billing fault.', '["00000002-0000-4000-8000-000000000064"]'::jsonb);

-- harbor.item-source-0
INSERT INTO workweave.handover_item_sources (source_id, organization_id, workspace_id, handover_item_id, source_type, external_system, external_id, source_reference, extracted_data, detected_by_ai, confirmed_by_employee_id)
VALUES ('00000002-0000-4000-8000-000000000113', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000111', 'TICKET', 'synthetic_seed', 'CASE-104', 'Synthetic work item', '{"synthetic":true,"fixture":"review-only-sql-v1","not_real_employee_evidence":true}'::jsonb, FALSE, '00000002-0000-4000-8000-000000000009');

-- harbor.handover-item-1
INSERT INTO workweave.handover_items (handover_item_id, organization_id, workspace_id, work_item_id, title, description, originating_shift_instance_id, originating_employee_id, current_owner_shift_instance_id, work_status, acknowledgement_status)
VALUES ('00000002-0000-4000-8000-000000000114', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000091', 'Account escalation refresher', 'A team refresher is scheduled; the session time needs confirmation.', '00000002-0000-4000-8000-000000000038', '00000002-0000-4000-8000-000000000009', '00000002-0000-4000-8000-000000000043', 'ACTIVE', 'NOT_REQUIRED');

-- harbor.morning-entry-1
INSERT INTO workweave.handover_entries (handover_entry_id, organization_id, workspace_id, publication_id, handover_item_id, section_id, snapshot_work_status, snapshot_acknowledgement_status, snapshot_description, snapshot_source_refs)
VALUES ('00000002-0000-4000-8000-000000000115', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000109', '00000002-0000-4000-8000-000000000114', '00000002-0000-4000-8000-000000000103', 'ACTIVE', 'NOT_REQUIRED', 'A team refresher is scheduled; the session time needs confirmation.', '["00000002-0000-4000-8000-000000000064"]'::jsonb);

-- harbor.item-source-1
INSERT INTO workweave.handover_item_sources (source_id, organization_id, workspace_id, handover_item_id, source_type, external_system, external_id, source_reference, extracted_data, detected_by_ai, confirmed_by_employee_id)
VALUES ('00000002-0000-4000-8000-000000000116', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000114', 'TICKET', 'synthetic_seed', 'ACT-105', 'Synthetic work item', '{"synthetic":true,"fixture":"review-only-sql-v1","not_real_employee_evidence":true}'::jsonb, FALSE, '00000002-0000-4000-8000-000000000009');

-- harbor.report-suggestion
INSERT INTO workweave.handover_suggestions (suggestion_id, organization_id, workspace_id, handover_id, handover_item_id, suggestion_type, suggested_data, reason, source_refs, context_revisions, status)
VALUES ('00000002-0000-4000-8000-000000000117', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000110', '00000002-0000-4000-8000-000000000111', 'STALE_INFORMATION', '{"work_event_id":"00000002-0000-4000-8000-000000000098","reported_complete":false,"synthetic":true}'::jsonb, 'Compare the prior-shift report with the draft. Human review required.', '["00000002-0000-4000-8000-000000000098"]'::jsonb, '{"synthetic":true,"fixture":"review-only-sql-v1","not_real_employee_evidence":true}'::jsonb, 'PENDING');

-- harbor.report-source
INSERT INTO workweave.handover_item_sources (source_id, organization_id, workspace_id, suggestion_id, source_type, source_reference, extracted_data, detected_by_ai)
VALUES ('00000002-0000-4000-8000-000000000118', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000117', 'WORK_EVENT', '00000002-0000-4000-8000-000000000098', '{"synthetic":true,"fixture":"review-only-sql-v1","not_real_employee_evidence":true}'::jsonb, FALSE);

-- harbor.email
INSERT INTO workweave.source_records (source_id, organization_id, workspace_id, source_type, owner_employee_id, evidence_type, access_partition, metadata)
VALUES ('00000002-0000-4000-8000-000000000119', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', 'EMAIL', '00000002-0000-4000-8000-000000000009', 'REPORTED', 'TEAM', '{"synthetic":true,"fixture":"review-only-sql-v1","not_real_employee_evidence":true,"subject":"Upcoming team activity","scheduled_at_relative":"+6 hours"}'::jsonb);

-- harbor.email-suggestion
INSERT INTO workweave.handover_suggestions (suggestion_id, organization_id, workspace_id, handover_id, suggestion_type, suggested_data, reason, source_refs, context_revisions, status)
VALUES ('00000002-0000-4000-8000-000000000120', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000110', 'MISSING_ITEM', '{"title":"Upcoming team briefing","section":"Scheduled Activities","time_confirmation":"PENDING","source_id":"00000002-0000-4000-8000-000000000119","synthetic":true}'::jsonb, 'Synthetic email activity does not appear in the draft; review before adding.', '["00000002-0000-4000-8000-000000000119"]'::jsonb, '{"synthetic":true,"fixture":"review-only-sql-v1","not_real_employee_evidence":true}'::jsonb, 'PENDING');

-- harbor.email-source
INSERT INTO workweave.handover_item_sources (source_id, organization_id, workspace_id, suggestion_id, source_type, external_system, external_id, source_reference, extracted_data, detected_by_ai)
VALUES ('00000002-0000-4000-8000-000000000121', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000120', 'EMAIL', 'synthetic_seed', 'MAIL-101', '00000002-0000-4000-8000-000000000119', '{"synthetic":true,"fixture":"review-only-sql-v1","not_real_employee_evidence":true}'::jsonb, FALSE);

-- harbor.kt-consent
INSERT INTO workweave.consent_sessions (consent_session_id, organization_id, workspace_id, purpose, owner_employee_id, notice_version, accepted_at, requested_audience, raw_retention, status)
VALUES ('00000002-0000-4000-8000-000000000122', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', 'EXIT_KT_INTERVIEW', '00000002-0000-4000-8000-000000000009', 'synthetic-notice-v1', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000002-0000-4000-8000-000000000002') + interval '-30 minutes', '{"draft":"OWNER_ONLY","submitted":"DESIGNATED_REVIEWER","approved":"AUTHORIZED_SUCCESSOR"}'::jsonb, '{"days":7,"synthetic":true}'::jsonb, 'ACTIVE');

-- harbor.interview-source
INSERT INTO workweave.source_records (source_id, organization_id, workspace_id, source_type, owner_employee_id, consent_session_id, evidence_type, access_partition, retention_until, metadata)
VALUES ('00000002-0000-4000-8000-000000000123', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', 'INTERVIEW', '00000002-0000-4000-8000-000000000009', '00000002-0000-4000-8000-000000000122', 'REPORTED', 'PRIVATE', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000002-0000-4000-8000-000000000002') + interval '7 days', '{"synthetic":true,"fixture":"review-only-sql-v1","not_real_employee_evidence":true}'::jsonb);

-- harbor.kt-case
INSERT INTO workweave.exit_kt_cases (exit_kt_case_id, organization_id, workspace_id, employee_id, case_kind, status, initiated_by_employee_id, reviewer_employee_id, started_at)
VALUES ('00000002-0000-4000-8000-000000000124', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000009', 'ROLE_TRANSITION', 'IN_PROGRESS', '00000002-0000-4000-8000-000000000011', '00000002-0000-4000-8000-000000000011', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000002-0000-4000-8000-000000000002') + interval '-1 day');

-- harbor.inventory-documented
INSERT INTO workweave.exit_kt_knowledge_items (kt_item_id, organization_id, workspace_id, exit_kt_case_id, title, description, documentation_status, kt_status, risk_level)
VALUES ('00000002-0000-4000-8000-000000000125', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000124', 'Customer account escalation', 'Current approved SOP already exists.', 'DOCUMENTED', 'EXISTING_KNOWLEDGE', 'MEDIUM');

-- harbor.inventory-outdated
INSERT INTO workweave.exit_kt_knowledge_items (kt_item_id, organization_id, workspace_id, exit_kt_case_id, title, description, documentation_status, kt_status, risk_level)
VALUES ('00000002-0000-4000-8000-000000000126', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000124', 'Historical procedure references', 'Historical version appears in older notes; compare against current source.', 'OUTDATED', 'NOT_STARTED', 'MEDIUM');

-- harbor.inventory-missing
INSERT INTO workweave.exit_kt_knowledge_items (kt_item_id, organization_id, workspace_id, exit_kt_case_id, title, description, documentation_status, kt_status, risk_level)
VALUES ('00000002-0000-4000-8000-000000000127', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000124', 'Evidence-based escalation practice', 'Employee reporting practice is not yet approved reusable knowledge.', 'MISSING', 'DRAFT_CREATED', 'HIGH');

-- harbor.kt-doc-source
INSERT INTO workweave.exit_kt_sources (source_id, organization_id, workspace_id, kt_item_id, source_type, source_reference, relevance_data)
VALUES ('00000002-0000-4000-8000-000000000128', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000125', 'DOCUMENT', '00000002-0000-4000-8000-000000000067', '{"synthetic":true,"fixture":"review-only-sql-v1","not_real_employee_evidence":true}'::jsonb);

-- harbor.finding-OUTDATED_DOCUMENTATION
INSERT INTO workweave.exit_kt_findings (finding_id, organization_id, workspace_id, exit_kt_case_id, kt_item_id, finding_type, description, evidence_refs, status)
VALUES ('00000002-0000-4000-8000-000000000129', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000124', '00000002-0000-4000-8000-000000000126', 'OUTDATED_DOCUMENTATION', 'Review the old document reference; it is not proof that current instructions are wrong.', '["00000002-0000-4000-8000-000000000064"]'::jsonb, 'OPEN');

-- harbor.finding-UNDOCUMENTED_KNOWLEDGE
INSERT INTO workweave.exit_kt_findings (finding_id, organization_id, workspace_id, exit_kt_case_id, kt_item_id, finding_type, description, evidence_refs, status)
VALUES ('00000002-0000-4000-8000-000000000130', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000124', '00000002-0000-4000-8000-000000000127', 'UNDOCUMENTED_KNOWLEDGE', 'Reporting practice needs employee review and knowledge approval.', '["00000002-0000-4000-8000-000000000064"]'::jsonb, 'OPEN');

-- harbor.finding-MISSING_SUCCESSOR
INSERT INTO workweave.exit_kt_findings (finding_id, organization_id, workspace_id, exit_kt_case_id, kt_item_id, finding_type, description, evidence_refs, status)
VALUES ('00000002-0000-4000-8000-000000000131', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000124', '00000002-0000-4000-8000-000000000127', 'MISSING_SUCCESSOR', 'A proposed successor is not a completed ownership transfer.', '["00000002-0000-4000-8000-000000000064"]'::jsonb, 'OPEN');

-- harbor.interview
INSERT INTO workweave.exit_kt_interviews (interview_id, organization_id, workspace_id, kt_item_id, employee_id, consent_session_id, status, started_at)
VALUES ('00000002-0000-4000-8000-000000000132', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000127', '00000002-0000-4000-8000-000000000009', '00000002-0000-4000-8000-000000000122', 'PAUSED', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000002-0000-4000-8000-000000000002') + interval '-30 minutes');

-- harbor.interview-question
INSERT INTO workweave.exit_kt_interview_messages (message_id, organization_id, workspace_id, interview_id, sender_type, message_type, content, metadata, source_refs)
VALUES ('00000002-0000-4000-8000-000000000133', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000132', 'AI', 'SCRIPTED_FIXTURE', 'Which current work item and approved source do you include when requesting missing evidence?', '{"synthetic":true,"fixture":"review-only-sql-v1","not_real_employee_evidence":true,"no_model_was_called":true}'::jsonb, '["00000002-0000-4000-8000-000000000064"]'::jsonb);

-- harbor.interview-answer
INSERT INTO workweave.exit_kt_interview_messages (message_id, organization_id, workspace_id, interview_id, sender_type, content, metadata, source_refs)
VALUES ('00000002-0000-4000-8000-000000000134', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000132', 'EMPLOYEE', 'I include the work item and source version, keep the cause unknown, and ask the reviewer to verify the missing evidence.', '{"synthetic":true,"fixture":"review-only-sql-v1","not_real_employee_evidence":true}'::jsonb, '["00000002-0000-4000-8000-000000000123"]'::jsonb);

-- harbor.artifact
INSERT INTO workweave.exit_kt_artifacts (artifact_id, organization_id, workspace_id, kt_item_id, artifact_type, title, generated_from_interview_id)
VALUES ('00000002-0000-4000-8000-000000000135', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000127', 'CHECKLIST', 'Requesting evidence-based clarification', '00000002-0000-4000-8000-000000000132');

-- harbor.artifact-draft
INSERT INTO workweave.exit_kt_artifact_revisions (artifact_revision_id, organization_id, workspace_id, artifact_id, version, content, status, source_refs)
VALUES ('00000002-0000-4000-8000-000000000136', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000135', 1, '# Private synthetic checklist
1. Identify the current work item.
2. Cite the approved source version.
3. State missing evidence and ask the reviewer.

DRAFT: employee review and knowledge approval are pending.', 'DRAFT', '["00000002-0000-4000-8000-000000000123"]'::jsonb);

-- harbor.responsibility
INSERT INTO workweave.responsibilities (responsibility_id, organization_id, workspace_id, responsibility_type, title, owner_employee_id, ownership_revision, description)
VALUES ('00000002-0000-4000-8000-000000000137', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', 'PROCESS', 'Priority customer account escalation', '00000002-0000-4000-8000-000000000009', 1, 'Synthetic role responsibility. No transfer has been completed.');

-- harbor.transfer
INSERT INTO workweave.responsibility_transfers (transfer_id, organization_id, workspace_id, exit_kt_case_id, responsibility_id, current_owner_employee_id, recommended_owner_employee_id, recommendation_reason, recommendation_data, status, effective_at, expected_owner_revision)
VALUES ('00000002-0000-4000-8000-000000000138', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000124', '00000002-0000-4000-8000-000000000137', '00000002-0000-4000-8000-000000000009', '00000002-0000-4000-8000-000000000010', 'Synthetic proposed successor; human confirmation and package receipt remain required.', '{"synthetic":true,"fixture":"review-only-sql-v1","not_real_employee_evidence":true}'::jsonb, 'PROPOSED', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000002-0000-4000-8000-000000000002') + interval '1 day', 1);

-- harbor.uncovered-responsibility
INSERT INTO workweave.responsibilities (responsibility_id, organization_id, workspace_id, responsibility_type, title, owner_employee_id, ownership_revision)
VALUES ('00000002-0000-4000-8000-000000000139', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', 'RECURRING_TASK', 'Recurring source-reference review', '00000002-0000-4000-8000-000000000009', 1);

-- harbor.kt-package
INSERT INTO workweave.exit_kt_packages (package_id, organization_id, workspace_id, exit_kt_case_id, successor_employee_id, status, effective_at, context_revisions, draft_sections)
VALUES ('00000002-0000-4000-8000-000000000140', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000124', '00000002-0000-4000-8000-000000000010', 'DRAFT', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000002-0000-4000-8000-000000000002') + interval '1 day', '{"synthetic":true,"fixture":"review-only-sql-v1","not_real_employee_evidence":true}'::jsonb, '[{"title":"Responsibilities","content":"Priority customer account escalation"},{"title":"Knowledge gaps","content":"Private checklist awaits employee review and knowledge approval."}]'::jsonb);

-- harbor.package-responsibility
INSERT INTO workweave.exit_kt_package_responsibilities (package_responsibility_id, organization_id, workspace_id, package_id, responsibility_id)
VALUES ('00000002-0000-4000-8000-000000000141', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000140', '00000002-0000-4000-8000-000000000137');

-- harbor.knowledge-checklist
INSERT INTO workweave.kt_checklist_items (checklist_item_id, organization_id, workspace_id, exit_kt_case_id, knowledge_item_id, required, status, evidence_refs)
VALUES ('00000002-0000-4000-8000-000000000142', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000124', '00000002-0000-4000-8000-000000000127', TRUE, 'OPEN', '[]'::jsonb);

-- harbor.responsibility-checklist
INSERT INTO workweave.kt_checklist_items (checklist_item_id, organization_id, workspace_id, exit_kt_case_id, responsibility_id, required, status, evidence_refs)
VALUES ('00000002-0000-4000-8000-000000000143', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000124', '00000002-0000-4000-8000-000000000137', TRUE, 'OPEN', '[]'::jsonb);

-- harbor.seed-audit
INSERT INTO workweave.audit_events (audit_event_id, organization_id, workspace_id, actor_id, action, resource_type, resource_id, resource_revision, result, source_refs, request_id)
VALUES ('00000002-0000-4000-8000-000000000145', '00000002-0000-4000-8000-000000000001', '00000002-0000-4000-8000-000000000002', '00000002-0000-4000-8000-000000000011', 'SYNTHETIC_FIXTURE_STAGED', 'workspace', '00000002-0000-4000-8000-000000000002', 1, 'REVIEW_ONLY_NO_LIVE_WORKFLOW_COMPLETED', '[]'::jsonb, '00000002-0000-4000-8000-000000000144');


-- ACME synthetic fixtures
-- acme.organization
INSERT INTO workweave.organizations (organization_id, name, industry, company_key)
VALUES ('00000003-0000-4000-8000-000000000001', 'Acme Infrastructure Operations', 'infrastructure_operations', 'acme');

-- acme.workspace
INSERT INTO workweave.workspaces (workspace_id, organization_id, kind, pack_version, clock_anchor, expires_at)
VALUES ('00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000001', 'DEMO', 'review-only-v1', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP + interval '7 days');

-- acme.scenario
INSERT INTO workweave.scenario_catalog (scenario_id, organization_id, workspace_id, company_key, name, industry, pack_version, content_hash, provenance, status)
VALUES ('00000003-0000-4000-8000-000000000003', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', 'acme', 'Acme Infrastructure Operations — review fixture', 'infrastructure_operations', 'review-only-v1', 'synthetic-sql-fixture-not-a-pack-hash', '{"synthetic":true,"fixture":"review-only-sql-v1","not_real_employee_evidence":true}'::jsonb, 'DRAFT');

-- acme.department
INSERT INTO workweave.departments (department_id, organization_id, workspace_id, name)
VALUES ('00000003-0000-4000-8000-000000000004', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', 'Operations');

-- acme.team
INSERT INTO workweave.teams (team_id, organization_id, workspace_id, department_id, name)
VALUES ('00000003-0000-4000-8000-000000000005', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000004', 'Platform Operations');

-- acme.worker-role
INSERT INTO workweave.roles (role_id, organization_id, workspace_id, name)
VALUES ('00000003-0000-4000-8000-000000000006', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', 'Operations engineer');

-- acme.manager-role
INSERT INTO workweave.roles (role_id, organization_id, workspace_id, name)
VALUES ('00000003-0000-4000-8000-000000000007', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', 'Knowledge reviewer / manager');

-- acme.lead
INSERT INTO workweave.employees (employee_id, organization_id, workspace_id, role_id, first_name, last_name, email, employment_status, hire_date)
VALUES ('00000003-0000-4000-8000-000000000008', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000006', 'Alex', 'Chen', 'alex.chen@acme.example', 'ACTIVE', CURRENT_DATE - 180);

-- acme.john
INSERT INTO workweave.employees (employee_id, organization_id, workspace_id, role_id, first_name, last_name, email, employment_status, hire_date)
VALUES ('00000003-0000-4000-8000-000000000009', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000006', 'John', 'Tan', 'john.tan@acme.example', 'ACTIVE', CURRENT_DATE - 180);

-- acme.maria
INSERT INTO workweave.employees (employee_id, organization_id, workspace_id, role_id, first_name, last_name, email, employment_status, hire_date)
VALUES ('00000003-0000-4000-8000-000000000010', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000006', 'Maria', 'Garcia', 'maria.garcia@acme.example', 'ACTIVE', CURRENT_DATE - 180);

-- acme.learner
INSERT INTO workweave.employees (employee_id, organization_id, workspace_id, role_id, first_name, last_name, email, employment_status, hire_date)
VALUES ('00000003-0000-4000-8000-000000000011', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000006', 'Sam', 'Lim', 'sam.lim@acme.example', 'ACTIVE', CURRENT_DATE - 180);

-- acme.outgoing
INSERT INTO workweave.employees (employee_id, organization_id, workspace_id, role_id, first_name, last_name, email, employment_status, hire_date, final_working_date)
VALUES ('00000003-0000-4000-8000-000000000012', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000006', 'Pat', 'Reyes', 'pat.reyes@acme.example', 'NOTICE_PERIOD', CURRENT_DATE - 180, CURRENT_DATE + 14);

-- acme.reviewer
INSERT INTO workweave.employees (employee_id, organization_id, workspace_id, role_id, first_name, last_name, email, employment_status, hire_date)
VALUES ('00000003-0000-4000-8000-000000000013', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000007', 'Morgan', 'Lee', 'morgan.lee@acme.example', 'ACTIVE', CURRENT_DATE - 180);

-- acme.lead-membership
INSERT INTO workweave.employee_team_memberships (membership_id, organization_id, workspace_id, employee_id, team_id, team_role, start_date, is_active)
VALUES ('00000003-0000-4000-8000-000000000014', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000008', '00000003-0000-4000-8000-000000000005', 'SHIFT_LEAD', CURRENT_DATE - 180, TRUE);

-- acme.lead-work:read
INSERT INTO workweave.permission_grants (grant_id, organization_id, workspace_id, actor_id, resource_scope, action, valid_from, granted_by)
VALUES ('00000003-0000-4000-8000-000000000015', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000008', '{"team_id":"00000003-0000-4000-8000-000000000005","synthetic":true}'::jsonb, 'work:read', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000003-0000-4000-8000-000000000002') + interval '-1 day', '00000003-0000-4000-8000-000000000013');

-- acme.lead-work:report
INSERT INTO workweave.permission_grants (grant_id, organization_id, workspace_id, actor_id, resource_scope, action, valid_from, granted_by)
VALUES ('00000003-0000-4000-8000-000000000016', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000008', '{"team_id":"00000003-0000-4000-8000-000000000005","synthetic":true}'::jsonb, 'work:report', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000003-0000-4000-8000-000000000002') + interval '-1 day', '00000003-0000-4000-8000-000000000013');

-- acme.lead-delegation:confirm
INSERT INTO workweave.permission_grants (grant_id, organization_id, workspace_id, actor_id, resource_scope, action, valid_from, granted_by)
VALUES ('00000003-0000-4000-8000-000000000017', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000008', '{"team_id":"00000003-0000-4000-8000-000000000005","synthetic":true}'::jsonb, 'delegation:confirm', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000003-0000-4000-8000-000000000002') + interval '-1 day', '00000003-0000-4000-8000-000000000013');

-- acme.lead-handover:publish
INSERT INTO workweave.permission_grants (grant_id, organization_id, workspace_id, actor_id, resource_scope, action, valid_from, granted_by)
VALUES ('00000003-0000-4000-8000-000000000018', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000008', '{"team_id":"00000003-0000-4000-8000-000000000005","synthetic":true}'::jsonb, 'handover:publish', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000003-0000-4000-8000-000000000002') + interval '-1 day', '00000003-0000-4000-8000-000000000013');

-- acme.lead-handover:suggestion:review
INSERT INTO workweave.permission_grants (grant_id, organization_id, workspace_id, actor_id, resource_scope, action, valid_from, granted_by)
VALUES ('00000003-0000-4000-8000-000000000019', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000008', '{"team_id":"00000003-0000-4000-8000-000000000005","synthetic":true}'::jsonb, 'handover:suggestion:review', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000003-0000-4000-8000-000000000002') + interval '-1 day', '00000003-0000-4000-8000-000000000013');

-- acme.lead-availability
INSERT INTO workweave.employee_availability (availability_id, organization_id, workspace_id, employee_id, start_at, end_at, status, source_reference)
VALUES ('00000003-0000-4000-8000-000000000020', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000008', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000003-0000-4000-8000-000000000002') + interval '-8 hours', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000003-0000-4000-8000-000000000002') + interval '16 hours', 'AVAILABLE', 'Synthetic declared availability, not monitoring');

-- acme.john-membership
INSERT INTO workweave.employee_team_memberships (membership_id, organization_id, workspace_id, employee_id, team_id, team_role, start_date, is_active)
VALUES ('00000003-0000-4000-8000-000000000021', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000009', '00000003-0000-4000-8000-000000000005', 'MEMBER', CURRENT_DATE - 180, TRUE);

-- acme.john-work:read
INSERT INTO workweave.permission_grants (grant_id, organization_id, workspace_id, actor_id, resource_scope, action, valid_from, granted_by)
VALUES ('00000003-0000-4000-8000-000000000022', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000009', '{"team_id":"00000003-0000-4000-8000-000000000005","synthetic":true}'::jsonb, 'work:read', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000003-0000-4000-8000-000000000002') + interval '-1 day', '00000003-0000-4000-8000-000000000013');

-- acme.john-work:report
INSERT INTO workweave.permission_grants (grant_id, organization_id, workspace_id, actor_id, resource_scope, action, valid_from, granted_by)
VALUES ('00000003-0000-4000-8000-000000000023', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000009', '{"team_id":"00000003-0000-4000-8000-000000000005","synthetic":true}'::jsonb, 'work:report', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000003-0000-4000-8000-000000000002') + interval '-1 day', '00000003-0000-4000-8000-000000000013');

-- acme.john-learning:own
INSERT INTO workweave.permission_grants (grant_id, organization_id, workspace_id, actor_id, resource_scope, action, valid_from, granted_by)
VALUES ('00000003-0000-4000-8000-000000000024', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000009', '{"team_id":"00000003-0000-4000-8000-000000000005","synthetic":true}'::jsonb, 'learning:own', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000003-0000-4000-8000-000000000002') + interval '-1 day', '00000003-0000-4000-8000-000000000013');

-- acme.john-exit_kt:own
INSERT INTO workweave.permission_grants (grant_id, organization_id, workspace_id, actor_id, resource_scope, action, valid_from, granted_by)
VALUES ('00000003-0000-4000-8000-000000000025', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000009', '{"team_id":"00000003-0000-4000-8000-000000000005","synthetic":true}'::jsonb, 'exit_kt:own', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000003-0000-4000-8000-000000000002') + interval '-1 day', '00000003-0000-4000-8000-000000000013');

-- acme.john-availability
INSERT INTO workweave.employee_availability (availability_id, organization_id, workspace_id, employee_id, start_at, end_at, status, source_reference)
VALUES ('00000003-0000-4000-8000-000000000026', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000009', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000003-0000-4000-8000-000000000002') + interval '-8 hours', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000003-0000-4000-8000-000000000002') + interval '16 hours', 'AVAILABLE', 'Synthetic declared availability, not monitoring');

-- acme.maria-membership
INSERT INTO workweave.employee_team_memberships (membership_id, organization_id, workspace_id, employee_id, team_id, team_role, start_date, is_active)
VALUES ('00000003-0000-4000-8000-000000000027', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000010', '00000003-0000-4000-8000-000000000005', 'MEMBER', CURRENT_DATE - 180, TRUE);

-- acme.maria-work:read
INSERT INTO workweave.permission_grants (grant_id, organization_id, workspace_id, actor_id, resource_scope, action, valid_from, granted_by)
VALUES ('00000003-0000-4000-8000-000000000028', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000010', '{"team_id":"00000003-0000-4000-8000-000000000005","synthetic":true}'::jsonb, 'work:read', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000003-0000-4000-8000-000000000002') + interval '-1 day', '00000003-0000-4000-8000-000000000013');

-- acme.maria-work:report
INSERT INTO workweave.permission_grants (grant_id, organization_id, workspace_id, actor_id, resource_scope, action, valid_from, granted_by)
VALUES ('00000003-0000-4000-8000-000000000029', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000010', '{"team_id":"00000003-0000-4000-8000-000000000005","synthetic":true}'::jsonb, 'work:report', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000003-0000-4000-8000-000000000002') + interval '-1 day', '00000003-0000-4000-8000-000000000013');

-- acme.maria-learning:own
INSERT INTO workweave.permission_grants (grant_id, organization_id, workspace_id, actor_id, resource_scope, action, valid_from, granted_by)
VALUES ('00000003-0000-4000-8000-000000000030', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000010', '{"team_id":"00000003-0000-4000-8000-000000000005","synthetic":true}'::jsonb, 'learning:own', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000003-0000-4000-8000-000000000002') + interval '-1 day', '00000003-0000-4000-8000-000000000013');

-- acme.maria-exit_kt:own
INSERT INTO workweave.permission_grants (grant_id, organization_id, workspace_id, actor_id, resource_scope, action, valid_from, granted_by)
VALUES ('00000003-0000-4000-8000-000000000031', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000010', '{"team_id":"00000003-0000-4000-8000-000000000005","synthetic":true}'::jsonb, 'exit_kt:own', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000003-0000-4000-8000-000000000002') + interval '-1 day', '00000003-0000-4000-8000-000000000013');

-- acme.maria-availability
INSERT INTO workweave.employee_availability (availability_id, organization_id, workspace_id, employee_id, start_at, end_at, status, source_reference)
VALUES ('00000003-0000-4000-8000-000000000032', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000010', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000003-0000-4000-8000-000000000002') + interval '-8 hours', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000003-0000-4000-8000-000000000002') + interval '16 hours', 'AVAILABLE', 'Synthetic declared availability, not monitoring');

-- acme.learner-membership
INSERT INTO workweave.employee_team_memberships (membership_id, organization_id, workspace_id, employee_id, team_id, team_role, start_date, is_active)
VALUES ('00000003-0000-4000-8000-000000000033', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000011', '00000003-0000-4000-8000-000000000005', 'MEMBER', CURRENT_DATE - 180, TRUE);

-- acme.learner-work:read
INSERT INTO workweave.permission_grants (grant_id, organization_id, workspace_id, actor_id, resource_scope, action, valid_from, granted_by)
VALUES ('00000003-0000-4000-8000-000000000034', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000011', '{"team_id":"00000003-0000-4000-8000-000000000005","synthetic":true}'::jsonb, 'work:read', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000003-0000-4000-8000-000000000002') + interval '-1 day', '00000003-0000-4000-8000-000000000013');

-- acme.learner-work:report
INSERT INTO workweave.permission_grants (grant_id, organization_id, workspace_id, actor_id, resource_scope, action, valid_from, granted_by)
VALUES ('00000003-0000-4000-8000-000000000035', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000011', '{"team_id":"00000003-0000-4000-8000-000000000005","synthetic":true}'::jsonb, 'work:report', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000003-0000-4000-8000-000000000002') + interval '-1 day', '00000003-0000-4000-8000-000000000013');

-- acme.learner-learning:own
INSERT INTO workweave.permission_grants (grant_id, organization_id, workspace_id, actor_id, resource_scope, action, valid_from, granted_by)
VALUES ('00000003-0000-4000-8000-000000000036', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000011', '{"team_id":"00000003-0000-4000-8000-000000000005","synthetic":true}'::jsonb, 'learning:own', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000003-0000-4000-8000-000000000002') + interval '-1 day', '00000003-0000-4000-8000-000000000013');

-- acme.learner-exit_kt:own
INSERT INTO workweave.permission_grants (grant_id, organization_id, workspace_id, actor_id, resource_scope, action, valid_from, granted_by)
VALUES ('00000003-0000-4000-8000-000000000037', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000011', '{"team_id":"00000003-0000-4000-8000-000000000005","synthetic":true}'::jsonb, 'exit_kt:own', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000003-0000-4000-8000-000000000002') + interval '-1 day', '00000003-0000-4000-8000-000000000013');

-- acme.learner-availability
INSERT INTO workweave.employee_availability (availability_id, organization_id, workspace_id, employee_id, start_at, end_at, status, source_reference)
VALUES ('00000003-0000-4000-8000-000000000038', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000011', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000003-0000-4000-8000-000000000002') + interval '-8 hours', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000003-0000-4000-8000-000000000002') + interval '16 hours', 'AVAILABLE', 'Synthetic declared availability, not monitoring');

-- acme.outgoing-membership
INSERT INTO workweave.employee_team_memberships (membership_id, organization_id, workspace_id, employee_id, team_id, team_role, start_date, is_active)
VALUES ('00000003-0000-4000-8000-000000000039', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000012', '00000003-0000-4000-8000-000000000005', 'MEMBER', CURRENT_DATE - 180, TRUE);

-- acme.outgoing-work:read
INSERT INTO workweave.permission_grants (grant_id, organization_id, workspace_id, actor_id, resource_scope, action, valid_from, granted_by)
VALUES ('00000003-0000-4000-8000-000000000040', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000012', '{"team_id":"00000003-0000-4000-8000-000000000005","synthetic":true}'::jsonb, 'work:read', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000003-0000-4000-8000-000000000002') + interval '-1 day', '00000003-0000-4000-8000-000000000013');

-- acme.outgoing-work:report
INSERT INTO workweave.permission_grants (grant_id, organization_id, workspace_id, actor_id, resource_scope, action, valid_from, granted_by)
VALUES ('00000003-0000-4000-8000-000000000041', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000012', '{"team_id":"00000003-0000-4000-8000-000000000005","synthetic":true}'::jsonb, 'work:report', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000003-0000-4000-8000-000000000002') + interval '-1 day', '00000003-0000-4000-8000-000000000013');

-- acme.outgoing-learning:own
INSERT INTO workweave.permission_grants (grant_id, organization_id, workspace_id, actor_id, resource_scope, action, valid_from, granted_by)
VALUES ('00000003-0000-4000-8000-000000000042', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000012', '{"team_id":"00000003-0000-4000-8000-000000000005","synthetic":true}'::jsonb, 'learning:own', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000003-0000-4000-8000-000000000002') + interval '-1 day', '00000003-0000-4000-8000-000000000013');

-- acme.outgoing-exit_kt:own
INSERT INTO workweave.permission_grants (grant_id, organization_id, workspace_id, actor_id, resource_scope, action, valid_from, granted_by)
VALUES ('00000003-0000-4000-8000-000000000043', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000012', '{"team_id":"00000003-0000-4000-8000-000000000005","synthetic":true}'::jsonb, 'exit_kt:own', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000003-0000-4000-8000-000000000002') + interval '-1 day', '00000003-0000-4000-8000-000000000013');

-- acme.outgoing-availability
INSERT INTO workweave.employee_availability (availability_id, organization_id, workspace_id, employee_id, start_at, end_at, status, source_reference)
VALUES ('00000003-0000-4000-8000-000000000044', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000012', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000003-0000-4000-8000-000000000002') + interval '-8 hours', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000003-0000-4000-8000-000000000002') + interval '16 hours', 'AVAILABLE', 'Synthetic declared availability, not monitoring');

-- acme.reviewer-membership
INSERT INTO workweave.employee_team_memberships (membership_id, organization_id, workspace_id, employee_id, team_id, team_role, start_date, is_active)
VALUES ('00000003-0000-4000-8000-000000000045', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000013', '00000003-0000-4000-8000-000000000005', 'MANAGER', CURRENT_DATE - 180, TRUE);

-- acme.reviewer-work:read
INSERT INTO workweave.permission_grants (grant_id, organization_id, workspace_id, actor_id, resource_scope, action, valid_from, granted_by)
VALUES ('00000003-0000-4000-8000-000000000046', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000013', '{"team_id":"00000003-0000-4000-8000-000000000005","synthetic":true}'::jsonb, 'work:read', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000003-0000-4000-8000-000000000002') + interval '-1 day', '00000003-0000-4000-8000-000000000013');

-- acme.reviewer-knowledge:review
INSERT INTO workweave.permission_grants (grant_id, organization_id, workspace_id, actor_id, resource_scope, action, valid_from, granted_by)
VALUES ('00000003-0000-4000-8000-000000000047', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000013', '{"team_id":"00000003-0000-4000-8000-000000000005","synthetic":true}'::jsonb, 'knowledge:review', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000003-0000-4000-8000-000000000002') + interval '-1 day', '00000003-0000-4000-8000-000000000013');

-- acme.reviewer-exit_kt:review
INSERT INTO workweave.permission_grants (grant_id, organization_id, workspace_id, actor_id, resource_scope, action, valid_from, granted_by)
VALUES ('00000003-0000-4000-8000-000000000048', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000013', '{"team_id":"00000003-0000-4000-8000-000000000005","synthetic":true}'::jsonb, 'exit_kt:review', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000003-0000-4000-8000-000000000002') + interval '-1 day', '00000003-0000-4000-8000-000000000013');

-- acme.reviewer-responsibility:transfer
INSERT INTO workweave.permission_grants (grant_id, organization_id, workspace_id, actor_id, resource_scope, action, valid_from, granted_by)
VALUES ('00000003-0000-4000-8000-000000000049', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000013', '{"team_id":"00000003-0000-4000-8000-000000000005","synthetic":true}'::jsonb, 'responsibility:transfer', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000003-0000-4000-8000-000000000002') + interval '-1 day', '00000003-0000-4000-8000-000000000013');

-- acme.reviewer-availability
INSERT INTO workweave.employee_availability (availability_id, organization_id, workspace_id, employee_id, start_at, end_at, status, source_reference)
VALUES ('00000003-0000-4000-8000-000000000050', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000013', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000003-0000-4000-8000-000000000002') + interval '-8 hours', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000003-0000-4000-8000-000000000002') + interval '16 hours', 'AVAILABLE', 'Synthetic declared availability, not monitoring');

-- acme.Morning-shift
INSERT INTO workweave.shifts (shift_id, organization_id, workspace_id, team_id, name, start_time, end_time, timezone)
VALUES ('00000003-0000-4000-8000-000000000051', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000005', 'Morning', '07:00', '15:00', 'Asia/Manila');

-- acme.Morning-instance
INSERT INTO workweave.shift_instances (shift_instance_id, organization_id, workspace_id, shift_id, shift_date, scheduled_start_at, scheduled_end_at, shift_lead_employee_id, status)
VALUES ('00000003-0000-4000-8000-000000000052', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000051', ((SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000003-0000-4000-8000-000000000002') AT TIME ZONE 'Asia/Manila')::date, (date_trunc('day', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000003-0000-4000-8000-000000000002') AT TIME ZONE 'Asia/Manila') + time '07:00') AT TIME ZONE 'Asia/Manila', (date_trunc('day', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000003-0000-4000-8000-000000000002') AT TIME ZONE 'Asia/Manila') + time '15:00') AT TIME ZONE 'Asia/Manila', '00000003-0000-4000-8000-000000000008', 'COMPLETED');

-- acme.Morning-lead
INSERT INTO workweave.shift_instance_memberships (shift_membership_id, organization_id, workspace_id, shift_instance_id, employee_id, membership_role, availability_status)
VALUES ('00000003-0000-4000-8000-000000000053', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000052', '00000003-0000-4000-8000-000000000008', 'SHIFT_LEAD', 'AVAILABLE');

-- acme.Morning-john
INSERT INTO workweave.shift_instance_memberships (shift_membership_id, organization_id, workspace_id, shift_instance_id, employee_id, membership_role, availability_status)
VALUES ('00000003-0000-4000-8000-000000000054', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000052', '00000003-0000-4000-8000-000000000009', 'MEMBER', 'AVAILABLE');

-- acme.Morning-maria
INSERT INTO workweave.shift_instance_memberships (shift_membership_id, organization_id, workspace_id, shift_instance_id, employee_id, membership_role, availability_status)
VALUES ('00000003-0000-4000-8000-000000000055', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000052', '00000003-0000-4000-8000-000000000010', 'MEMBER', 'AVAILABLE');

-- acme.Morning-learner
INSERT INTO workweave.shift_instance_memberships (shift_membership_id, organization_id, workspace_id, shift_instance_id, employee_id, membership_role, availability_status)
VALUES ('00000003-0000-4000-8000-000000000056', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000052', '00000003-0000-4000-8000-000000000011', 'MEMBER', 'AVAILABLE');

-- acme.Morning-outgoing
INSERT INTO workweave.shift_instance_memberships (shift_membership_id, organization_id, workspace_id, shift_instance_id, employee_id, membership_role, availability_status)
VALUES ('00000003-0000-4000-8000-000000000057', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000052', '00000003-0000-4000-8000-000000000012', 'MEMBER', 'AVAILABLE');

-- acme.Afternoon-shift
INSERT INTO workweave.shifts (shift_id, organization_id, workspace_id, team_id, name, start_time, end_time, timezone)
VALUES ('00000003-0000-4000-8000-000000000058', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000005', 'Afternoon', '15:00', '23:00', 'Asia/Manila');

-- acme.Afternoon-instance
INSERT INTO workweave.shift_instances (shift_instance_id, organization_id, workspace_id, shift_id, shift_date, scheduled_start_at, scheduled_end_at, shift_lead_employee_id, status)
VALUES ('00000003-0000-4000-8000-000000000059', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000058', ((SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000003-0000-4000-8000-000000000002') AT TIME ZONE 'Asia/Manila')::date, (date_trunc('day', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000003-0000-4000-8000-000000000002') AT TIME ZONE 'Asia/Manila') + time '15:00') AT TIME ZONE 'Asia/Manila', (date_trunc('day', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000003-0000-4000-8000-000000000002') AT TIME ZONE 'Asia/Manila') + time '23:00') AT TIME ZONE 'Asia/Manila', '00000003-0000-4000-8000-000000000008', 'ACTIVE');

-- acme.Afternoon-lead
INSERT INTO workweave.shift_instance_memberships (shift_membership_id, organization_id, workspace_id, shift_instance_id, employee_id, membership_role, availability_status)
VALUES ('00000003-0000-4000-8000-000000000060', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000059', '00000003-0000-4000-8000-000000000008', 'SHIFT_LEAD', 'AVAILABLE');

-- acme.Afternoon-john
INSERT INTO workweave.shift_instance_memberships (shift_membership_id, organization_id, workspace_id, shift_instance_id, employee_id, membership_role, availability_status)
VALUES ('00000003-0000-4000-8000-000000000061', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000059', '00000003-0000-4000-8000-000000000009', 'MEMBER', 'AVAILABLE');

-- acme.Afternoon-maria
INSERT INTO workweave.shift_instance_memberships (shift_membership_id, organization_id, workspace_id, shift_instance_id, employee_id, membership_role, availability_status)
VALUES ('00000003-0000-4000-8000-000000000062', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000059', '00000003-0000-4000-8000-000000000010', 'MEMBER', 'AVAILABLE');

-- acme.Afternoon-learner
INSERT INTO workweave.shift_instance_memberships (shift_membership_id, organization_id, workspace_id, shift_instance_id, employee_id, membership_role, availability_status)
VALUES ('00000003-0000-4000-8000-000000000063', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000059', '00000003-0000-4000-8000-000000000011', 'MEMBER', 'AVAILABLE');

-- acme.Afternoon-outgoing
INSERT INTO workweave.shift_instance_memberships (shift_membership_id, organization_id, workspace_id, shift_instance_id, employee_id, membership_role, availability_status)
VALUES ('00000003-0000-4000-8000-000000000064', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000059', '00000003-0000-4000-8000-000000000012', 'MEMBER', 'AVAILABLE');

-- acme.Evening-shift
INSERT INTO workweave.shifts (shift_id, organization_id, workspace_id, team_id, name, start_time, end_time, timezone)
VALUES ('00000003-0000-4000-8000-000000000065', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000005', 'Evening', '23:00', '07:00', 'Asia/Manila');

-- acme.Evening-instance
INSERT INTO workweave.shift_instances (shift_instance_id, organization_id, workspace_id, shift_id, shift_date, scheduled_start_at, scheduled_end_at, shift_lead_employee_id, status)
VALUES ('00000003-0000-4000-8000-000000000066', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000065', ((SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000003-0000-4000-8000-000000000002') AT TIME ZONE 'Asia/Manila')::date, (date_trunc('day', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000003-0000-4000-8000-000000000002') AT TIME ZONE 'Asia/Manila') + time '23:00') AT TIME ZONE 'Asia/Manila', (date_trunc('day', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000003-0000-4000-8000-000000000002') AT TIME ZONE 'Asia/Manila') + interval '1 day' + time '07:00') AT TIME ZONE 'Asia/Manila', '00000003-0000-4000-8000-000000000008', 'SCHEDULED');

-- acme.Evening-lead
INSERT INTO workweave.shift_instance_memberships (shift_membership_id, organization_id, workspace_id, shift_instance_id, employee_id, membership_role, availability_status)
VALUES ('00000003-0000-4000-8000-000000000067', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000066', '00000003-0000-4000-8000-000000000008', 'SHIFT_LEAD', 'AVAILABLE');

-- acme.Evening-john
INSERT INTO workweave.shift_instance_memberships (shift_membership_id, organization_id, workspace_id, shift_instance_id, employee_id, membership_role, availability_status)
VALUES ('00000003-0000-4000-8000-000000000068', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000066', '00000003-0000-4000-8000-000000000009', 'MEMBER', 'AVAILABLE');

-- acme.Evening-maria
INSERT INTO workweave.shift_instance_memberships (shift_membership_id, organization_id, workspace_id, shift_instance_id, employee_id, membership_role, availability_status)
VALUES ('00000003-0000-4000-8000-000000000069', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000066', '00000003-0000-4000-8000-000000000010', 'MEMBER', 'AVAILABLE');

-- acme.Evening-learner
INSERT INTO workweave.shift_instance_memberships (shift_membership_id, organization_id, workspace_id, shift_instance_id, employee_id, membership_role, availability_status)
VALUES ('00000003-0000-4000-8000-000000000070', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000066', '00000003-0000-4000-8000-000000000011', 'MEMBER', 'AVAILABLE');

-- acme.Evening-outgoing
INSERT INTO workweave.shift_instance_memberships (shift_membership_id, organization_id, workspace_id, shift_instance_id, employee_id, membership_role, availability_status)
VALUES ('00000003-0000-4000-8000-000000000071', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000066', '00000003-0000-4000-8000-000000000012', 'MEMBER', 'AVAILABLE');

-- acme.payment_gateway
INSERT INTO workweave.competencies (competency_id, organization_id, workspace_id, code, name, category)
VALUES ('00000003-0000-4000-8000-000000000072', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', 'payment_gateway', 'payment gateway', 'infrastructure_operations');

-- acme.network_diagnostics
INSERT INTO workweave.competencies (competency_id, organization_id, workspace_id, code, name, category)
VALUES ('00000003-0000-4000-8000-000000000073', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', 'network_diagnostics', 'network diagnostics', 'infrastructure_operations');

-- acme.database_operations
INSERT INTO workweave.competencies (competency_id, organization_id, workspace_id, code, name, category)
VALUES ('00000003-0000-4000-8000-000000000074', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', 'database_operations', 'database operations', 'infrastructure_operations');

-- acme.maintenance_procedures
INSERT INTO workweave.competencies (competency_id, organization_id, workspace_id, code, name, category)
VALUES ('00000003-0000-4000-8000-000000000075', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', 'maintenance_procedures', 'maintenance procedures', 'infrastructure_operations');

-- acme.incident_response
INSERT INTO workweave.competencies (competency_id, organization_id, workspace_id, code, name, category)
VALUES ('00000003-0000-4000-8000-000000000076', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', 'incident_response', 'incident response', 'infrastructure_operations');

-- acme.role-00000003-0000-4000-8000-000000000072
INSERT INTO workweave.role_competency_requirements (requirement_id, organization_id, workspace_id, role_id, competency_id, required_level, is_mandatory)
VALUES ('00000003-0000-4000-8000-000000000077', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000006', '00000003-0000-4000-8000-000000000072', 1, TRUE);

-- acme.role-00000003-0000-4000-8000-000000000073
INSERT INTO workweave.role_competency_requirements (requirement_id, organization_id, workspace_id, role_id, competency_id, required_level, is_mandatory)
VALUES ('00000003-0000-4000-8000-000000000078', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000006', '00000003-0000-4000-8000-000000000073', 1, TRUE);

-- acme.role-00000003-0000-4000-8000-000000000074
INSERT INTO workweave.role_competency_requirements (requirement_id, organization_id, workspace_id, role_id, competency_id, required_level, is_mandatory)
VALUES ('00000003-0000-4000-8000-000000000079', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000006', '00000003-0000-4000-8000-000000000074', 1, TRUE);

-- acme.role-00000003-0000-4000-8000-000000000075
INSERT INTO workweave.role_competency_requirements (requirement_id, organization_id, workspace_id, role_id, competency_id, required_level, is_mandatory)
VALUES ('00000003-0000-4000-8000-000000000080', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000006', '00000003-0000-4000-8000-000000000075', 1, TRUE);

-- acme.role-00000003-0000-4000-8000-000000000076
INSERT INTO workweave.role_competency_requirements (requirement_id, organization_id, workspace_id, role_id, competency_id, required_level, is_mandatory)
VALUES ('00000003-0000-4000-8000-000000000081', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000006', '00000003-0000-4000-8000-000000000076', 1, TRUE);

-- acme.evidence-00000003-0000-4000-8000-000000000009-0
INSERT INTO workweave.employee_competency_evidence (evidence_id, organization_id, workspace_id, employee_id, competency_id, evidence_type, source_type, description, metadata, observed_at, validation_status, validated_by)
VALUES ('00000003-0000-4000-8000-000000000082', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000009', '00000003-0000-4000-8000-000000000072', 'SUPERVISOR_VALIDATION', 'MANUAL', 'Synthetic baseline validation for scenario review; not a real assessment.', '{"synthetic":true,"fixture":"review-only-sql-v1","not_real_employee_evidence":true}'::jsonb, (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000003-0000-4000-8000-000000000002') + interval '-7 days', 'VALIDATED', '00000003-0000-4000-8000-000000000013');

-- acme.state-00000003-0000-4000-8000-000000000009-0
INSERT INTO workweave.employee_competency_state (employee_competency_state_id, organization_id, workspace_id, employee_id, competency_id, current_level, last_evaluated_at, policy_version, evidence_refs)
VALUES ('00000003-0000-4000-8000-000000000083', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000009', '00000003-0000-4000-8000-000000000072', 2, (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000003-0000-4000-8000-000000000002') + interval '-7 days', 'synthetic-setup-v1', '["00000003-0000-4000-8000-000000000082"]'::jsonb);

-- acme.evidence-00000003-0000-4000-8000-000000000009-4
INSERT INTO workweave.employee_competency_evidence (evidence_id, organization_id, workspace_id, employee_id, competency_id, evidence_type, source_type, description, metadata, observed_at, validation_status, validated_by)
VALUES ('00000003-0000-4000-8000-000000000084', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000009', '00000003-0000-4000-8000-000000000076', 'SUPERVISOR_VALIDATION', 'MANUAL', 'Synthetic baseline validation for scenario review; not a real assessment.', '{"synthetic":true,"fixture":"review-only-sql-v1","not_real_employee_evidence":true}'::jsonb, (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000003-0000-4000-8000-000000000002') + interval '-7 days', 'VALIDATED', '00000003-0000-4000-8000-000000000013');

-- acme.state-00000003-0000-4000-8000-000000000009-4
INSERT INTO workweave.employee_competency_state (employee_competency_state_id, organization_id, workspace_id, employee_id, competency_id, current_level, last_evaluated_at, policy_version, evidence_refs)
VALUES ('00000003-0000-4000-8000-000000000085', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000009', '00000003-0000-4000-8000-000000000076', 2, (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000003-0000-4000-8000-000000000002') + interval '-7 days', 'synthetic-setup-v1', '["00000003-0000-4000-8000-000000000084"]'::jsonb);

-- acme.evidence-00000003-0000-4000-8000-000000000010-1
INSERT INTO workweave.employee_competency_evidence (evidence_id, organization_id, workspace_id, employee_id, competency_id, evidence_type, source_type, description, metadata, observed_at, validation_status, validated_by)
VALUES ('00000003-0000-4000-8000-000000000086', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000010', '00000003-0000-4000-8000-000000000073', 'SUPERVISOR_VALIDATION', 'MANUAL', 'Synthetic baseline validation for scenario review; not a real assessment.', '{"synthetic":true,"fixture":"review-only-sql-v1","not_real_employee_evidence":true}'::jsonb, (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000003-0000-4000-8000-000000000002') + interval '-7 days', 'VALIDATED', '00000003-0000-4000-8000-000000000013');

-- acme.state-00000003-0000-4000-8000-000000000010-1
INSERT INTO workweave.employee_competency_state (employee_competency_state_id, organization_id, workspace_id, employee_id, competency_id, current_level, last_evaluated_at, policy_version, evidence_refs)
VALUES ('00000003-0000-4000-8000-000000000087', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000010', '00000003-0000-4000-8000-000000000073', 2, (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000003-0000-4000-8000-000000000002') + interval '-7 days', 'synthetic-setup-v1', '["00000003-0000-4000-8000-000000000086"]'::jsonb);

-- acme.evidence-00000003-0000-4000-8000-000000000010-4
INSERT INTO workweave.employee_competency_evidence (evidence_id, organization_id, workspace_id, employee_id, competency_id, evidence_type, source_type, description, metadata, observed_at, validation_status, validated_by)
VALUES ('00000003-0000-4000-8000-000000000088', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000010', '00000003-0000-4000-8000-000000000076', 'SUPERVISOR_VALIDATION', 'MANUAL', 'Synthetic baseline validation for scenario review; not a real assessment.', '{"synthetic":true,"fixture":"review-only-sql-v1","not_real_employee_evidence":true}'::jsonb, (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000003-0000-4000-8000-000000000002') + interval '-7 days', 'VALIDATED', '00000003-0000-4000-8000-000000000013');

-- acme.state-00000003-0000-4000-8000-000000000010-4
INSERT INTO workweave.employee_competency_state (employee_competency_state_id, organization_id, workspace_id, employee_id, competency_id, current_level, last_evaluated_at, policy_version, evidence_refs)
VALUES ('00000003-0000-4000-8000-000000000089', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000010', '00000003-0000-4000-8000-000000000076', 2, (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000003-0000-4000-8000-000000000002') + interval '-7 days', 'synthetic-setup-v1', '["00000003-0000-4000-8000-000000000088"]'::jsonb);

-- acme.evidence-00000003-0000-4000-8000-000000000011-2
INSERT INTO workweave.employee_competency_evidence (evidence_id, organization_id, workspace_id, employee_id, competency_id, evidence_type, source_type, description, metadata, observed_at, validation_status, validated_by)
VALUES ('00000003-0000-4000-8000-000000000090', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000011', '00000003-0000-4000-8000-000000000074', 'SUPERVISOR_VALIDATION', 'MANUAL', 'Synthetic baseline validation for scenario review; not a real assessment.', '{"synthetic":true,"fixture":"review-only-sql-v1","not_real_employee_evidence":true}'::jsonb, (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000003-0000-4000-8000-000000000002') + interval '-7 days', 'VALIDATED', '00000003-0000-4000-8000-000000000013');

-- acme.state-00000003-0000-4000-8000-000000000011-2
INSERT INTO workweave.employee_competency_state (employee_competency_state_id, organization_id, workspace_id, employee_id, competency_id, current_level, last_evaluated_at, policy_version, evidence_refs)
VALUES ('00000003-0000-4000-8000-000000000091', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000011', '00000003-0000-4000-8000-000000000074', 2, (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000003-0000-4000-8000-000000000002') + interval '-7 days', 'synthetic-setup-v1', '["00000003-0000-4000-8000-000000000090"]'::jsonb);

-- acme.evidence-00000003-0000-4000-8000-000000000011-3
INSERT INTO workweave.employee_competency_evidence (evidence_id, organization_id, workspace_id, employee_id, competency_id, evidence_type, source_type, description, metadata, observed_at, validation_status, validated_by)
VALUES ('00000003-0000-4000-8000-000000000092', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000011', '00000003-0000-4000-8000-000000000075', 'SUPERVISOR_VALIDATION', 'MANUAL', 'Synthetic baseline validation for scenario review; not a real assessment.', '{"synthetic":true,"fixture":"review-only-sql-v1","not_real_employee_evidence":true}'::jsonb, (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000003-0000-4000-8000-000000000002') + interval '-7 days', 'VALIDATED', '00000003-0000-4000-8000-000000000013');

-- acme.state-00000003-0000-4000-8000-000000000011-3
INSERT INTO workweave.employee_competency_state (employee_competency_state_id, organization_id, workspace_id, employee_id, competency_id, current_level, last_evaluated_at, policy_version, evidence_refs)
VALUES ('00000003-0000-4000-8000-000000000093', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000011', '00000003-0000-4000-8000-000000000075', 2, (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000003-0000-4000-8000-000000000002') + interval '-7 days', 'synthetic-setup-v1', '["00000003-0000-4000-8000-000000000092"]'::jsonb);

-- acme.sop-source
INSERT INTO workweave.source_records (source_id, organization_id, workspace_id, source_type, evidence_type, access_partition, metadata)
VALUES ('00000003-0000-4000-8000-000000000094', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', 'APPROVED_EXCERPT', 'REPORTED', 'ORGANIZATION', '{"synthetic":true,"fixture":"review-only-sql-v1","not_real_employee_evidence":true}'::jsonb);

-- acme.sop
INSERT INTO workweave.knowledge_documents (document_id, organization_id, workspace_id, document_code, title, document_type)
VALUES ('00000003-0000-4000-8000-000000000095', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', 'OPS-SOP-001', 'Deployment and rollback reporting', 'SOP');

-- acme.sop-historical
INSERT INTO workweave.knowledge_document_versions (document_version_id, organization_id, workspace_id, document_id, version, content, source_id, approval_status, temporal_status, effective_at, approved_by_employee_id, approved_at)
VALUES ('00000003-0000-4000-8000-000000000096', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000095', '1.0', '# Historical synthetic reference
Superseded; not current instructions.', '00000003-0000-4000-8000-000000000094', 'APPROVED', 'SUPERSEDED', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000003-0000-4000-8000-000000000002') + interval '-60 days', '00000003-0000-4000-8000-000000000013', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000003-0000-4000-8000-000000000002') + interval '-61 days');

-- acme.sop-current
INSERT INTO workweave.knowledge_document_versions (document_version_id, organization_id, workspace_id, document_id, version, content, source_id, approval_status, temporal_status, effective_at, approved_by_employee_id, approved_at)
VALUES ('00000003-0000-4000-8000-000000000097', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000095', '1.1', '# OPS-SOP-001: Deployment and rollback reporting

## 1. Fundamentals

### 1. Introduction
Use the current approved source, not a familiar historical version. This text is a synthetic training fixture.

### 2. Deployment Process
Keep reported and verified facts separate. An earlier incident cannot prove a current cause. No operational action is authorized by this fixture.

### 3. Rollback
Name the current work item and approved source version. State missing evidence and ask the authorized reviewer for clarification. Do not invent company procedures.', '00000003-0000-4000-8000-000000000094', 'APPROVED', 'CURRENT', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000003-0000-4000-8000-000000000002') + interval '-7 days', '00000003-0000-4000-8000-000000000013', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000003-0000-4000-8000-000000000002') + interval '-8 days');

-- acme.curriculum
INSERT INTO workweave.curricula (curriculum_id, organization_id, workspace_id, name, version, status, published_at, completion_policy_version)
VALUES ('00000003-0000-4000-8000-000000000098', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', 'Deployment Fundamentals', '1.0', 'PUBLISHED', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000003-0000-4000-8000-000000000002') + interval '-1 day', 'synthetic-objective-v1');

-- acme.topic
INSERT INTO workweave.curriculum_topics (topic_id, organization_id, workspace_id, curriculum_id, name, order_index)
VALUES ('00000003-0000-4000-8000-000000000099', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000098', 'Deployment Fundamentals', 1);

-- acme.subtopic-0
INSERT INTO workweave.curriculum_subtopics (subtopic_id, organization_id, workspace_id, topic_id, name, order_index)
VALUES ('00000003-0000-4000-8000-000000000100', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000099', 'Introduction', 1);

-- acme.objective-0
INSERT INTO workweave.learning_objectives (objective_id, organization_id, workspace_id, subtopic_id, description, assessment_criteria, criteria_version, required, hint_policy, competency_id)
VALUES ('00000003-0000-4000-8000-000000000101', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000100', 'Demonstrate introduction.', '{"required_checks":["use_current_approved_evidence","keep_unknowns_explicit"],"synthetic":true}'::jsonb, 'synthetic-criteria-v1', TRUE, '{"hinted_answers":"FORMATIVE_ONLY"}'::jsonb, '00000003-0000-4000-8000-000000000072');

-- acme.chunk-0
INSERT INTO workweave.knowledge_chunks (chunk_id, organization_id, workspace_id, document_version_id, source_id, section_path, heading, content, chunk_index, source_span, metadata)
VALUES ('00000003-0000-4000-8000-000000000102', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000097', '00000003-0000-4000-8000-000000000094', '["Fundamentals","Introduction"]'::jsonb, 'Introduction', '### 1. Introduction
Use the current approved source, not a familiar historical version. This text is a synthetic training fixture.', 0, '{"heading":"Introduction","synthetic":true}'::jsonb, '{"synthetic":true,"fixture":"review-only-sql-v1","not_real_employee_evidence":true}'::jsonb);

-- acme.mapping-0
INSERT INTO workweave.knowledge_mappings (mapping_id, organization_id, workspace_id, document_id, document_version_id, section_ref, entity_type, entity_id, relationship_type)
VALUES ('00000003-0000-4000-8000-000000000103', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000095', '00000003-0000-4000-8000-000000000097', 'Introduction', 'CURRICULUM_SUBTOPIC', '00000003-0000-4000-8000-000000000100', 'TEACHES');

-- acme.subtopic-1
INSERT INTO workweave.curriculum_subtopics (subtopic_id, organization_id, workspace_id, topic_id, name, order_index)
VALUES ('00000003-0000-4000-8000-000000000104', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000099', 'Deployment Process', 2);

-- acme.objective-1
INSERT INTO workweave.learning_objectives (objective_id, organization_id, workspace_id, subtopic_id, description, assessment_criteria, criteria_version, required, hint_policy, competency_id)
VALUES ('00000003-0000-4000-8000-000000000105', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000104', 'Demonstrate deployment process.', '{"required_checks":["use_current_approved_evidence","keep_unknowns_explicit"],"synthetic":true}'::jsonb, 'synthetic-criteria-v1', TRUE, '{"hinted_answers":"FORMATIVE_ONLY"}'::jsonb, '00000003-0000-4000-8000-000000000073');

-- acme.chunk-1
INSERT INTO workweave.knowledge_chunks (chunk_id, organization_id, workspace_id, document_version_id, source_id, section_path, heading, content, chunk_index, source_span, metadata)
VALUES ('00000003-0000-4000-8000-000000000106', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000097', '00000003-0000-4000-8000-000000000094', '["Fundamentals","Deployment Process"]'::jsonb, 'Deployment Process', '### 2. Deployment Process
Keep reported and verified facts separate. An earlier incident cannot prove a current cause. No operational action is authorized by this fixture.', 1, '{"heading":"Deployment Process","synthetic":true}'::jsonb, '{"synthetic":true,"fixture":"review-only-sql-v1","not_real_employee_evidence":true}'::jsonb);

-- acme.mapping-1
INSERT INTO workweave.knowledge_mappings (mapping_id, organization_id, workspace_id, document_id, document_version_id, section_ref, entity_type, entity_id, relationship_type)
VALUES ('00000003-0000-4000-8000-000000000107', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000095', '00000003-0000-4000-8000-000000000097', 'Deployment Process', 'CURRICULUM_SUBTOPIC', '00000003-0000-4000-8000-000000000104', 'TEACHES');

-- acme.prereq-1
INSERT INTO workweave.curriculum_prerequisites (prerequisite_id, organization_id, workspace_id, subtopic_id, prerequisite_subtopic_id)
VALUES ('00000003-0000-4000-8000-000000000108', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000104', '00000003-0000-4000-8000-000000000100');

-- acme.subtopic-2
INSERT INTO workweave.curriculum_subtopics (subtopic_id, organization_id, workspace_id, topic_id, name, order_index)
VALUES ('00000003-0000-4000-8000-000000000109', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000099', 'Rollback', 3);

-- acme.objective-2
INSERT INTO workweave.learning_objectives (objective_id, organization_id, workspace_id, subtopic_id, description, assessment_criteria, criteria_version, required, hint_policy, competency_id)
VALUES ('00000003-0000-4000-8000-000000000110', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000109', 'Demonstrate rollback.', '{"required_checks":["use_current_approved_evidence","keep_unknowns_explicit"],"synthetic":true}'::jsonb, 'synthetic-criteria-v1', TRUE, '{"hinted_answers":"FORMATIVE_ONLY"}'::jsonb, '00000003-0000-4000-8000-000000000074');

-- acme.chunk-2
INSERT INTO workweave.knowledge_chunks (chunk_id, organization_id, workspace_id, document_version_id, source_id, section_path, heading, content, chunk_index, source_span, metadata)
VALUES ('00000003-0000-4000-8000-000000000111', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000097', '00000003-0000-4000-8000-000000000094', '["Fundamentals","Rollback"]'::jsonb, 'Rollback', '### 3. Rollback
Name the current work item and approved source version. State missing evidence and ask the authorized reviewer for clarification. Do not invent company procedures.', 2, '{"heading":"Rollback","synthetic":true}'::jsonb, '{"synthetic":true,"fixture":"review-only-sql-v1","not_real_employee_evidence":true}'::jsonb);

-- acme.mapping-2
INSERT INTO workweave.knowledge_mappings (mapping_id, organization_id, workspace_id, document_id, document_version_id, section_ref, entity_type, entity_id, relationship_type)
VALUES ('00000003-0000-4000-8000-000000000112', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000095', '00000003-0000-4000-8000-000000000097', 'Rollback', 'CURRICULUM_SUBTOPIC', '00000003-0000-4000-8000-000000000109', 'TEACHES');

-- acme.prereq-2
INSERT INTO workweave.curriculum_prerequisites (prerequisite_id, organization_id, workspace_id, subtopic_id, prerequisite_subtopic_id)
VALUES ('00000003-0000-4000-8000-000000000113', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000109', '00000003-0000-4000-8000-000000000104');

-- acme.learner-curriculum
INSERT INTO workweave.curriculum_assignments (assignment_id, organization_id, workspace_id, curriculum_id, employee_id, assigned_at, assigned_by_employee_id)
VALUES ('00000003-0000-4000-8000-000000000114', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000098', '00000003-0000-4000-8000-000000000011', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000003-0000-4000-8000-000000000002') + interval '0 seconds', '00000003-0000-4000-8000-000000000013');

-- acme.learner-assignment
INSERT INTO workweave.learning_assignments (learning_assignment_id, organization_id, workspace_id, employee_id, curriculum_id, originating_assignment_id, assignment_kind)
VALUES ('00000003-0000-4000-8000-000000000115', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000011', '00000003-0000-4000-8000-000000000098', '00000003-0000-4000-8000-000000000114', 'INITIAL');

-- acme.learner-progress-0
INSERT INTO workweave.employee_learning_progress (progress_id, organization_id, workspace_id, employee_id, learning_assignment_id, subtopic_id, status)
VALUES ('00000003-0000-4000-8000-000000000116', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000011', '00000003-0000-4000-8000-000000000115', '00000003-0000-4000-8000-000000000100', 'NOT_STARTED');

-- acme.learner-progress-1
INSERT INTO workweave.employee_learning_progress (progress_id, organization_id, workspace_id, employee_id, learning_assignment_id, subtopic_id, status)
VALUES ('00000003-0000-4000-8000-000000000117', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000011', '00000003-0000-4000-8000-000000000115', '00000003-0000-4000-8000-000000000104', 'NOT_STARTED');

-- acme.learner-progress-2
INSERT INTO workweave.employee_learning_progress (progress_id, organization_id, workspace_id, employee_id, learning_assignment_id, subtopic_id, status)
VALUES ('00000003-0000-4000-8000-000000000118', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000011', '00000003-0000-4000-8000-000000000115', '00000003-0000-4000-8000-000000000109', 'NOT_STARTED');

-- acme.work-0
INSERT INTO workweave.work_items (work_item_id, organization_id, workspace_id, external_system, external_id, work_item_type, title, description, priority, status, due_at, metadata)
VALUES ('00000003-0000-4000-8000-000000000119', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', 'synthetic_seed', 'INC-203', 'INCIDENT', 'Payment API Timeout', 'Gateway investigation ongoing. A prior-shift member completion report requires lead verification.', 'HIGH', 'IN_PROGRESS', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000003-0000-4000-8000-000000000002') + interval '2 hours', '{"synthetic":true,"fixture":"review-only-sql-v1","not_real_employee_evidence":true}'::jsonb);

-- acme.requirement-0
INSERT INTO workweave.work_item_competency_requirements (id, organization_id, workspace_id, work_item_id, competency_id, required_level, importance)
VALUES ('00000003-0000-4000-8000-000000000120', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000119', '00000003-0000-4000-8000-000000000072', 1, 1);

-- acme.work-1
INSERT INTO workweave.work_items (work_item_id, organization_id, workspace_id, external_system, external_id, work_item_type, title, description, priority, status, due_at, metadata)
VALUES ('00000003-0000-4000-8000-000000000121', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', 'synthetic_seed', 'INC-221', 'INCIDENT', 'Network Latency', 'Waiting for approved network diagnostic evidence.', 'MEDIUM', 'BLOCKED', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000003-0000-4000-8000-000000000002') + interval '6 hours', '{"synthetic":true,"fixture":"review-only-sql-v1","not_real_employee_evidence":true}'::jsonb);

-- acme.requirement-1
INSERT INTO workweave.work_item_competency_requirements (id, organization_id, workspace_id, work_item_id, competency_id, required_level, importance)
VALUES ('00000003-0000-4000-8000-000000000122', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000121', '00000003-0000-4000-8000-000000000073', 1, 1);

-- acme.work-2
INSERT INTO workweave.work_items (work_item_id, organization_id, workspace_id, external_system, external_id, work_item_type, title, description, priority, status, due_at, metadata)
VALUES ('00000003-0000-4000-8000-000000000123', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', 'synthetic_seed', 'ACT-101', 'ACTIVITY', 'Production Database Maintenance', 'Maintenance tonight; approved window must be confirmed before execution.', 'MEDIUM', 'ACTIVE', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000003-0000-4000-8000-000000000002') + interval '6 hours', '{"synthetic":true,"fixture":"review-only-sql-v1","not_real_employee_evidence":true}'::jsonb);

-- acme.requirement-2
INSERT INTO workweave.work_item_competency_requirements (id, organization_id, workspace_id, work_item_id, competency_id, required_level, importance)
VALUES ('00000003-0000-4000-8000-000000000124', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000123', '00000003-0000-4000-8000-000000000074', 1, 1);

-- acme.work-session
INSERT INTO workweave.work_sessions (work_session_id, organization_id, workspace_id, employee_id, shift_instance_id, started_at, status)
VALUES ('00000003-0000-4000-8000-000000000125', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000008', '00000003-0000-4000-8000-000000000059', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000003-0000-4000-8000-000000000002') + interval '0 seconds', 'ACTIVE');

-- acme.proposal
INSERT INTO workweave.delegation_proposals (delegation_proposal_id, organization_id, workspace_id, shift_instance_id, team_id, created_by, status, context_revisions)
VALUES ('00000003-0000-4000-8000-000000000126', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000059', '00000003-0000-4000-8000-000000000005', '00000003-0000-4000-8000-000000000008', 'PROPOSED', '{"synthetic":true,"team_revision":1}'::jsonb);

-- acme.proposal-item-0
INSERT INTO workweave.delegation_proposal_items (proposal_item_id, organization_id, workspace_id, delegation_proposal_id, work_item_id, recommended_employee_id, recommendation_reason, match_data)
VALUES ('00000003-0000-4000-8000-000000000127', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000126', '00000003-0000-4000-8000-000000000119', '00000003-0000-4000-8000-000000000009', 'Synthetic proposed match from validated baseline evidence and declared availability; needs human confirmation.', '{"synthetic":true,"fixture":"review-only-sql-v1","not_real_employee_evidence":true}'::jsonb);

-- acme.proposal-item-1
INSERT INTO workweave.delegation_proposal_items (proposal_item_id, organization_id, workspace_id, delegation_proposal_id, work_item_id, recommended_employee_id, recommendation_reason, match_data)
VALUES ('00000003-0000-4000-8000-000000000128', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000126', '00000003-0000-4000-8000-000000000121', '00000003-0000-4000-8000-000000000010', 'Synthetic proposed match from validated baseline evidence and declared availability; needs human confirmation.', '{"synthetic":true,"fixture":"review-only-sql-v1","not_real_employee_evidence":true}'::jsonb);

-- acme.proposal-item-2
INSERT INTO workweave.delegation_proposal_items (proposal_item_id, organization_id, workspace_id, delegation_proposal_id, work_item_id, recommended_employee_id, recommendation_reason, match_data)
VALUES ('00000003-0000-4000-8000-000000000129', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000126', '00000003-0000-4000-8000-000000000123', '00000003-0000-4000-8000-000000000011', 'Synthetic proposed match from validated baseline evidence and declared availability; needs human confirmation.', '{"synthetic":true,"fixture":"review-only-sql-v1","not_real_employee_evidence":true}'::jsonb);

-- acme.historical-assignment
INSERT INTO workweave.work_item_assignments (assignment_id, organization_id, workspace_id, work_item_id, employee_id, assigned_by_employee_id, assignment_source, status, assigned_at)
VALUES ('00000003-0000-4000-8000-000000000130', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000119', '00000003-0000-4000-8000-000000000009', '00000003-0000-4000-8000-000000000008', 'MANUAL', 'CANCELLED', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000003-0000-4000-8000-000000000002') + interval '-8 hours');

-- acme.member-report
INSERT INTO workweave.work_events (work_event_id, organization_id, workspace_id, work_item_id, employee_id, shift_instance_id, event_type, description, event_data, evidence_refs, observed_at)
VALUES ('00000003-0000-4000-8000-000000000131', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000119', '00000003-0000-4000-8000-000000000009', '00000003-0000-4000-8000-000000000052', 'REPORTED_COMPLETE', 'John reported correcting the gateway configuration and validating transactions. Lead verification is still pending.', '{"synthetic":true,"fixture":"review-only-sql-v1","not_real_employee_evidence":true,"prior_assignment_ended":true}'::jsonb, '["00000003-0000-4000-8000-000000000094"]'::jsonb, (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000003-0000-4000-8000-000000000002') + interval '-1 hour');

-- acme.lead-work-state
INSERT INTO workweave.employee_work_state (employee_work_state_id, organization_id, workspace_id, employee_id, shift_instance_id, work_context_key, workload_state, active_work_count, blocked_work_count, metadata)
VALUES ('00000003-0000-4000-8000-000000000132', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000008', '00000003-0000-4000-8000-000000000059', 'shift:00000003-0000-4000-8000-000000000059', 'NEEDS_FOCUS', 3, 1, '{"synthetic":true,"fixture":"review-only-sql-v1","not_real_employee_evidence":true,"derived_from_current_items":true}'::jsonb);

-- acme.template
INSERT INTO workweave.handover_templates (template_id, organization_id, workspace_id, team_id, name, is_default)
VALUES ('00000003-0000-4000-8000-000000000133', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000005', 'Team continuity', TRUE);

-- acme.template-v1
INSERT INTO workweave.handover_template_versions (template_version_id, organization_id, workspace_id, template_id, version, published_at)
VALUES ('00000003-0000-4000-8000-000000000134', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000133', 1, (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000003-0000-4000-8000-000000000002') + interval '-2 days');

-- acme.section-0
INSERT INTO workweave.handover_template_sections (section_id, organization_id, workspace_id, template_version_id, name, order_index, is_required)
VALUES ('00000003-0000-4000-8000-000000000135', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000134', 'Shift Summary', 1, TRUE);

-- acme.section-1
INSERT INTO workweave.handover_template_sections (section_id, organization_id, workspace_id, template_version_id, name, order_index, is_required)
VALUES ('00000003-0000-4000-8000-000000000136', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000134', 'Active / Ongoing Items', 2, TRUE);

-- acme.section-2
INSERT INTO workweave.handover_template_sections (section_id, organization_id, workspace_id, template_version_id, name, order_index, is_required)
VALUES ('00000003-0000-4000-8000-000000000137', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000134', 'Incidents / Issues', 3, FALSE);

-- acme.section-3
INSERT INTO workweave.handover_template_sections (section_id, organization_id, workspace_id, template_version_id, name, order_index, is_required)
VALUES ('00000003-0000-4000-8000-000000000138', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000134', 'Scheduled Activities', 4, FALSE);

-- acme.section-4
INSERT INTO workweave.handover_template_sections (section_id, organization_id, workspace_id, template_version_id, name, order_index, is_required)
VALUES ('00000003-0000-4000-8000-000000000139', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000134', 'Blockers / Risks', 5, FALSE);

-- acme.section-5
INSERT INTO workweave.handover_template_sections (section_id, organization_id, workspace_id, template_version_id, name, order_index, is_required)
VALUES ('00000003-0000-4000-8000-000000000140', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000134', 'Important Notes', 6, FALSE);

-- acme.morning-handover
INSERT INTO workweave.shift_handovers (handover_id, organization_id, workspace_id, source_shift_instance_id, target_shift_instance_id, template_version_id, status, created_by_employee_id, context_as_of, context_revisions, draft_sections)
VALUES ('00000003-0000-4000-8000-000000000141', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000052', '00000003-0000-4000-8000-000000000059', '00000003-0000-4000-8000-000000000134', 'DRAFT', '00000003-0000-4000-8000-000000000008', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000003-0000-4000-8000-000000000002') + interval '-2 hours', '{"synthetic":true,"fixture":"review-only-sql-v1","not_real_employee_evidence":true}'::jsonb, '[{"section_id":"00000003-0000-4000-8000-000000000135","status":"DOCUMENTED","content":"Synthetic shift summary. Open work requires follow-up."},{"section_id":"00000003-0000-4000-8000-000000000136","status":"DOCUMENTED","content":"INC-203: IN_PROGRESS. Gateway investigation ongoing. A prior-shift member completion report requires lead verification.\nINC-221: BLOCKED. Waiting for approved network diagnostic evidence.\nACT-101: ACTIVE. Maintenance tonight; approved window must be confirmed before execution."}]'::jsonb);

-- acme.morning-publication
INSERT INTO workweave.handover_publications (publication_id, organization_id, workspace_id, handover_id, publication_number, content_revision, scope_snapshot, template_version_id, section_content, source_revisions, published_by, published_at)
VALUES ('00000003-0000-4000-8000-000000000142', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000141', 1, 1, '{"target_shift_instance_id":"00000003-0000-4000-8000-000000000059","synthetic":true}'::jsonb, '00000003-0000-4000-8000-000000000134', '[{"section_id":"00000003-0000-4000-8000-000000000135","status":"DOCUMENTED","content":"Synthetic shift summary. Open work requires follow-up."},{"section_id":"00000003-0000-4000-8000-000000000136","status":"DOCUMENTED","content":"INC-203: IN_PROGRESS. Gateway investigation ongoing. A prior-shift member completion report requires lead verification.\nINC-221: BLOCKED. Waiting for approved network diagnostic evidence.\nACT-101: ACTIVE. Maintenance tonight; approved window must be confirmed before execution."}]'::jsonb, '{"source_id":"00000003-0000-4000-8000-000000000094","document_version_id":"00000003-0000-4000-8000-000000000097"}'::jsonb, '00000003-0000-4000-8000-000000000008', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000003-0000-4000-8000-000000000002') + interval '-2 hours');

-- acme.afternoon-draft
INSERT INTO workweave.shift_handovers (handover_id, organization_id, workspace_id, source_shift_instance_id, target_shift_instance_id, template_version_id, status, created_by_employee_id, context_as_of, context_revisions, draft_sections)
VALUES ('00000003-0000-4000-8000-000000000143', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000059', '00000003-0000-4000-8000-000000000066', '00000003-0000-4000-8000-000000000134', 'DRAFT', '00000003-0000-4000-8000-000000000008', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000003-0000-4000-8000-000000000002') + interval '0 seconds', '{"synthetic":true,"fixture":"review-only-sql-v1","not_real_employee_evidence":true}'::jsonb, '[{"section_id":"00000003-0000-4000-8000-000000000135","status":"DOCUMENTED","content":"Synthetic shift summary. Open work requires follow-up."},{"section_id":"00000003-0000-4000-8000-000000000136","status":"DOCUMENTED","content":"INC-203: IN_PROGRESS. Gateway investigation ongoing. A prior-shift member completion report requires lead verification.\nINC-221: BLOCKED. Waiting for approved network diagnostic evidence.\nACT-101: ACTIVE. Maintenance tonight; approved window must be confirmed before execution."}]'::jsonb);

-- acme.handover-item-0
INSERT INTO workweave.handover_items (handover_item_id, organization_id, workspace_id, work_item_id, title, description, originating_shift_instance_id, originating_employee_id, current_owner_shift_instance_id, work_status, acknowledgement_status)
VALUES ('00000003-0000-4000-8000-000000000144', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000119', 'Payment API Timeout', 'Gateway investigation ongoing. A prior-shift member completion report requires lead verification.', '00000003-0000-4000-8000-000000000052', '00000003-0000-4000-8000-000000000008', '00000003-0000-4000-8000-000000000059', 'IN_PROGRESS', 'NOT_REQUIRED');

-- acme.morning-entry-0
INSERT INTO workweave.handover_entries (handover_entry_id, organization_id, workspace_id, publication_id, handover_item_id, section_id, snapshot_work_status, snapshot_acknowledgement_status, snapshot_description, snapshot_source_refs)
VALUES ('00000003-0000-4000-8000-000000000145', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000142', '00000003-0000-4000-8000-000000000144', '00000003-0000-4000-8000-000000000136', 'IN_PROGRESS', 'NOT_REQUIRED', 'Gateway investigation ongoing. A prior-shift member completion report requires lead verification.', '["00000003-0000-4000-8000-000000000094"]'::jsonb);

-- acme.item-source-0
INSERT INTO workweave.handover_item_sources (source_id, organization_id, workspace_id, handover_item_id, source_type, external_system, external_id, source_reference, extracted_data, detected_by_ai, confirmed_by_employee_id)
VALUES ('00000003-0000-4000-8000-000000000146', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000144', 'TICKET', 'synthetic_seed', 'INC-203', 'Synthetic work item', '{"synthetic":true,"fixture":"review-only-sql-v1","not_real_employee_evidence":true}'::jsonb, FALSE, '00000003-0000-4000-8000-000000000008');

-- acme.handover-item-1
INSERT INTO workweave.handover_items (handover_item_id, organization_id, workspace_id, work_item_id, title, description, originating_shift_instance_id, originating_employee_id, current_owner_shift_instance_id, work_status, acknowledgement_status)
VALUES ('00000003-0000-4000-8000-000000000147', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000121', 'Network Latency', 'Waiting for approved network diagnostic evidence.', '00000003-0000-4000-8000-000000000052', '00000003-0000-4000-8000-000000000008', '00000003-0000-4000-8000-000000000059', 'BLOCKED', 'NOT_REQUIRED');

-- acme.morning-entry-1
INSERT INTO workweave.handover_entries (handover_entry_id, organization_id, workspace_id, publication_id, handover_item_id, section_id, snapshot_work_status, snapshot_acknowledgement_status, snapshot_description, snapshot_source_refs)
VALUES ('00000003-0000-4000-8000-000000000148', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000142', '00000003-0000-4000-8000-000000000147', '00000003-0000-4000-8000-000000000136', 'BLOCKED', 'NOT_REQUIRED', 'Waiting for approved network diagnostic evidence.', '["00000003-0000-4000-8000-000000000094"]'::jsonb);

-- acme.item-source-1
INSERT INTO workweave.handover_item_sources (source_id, organization_id, workspace_id, handover_item_id, source_type, external_system, external_id, source_reference, extracted_data, detected_by_ai, confirmed_by_employee_id)
VALUES ('00000003-0000-4000-8000-000000000149', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000147', 'TICKET', 'synthetic_seed', 'INC-221', 'Synthetic work item', '{"synthetic":true,"fixture":"review-only-sql-v1","not_real_employee_evidence":true}'::jsonb, FALSE, '00000003-0000-4000-8000-000000000008');

-- acme.handover-item-2
INSERT INTO workweave.handover_items (handover_item_id, organization_id, workspace_id, work_item_id, title, description, originating_shift_instance_id, originating_employee_id, current_owner_shift_instance_id, work_status, acknowledgement_status)
VALUES ('00000003-0000-4000-8000-000000000150', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000123', 'Production Database Maintenance', 'Maintenance tonight; approved window must be confirmed before execution.', '00000003-0000-4000-8000-000000000052', '00000003-0000-4000-8000-000000000008', '00000003-0000-4000-8000-000000000059', 'ACTIVE', 'NOT_REQUIRED');

-- acme.morning-entry-2
INSERT INTO workweave.handover_entries (handover_entry_id, organization_id, workspace_id, publication_id, handover_item_id, section_id, snapshot_work_status, snapshot_acknowledgement_status, snapshot_description, snapshot_source_refs)
VALUES ('00000003-0000-4000-8000-000000000151', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000142', '00000003-0000-4000-8000-000000000150', '00000003-0000-4000-8000-000000000136', 'ACTIVE', 'NOT_REQUIRED', 'Maintenance tonight; approved window must be confirmed before execution.', '["00000003-0000-4000-8000-000000000094"]'::jsonb);

-- acme.item-source-2
INSERT INTO workweave.handover_item_sources (source_id, organization_id, workspace_id, handover_item_id, source_type, external_system, external_id, source_reference, extracted_data, detected_by_ai, confirmed_by_employee_id)
VALUES ('00000003-0000-4000-8000-000000000152', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000150', 'TICKET', 'synthetic_seed', 'ACT-101', 'Synthetic work item', '{"synthetic":true,"fixture":"review-only-sql-v1","not_real_employee_evidence":true}'::jsonb, FALSE, '00000003-0000-4000-8000-000000000008');

-- acme.report-suggestion
INSERT INTO workweave.handover_suggestions (suggestion_id, organization_id, workspace_id, handover_id, handover_item_id, suggestion_type, suggested_data, reason, source_refs, context_revisions, status)
VALUES ('00000003-0000-4000-8000-000000000153', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000143', '00000003-0000-4000-8000-000000000144', 'STATUS_UPDATE', '{"work_event_id":"00000003-0000-4000-8000-000000000131","reported_complete":true,"synthetic":true}'::jsonb, 'Compare the prior-shift report with the draft. Human review required.', '["00000003-0000-4000-8000-000000000131"]'::jsonb, '{"synthetic":true,"fixture":"review-only-sql-v1","not_real_employee_evidence":true}'::jsonb, 'PENDING');

-- acme.report-source
INSERT INTO workweave.handover_item_sources (source_id, organization_id, workspace_id, suggestion_id, source_type, source_reference, extracted_data, detected_by_ai)
VALUES ('00000003-0000-4000-8000-000000000154', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000153', 'WORK_EVENT', '00000003-0000-4000-8000-000000000131', '{"synthetic":true,"fixture":"review-only-sql-v1","not_real_employee_evidence":true}'::jsonb, FALSE);

-- acme.email
INSERT INTO workweave.source_records (source_id, organization_id, workspace_id, source_type, owner_employee_id, evidence_type, access_partition, metadata)
VALUES ('00000003-0000-4000-8000-000000000155', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', 'EMAIL', '00000003-0000-4000-8000-000000000008', 'REPORTED', 'TEAM', '{"synthetic":true,"fixture":"review-only-sql-v1","not_real_employee_evidence":true,"subject":"Upcoming team activity","scheduled_at_relative":"+6 hours"}'::jsonb);

-- acme.email-suggestion
INSERT INTO workweave.handover_suggestions (suggestion_id, organization_id, workspace_id, handover_id, suggestion_type, suggested_data, reason, source_refs, context_revisions, status)
VALUES ('00000003-0000-4000-8000-000000000156', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000143', 'MISSING_ITEM', '{"title":"Production database maintenance","section":"Scheduled Activities","time_confirmation":"PENDING","source_id":"00000003-0000-4000-8000-000000000155","synthetic":true}'::jsonb, 'Synthetic email activity does not appear in the draft; review before adding.', '["00000003-0000-4000-8000-000000000155"]'::jsonb, '{"synthetic":true,"fixture":"review-only-sql-v1","not_real_employee_evidence":true}'::jsonb, 'PENDING');

-- acme.email-source
INSERT INTO workweave.handover_item_sources (source_id, organization_id, workspace_id, suggestion_id, source_type, external_system, external_id, source_reference, extracted_data, detected_by_ai)
VALUES ('00000003-0000-4000-8000-000000000157', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000156', 'EMAIL', 'synthetic_seed', 'MAIL-101', '00000003-0000-4000-8000-000000000155', '{"synthetic":true,"fixture":"review-only-sql-v1","not_real_employee_evidence":true}'::jsonb, FALSE);

-- acme.kt-consent
INSERT INTO workweave.consent_sessions (consent_session_id, organization_id, workspace_id, purpose, owner_employee_id, notice_version, accepted_at, requested_audience, raw_retention, status)
VALUES ('00000003-0000-4000-8000-000000000158', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', 'EXIT_KT_INTERVIEW', '00000003-0000-4000-8000-000000000012', 'synthetic-notice-v1', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000003-0000-4000-8000-000000000002') + interval '-30 minutes', '{"draft":"OWNER_ONLY","submitted":"DESIGNATED_REVIEWER","approved":"AUTHORIZED_SUCCESSOR"}'::jsonb, '{"days":7,"synthetic":true}'::jsonb, 'ACTIVE');

-- acme.interview-source
INSERT INTO workweave.source_records (source_id, organization_id, workspace_id, source_type, owner_employee_id, consent_session_id, evidence_type, access_partition, retention_until, metadata)
VALUES ('00000003-0000-4000-8000-000000000159', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', 'INTERVIEW', '00000003-0000-4000-8000-000000000012', '00000003-0000-4000-8000-000000000158', 'REPORTED', 'PRIVATE', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000003-0000-4000-8000-000000000002') + interval '7 days', '{"synthetic":true,"fixture":"review-only-sql-v1","not_real_employee_evidence":true}'::jsonb);

-- acme.kt-case
INSERT INTO workweave.exit_kt_cases (exit_kt_case_id, organization_id, workspace_id, employee_id, case_kind, final_working_date, status, initiated_by_employee_id, reviewer_employee_id, started_at)
VALUES ('00000003-0000-4000-8000-000000000160', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000012', 'DEPARTURE', CURRENT_DATE + 14, 'IN_PROGRESS', '00000003-0000-4000-8000-000000000013', '00000003-0000-4000-8000-000000000013', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000003-0000-4000-8000-000000000002') + interval '-1 day');

-- acme.inventory-documented
INSERT INTO workweave.exit_kt_knowledge_items (kt_item_id, organization_id, workspace_id, exit_kt_case_id, title, description, documentation_status, kt_status, risk_level)
VALUES ('00000003-0000-4000-8000-000000000161', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000160', 'Deployment and rollback reporting', 'Current approved SOP already exists.', 'DOCUMENTED', 'EXISTING_KNOWLEDGE', 'MEDIUM');

-- acme.inventory-outdated
INSERT INTO workweave.exit_kt_knowledge_items (kt_item_id, organization_id, workspace_id, exit_kt_case_id, title, description, documentation_status, kt_status, risk_level)
VALUES ('00000003-0000-4000-8000-000000000162', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000160', 'Historical procedure references', 'Historical version appears in older notes; compare against current source.', 'OUTDATED', 'NOT_STARTED', 'MEDIUM');

-- acme.inventory-missing
INSERT INTO workweave.exit_kt_knowledge_items (kt_item_id, organization_id, workspace_id, exit_kt_case_id, title, description, documentation_status, kt_status, risk_level)
VALUES ('00000003-0000-4000-8000-000000000163', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000160', 'Evidence-based escalation practice', 'Employee reporting practice is not yet approved reusable knowledge.', 'MISSING', 'DRAFT_CREATED', 'HIGH');

-- acme.kt-doc-source
INSERT INTO workweave.exit_kt_sources (source_id, organization_id, workspace_id, kt_item_id, source_type, source_reference, relevance_data)
VALUES ('00000003-0000-4000-8000-000000000164', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000161', 'DOCUMENT', '00000003-0000-4000-8000-000000000097', '{"synthetic":true,"fixture":"review-only-sql-v1","not_real_employee_evidence":true}'::jsonb);

-- acme.finding-OUTDATED_DOCUMENTATION
INSERT INTO workweave.exit_kt_findings (finding_id, organization_id, workspace_id, exit_kt_case_id, kt_item_id, finding_type, description, evidence_refs, status)
VALUES ('00000003-0000-4000-8000-000000000165', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000160', '00000003-0000-4000-8000-000000000162', 'OUTDATED_DOCUMENTATION', 'Review the old document reference; it is not proof that current instructions are wrong.', '["00000003-0000-4000-8000-000000000094"]'::jsonb, 'OPEN');

-- acme.finding-UNDOCUMENTED_KNOWLEDGE
INSERT INTO workweave.exit_kt_findings (finding_id, organization_id, workspace_id, exit_kt_case_id, kt_item_id, finding_type, description, evidence_refs, status)
VALUES ('00000003-0000-4000-8000-000000000166', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000160', '00000003-0000-4000-8000-000000000163', 'UNDOCUMENTED_KNOWLEDGE', 'Reporting practice needs employee review and knowledge approval.', '["00000003-0000-4000-8000-000000000094"]'::jsonb, 'OPEN');

-- acme.finding-MISSING_SUCCESSOR
INSERT INTO workweave.exit_kt_findings (finding_id, organization_id, workspace_id, exit_kt_case_id, kt_item_id, finding_type, description, evidence_refs, status)
VALUES ('00000003-0000-4000-8000-000000000167', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000160', '00000003-0000-4000-8000-000000000163', 'MISSING_SUCCESSOR', 'A proposed successor is not a completed ownership transfer.', '["00000003-0000-4000-8000-000000000094"]'::jsonb, 'OPEN');

-- acme.interview
INSERT INTO workweave.exit_kt_interviews (interview_id, organization_id, workspace_id, kt_item_id, employee_id, consent_session_id, status, started_at)
VALUES ('00000003-0000-4000-8000-000000000168', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000163', '00000003-0000-4000-8000-000000000012', '00000003-0000-4000-8000-000000000158', 'PAUSED', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000003-0000-4000-8000-000000000002') + interval '-30 minutes');

-- acme.interview-question
INSERT INTO workweave.exit_kt_interview_messages (message_id, organization_id, workspace_id, interview_id, sender_type, message_type, content, metadata, source_refs)
VALUES ('00000003-0000-4000-8000-000000000169', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000168', 'AI', 'SCRIPTED_FIXTURE', 'Which current work item and approved source do you include when requesting missing evidence?', '{"synthetic":true,"fixture":"review-only-sql-v1","not_real_employee_evidence":true,"no_model_was_called":true}'::jsonb, '["00000003-0000-4000-8000-000000000094"]'::jsonb);

-- acme.interview-answer
INSERT INTO workweave.exit_kt_interview_messages (message_id, organization_id, workspace_id, interview_id, sender_type, content, metadata, source_refs)
VALUES ('00000003-0000-4000-8000-000000000170', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000168', 'EMPLOYEE', 'I include the work item and source version, keep the cause unknown, and ask the reviewer to verify the missing evidence.', '{"synthetic":true,"fixture":"review-only-sql-v1","not_real_employee_evidence":true}'::jsonb, '["00000003-0000-4000-8000-000000000159"]'::jsonb);

-- acme.artifact
INSERT INTO workweave.exit_kt_artifacts (artifact_id, organization_id, workspace_id, kt_item_id, artifact_type, title, generated_from_interview_id)
VALUES ('00000003-0000-4000-8000-000000000171', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000163', 'CHECKLIST', 'Requesting evidence-based clarification', '00000003-0000-4000-8000-000000000168');

-- acme.artifact-draft
INSERT INTO workweave.exit_kt_artifact_revisions (artifact_revision_id, organization_id, workspace_id, artifact_id, version, content, status, source_refs)
VALUES ('00000003-0000-4000-8000-000000000172', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000171', 1, '# Private synthetic checklist
1. Identify the current work item.
2. Cite the approved source version.
3. State missing evidence and ask the reviewer.

DRAFT: employee review and knowledge approval are pending.', 'DRAFT', '["00000003-0000-4000-8000-000000000159"]'::jsonb);

-- acme.responsibility
INSERT INTO workweave.responsibilities (responsibility_id, organization_id, workspace_id, responsibility_type, title, owner_employee_id, ownership_revision, description)
VALUES ('00000003-0000-4000-8000-000000000173', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', 'PROCESS', 'Payment gateway operations', '00000003-0000-4000-8000-000000000012', 1, 'Synthetic role responsibility. No transfer has been completed.');

-- acme.transfer
INSERT INTO workweave.responsibility_transfers (transfer_id, organization_id, workspace_id, exit_kt_case_id, responsibility_id, current_owner_employee_id, recommended_owner_employee_id, recommendation_reason, recommendation_data, status, effective_at, expected_owner_revision)
VALUES ('00000003-0000-4000-8000-000000000174', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000160', '00000003-0000-4000-8000-000000000173', '00000003-0000-4000-8000-000000000012', '00000003-0000-4000-8000-000000000010', 'Synthetic proposed successor; human confirmation and package receipt remain required.', '{"synthetic":true,"fixture":"review-only-sql-v1","not_real_employee_evidence":true}'::jsonb, 'PROPOSED', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000003-0000-4000-8000-000000000002') + interval '1 day', 1);

-- acme.uncovered-responsibility
INSERT INTO workweave.responsibilities (responsibility_id, organization_id, workspace_id, responsibility_type, title, owner_employee_id, ownership_revision)
VALUES ('00000003-0000-4000-8000-000000000175', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', 'RECURRING_TASK', 'Certificate renewal and vendor escalation', '00000003-0000-4000-8000-000000000012', 1);

-- acme.kt-package
INSERT INTO workweave.exit_kt_packages (package_id, organization_id, workspace_id, exit_kt_case_id, successor_employee_id, status, effective_at, context_revisions, draft_sections)
VALUES ('00000003-0000-4000-8000-000000000176', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000160', '00000003-0000-4000-8000-000000000010', 'DRAFT', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000003-0000-4000-8000-000000000002') + interval '1 day', '{"synthetic":true,"fixture":"review-only-sql-v1","not_real_employee_evidence":true}'::jsonb, '[{"title":"Responsibilities","content":"Payment gateway operations"},{"title":"Knowledge gaps","content":"Private checklist awaits employee review and knowledge approval."}]'::jsonb);

-- acme.package-responsibility
INSERT INTO workweave.exit_kt_package_responsibilities (package_responsibility_id, organization_id, workspace_id, package_id, responsibility_id)
VALUES ('00000003-0000-4000-8000-000000000177', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000176', '00000003-0000-4000-8000-000000000173');

-- acme.knowledge-checklist
INSERT INTO workweave.kt_checklist_items (checklist_item_id, organization_id, workspace_id, exit_kt_case_id, knowledge_item_id, required, status, evidence_refs)
VALUES ('00000003-0000-4000-8000-000000000178', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000160', '00000003-0000-4000-8000-000000000163', TRUE, 'OPEN', '[]'::jsonb);

-- acme.responsibility-checklist
INSERT INTO workweave.kt_checklist_items (checklist_item_id, organization_id, workspace_id, exit_kt_case_id, responsibility_id, required, status, evidence_refs)
VALUES ('00000003-0000-4000-8000-000000000179', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000160', '00000003-0000-4000-8000-000000000173', TRUE, 'OPEN', '[]'::jsonb);

-- acme.seed-audit
INSERT INTO workweave.audit_events (audit_event_id, organization_id, workspace_id, actor_id, action, resource_type, resource_id, resource_revision, result, source_refs, request_id)
VALUES ('00000003-0000-4000-8000-000000000181', '00000003-0000-4000-8000-000000000001', '00000003-0000-4000-8000-000000000002', '00000003-0000-4000-8000-000000000013', 'SYNTHETIC_FIXTURE_STAGED', 'workspace', '00000003-0000-4000-8000-000000000002', 1, 'REVIEW_ONLY_NO_LIVE_WORKFLOW_COMPLETED', '[]'::jsonb, '00000003-0000-4000-8000-000000000180');


-- NORTHSTAR synthetic fixtures
-- northstar.resume-curriculum-assignment
INSERT INTO workweave.curriculum_assignments (assignment_id, organization_id, workspace_id, curriculum_id, employee_id, assigned_at, assigned_by_employee_id, status)
VALUES ('00000001-0000-4000-8000-000000000900', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000068', '00000001-0000-4000-8000-000000000010', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000001-0000-4000-8000-000000000002') + interval '-2 days', '00000001-0000-4000-8000-000000000011', 'ACTIVE');

-- northstar.resume-learning-assignment
INSERT INTO workweave.learning_assignments (learning_assignment_id, organization_id, workspace_id, employee_id, curriculum_id, originating_assignment_id, assignment_kind, status)
VALUES ('00000001-0000-4000-8000-000000000901', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000010', '00000001-0000-4000-8000-000000000068', '00000001-0000-4000-8000-000000000900', 'INITIAL', 'ACTIVE');

-- northstar.resume-session
INSERT INTO workweave.learning_sessions (learning_session_id, organization_id, workspace_id, employee_id, learning_assignment_id, curriculum_id, current_topic_id, current_subtopic_id, started_at, ended_at, status, langgraph_thread_id, graph_version)
VALUES ('00000001-0000-4000-8000-000000000902', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000010', '00000001-0000-4000-8000-000000000901', '00000001-0000-4000-8000-000000000068', '00000001-0000-4000-8000-000000000069', '00000001-0000-4000-8000-000000000074', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000001-0000-4000-8000-000000000002') + interval '-1 day', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000001-0000-4000-8000-000000000002') + interval '-23 hours', 'PAUSED', 'fixture-only-no-checkpoint-northstar-jamie', 'synthetic-history-no-graph-executed');

-- northstar.resume-turn
INSERT INTO workweave.learning_turns (turn_id, organization_id, workspace_id, learning_session_id, client_turn_id, input_hash, sequence, input_reference, response_envelope, committed_revision, stage)
VALUES ('00000001-0000-4000-8000-000000000904', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000902', '00000001-0000-4000-8000-000000000903', 'fixture-only-not-a-runtime-input-hash', 1, '{"synthetic":true,"fixture":"review-only-sql-v1","text":"I would use SOP-001 version 3.3 and keep the reported cause unverified."}'::jsonb, '{"synthetic":true,"fixture":"review-only-sql-v1","historical_fixture":true,"no_ai_called":true}'::jsonb, 1, 'COMMITTED');

-- northstar.resume-attempt
INSERT INTO workweave.learning_assessment_attempts (attempt_id, organization_id, workspace_id, turn_id, pending_question_id, objective_id, criteria_version, answer_reference, criterion_results, outcome, support_metadata)
VALUES ('00000001-0000-4000-8000-000000000906', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000904', '00000001-0000-4000-8000-000000000905', '00000001-0000-4000-8000-000000000071', 'synthetic-criteria-v1', '{"synthetic":true,"fixture":"review-only-sql-v1","turn_id":"00000001-0000-4000-8000-000000000904"}'::jsonb, '{"synthetic":true,"fixture":"review-only-sql-v1","use_current_approved_evidence":"PASSED","keep_unknowns_explicit":"PASSED"}'::jsonb, 'CORRECT', '{"synthetic":true,"fixture":"review-only-sql-v1","hints_used":0,"historical_fixture":true,"no_ai_called":true}'::jsonb);

-- northstar.resume-evidence
INSERT INTO workweave.objective_evidence (objective_evidence_id, organization_id, workspace_id, learning_assignment_id, objective_id, criteria_version, attempt_id, outcome, accepted_at, policy_version)
VALUES ('00000001-0000-4000-8000-000000000907', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000901', '00000001-0000-4000-8000-000000000071', 'synthetic-criteria-v1', '00000001-0000-4000-8000-000000000906', 'PASSED', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000001-0000-4000-8000-000000000002') + interval '-23 hours', 'synthetic-policy-v1');

-- northstar.resume-progress-0
INSERT INTO workweave.employee_learning_progress (progress_id, organization_id, workspace_id, employee_id, learning_assignment_id, subtopic_id, status, started_at, completed_at)
VALUES ('00000001-0000-4000-8000-000000000908', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000010', '00000001-0000-4000-8000-000000000901', '00000001-0000-4000-8000-000000000070', 'COMPLETED', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000001-0000-4000-8000-000000000002') + interval '-1 day', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000001-0000-4000-8000-000000000002') + interval '-23 hours');

-- northstar.resume-progress-1
INSERT INTO workweave.employee_learning_progress (progress_id, organization_id, workspace_id, employee_id, learning_assignment_id, subtopic_id, status, started_at)
VALUES ('00000001-0000-4000-8000-000000000909', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000010', '00000001-0000-4000-8000-000000000901', '00000001-0000-4000-8000-000000000074', 'IN_PROGRESS', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000001-0000-4000-8000-000000000002') + interval '-1 day');

-- northstar.resume-progress-2
INSERT INTO workweave.employee_learning_progress (progress_id, organization_id, workspace_id, employee_id, learning_assignment_id, subtopic_id, status)
VALUES ('00000001-0000-4000-8000-000000000910', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000010', '00000001-0000-4000-8000-000000000901', '00000001-0000-4000-8000-000000000079', 'NOT_STARTED');

-- northstar.resume-event-0
INSERT INTO workweave.employee_learning_events (learning_event_id, organization_id, workspace_id, learning_session_id, employee_id, topic_id, subtopic_id, event_type, strategy, event_data, source_refs, operation_key, created_at)
VALUES ('00000001-0000-4000-8000-000000000911', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000902', '00000001-0000-4000-8000-000000000010', '00000001-0000-4000-8000-000000000069', '00000001-0000-4000-8000-000000000070', 'SUBTOPIC_COMPLETED', 'EXAMPLE', '{"synthetic":true,"fixture":"review-only-sql-v1","attempt_id":"00000001-0000-4000-8000-000000000906","historical_fixture":true,"no_ai_called":true}'::jsonb, '[{"document_version_id":"00000001-0000-4000-8000-000000000067"}]'::jsonb, 'fixture:northstar:resume:0', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000001-0000-4000-8000-000000000002') + interval '-23 hours');

-- northstar.resume-event-1
INSERT INTO workweave.employee_learning_events (learning_event_id, organization_id, workspace_id, learning_session_id, employee_id, topic_id, subtopic_id, event_type, strategy, event_data, source_refs, operation_key, created_at)
VALUES ('00000001-0000-4000-8000-000000000912', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000902', '00000001-0000-4000-8000-000000000010', '00000001-0000-4000-8000-000000000069', '00000001-0000-4000-8000-000000000074', 'EXAMPLE_REQUESTED', 'EXAMPLE', '{"synthetic":true,"fixture":"review-only-sql-v1","explicit_request":"Please show a practical example.","historical_fixture":true,"no_ai_called":true}'::jsonb, '[{"document_version_id":"00000001-0000-4000-8000-000000000067"}]'::jsonb, 'fixture:northstar:resume:1', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000001-0000-4000-8000-000000000002') + interval '-23 hours');

-- northstar.resume-event-2
INSERT INTO workweave.employee_learning_events (learning_event_id, organization_id, workspace_id, learning_session_id, employee_id, topic_id, subtopic_id, event_type, strategy, event_data, source_refs, operation_key, created_at)
VALUES ('00000001-0000-4000-8000-000000000913', '00000001-0000-4000-8000-000000000001', '00000001-0000-4000-8000-000000000002', '00000001-0000-4000-8000-000000000902', '00000001-0000-4000-8000-000000000010', '00000001-0000-4000-8000-000000000069', '00000001-0000-4000-8000-000000000074', 'SESSION_PAUSED', 'EXAMPLE', '{"synthetic":true,"fixture":"review-only-sql-v1","unfinished_practice":true,"historical_fixture":true,"no_ai_called":true}'::jsonb, '[{"document_version_id":"00000001-0000-4000-8000-000000000067"}]'::jsonb, 'fixture:northstar:resume:2', (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000001-0000-4000-8000-000000000002') + interval '-23 hours');

-- Resolve cyclic pointers only after all referenced fixture rows exist.
UPDATE workweave.workspaces SET scenario_id = '00000001-0000-4000-8000-000000000003' WHERE organization_id = '00000001-0000-4000-8000-000000000001' AND workspace_id = '00000001-0000-4000-8000-000000000002';
UPDATE workweave.knowledge_documents SET current_version_id = '00000001-0000-4000-8000-000000000067' WHERE organization_id = '00000001-0000-4000-8000-000000000001' AND workspace_id = '00000001-0000-4000-8000-000000000002' AND document_id = '00000001-0000-4000-8000-000000000065';
UPDATE workweave.shift_handovers SET status = 'PUBLISHED', published_by_employee_id = '00000001-0000-4000-8000-000000000009', published_at = (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000001-0000-4000-8000-000000000002') + interval '-2 hours', current_publication_id = '00000001-0000-4000-8000-000000000109' WHERE organization_id = '00000001-0000-4000-8000-000000000001' AND workspace_id = '00000001-0000-4000-8000-000000000002' AND handover_id = '00000001-0000-4000-8000-000000000108';
UPDATE workweave.exit_kt_artifacts SET current_revision_id = '00000001-0000-4000-8000-000000000136' WHERE organization_id = '00000001-0000-4000-8000-000000000001' AND workspace_id = '00000001-0000-4000-8000-000000000002' AND artifact_id = '00000001-0000-4000-8000-000000000135';

UPDATE workweave.workspaces SET scenario_id = '00000002-0000-4000-8000-000000000003' WHERE organization_id = '00000002-0000-4000-8000-000000000001' AND workspace_id = '00000002-0000-4000-8000-000000000002';
UPDATE workweave.knowledge_documents SET current_version_id = '00000002-0000-4000-8000-000000000067' WHERE organization_id = '00000002-0000-4000-8000-000000000001' AND workspace_id = '00000002-0000-4000-8000-000000000002' AND document_id = '00000002-0000-4000-8000-000000000065';
UPDATE workweave.shift_handovers SET status = 'PUBLISHED', published_by_employee_id = '00000002-0000-4000-8000-000000000009', published_at = (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000002-0000-4000-8000-000000000002') + interval '-2 hours', current_publication_id = '00000002-0000-4000-8000-000000000109' WHERE organization_id = '00000002-0000-4000-8000-000000000001' AND workspace_id = '00000002-0000-4000-8000-000000000002' AND handover_id = '00000002-0000-4000-8000-000000000108';
UPDATE workweave.exit_kt_artifacts SET current_revision_id = '00000002-0000-4000-8000-000000000136' WHERE organization_id = '00000002-0000-4000-8000-000000000001' AND workspace_id = '00000002-0000-4000-8000-000000000002' AND artifact_id = '00000002-0000-4000-8000-000000000135';

UPDATE workweave.workspaces SET scenario_id = '00000003-0000-4000-8000-000000000003' WHERE organization_id = '00000003-0000-4000-8000-000000000001' AND workspace_id = '00000003-0000-4000-8000-000000000002';
UPDATE workweave.knowledge_documents SET current_version_id = '00000003-0000-4000-8000-000000000097' WHERE organization_id = '00000003-0000-4000-8000-000000000001' AND workspace_id = '00000003-0000-4000-8000-000000000002' AND document_id = '00000003-0000-4000-8000-000000000095';
UPDATE workweave.shift_handovers SET status = 'PUBLISHED', published_by_employee_id = '00000003-0000-4000-8000-000000000008', published_at = (SELECT clock_anchor FROM workweave.workspaces WHERE workspace_id = '00000003-0000-4000-8000-000000000002') + interval '-2 hours', current_publication_id = '00000003-0000-4000-8000-000000000142' WHERE organization_id = '00000003-0000-4000-8000-000000000001' AND workspace_id = '00000003-0000-4000-8000-000000000002' AND handover_id = '00000003-0000-4000-8000-000000000141';
UPDATE workweave.exit_kt_artifacts SET current_revision_id = '00000003-0000-4000-8000-000000000172' WHERE organization_id = '00000003-0000-4000-8000-000000000001' AND workspace_id = '00000003-0000-4000-8000-000000000002' AND artifact_id = '00000003-0000-4000-8000-000000000171';

SET CONSTRAINTS ALL IMMEDIATE;
COMMIT;
