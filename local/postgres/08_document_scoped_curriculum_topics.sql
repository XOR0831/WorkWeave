-- Review before applying. One-shot migration after 07_sop_curriculum_links.sql.
-- A curriculum source is an exact document version. New learning topics can
-- belong to that source and use H2-local order; legacy seeded topics keep
-- their existing IDs and NULL source until explicitly reviewed/mapped.
BEGIN;
SET LOCAL search_path = workweave, public;

ALTER TABLE curriculum_sources ADD COLUMN order_index integer;

-- Preserve existing source links without guessing which document owns any
-- pre-existing curriculum topic. The row-number is deterministic for ties.
WITH ranked AS (
    SELECT curriculum_source_id,
           row_number() OVER (
               PARTITION BY organization_id, workspace_id, curriculum_id
               ORDER BY created_at, document_version_id, curriculum_source_id
           )::integer AS source_order
    FROM curriculum_sources
)
UPDATE curriculum_sources AS cs
SET order_index = ranked.source_order
FROM ranked
WHERE cs.curriculum_source_id = ranked.curriculum_source_id;

ALTER TABLE curriculum_sources
    ALTER COLUMN order_index SET NOT NULL,
    ADD CONSTRAINT curriculum_sources_order_nonnegative
        CHECK (order_index >= 0),
    ADD CONSTRAINT curriculum_sources_topic_parent_unique
        UNIQUE (organization_id, workspace_id,
                curriculum_source_id, curriculum_id),
    ADD CONSTRAINT curriculum_sources_curriculum_order_unique
        UNIQUE (organization_id, workspace_id, curriculum_id, order_index);

ALTER TABLE curriculum_topics
    ADD COLUMN curriculum_source_id uuid,
    ADD COLUMN source_topic_key text,
    ADD CONSTRAINT curriculum_topics_source_key_pair
        CHECK ((curriculum_source_id IS NULL AND source_topic_key IS NULL)
            OR (curriculum_source_id IS NOT NULL
                AND source_topic_key IS NOT NULL
                AND length(btrim(source_topic_key)) > 0)),
    ADD CONSTRAINT curriculum_topics_primary_source_fk
        FOREIGN KEY (organization_id, workspace_id,
                     curriculum_source_id, curriculum_id)
        REFERENCES curriculum_sources
            (organization_id, workspace_id,
             curriculum_source_id, curriculum_id)
        DEFERRABLE INITIALLY IMMEDIATE;

-- Drop only the old curriculum-global ordering constraint, regardless of
-- PostgreSQL's identifier truncation for its generated name.
DO $migration$
DECLARE old_order_constraint text;
BEGIN
    SELECT con.conname INTO old_order_constraint
    FROM pg_constraint AS con
    WHERE con.conrelid = 'workweave.curriculum_topics'::regclass
      AND con.contype = 'u'
      AND (
          SELECT array_agg(att.attname::text ORDER BY key_col.position)
          FROM unnest(con.conkey) WITH ORDINALITY AS key_col(attnum, position)
          JOIN pg_attribute AS att
            ON att.attrelid = con.conrelid
           AND att.attnum = key_col.attnum
      ) = ARRAY['organization_id', 'workspace_id',
                'curriculum_id', 'order_index'];

    IF old_order_constraint IS NULL THEN
        RAISE EXCEPTION 'Expected curriculum-global topic order constraint not found';
    END IF;
    EXECUTE format('ALTER TABLE workweave.curriculum_topics DROP CONSTRAINT %I',
                   old_order_constraint);
END;
$migration$;

-- New H2 topics can each start at 1 in different linked documents.
CREATE UNIQUE INDEX curriculum_topics_source_order_unique
    ON curriculum_topics
       (organization_id, workspace_id, curriculum_source_id, order_index)
    WHERE curriculum_source_id IS NOT NULL;
CREATE UNIQUE INDEX curriculum_topics_source_key_unique
    ON curriculum_topics
       (organization_id, workspace_id, curriculum_source_id, source_topic_key)
    WHERE curriculum_source_id IS NOT NULL;

-- Do not silently co-own or renumber seeded topics that predate source links.
CREATE UNIQUE INDEX curriculum_topics_legacy_order_unique
    ON curriculum_topics
       (organization_id, workspace_id, curriculum_id, order_index)
    WHERE curriculum_source_id IS NULL;

CREATE INDEX curriculum_topics_primary_source_lookup
    ON curriculum_topics
       (organization_id, workspace_id, curriculum_source_id, order_index);

COMMIT;
