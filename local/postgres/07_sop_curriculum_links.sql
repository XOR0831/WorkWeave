-- Schema-only, additive migration for approved-SOP ingestion and curriculum links.
-- Applied to the local workweave database on 2026-09-29. Do not rerun there.
-- Apply once after 01_schema.sql. Existing 02/04/05 fixture rows are preserved.
--
-- H2 = source topic; H3 = source subtopic; H4+ remains lesson/chunk content.
-- A source section belongs to one document version, whether or not it teaches
-- a curriculum subtopic. A curriculum may use many document versions, and a
-- document version may support many curricula. Typed mappings enforce scope
-- and topic/subtopic ancestry without replacing other knowledge_mappings uses.

BEGIN;
SET LOCAL search_path = workweave, public;

-- One parsed H3 source section. The H2 heading is retained as its source
-- parent; H4 headings do not create rows here. Reference-aid H3 sections may
-- exist without a curriculum mapping. section_key is stable within this exact
-- document version (for example h2:1/h3:2), not a curriculum ID.
CREATE TABLE knowledge_sections (
    section_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    document_version_id uuid NOT NULL,
    section_key text NOT NULL CHECK (length(btrim(section_key)) > 0),
    topic_heading text NOT NULL CHECK (length(btrim(topic_heading)) > 0),
    subtopic_heading text NOT NULL CHECK (length(btrim(subtopic_heading)) > 0),
    topic_order_index integer NOT NULL CHECK (topic_order_index >= 0),
    subtopic_order_index integer NOT NULL CHECK (subtopic_order_index >= 0),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    UNIQUE (organization_id, workspace_id, section_id),
    UNIQUE (organization_id, workspace_id, document_version_id, section_id),
    UNIQUE (organization_id, workspace_id, document_version_id, section_key),
    UNIQUE (organization_id, workspace_id, document_version_id,
            topic_order_index, subtopic_order_index),
    FOREIGN KEY (organization_id, workspace_id, document_version_id)
        REFERENCES knowledge_document_versions
            (organization_id, workspace_id, document_version_id)
        DEFERRABLE INITIALLY IMMEDIATE
);
CREATE INDEX ix_knowledge_sections_version_order
    ON knowledge_sections (organization_id, workspace_id, document_version_id,
                           topic_order_index, subtopic_order_index);
CREATE TRIGGER touch_knowledge_sections
    BEFORE UPDATE ON knowledge_sections FOR EACH ROW
    EXECUTE FUNCTION workweave.touch_revision();

-- Once the parent source version is approved, its parsed H2/H3 identity is
-- source provenance, not editable curriculum copy. Draft parses can be fixed
-- before approval; later source changes require a new document version.
CREATE FUNCTION workweave.protect_approved_section()
RETURNS trigger LANGUAGE plpgsql AS $body$
BEGIN
    IF EXISTS (
        SELECT 1 FROM workweave.knowledge_document_versions v
        WHERE (v.organization_id, v.workspace_id, v.document_version_id) =
              (OLD.organization_id, OLD.workspace_id, OLD.document_version_id)
          AND v.approval_status = 'APPROVED'
    ) AND (NEW.organization_id IS DISTINCT FROM OLD.organization_id
        OR NEW.workspace_id IS DISTINCT FROM OLD.workspace_id
        OR NEW.document_version_id IS DISTINCT FROM OLD.document_version_id
        OR NEW.section_key IS DISTINCT FROM OLD.section_key
        OR NEW.topic_heading IS DISTINCT FROM OLD.topic_heading
        OR NEW.subtopic_heading IS DISTINCT FROM OLD.subtopic_heading
        OR NEW.topic_order_index IS DISTINCT FROM OLD.topic_order_index
        OR NEW.subtopic_order_index IS DISTINCT FROM OLD.subtopic_order_index) THEN
        RAISE EXCEPTION 'Create a new document version instead of editing an approved source section';
    END IF;
    RETURN NEW;
END;
$body$;
CREATE TRIGGER approved_section_identity
    BEFORE UPDATE ON knowledge_sections FOR EACH ROW
    EXECUTE FUNCTION workweave.protect_approved_section();

-- A chunk still belongs to its document version and source record. New H3
-- chunks also identify the exact parsed source section. Nullable only so
-- historical fixture chunks and non-H3 document-level chunks remain valid.
ALTER TABLE knowledge_chunks ADD COLUMN source_section_id uuid;
ALTER TABLE knowledge_chunks
    ADD CONSTRAINT fk_knowledge_chunks_source_section
    FOREIGN KEY (organization_id, workspace_id,
                 document_version_id, source_section_id)
    REFERENCES knowledge_sections
        (organization_id, workspace_id, document_version_id, section_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_knowledge_chunks_source_section
    ON knowledge_chunks (organization_id, workspace_id,
                         document_version_id, source_section_id);

-- Enforce the agreed H2/H3 representation for every new linked chunk.
-- Old chunks with NULL source_section_id are intentionally unaffected.
CREATE FUNCTION workweave.validate_chunk_source_section()
RETURNS trigger LANGUAGE plpgsql AS $body$
DECLARE
    source_topic text;
    source_subtopic text;
BEGIN
    IF NEW.source_section_id IS NOT NULL THEN
        SELECT s.topic_heading, s.subtopic_heading
          INTO source_topic, source_subtopic
        FROM workweave.knowledge_sections s
        WHERE (s.organization_id, s.workspace_id,
               s.document_version_id, s.section_id) =
              (NEW.organization_id, NEW.workspace_id,
               NEW.document_version_id, NEW.source_section_id);
        IF NOT FOUND THEN
            RAISE EXCEPTION 'Chunk source_section_id does not belong to its document version';
        END IF;
        IF NEW.section_path <> jsonb_build_array(source_topic)
           OR NEW.heading IS DISTINCT FROM source_subtopic THEN
            RAISE EXCEPTION 'Chunk H2 section_path/H3 heading differs from its source section';
        END IF;
    END IF;
    RETURN NEW;
END;
$body$;
CREATE TRIGGER validate_knowledge_chunk_section
    BEFORE INSERT OR UPDATE ON knowledge_chunks FOR EACH ROW
    EXECUTE FUNCTION workweave.validate_chunk_source_section();

-- Explicit parent-level bridge. Do not put a single document_id on curricula:
-- one curriculum can draw on multiple SOPs, and one SOP can teach multiple
-- curricula. Linking the exact document version preserves historical meaning.
CREATE TABLE curriculum_sources (
    curriculum_source_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    curriculum_id uuid NOT NULL,
    document_id uuid NOT NULL,
    document_version_id uuid NOT NULL,
    relationship_type text NOT NULL DEFAULT 'TEACHES'
        CHECK (relationship_type IN ('TEACHES', 'SUPPORTS')),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    UNIQUE (organization_id, workspace_id, curriculum_source_id),
    UNIQUE (organization_id, workspace_id, curriculum_id,
            document_version_id),
    UNIQUE (organization_id, workspace_id, curriculum_source_id,
            curriculum_id, document_version_id),
    FOREIGN KEY (organization_id, workspace_id, curriculum_id)
        REFERENCES curricula (organization_id, workspace_id, curriculum_id)
        DEFERRABLE INITIALLY IMMEDIATE,
    FOREIGN KEY (organization_id, workspace_id, document_id,
                 document_version_id)
        REFERENCES knowledge_document_versions
            (organization_id, workspace_id, document_id, document_version_id)
        DEFERRABLE INITIALLY IMMEDIATE
);
CREATE INDEX ix_curriculum_sources_document_version
    ON curriculum_sources (organization_id, workspace_id,
                           document_id, document_version_id);
CREATE TRIGGER touch_curriculum_sources
    BEFORE UPDATE ON curriculum_sources FOR EACH ROW
    EXECUTE FUNCTION workweave.touch_revision();

-- Typed H3-to-learning-subtopic mapping. All four composite FKs matter:
-- the source section must be from the linked document version; the topic
-- must belong to the linked curriculum; the subtopic must belong to that
-- topic. A source section can teach multiple subtopics and vice versa.
CREATE TABLE curriculum_source_sections (
    curriculum_source_section_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    curriculum_source_id uuid NOT NULL,
    curriculum_id uuid NOT NULL,
    document_version_id uuid NOT NULL,
    section_id uuid NOT NULL,
    topic_id uuid NOT NULL,
    subtopic_id uuid NOT NULL,
    relationship_type text NOT NULL DEFAULT 'TEACHES'
        CHECK (relationship_type IN ('TEACHES', 'SUPPORTS')),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    UNIQUE (organization_id, workspace_id, curriculum_source_section_id),
    UNIQUE (organization_id, workspace_id,
            curriculum_source_id, section_id, subtopic_id),
    FOREIGN KEY (organization_id, workspace_id, curriculum_source_id,
                 curriculum_id, document_version_id)
        REFERENCES curriculum_sources
            (organization_id, workspace_id, curriculum_source_id,
             curriculum_id, document_version_id)
        DEFERRABLE INITIALLY IMMEDIATE,
    FOREIGN KEY (organization_id, workspace_id, document_version_id,
                 section_id)
        REFERENCES knowledge_sections
            (organization_id, workspace_id, document_version_id, section_id)
        DEFERRABLE INITIALLY IMMEDIATE,
    FOREIGN KEY (organization_id, workspace_id, curriculum_id, topic_id)
        REFERENCES curriculum_topics
            (organization_id, workspace_id, curriculum_id, topic_id)
        DEFERRABLE INITIALLY IMMEDIATE,
    FOREIGN KEY (organization_id, workspace_id, topic_id, subtopic_id)
        REFERENCES curriculum_subtopics
            (organization_id, workspace_id, topic_id, subtopic_id)
        DEFERRABLE INITIALLY IMMEDIATE
);
CREATE INDEX ix_curriculum_source_sections_subtopic
    ON curriculum_source_sections
        (organization_id, workspace_id, subtopic_id, document_version_id);
CREATE INDEX ix_curriculum_source_sections_section
    ON curriculum_source_sections
        (organization_id, workspace_id, document_version_id, section_id);
CREATE TRIGGER touch_curriculum_source_sections
    BEFORE UPDATE ON curriculum_source_sections FOR EACH ROW
    EXECUTE FUNCTION workweave.touch_revision();

-- The existing approved-chunk guard does not know about the new section FK.
-- Prevent approved excerpts from being silently remapped to another section.
CREATE OR REPLACE FUNCTION workweave.protect_approved_chunk()
RETURNS trigger LANGUAGE plpgsql AS $body$
BEGIN
    IF EXISTS (
        SELECT 1 FROM workweave.knowledge_document_versions v
        WHERE (v.organization_id, v.workspace_id, v.document_version_id) =
              (OLD.organization_id, OLD.workspace_id, OLD.document_version_id)
          AND v.approval_status = 'APPROVED'
    ) AND (NEW.content IS DISTINCT FROM OLD.content
        OR NEW.document_version_id IS DISTINCT FROM OLD.document_version_id
        OR NEW.source_id IS DISTINCT FROM OLD.source_id
        OR NEW.source_section_id IS DISTINCT FROM OLD.source_section_id
        OR NEW.section_path IS DISTINCT FROM OLD.section_path
        OR NEW.heading IS DISTINCT FROM OLD.heading
        OR NEW.parent_chunk_id IS DISTINCT FROM OLD.parent_chunk_id
        OR NEW.source_span IS DISTINCT FROM OLD.source_span
        OR NEW.organization_id IS DISTINCT FROM OLD.organization_id
        OR NEW.workspace_id IS DISTINCT FROM OLD.workspace_id) THEN
        RAISE EXCEPTION 'Re-ingest a new document version instead of editing an approved excerpt';
    END IF;
    RETURN NEW;
END;
$body$;

COMMIT;
