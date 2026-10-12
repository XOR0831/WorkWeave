-- Run only after 10_remove_curriculum_source_order.sql is applied.
BEGIN TRANSACTION READ ONLY;
SET LOCAL search_path = workweave, public;

SELECT c.name AS curriculum,
       d.document_code,
       v.version AS document_version,
       t.topic_id,
       t.name AS topic,
       t.order_index AS h2_order_in_document,
       CASE WHEN t.document_version_id IS NULL
            THEN 'LEGACY_UNMAPPED' ELSE 'DOCUMENT_BOUND' END AS topic_origin
FROM curriculum_topics AS t
JOIN curricula AS c
  ON c.organization_id = t.organization_id
 AND c.workspace_id = t.workspace_id
 AND c.curriculum_id = t.curriculum_id
LEFT JOIN curriculum_sources AS cs
  ON cs.organization_id = t.organization_id
 AND cs.workspace_id = t.workspace_id
 AND cs.curriculum_id = t.curriculum_id
 AND cs.document_version_id = t.document_version_id
LEFT JOIN knowledge_documents AS d
  ON d.organization_id = cs.organization_id
 AND d.workspace_id = cs.workspace_id
 AND d.document_id = cs.document_id
LEFT JOIN knowledge_document_versions AS v
  ON v.organization_id = cs.organization_id
 AND v.workspace_id = cs.workspace_id
 AND v.document_version_id = cs.document_version_id
ORDER BY c.organization_id, c.workspace_id, c.name,
         cs.created_at NULLS FIRST, cs.curriculum_source_id,
         t.order_index, t.topic_id;

COMMIT;
