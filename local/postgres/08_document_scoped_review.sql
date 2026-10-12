-- Run only after 08_document_scoped_curriculum_topics.sql is applied.
-- Read-only inspection of document-local and legacy topic order.
BEGIN TRANSACTION READ ONLY;
SET LOCAL search_path = workweave, public;

SELECT c.name AS curriculum,
       cs.order_index AS document_order,
       d.document_code,
       v.version AS document_version,
       t.topic_id,
       t.source_topic_key,
       t.name AS topic,
       t.order_index AS topic_order,
       CASE WHEN cs.curriculum_source_id IS NULL
            THEN 'LEGACY_UNMAPPED' ELSE 'SOURCE_BOUND' END AS topic_origin
FROM curriculum_topics AS t
JOIN curricula AS c
  ON c.organization_id = t.organization_id
 AND c.workspace_id = t.workspace_id
 AND c.curriculum_id = t.curriculum_id
LEFT JOIN curriculum_sources AS cs
  ON cs.organization_id = t.organization_id
 AND cs.workspace_id = t.workspace_id
 AND cs.curriculum_id = t.curriculum_id
 AND cs.curriculum_source_id = t.curriculum_source_id
LEFT JOIN knowledge_documents AS d
  ON d.organization_id = cs.organization_id
 AND d.workspace_id = cs.workspace_id
 AND d.document_id = cs.document_id
LEFT JOIN knowledge_document_versions AS v
  ON v.organization_id = cs.organization_id
 AND v.workspace_id = cs.workspace_id
 AND v.document_version_id = cs.document_version_id
ORDER BY c.organization_id, c.workspace_id, c.name,
         COALESCE(cs.order_index, 0), t.order_index, t.topic_id;

COMMIT;
