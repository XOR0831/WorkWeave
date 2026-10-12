-- One-shot migration after 08_document_scoped_curriculum_topics.sql.
-- Topics identify their exact source version directly. curriculum_sources
-- remains the curriculum/document-version bridge and owns document order.
BEGIN;
SET LOCAL search_path = workweave, public;

ALTER TABLE curriculum_topics ADD COLUMN document_version_id uuid;

-- Preserve any topics already bound through migration 08's source UUID.
UPDATE curriculum_topics AS t
SET document_version_id = cs.document_version_id
FROM curriculum_sources AS cs
WHERE t.organization_id = cs.organization_id
  AND t.workspace_id = cs.workspace_id
  AND t.curriculum_id = cs.curriculum_id
  AND t.curriculum_source_id = cs.curriculum_source_id;

ALTER TABLE curriculum_topics
    ADD CONSTRAINT curriculum_topics_document_version_fk
        FOREIGN KEY (organization_id, workspace_id,
                     curriculum_id, document_version_id)
        REFERENCES curriculum_sources
            (organization_id, workspace_id,
             curriculum_id, document_version_id)
        DEFERRABLE INITIALLY IMMEDIATE;

-- Replace source-UUID order/key indexes before dropping their columns.
DROP INDEX curriculum_topics_source_order_unique;
DROP INDEX curriculum_topics_source_key_unique;
DROP INDEX curriculum_topics_legacy_order_unique;
DROP INDEX curriculum_topics_primary_source_lookup;

ALTER TABLE curriculum_topics
    DROP CONSTRAINT curriculum_topics_primary_source_fk,
    DROP CONSTRAINT curriculum_topics_source_key_pair,
    DROP COLUMN curriculum_source_id,
    DROP COLUMN source_topic_key;

-- H2 order restarts for each exact document version linked to a curriculum.
CREATE UNIQUE INDEX curriculum_topics_document_order_unique
    ON curriculum_topics
       (organization_id, workspace_id, curriculum_id,
        document_version_id, order_index)
    WHERE document_version_id IS NOT NULL;

-- Existing fixture/imported topics have no proven document link. Keep their
-- UUIDs and old curriculum-local order until a coordinator reconciles them.
CREATE UNIQUE INDEX curriculum_topics_legacy_order_unique
    ON curriculum_topics
       (organization_id, workspace_id, curriculum_id, order_index)
    WHERE document_version_id IS NULL;

CREATE INDEX curriculum_topics_document_lookup
    ON curriculum_topics
       (organization_id, workspace_id, curriculum_id,
        document_version_id, order_index);

-- The four-column candidate key existed only for the migration 08 topic FK.
ALTER TABLE curriculum_sources
    DROP CONSTRAINT curriculum_sources_topic_parent_unique;

COMMIT;
