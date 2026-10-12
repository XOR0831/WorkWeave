-- Read-only inspection for the optional full SOP-001 v3.4 synthetic test fixture.
-- Safe to run before or after 05_northstar_full_sop_approved_test.sql.
BEGIN TRANSACTION READ ONLY;
SET LOCAL search_path = workweave, public;

-- The baseline points to v3.3. After 05, the same document points to v3.4.
SELECT d.document_code, d.title, d.current_version_id,
       v.version AS pointed_version, v.approval_status, v.temporal_status,
       v.approved_by_employee_id, v.approved_at, v.effective_at,
       length(v.content) AS content_characters, md5(v.content) AS content_md5
FROM knowledge_documents d
LEFT JOIN knowledge_document_versions v
  ON (v.organization_id, v.workspace_id, v.document_id, v.document_version_id) =
     (d.organization_id, d.workspace_id, d.document_id, d.current_version_id)
WHERE d.organization_id = '00000001-0000-4000-8000-000000000001'
  AND d.workspace_id = '00000001-0000-4000-8000-000000000002'
  AND d.document_id = '00000001-0000-4000-8000-000000000065';

-- All versions remain separate. No historical document or chunk is overwritten.
SELECT document_version_id, version, approval_status, temporal_status,
       source_id, length(content) AS content_characters, md5(content) AS content_md5
FROM knowledge_document_versions
WHERE organization_id = '00000001-0000-4000-8000-000000000001'
  AND workspace_id = '00000001-0000-4000-8000-000000000002'
  AND document_id = '00000001-0000-4000-8000-000000000065'
ORDER BY version;

-- Source provenance for the full document. Zero rows before applying 05.
SELECT source_id, source_type, access_partition, checksum, metadata,
       revoked_at, retention_until
FROM source_records
WHERE source_id = '00000001-0000-4000-8000-000000000950';

-- Three new version-specific curriculum links after 05.
SELECT mapping_id, document_version_id, section_ref, entity_type,
       entity_id, relationship_type
FROM knowledge_mappings
WHERE organization_id = '00000001-0000-4000-8000-000000000001'
  AND workspace_id = '00000001-0000-4000-8000-000000000002'
  AND document_version_id = '00000001-0000-4000-8000-000000000951'
ORDER BY section_ref;

-- This should initially be zero; the ingestion code under test populates it.
SELECT count(*) AS v34_chunks,
       count(*) FILTER (WHERE embedding IS NOT NULL) AS embedded_chunks,
       count(*) FILTER (WHERE embedding IS NULL) AS unembedded_chunks,
       min(embedding_model) AS embedding_model,
       min(embedding_dimension) AS embedding_dimension
FROM knowledge_chunks
WHERE organization_id = '00000001-0000-4000-8000-000000000001'
  AND workspace_id = '00000001-0000-4000-8000-000000000002'
  AND document_version_id = '00000001-0000-4000-8000-000000000951';

-- Current-knowledge projection has no v3.4 rows until the ingestion code writes chunks.
-- This view is NOT a substitute for application authorization checks.
SELECT document_version_id, version, section_path, chunk_id, source_id
FROM current_approved_knowledge
WHERE organization_id = '00000001-0000-4000-8000-000000000001'
  AND workspace_id = '00000001-0000-4000-8000-000000000002'
  AND document_id = '00000001-0000-4000-8000-000000000065'
ORDER BY section_path, chunk_id;

COMMIT;
