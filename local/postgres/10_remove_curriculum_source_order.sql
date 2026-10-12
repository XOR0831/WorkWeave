-- One-shot migration after 09_direct_document_topic_link.sql.
-- Document sources are links, not ordered learning units. H2 order remains
-- local to each (curriculum_id, document_version_id) in curriculum_topics.
BEGIN;
SET LOCAL search_path = workweave, public;

ALTER TABLE curriculum_sources
    DROP CONSTRAINT curriculum_sources_curriculum_order_unique,
    DROP CONSTRAINT curriculum_sources_order_nonnegative,
    DROP COLUMN order_index RESTRICT;

COMMIT;
