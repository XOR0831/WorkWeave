-- Read-only fixture inspection. Apply the additive Northstar alignment first.
-- No data mutations occur in this file.
BEGIN TRANSACTION READ ONLY;
SET LOCAL search_path = workweave, public;

-- 1. Inventory: expected 86 business tables, 2 views. Counts below exclude init extensions.
SELECT table_type, count(*) AS object_count
FROM information_schema.tables WHERE table_schema = 'workweave'
GROUP BY table_type ORDER BY table_type;

-- 2. Company/workspace boundaries and synthetic demo clocks.
SELECT o.name, w.workspace_id, w.kind, w.clock_anchor, w.expires_at, s.status AS scenario_status
FROM organizations o JOIN workspaces w USING (organization_id)
LEFT JOIN scenario_catalog s USING (organization_id, workspace_id, scenario_id)
ORDER BY o.name;

-- 3. Synthetic employee roster; business roles are NOT permission roles.
SELECT o.name AS company, e.first_name, e.last_name, e.employment_status,
       r.name AS business_role, t.name AS team, m.team_role
FROM employees e JOIN organizations o USING (organization_id)
LEFT JOIN roles r USING (organization_id, workspace_id, role_id)
LEFT JOIN employee_team_memberships m USING (organization_id, workspace_id, employee_id)
LEFT JOIN teams t USING (organization_id, workspace_id, team_id)
ORDER BY company, e.first_name;

-- 4. Onboarding: employee-specific progress; Jamie resumes subtopic 2.
SELECT o.name AS company, e.first_name, e.last_name, c.name AS curriculum,
       ct.order_index AS topic_order, st.order_index AS subtopic_order,
       st.name AS subtopic, p.status, p.started_at, p.completed_at
FROM employee_learning_progress p
JOIN employees e USING (organization_id, workspace_id, employee_id)
JOIN organizations o USING (organization_id)
JOIN learning_assignments a USING (organization_id, workspace_id, learning_assignment_id)
JOIN curricula c USING (organization_id, workspace_id, curriculum_id)
JOIN curriculum_subtopics st USING (organization_id, workspace_id, subtopic_id)
JOIN curriculum_topics ct USING (organization_id, workspace_id, topic_id)
ORDER BY company, e.first_name, topic_order, subtopic_order;

-- 5. Historical resume evidence (synthetic, not actual learner validation).
SELECT e.first_name, ev.event_type, ev.strategy, ev.created_at, ev.event_data
FROM employee_learning_events ev
JOIN employees e USING (organization_id, workspace_id, employee_id)
ORDER BY ev.created_at, ev.learning_event_id;

-- 6. Baseline source eligibility was 9 current chunks. Applied v3.4 test
-- overlay (05) makes Northstar v3.4 current with 0 chunks until ingestion,
-- so the current local total is 6. Historical versions stay out.
-- This administrative view is NOT an authorization boundary or complete RAG implementation.
SELECT o.name AS company, k.title, k.version, k.section_path, k.chunk_id
FROM current_approved_knowledge k JOIN organizations o USING (organization_id)
ORDER BY company, k.section_path;

-- 7. No embeddings were generated; every seeded chunk embedding is NULL.
SELECT count(*) AS total_chunks,
       count(*) FILTER (WHERE embedding IS NULL) AS awaiting_embedding,
       count(*) FILTER (WHERE embedding IS NOT NULL) AS embedded
FROM knowledge_chunks;

-- 8. Proposals are not assignments: expected PROPOSED and NULL final employees.
SELECT o.name AS company, d.status, w.external_id, w.title,
       recommended.first_name AS recommended_employee,
       final_employee.first_name AS final_employee, d.confirmed_at
FROM delegation_proposal_items i
JOIN delegation_proposals d USING (organization_id, workspace_id, delegation_proposal_id)
JOIN work_items w USING (organization_id, workspace_id, work_item_id)
JOIN organizations o USING (organization_id)
JOIN employees recommended ON
 (recommended.organization_id,recommended.workspace_id,recommended.employee_id) =
 (i.organization_id,i.workspace_id,i.recommended_employee_id)
LEFT JOIN employees final_employee ON
 (final_employee.organization_id,final_employee.workspace_id,final_employee.employee_id) =
 (i.organization_id,i.workspace_id,i.final_employee_id)
ORDER BY company, w.external_id;

-- 9. Only historical CANCELLED manual assignments are seeded.
SELECT assignment_source, status, count(*) FROM work_item_assignments
GROUP BY assignment_source, status ORDER BY assignment_source, status;

-- 10. Member report is evidence, not authorized operational completion.
SELECT o.name AS company, w.external_id, w.status AS official_work_status,
       e.first_name AS reporter, ev.event_type, ev.description
FROM work_events ev JOIN work_items w USING (organization_id, workspace_id, work_item_id)
JOIN employees e USING (organization_id, workspace_id, employee_id)
JOIN organizations o USING (organization_id)
ORDER BY company, w.external_id;

-- 11. A shift lead publishes directly: no second reviewer field/gate.
SELECT o.name AS company, h.status, e.first_name AS publisher,
       p.publication_number, p.published_at, count(ent.handover_entry_id) AS snapshot_items
FROM shift_handovers h JOIN organizations o USING (organization_id)
LEFT JOIN handover_publications p ON
 (p.organization_id,p.workspace_id,p.publication_id) =
 (h.organization_id,h.workspace_id,h.current_publication_id)
LEFT JOIN employees e ON
 (e.organization_id,e.workspace_id,e.employee_id) =
 (p.organization_id,p.workspace_id,p.published_by)
LEFT JOIN handover_entries ent ON
 (ent.organization_id,ent.workspace_id,ent.publication_id) =
 (p.organization_id,p.workspace_id,p.publication_id)
GROUP BY o.name,h.handover_id,h.status,e.first_name,p.publication_number,p.published_at
ORDER BY o.name, h.status;

-- 12. Persistent items have separate operational and acknowledgement states.
SELECT o.name AS company, h.title, h.effective_work_status, h.acknowledgement_status
FROM handover_current_items h JOIN organizations o USING (organization_id)
ORDER BY company, h.title;

-- 13. Copilot suggestions remain pending; email inputs are synthetic adapter fixtures.
SELECT o.name AS company, s.suggestion_type, s.status, s.reason, s.source_refs
FROM handover_suggestions s JOIN organizations o USING (organization_id)
ORDER BY company, s.suggestion_type;

-- 14. KT inventory/findings and structured drafts remain unapproved.
SELECT o.name AS company, k.title, k.documentation_status, k.kt_status, k.risk_level
FROM exit_kt_knowledge_items k JOIN organizations o USING (organization_id)
ORDER BY company,k.title;
SELECT finding_type,status,count(*) FROM exit_kt_findings
GROUP BY finding_type,status ORDER BY finding_type,status;
SELECT o.name AS company,a.title,r.version,r.status,r.employee_reviewed_at
FROM exit_kt_artifacts a JOIN organizations o USING (organization_id)
LEFT JOIN exit_kt_artifact_revisions r ON
 (r.organization_id,r.workspace_id,r.artifact_revision_id) =
 (a.organization_id,a.workspace_id,a.current_revision_id)
ORDER BY company;

-- 15. Ownership has NOT transferred simply because AI recommended a successor.
SELECT o.name AS company,r.title,current_owner.first_name AS current_owner,
       recommended.first_name AS recommended_owner,t.status,t.completed_at
FROM responsibility_transfers t
JOIN responsibilities r USING (organization_id, workspace_id, responsibility_id)
JOIN organizations o USING (organization_id)
JOIN employees current_owner ON
 (current_owner.organization_id,current_owner.workspace_id,current_owner.employee_id) =
 (t.organization_id,t.workspace_id,t.current_owner_employee_id)
LEFT JOIN employees recommended ON
 (recommended.organization_id,recommended.workspace_id,recommended.employee_id) =
 (t.organization_id,t.workspace_id,t.recommended_owner_employee_id)
ORDER BY company;

-- 16. All of these should be zero immediately after seeding.
SELECT 'confirmed_delegation_proposals' AS check_name,count(*) AS expected_zero
FROM delegation_proposals WHERE status = 'CONFIRMED'
UNION ALL SELECT 'active_assignments',count(*) FROM work_item_assignments WHERE status <> 'CANCELLED'
UNION ALL SELECT 'approved_kt_artifact_revisions',count(*) FROM exit_kt_artifact_revisions WHERE status = 'APPROVED'
UNION ALL SELECT 'knowledge_promotions',count(*) FROM knowledge_promotions
UNION ALL SELECT 'completed_responsibility_transfers',count(*) FROM responsibility_transfers WHERE status = 'TRANSFERRED'
UNION ALL SELECT 'completed_exit_cases',count(*) FROM exit_kt_cases WHERE status = 'COMPLETE'
UNION ALL SELECT 'delivered_outbox_events',count(*) FROM outbox_events WHERE status = 'DELIVERED';

-- 17. Cross-scope relationship diagnostic: expected zero (also FK-protected).
SELECT count(*) AS cross_scope_work_assignments
FROM work_item_assignments a JOIN work_items w ON a.work_item_id = w.work_item_id
WHERE (a.organization_id,a.workspace_id) IS DISTINCT FROM (w.organization_id,w.workspace_id);

-- 18. Northstar contract: one closed historical incident, one open current incident,
-- baseline v3.3/current; after applied test overlay v3.4/current with older
-- versions superseded. No inferred current cause.
SELECT w.external_id, w.status, w.description
FROM work_items w JOIN organizations o USING (organization_id)
WHERE o.company_key = 'northstar' AND w.external_id IN ('Ticket #492', 'Ticket #829')
ORDER BY w.external_id;
SELECT v.version, v.approval_status, v.temporal_status, d.current_version_id = v.document_version_id AS is_current_pointer
FROM knowledge_documents d
JOIN knowledge_document_versions v USING (organization_id, workspace_id, document_id)
JOIN organizations o USING (organization_id)
WHERE o.company_key = 'northstar' AND d.document_code = 'SOP-001'
ORDER BY v.version;
SELECT count(*) AS northstar_historical_492_events
FROM work_events e JOIN work_items w USING (organization_id, workspace_id, work_item_id)
JOIN organizations o USING (organization_id)
WHERE o.company_key = 'northstar' AND w.external_id = 'Ticket #492'
  AND e.event_data->>'not_current_diagnosis' = 'true';

COMMIT;
