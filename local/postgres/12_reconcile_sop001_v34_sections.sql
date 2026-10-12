-- Reconcile SOP-001 v3.4 instructional source sections with the reviewed Northstar learner path.
--
-- Additive and idempotent. Inserts at most three curriculum_source_sections rows linking the
-- v3.4 H3 sections h2:1/h3:1..3 to the existing "Machine Fundamentals" subtopics, which keep their
-- reviewed objectives, prerequisites and learner progress. The legacy topic stays version-null:
-- curriculum_source_sections only requires the topic to belong to the same curriculum (07).
-- The four "Reference aids" sections and the document-scoped topics are left untouched: they stay
-- available as source context and are not learner objectives or visible learning-path items.
--
-- Fails (and changes nothing) on any missing, ambiguous, unapproved, superseded or revoked state,
-- or if a section has no embedded chunk. Never updates or deletes rows.
-- Requires the SOP-001 v3.4 ingestion output (knowledge_sections, curriculum_sources), which is
-- present in the local dev database but not produced by these repo scripts.
BEGIN;

DO $reconcile$
DECLARE
    v_org constant uuid := '00000001-0000-4000-8000-000000000001'; -- Northstar baseline
    v_ws  constant uuid := '00000001-0000-4000-8000-000000000002';
    v_curriculum uuid;
    v_version uuid;
    v_document uuid;
    v_source uuid;
    v_topic uuid;
    v_section uuid;
    v_subtopic uuid;
    n bigint;
    pair record;
BEGIN
    -- Curriculum: exactly one published "Machine Fundamentals" 1.0 in the Northstar baseline.
    SELECT count(*), min(curriculum_id::text)::uuid INTO n, v_curriculum
    FROM workweave.curricula
    WHERE organization_id = v_org AND workspace_id = v_ws
      AND name = 'Machine Fundamentals' AND version = '1.0' AND status = 'PUBLISHED';
    IF n <> 1 THEN RAISE EXCEPTION 'reconcile: expected 1 published Machine Fundamentals 1.0, found %', n; END IF;

    -- Document version: SOP-001 v3.4, approved, current, the document's current pointer, source not revoked.
    SELECT count(*), min(v.document_version_id::text)::uuid, min(v.document_id::text)::uuid INTO n, v_version, v_document
    FROM workweave.knowledge_document_versions v
    JOIN workweave.knowledge_documents d
      ON d.organization_id = v.organization_id AND d.workspace_id = v.workspace_id AND d.document_id = v.document_id
    JOIN workweave.source_records r
      ON r.organization_id = v.organization_id AND r.workspace_id = v.workspace_id AND r.source_id = v.source_id
    WHERE v.organization_id = v_org AND v.workspace_id = v_ws
      AND d.document_code = 'SOP-001' AND v.version = '3.4'
      AND v.approval_status = 'APPROVED' AND v.temporal_status = 'CURRENT'
      AND d.current_version_id = v.document_version_id
      AND r.revoked_at IS NULL;
    IF n <> 1 THEN RAISE EXCEPTION 'reconcile: expected 1 approved, current, unrevoked SOP-001 v3.4, found %', n; END IF;

    -- Bridge: exactly one TEACHES curriculum_sources row for this curriculum and exact version.
    SELECT count(*), min(curriculum_source_id::text)::uuid INTO n, v_source
    FROM workweave.curriculum_sources
    WHERE organization_id = v_org AND workspace_id = v_ws
      AND curriculum_id = v_curriculum AND document_id = v_document AND document_version_id = v_version
      AND relationship_type = 'TEACHES';
    IF n <> 1 THEN RAISE EXCEPTION 'reconcile: expected 1 TEACHES curriculum source for Machine Fundamentals and SOP-001 v3.4, found %', n; END IF;

    -- Learner topic: exactly one active, version-null "Machine Fundamentals" topic in this curriculum.
    SELECT count(*), min(topic_id::text)::uuid INTO n, v_topic
    FROM workweave.curriculum_topics
    WHERE organization_id = v_org AND workspace_id = v_ws AND curriculum_id = v_curriculum
      AND name = 'Machine Fundamentals' AND document_version_id IS NULL AND active;
    IF n <> 1 THEN RAISE EXCEPTION 'reconcile: expected 1 legacy Machine Fundamentals topic, found %', n; END IF;

    FOR pair IN
        SELECT * FROM (VALUES
            ('h2:1/h3:1', 'Fundamentals', 'Find the current procedure'),
            ('h2:1/h3:2', 'Fundamentals', 'Separate history from evidence'),
            ('h2:1/h3:3', 'Fundamentals', 'Ask a clearer question')
        ) AS p(section_key, topic_heading, subtopic_name)
    LOOP
        -- Source section: exact key, H2 and H3 headings within the exact version.
        SELECT count(*), min(section_id::text)::uuid INTO n, v_section
        FROM workweave.knowledge_sections
        WHERE organization_id = v_org AND workspace_id = v_ws AND document_version_id = v_version
          AND section_key = pair.section_key AND topic_heading = pair.topic_heading AND subtopic_heading = pair.subtopic_name;
        IF n <> 1 THEN RAISE EXCEPTION 'reconcile: expected 1 section % (%), found %', pair.section_key, pair.subtopic_name, n; END IF;

        -- Learner subtopic: exactly one active subtopic with that name under the legacy topic,
        -- carrying a reviewed objective.
        SELECT count(*), min(s.subtopic_id::text)::uuid INTO n, v_subtopic
        FROM workweave.curriculum_subtopics s
        WHERE s.organization_id = v_org AND s.workspace_id = v_ws AND s.topic_id = v_topic
          AND s.name = pair.subtopic_name AND s.active
          AND EXISTS (SELECT 1 FROM workweave.learning_objectives lo
                      WHERE lo.organization_id = s.organization_id AND lo.workspace_id = s.workspace_id AND lo.subtopic_id = s.subtopic_id);
        IF n <> 1 THEN RAISE EXCEPTION 'reconcile: expected 1 learner subtopic "%" with an objective, found %', pair.subtopic_name, n; END IF;

        -- Retrieval readiness: the section must have at least one embedded chunk.
        SELECT count(*) INTO n FROM workweave.knowledge_chunks
        WHERE organization_id = v_org AND workspace_id = v_ws AND document_version_id = v_version
          AND source_section_id = v_section AND embedding IS NOT NULL;
        IF n = 0 THEN RAISE EXCEPTION 'reconcile: section % has no embedded chunk', pair.section_key; END IF;

        -- A different relationship for the same section/subtopic would be ambiguous: refuse.
        SELECT count(*) INTO n FROM workweave.curriculum_source_sections
        WHERE organization_id = v_org AND workspace_id = v_ws AND curriculum_source_id = v_source
          AND section_id = v_section AND subtopic_id = v_subtopic AND relationship_type <> 'TEACHES';
        IF n > 0 THEN RAISE EXCEPTION 'reconcile: section % already maps to "%" with a non-TEACHES relationship', pair.section_key, pair.subtopic_name; END IF;

        INSERT INTO workweave.curriculum_source_sections
            (organization_id, workspace_id, curriculum_source_id, curriculum_id, document_version_id,
             section_id, topic_id, subtopic_id, relationship_type)
        VALUES (v_org, v_ws, v_source, v_curriculum, v_version, v_section, v_topic, v_subtopic, 'TEACHES')
        ON CONFLICT (organization_id, workspace_id, curriculum_source_id, section_id, subtopic_id) DO NOTHING;
    END LOOP;
END
$reconcile$;

COMMIT;
