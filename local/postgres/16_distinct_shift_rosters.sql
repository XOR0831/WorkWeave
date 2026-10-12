-- Synthetic demo roster extension for Northstar, Harbor and Acme.
-- Keep the completed Morning and active Afternoon shifts (and their handover history) intact.
-- Replace only the unstarted Evening roster, then schedule the following Morning with
-- one new lead plus one existing employee in each shift. Existing employees are retained.
-- Run once, after 15_machine_fundamentals_v11.sql. The guarded transaction rejects
-- an Evening shift that has started or whose roster differs from the reviewed seed.
BEGIN;

DO $rosters$
DECLARE
    r record;
    g record;
    p text;
    o uuid;
    w uuid;
    team uuid;
    role_id uuid;
    reviewer uuid;
    old_lead uuid;
    morning_lead uuid;
    evening_lead uuid;
    morning_member uuid;
    evening_member uuid;
    morning_shift uuid;
    evening_shift uuid;
    next_morning uuid;
    evening_lead_membership uuid;
    evening_member_membership uuid;
    expected_ids uuid[];
    actual_ids uuid[];
    evening_row workweave.shift_instances%ROWTYPE;
BEGIN
    FOR r IN
        SELECT * FROM (VALUES
            ('00000001-0000-4000-8000-', 'Priya', 'Nair', 'Dana', 'Brooks',
             'northstar.example', 9, 11, 37, 48, 50, 51, 10, 8,
             ARRAY[49,50,51]::integer[]),
            ('00000002-0000-4000-8000-', 'Cora', 'Mendoza', 'Tessa', 'Lim',
             'harbor.example', 9, 11, 37, 48, 50, 51, 10, 8,
             ARRAY[49,50,51]::integer[]),
            ('00000003-0000-4000-8000-', 'Neha', 'Shah', 'Aisha', 'Rahman',
             'acme.example', 8, 13, 51, 66, 67, 69, 10, 11,
             ARRAY[67,68,69,70,71]::integer[])
        ) AS x(prefix, morning_first, morning_last, evening_first, evening_last,
               email_domain, old_lead_no, reviewer_no, morning_shift_no,
               evening_shift_no, evening_lead_membership_no,
               evening_member_membership_no, evening_member_no, morning_member_no,
               original_membership_nos)
    LOOP
        p := r.prefix;
        o := (p || '000000000001')::uuid;
        w := (p || '000000000002')::uuid;
        team := (p || '000000000005')::uuid;
        role_id := (p || '000000000006')::uuid;
        reviewer := (p || lpad(r.reviewer_no::text, 12, '0'))::uuid;
        old_lead := (p || lpad(r.old_lead_no::text, 12, '0'))::uuid;
        morning_lead := (p || '000000009001')::uuid;
        evening_lead := (p || '000000009002')::uuid;
        morning_shift := (p || lpad(r.morning_shift_no::text, 12, '0'))::uuid;
        evening_shift := (p || lpad(r.evening_shift_no::text, 12, '0'))::uuid;
        evening_lead_membership := (p || lpad(r.evening_lead_membership_no::text, 12, '0'))::uuid;
        evening_member_membership := (p || lpad(r.evening_member_membership_no::text, 12, '0'))::uuid;
        evening_member := (p || lpad(r.evening_member_no::text, 12, '0'))::uuid;
        morning_member := (p || lpad(r.morning_member_no::text, 12, '0'))::uuid;
        next_morning := (p || '000000009007')::uuid;

        SELECT * INTO evening_row FROM workweave.shift_instances
         WHERE organization_id = o AND workspace_id = w AND shift_instance_id = evening_shift
         FOR UPDATE;
        IF NOT FOUND OR evening_row.status <> 'SCHEDULED'
           OR evening_row.shift_lead_employee_id <> old_lead THEN
            RAISE EXCEPTION '16_shift_rosters: Evening shift % is not the reviewed unstarted shift', evening_shift;
        END IF;
        IF NOT EXISTS (SELECT 1 FROM workweave.shifts WHERE shift_id = morning_shift
                       AND organization_id = o AND workspace_id = w AND team_id = team AND name = 'Morning')
           OR NOT EXISTS (SELECT 1 FROM workweave.employees WHERE employee_id = morning_member AND workspace_id = w)
           OR NOT EXISTS (SELECT 1 FROM workweave.employees WHERE employee_id = evening_member AND workspace_id = w)
           OR NOT EXISTS (SELECT 1 FROM workweave.employees WHERE employee_id = reviewer AND workspace_id = w) THEN
            RAISE EXCEPTION '16_shift_rosters: required seed identities or Morning shift missing for %', w;
        END IF;
        SELECT array_agg((p || lpad(n::text, 12, '0'))::uuid ORDER BY n)
          INTO expected_ids FROM unnest(r.original_membership_nos) AS n;
        SELECT array_agg(shift_membership_id ORDER BY shift_membership_id)
          INTO actual_ids FROM workweave.shift_instance_memberships
         WHERE organization_id = o AND workspace_id = w AND shift_instance_id = evening_shift;
        IF actual_ids IS DISTINCT FROM expected_ids
           OR NOT EXISTS (SELECT 1 FROM workweave.shift_instance_memberships
                           WHERE shift_membership_id = evening_lead_membership
                             AND employee_id = old_lead AND membership_role = 'SHIFT_LEAD')
           OR NOT EXISTS (SELECT 1 FROM workweave.shift_instance_memberships
                           WHERE shift_membership_id = evening_member_membership
                             AND employee_id = evening_member AND membership_role = 'MEMBER') THEN
            RAISE EXCEPTION '16_shift_rosters: Evening roster % differs from reviewed seed', evening_shift;
        END IF;
        IF EXISTS (SELECT 1 FROM workweave.employees WHERE employee_id IN (morning_lead, evening_lead))
           OR EXISTS (SELECT 1 FROM workweave.shift_instances WHERE shift_instance_id = next_morning) THEN
            RAISE EXCEPTION '16_shift_rosters: new IDs already used for %', w;
        END IF;

        INSERT INTO workweave.employees
            (employee_id, organization_id, workspace_id, role_id, first_name, last_name, email, employment_status, hire_date)
        VALUES
            (morning_lead, o, w, role_id, r.morning_first, r.morning_last,
             lower(r.morning_first || '.' || r.morning_last || '@' || r.email_domain), 'ACTIVE', CURRENT_DATE - 180),
            (evening_lead, o, w, role_id, r.evening_first, r.evening_last,
             lower(r.evening_first || '.' || r.evening_last || '@' || r.email_domain), 'ACTIVE', CURRENT_DATE - 180);

        INSERT INTO workweave.employee_team_memberships
            (membership_id, organization_id, workspace_id, employee_id, team_id, team_role, start_date, is_active)
        VALUES
            ((p || '000000009003')::uuid, o, w, morning_lead, team, 'SHIFT_LEAD', CURRENT_DATE - 180, TRUE),
            ((p || '000000009004')::uuid, o, w, evening_lead, team, 'SHIFT_LEAD', CURRENT_DATE - 180, TRUE);

        -- Mirror only the five operational actions held by the existing Afternoon lead.
        FOR g IN SELECT * FROM (VALUES (morning_lead, 9010), (evening_lead, 9020)) AS x(actor, grant_base)
        LOOP
            INSERT INTO workweave.permission_grants
                (grant_id, organization_id, workspace_id, actor_id, resource_scope, action, valid_from, granted_by)
            SELECT (p || lpad((g.grant_base + row_number() OVER (ORDER BY pg.action) - 1)::text, 12, '0'))::uuid,
                   o, w, g.actor, pg.resource_scope, pg.action, pg.valid_from, pg.granted_by
              FROM workweave.permission_grants pg
             WHERE pg.organization_id = o AND pg.workspace_id = w AND pg.actor_id = old_lead
               AND pg.action IN ('work:read', 'work:report', 'delegation:confirm',
                                 'handover:publish', 'handover:suggestion:review');
            IF (SELECT count(*) FROM workweave.permission_grants
                 WHERE organization_id = o AND workspace_id = w AND actor_id = g.actor) <> 5 THEN
                RAISE EXCEPTION '16_shift_rosters: expected five operational grants for %', g.actor;
            END IF;
        END LOOP;

        INSERT INTO workweave.employee_availability
            (availability_id, organization_id, workspace_id, employee_id, start_at, end_at, status, source_reference)
        VALUES
            ((p || '000000009005')::uuid, o, w, morning_lead,
             evening_row.scheduled_end_at, evening_row.scheduled_end_at + interval '8 hours',
             'AVAILABLE', 'Synthetic scheduled Morning-shift availability'),
            ((p || '000000009006')::uuid, o, w, evening_lead,
             evening_row.scheduled_start_at, evening_row.scheduled_end_at,
             'AVAILABLE', 'Synthetic scheduled Evening-shift availability');

        -- The Evening occurrence has not started; keep the chosen existing member's row.
        DELETE FROM workweave.shift_instance_memberships
         WHERE organization_id = o AND workspace_id = w AND shift_instance_id = evening_shift
           AND shift_membership_id NOT IN (evening_lead_membership, evening_member_membership);
        UPDATE workweave.shift_instance_memberships
           SET employee_id = evening_lead
         WHERE organization_id = o AND workspace_id = w AND shift_membership_id = evening_lead_membership;
        UPDATE workweave.shift_instances
           SET shift_lead_employee_id = evening_lead
         WHERE organization_id = o AND workspace_id = w AND shift_instance_id = evening_shift;

        INSERT INTO workweave.shift_instances
            (shift_instance_id, organization_id, workspace_id, shift_id, shift_date,
             scheduled_start_at, scheduled_end_at, shift_lead_employee_id, status)
        VALUES
            (next_morning, o, w, morning_shift,
             (evening_row.scheduled_end_at AT TIME ZONE 'Asia/Manila')::date,
             evening_row.scheduled_end_at, evening_row.scheduled_end_at + interval '8 hours',
             morning_lead, 'SCHEDULED');
        INSERT INTO workweave.shift_instance_memberships
            (shift_membership_id, organization_id, workspace_id, shift_instance_id,
             employee_id, membership_role, availability_status)
        VALUES
            ((p || '000000009008')::uuid, o, w, next_morning, morning_lead, 'SHIFT_LEAD', 'AVAILABLE'),
            ((p || '000000009009')::uuid, o, w, next_morning, morning_member, 'MEMBER', 'AVAILABLE');
    END LOOP;
END
$rosters$;

COMMIT;
