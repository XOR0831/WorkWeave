from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

import json
import os

load_dotenv()

# DB CREDS
db_port = os.getenv("PORT")
db_name = os.getenv("DB_NAME")
db_pass = os.getenv("PASS")

DATABASE_URL = f"postgresql+psycopg://{db_name}:{db_pass}@localhost:{db_port}/{db_name}"

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False)

def configure(database_url):
    """Point every query at the caller's database (the WorkWeave backend passes its own)."""
    global engine, session_local
    engine = create_engine(database_url, pool_pre_ping=True)
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False)

def query_document(document_code, workspace_id):
    query = text("""
        SELECT
            d.organization_id,
            d.workspace_id,
            d.document_id,
            d.document_code,
            v.document_version_id,
            v.version,
            v.source_id,
            v.content
        FROM workweave.knowledge_documents AS d
        JOIN workweave.knowledge_document_versions AS v
            ON v.organization_id = d.organization_id
        AND v.workspace_id = d.workspace_id
        AND v.document_id = d.document_id
        AND v.document_version_id = d.current_version_id
        JOIN workweave.source_records AS sr
            ON sr.organization_id = v.organization_id
        AND sr.workspace_id = v.workspace_id
        AND sr.source_id = v.source_id
        WHERE d.document_code = :document_code
            AND d.workspace_id = :workspace_id
            AND v.approval_status = 'APPROVED'
            AND v.temporal_status = 'CURRENT'
            AND sr.revoked_at IS null;
    """)

    with session_local() as session:
        result = session.execute(query, {
            "document_code": document_code,
            "workspace_id": workspace_id
        })

        row = result.mappings().first()

        if row:
            # print(row["content"])
            return row
        else:
            print(f"Document '{document_code}' not found.")
            return None

def query_curriculum_sources(document_version_id, curriculum_id):
    query = text("""
        INSERT INTO workweave.curriculum_sources (
            organization_id,
            workspace_id,
            curriculum_id,
            document_id,
            document_version_id,
            relationship_type
        )
        SELECT
            c.organization_id,
            c.workspace_id,
            c.curriculum_id,
            v.document_id,
            v.document_version_id,
            'TEACHES'
        FROM workweave.curricula AS c
        JOIN workweave.knowledge_document_versions AS v
            ON v.organization_id = c.organization_id
        AND v.workspace_id = c.workspace_id
        WHERE c.curriculum_id = :curriculum_id
            AND v.document_version_id = :document_version_id
            AND v.approval_status = 'APPROVED'
            AND v.temporal_status = 'CURRENT'
        ON CONFLICT (
            organization_id,
            workspace_id,
            curriculum_id,
            document_version_id
        ) DO NOTHING
        RETURNING curriculum_source_id;
    """)

    with session_local() as session:
        session.execute(query, {
            "curriculum_id": curriculum_id,
            "document_version_id": document_version_id
        })

        session.commit()

def query_curriculum_topics(document_version_id, curriculum_id, insert_topic, topic=None, topic_order_index=None,):
    print(document_version_id, curriculum_id, topic, topic_order_index)
    insert_topic_query = text("""
        INSERT INTO workweave.curriculum_topics (
            organization_id,
            workspace_id,
            curriculum_id,
            document_version_id,
            name,
            order_index
        )
        SELECT
            cs.organization_id,
            cs.workspace_id,
            cs.curriculum_id,
            cs.document_version_id,
            :topic_name,
            :topic_order_index
        FROM workweave.curriculum_sources AS cs
        WHERE cs.curriculum_id = :curriculum_id
            AND cs.document_version_id = :document_version_id
        ON CONFLICT (
            organization_id, workspace_id, curriculum_id,
            document_version_id, order_index
        ) WHERE document_version_id IS NOT NULL
        DO NOTHING
        RETURNING topic_id;
    """)

    fetch_topic_query = text("""
        SELECT topic_id, name
        FROM workweave.curriculum_topics
        WHERE curriculum_id = :curriculum_id
        AND document_version_id = :document_version_id
        ORDER BY order_index
    """)

    with session_local() as session:
        if insert_topic:
            session.execute(insert_topic_query, {
                "curriculum_id": curriculum_id,
                "document_version_id": document_version_id,
                "topic_name": topic,
                "topic_order_index": topic_order_index
            })

            session.commit()
        else:
            result = session.execute(fetch_topic_query, {
                "curriculum_id": curriculum_id,
                "document_version_id": document_version_id
            })
            row = result.mappings().all()

            print(row)
            if row:
                # print(row["content"])
                return row
            else:
                return None

def query_curriculum_subtopics(document_version_id, curriculum_id, topic_id, subtopic_name=None, subtopic_order_index=None):
    query = text("""
        INSERT INTO workweave.curriculum_subtopics (
            organization_id,
            workspace_id,
            topic_id,
            name,
            order_index
        )
        SELECT
            t.organization_id,
            t.workspace_id,
            t.topic_id,
            :subtopic_name,
            :subtopic_order_index
        FROM workweave.curriculum_topics AS t
        WHERE t.topic_id = :topic_id
            AND t.curriculum_id = :curriculum_id
            AND t.document_version_id = :document_version_id
        ON CONFLICT (
            organization_id, workspace_id, topic_id, order_index
        ) DO NOTHING
        RETURNING subtopic_id;
    """)

    with session_local() as session:
        session.execute(query, {
            "curriculum_id": curriculum_id,
            "document_version_id": document_version_id,
            "topic_id": topic_id,
            "subtopic_name": subtopic_name,
            "subtopic_order_index": subtopic_order_index
        })

        session.commit()

def query_knowledge_sections(document_version_id, section_key, topic_heading, subtopic_heading, topic_order_index, subtopic_order_index):
    query = text("""
        INSERT INTO workweave.knowledge_sections (
            organization_id,
            workspace_id,
            document_version_id,
            section_key,
            topic_heading,
            subtopic_heading,
            topic_order_index,
            subtopic_order_index
        )
        SELECT
            v.organization_id,
            v.workspace_id,
            v.document_version_id,
            :section_key,
            :topic_heading,
            :subtopic_heading,
            :topic_order_index,
            :subtopic_order_index
        FROM workweave.knowledge_document_versions AS v
        WHERE v.document_version_id = :document_version_id
        ON CONFLICT (
            organization_id, workspace_id, document_version_id, section_key
        ) DO NOTHING
        RETURNING section_id;
    """)

    with session_local() as session:
        session.execute(query, {
            "document_version_id": document_version_id,
            "section_key": section_key,
            "topic_heading": topic_heading,
            "subtopic_heading": subtopic_heading,
            "topic_order_index": topic_order_index,
            "subtopic_order_index": subtopic_order_index
        })

        session.commit()

def query_sections(document_version_id, curriculum_id, section_key):
    query = text("""
        SELECT
            cs.curriculum_source_id,
            s.section_id,
            t.topic_id,
            st.subtopic_id
        FROM workweave.curriculum_sources AS cs
        JOIN workweave.knowledge_sections AS s
            ON s.organization_id = cs.organization_id
        AND s.workspace_id = cs.workspace_id
        AND s.document_version_id = cs.document_version_id
        JOIN workweave.curriculum_topics AS t
            ON t.organization_id = cs.organization_id
        AND t.workspace_id = cs.workspace_id
        AND t.curriculum_id = cs.curriculum_id
        AND t.document_version_id = cs.document_version_id
        AND t.order_index = s.topic_order_index
        AND t.name = s.topic_heading
        JOIN workweave.curriculum_subtopics AS st
            ON st.organization_id = t.organization_id
        AND st.workspace_id = t.workspace_id
        AND st.topic_id = t.topic_id
        AND st.order_index = s.subtopic_order_index
        AND st.name = s.subtopic_heading
        WHERE cs.curriculum_id = :curriculum_id
            AND cs.document_version_id = :document_version_id
            AND s.section_key = :section_key;
    """)

    with session_local() as session:
        result = session.execute(query, {
            "curriculum_id": curriculum_id,
            "document_version_id": document_version_id,
            "section_key": section_key
        })
        row = result.mappings().all()

        print("sections", row)
        if row:
            # print(row["content"])
            return row
        else:
            return None

def query_curriculum_source_sections(topic_id, subtopic_id, section_id, curriculum_source_id, curriculum_id, document_version_id):
    query = text("""
        INSERT INTO workweave.curriculum_source_sections (
            organization_id, workspace_id, curriculum_source_id,
            curriculum_id, document_version_id,
            section_id, topic_id, subtopic_id, relationship_type
        )
        SELECT
            cs.organization_id, cs.workspace_id, cs.curriculum_source_id,
            cs.curriculum_id, cs.document_version_id,
            :section_id, :topic_id, :subtopic_id, 'TEACHES'
        FROM workweave.curriculum_sources AS cs
        WHERE cs.curriculum_source_id = :curriculum_source_id
            AND cs.curriculum_id = :curriculum_id
            AND cs.document_version_id = :document_version_id
        ON CONFLICT (
            organization_id, workspace_id,
            curriculum_source_id, section_id, subtopic_id
        ) DO NOTHING
        RETURNING curriculum_source_section_id;
    """)

    with session_local() as session:
        session.execute(query, {
            "topic_id": topic_id,
            "subtopic_id": subtopic_id,
            "section_id": section_id,
            "curriculum_source_id": curriculum_source_id,
            "curriculum_id": curriculum_id,
            "document_version_id": document_version_id
        })

        session.commit()

def query_knowledge_chunks(organization_id, workspace_id, document_version_id, source_id, chunks, embedding_model, embedding_dimension, index_generation=None):
    query = text("""
        INSERT INTO workweave.knowledge_chunks AS existing (
            organization_id, workspace_id, document_version_id,
            source_id, source_section_id, section_path, heading,
            content, chunk_index, embedding, embedding_model,
            embedding_dimension, index_generation
        )
        SELECT
            v.organization_id, v.workspace_id, v.document_version_id,
            v.source_id, s.section_id,
            jsonb_build_array(s.topic_heading), s.subtopic_heading,
            :content, :chunk_index, CAST(:embedding AS public.vector),
            :embedding_model, :embedding_dimension, :index_generation
        FROM workweave.knowledge_document_versions AS v
        JOIN workweave.knowledge_sections AS s
        ON s.organization_id = v.organization_id
        AND s.workspace_id = v.workspace_id
        AND s.document_version_id = v.document_version_id
        WHERE v.organization_id = :organization_id
        AND v.workspace_id = :workspace_id
        AND v.document_version_id = :document_version_id
        AND v.source_id = :source_id
        AND v.approval_status = 'APPROVED'
        AND v.temporal_status = 'CURRENT'
        AND s.section_key = :section_key
        AND s.topic_heading = :topic
        AND s.subtopic_heading = :subtopic
        ON CONFLICT (
            organization_id, workspace_id, document_version_id, chunk_index
        )
        DO UPDATE SET
            embedding = EXCLUDED.embedding,
            embedding_model = EXCLUDED.embedding_model,
            embedding_dimension = EXCLUDED.embedding_dimension,
            index_generation = EXCLUDED.index_generation
        WHERE existing.source_id = EXCLUDED.source_id
        AND existing.source_section_id = EXCLUDED.source_section_id
        AND existing.section_path = EXCLUDED.section_path
        AND existing.heading = EXCLUDED.heading
        AND existing.content = EXCLUDED.content
        RETURNING chunk_id
    """)

    with session_local.begin() as session:
        for chunk in chunks:
            session.execute(query, {
                "organization_id": organization_id,
                "workspace_id": workspace_id,
                "document_version_id": document_version_id,
                "source_id": source_id,
                "section_key": chunk["section_key"],
                "topic": chunk["topic"],
                "subtopic": chunk["subtopic"],
                "content": chunk["content"],
                "chunk_index": chunk["chunk_index"],
                "embedding": json.dumps(chunk["embedding"]),
                "embedding_model": embedding_model,
                "embedding_dimension": embedding_dimension,
                "index_generation": index_generation,
            })

