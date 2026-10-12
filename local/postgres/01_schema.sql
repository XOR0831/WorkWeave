-- One-shot reviewed schema baseline. Applied to the local WorkWeave database on 2026-09-27.
-- Do not rerun against a populated database; production migrations remain to be built.
-- PostgreSQL 16 + pgvector; business schema only, not the AI checkpointer.
-- Intentionally not placed in init/: Compose will NEVER auto-run this file.
-- One-shot empty-schema install. Existing schema causes failure, not replacement.
-- All changes are enclosed in one transaction. Use psql -v ON_ERROR_STOP=1.
BEGIN;
CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;
CREATE SCHEMA workweave;
SET LOCAL search_path = workweave, public;

-- Mutable: organizations
CREATE TABLE workweave.organizations (
    organization_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL,
    industry text,
    company_key text UNIQUE,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0)
);

-- Mutable: workspaces
CREATE TABLE workweave.workspaces (
    workspace_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    kind text NOT NULL DEFAULT 'DEMO' CHECK (kind IN ('DEMO', 'OPERATIONAL')),
    scenario_id uuid,
    pack_version text,
    content_hash text,
    clock_anchor timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    UNIQUE (organization_id, workspace_id),
    FOREIGN KEY (organization_id) REFERENCES workweave.organizations (organization_id)
);

-- Mutable: departments
CREATE TABLE workweave.departments (
    department_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    name text NOT NULL,
    description text,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    UNIQUE (organization_id, workspace_id, department_id),
    FOREIGN KEY (organization_id, workspace_id) REFERENCES workweave.workspaces (organization_id, workspace_id)
);

-- Mutable: teams
CREATE TABLE workweave.teams (
    team_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    department_id uuid NOT NULL,
    name text NOT NULL,
    description text,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    UNIQUE (organization_id, workspace_id, team_id),
    FOREIGN KEY (organization_id, workspace_id) REFERENCES workweave.workspaces (organization_id, workspace_id)
);

-- Mutable: roles
CREATE TABLE workweave.roles (
    role_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    name text NOT NULL,
    description text,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    UNIQUE (organization_id, workspace_id, role_id),
    FOREIGN KEY (organization_id, workspace_id) REFERENCES workweave.workspaces (organization_id, workspace_id)
);

-- Mutable: employees
CREATE TABLE workweave.employees (
    employee_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    role_id uuid,
    first_name text NOT NULL,
    last_name text NOT NULL,
    email text NOT NULL,
    employment_status text NOT NULL DEFAULT 'ACTIVE' CHECK (employment_status IN ('ONBOARDING', 'ACTIVE', 'NOTICE_PERIOD', 'EXITED')),
    hire_date date,
    final_working_date date,
    preferred_language text NOT NULL DEFAULT 'en',
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    UNIQUE (organization_id, workspace_id, employee_id),
    FOREIGN KEY (organization_id, workspace_id) REFERENCES workweave.workspaces (organization_id, workspace_id),
    CHECK (final_working_date IS NULL OR hire_date IS NULL OR final_working_date >= hire_date)
);

-- Mutable: employee_team_memberships
CREATE TABLE workweave.employee_team_memberships (
    membership_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    employee_id uuid NOT NULL,
    team_id uuid NOT NULL,
    team_role text NOT NULL CHECK (team_role IN ('MEMBER', 'SHIFT_LEAD', 'TEAM_LEAD', 'MANAGER')),
    start_date date NOT NULL,
    end_date date,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    UNIQUE (organization_id, workspace_id, membership_id),
    FOREIGN KEY (organization_id, workspace_id) REFERENCES workweave.workspaces (organization_id, workspace_id),
    CHECK (end_date IS NULL OR end_date >= start_date)
);

-- Mutable: auth_identity_links
CREATE TABLE workweave.auth_identity_links (
    identity_link_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    provider text NOT NULL,
    provider_subject text NOT NULL,
    employee_id uuid NOT NULL,
    active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    UNIQUE (organization_id, workspace_id, identity_link_id),
    FOREIGN KEY (organization_id, workspace_id) REFERENCES workweave.workspaces (organization_id, workspace_id),
    UNIQUE (organization_id, workspace_id, provider, provider_subject)
);

-- Mutable: permission_grants
CREATE TABLE workweave.permission_grants (
    grant_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    actor_id uuid NOT NULL,
    resource_scope jsonb NOT NULL DEFAULT '{}'::jsonb,
    action text NOT NULL,
    valid_from timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    valid_until timestamptz,
    granted_by uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    UNIQUE (organization_id, workspace_id, grant_id),
    FOREIGN KEY (organization_id, workspace_id) REFERENCES workweave.workspaces (organization_id, workspace_id),
    CHECK (valid_until IS NULL OR valid_until > valid_from)
);

-- Mutable: shifts
CREATE TABLE workweave.shifts (
    shift_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    team_id uuid NOT NULL,
    name text NOT NULL,
    start_time time NOT NULL,
    end_time time NOT NULL,
    timezone text NOT NULL DEFAULT 'Asia/Manila',
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    UNIQUE (organization_id, workspace_id, shift_id),
    FOREIGN KEY (organization_id, workspace_id) REFERENCES workweave.workspaces (organization_id, workspace_id)
);

-- Mutable: shift_instances
CREATE TABLE workweave.shift_instances (
    shift_instance_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    shift_id uuid NOT NULL,
    shift_date date NOT NULL,
    scheduled_start_at timestamptz NOT NULL,
    scheduled_end_at timestamptz NOT NULL,
    started_at timestamptz,
    ended_at timestamptz,
    shift_lead_employee_id uuid,
    status text NOT NULL DEFAULT 'SCHEDULED' CHECK (status IN ('SCHEDULED', 'ACTIVE', 'COMPLETED', 'CANCELLED')),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    UNIQUE (organization_id, workspace_id, shift_instance_id),
    FOREIGN KEY (organization_id, workspace_id) REFERENCES workweave.workspaces (organization_id, workspace_id),
    CHECK (scheduled_end_at > scheduled_start_at),
    CHECK (ended_at IS NULL OR (started_at IS NOT NULL AND ended_at > started_at))
);

-- Mutable: shift_instance_memberships
CREATE TABLE workweave.shift_instance_memberships (
    shift_membership_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    shift_instance_id uuid NOT NULL,
    employee_id uuid NOT NULL,
    membership_role text NOT NULL CHECK (membership_role IN ('MEMBER', 'SHIFT_LEAD')),
    availability_status text NOT NULL DEFAULT 'UNKNOWN' CHECK (availability_status IN ('AVAILABLE', 'UNAVAILABLE', 'UNKNOWN')),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    UNIQUE (organization_id, workspace_id, shift_membership_id),
    FOREIGN KEY (organization_id, workspace_id) REFERENCES workweave.workspaces (organization_id, workspace_id),
    UNIQUE (organization_id, workspace_id, shift_instance_id, employee_id)
);

-- Mutable: employee_availability
CREATE TABLE workweave.employee_availability (
    availability_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    employee_id uuid NOT NULL,
    start_at timestamptz NOT NULL,
    end_at timestamptz NOT NULL,
    status text NOT NULL CHECK (status IN ('AVAILABLE', 'UNAVAILABLE', 'UNKNOWN')),
    source_reference text,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    UNIQUE (organization_id, workspace_id, availability_id),
    FOREIGN KEY (organization_id, workspace_id) REFERENCES workweave.workspaces (organization_id, workspace_id),
    CHECK (end_at > start_at)
);

-- Mutable: consent_sessions
CREATE TABLE workweave.consent_sessions (
    consent_session_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    purpose text NOT NULL,
    owner_employee_id uuid NOT NULL,
    notice_version text NOT NULL,
    accepted_at timestamptz NOT NULL,
    requested_audience jsonb NOT NULL DEFAULT '[]'::jsonb,
    raw_retention jsonb NOT NULL DEFAULT '{}'::jsonb,
    status text NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'REVOKED', 'EXPIRED')),
    revoked_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    UNIQUE (organization_id, workspace_id, consent_session_id),
    FOREIGN KEY (organization_id, workspace_id) REFERENCES workweave.workspaces (organization_id, workspace_id),
    CHECK ((status = 'REVOKED') = (revoked_at IS NOT NULL))
);

-- Mutable: source_records
CREATE TABLE workweave.source_records (
    source_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    source_type text NOT NULL CHECK (source_type IN ('DOCUMENT', 'INTERVIEW', 'WORK_EVENT', 'EMAIL', 'CALENDAR', 'TICKET', 'MANUAL', 'APPROVED_EXCERPT')),
    storage_object text,
    checksum text,
    owner_employee_id uuid,
    consent_session_id uuid,
    retention_until timestamptz,
    revoked_at timestamptz,
    evidence_type text NOT NULL CHECK (evidence_type IN ('OBSERVED', 'REPORTED', 'INFERRED', 'UNKNOWN')),
    access_partition text NOT NULL DEFAULT 'PRIVATE' CHECK (access_partition IN ('ORGANIZATION', 'TEAM', 'PRIVATE', 'SUBMITTED')),
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    UNIQUE (organization_id, workspace_id, source_id),
    FOREIGN KEY (organization_id, workspace_id) REFERENCES workweave.workspaces (organization_id, workspace_id)
);

-- Mutable: knowledge_documents
CREATE TABLE workweave.knowledge_documents (
    document_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    document_code text,
    title text NOT NULL,
    document_type text NOT NULL CHECK (document_type IN ('SOP', 'PROCEDURE', 'GUIDE', 'CHECKLIST', 'REFERENCE', 'KT_ARTIFACT')),
    current_version_id uuid,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    UNIQUE (organization_id, workspace_id, document_id),
    FOREIGN KEY (organization_id, workspace_id) REFERENCES workweave.workspaces (organization_id, workspace_id),
    UNIQUE (organization_id, workspace_id, document_code)
);

-- Mutable: knowledge_document_versions
CREATE TABLE workweave.knowledge_document_versions (
    document_version_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    document_id uuid NOT NULL,
    version text NOT NULL,
    content text NOT NULL,
    source_id uuid,
    approval_status text NOT NULL DEFAULT 'DRAFT' CHECK (approval_status IN ('DRAFT', 'PENDING_REVIEW', 'APPROVED', 'REJECTED')),
    temporal_status text NOT NULL DEFAULT 'CURRENT' CHECK (temporal_status IN ('CURRENT', 'SUPERSEDED', 'ARCHIVED')),
    effective_at timestamptz,
    approved_by_employee_id uuid,
    approved_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    UNIQUE (organization_id, workspace_id, document_version_id),
    FOREIGN KEY (organization_id, workspace_id) REFERENCES workweave.workspaces (organization_id, workspace_id),
    UNIQUE (organization_id, workspace_id, document_id, version),
    UNIQUE (organization_id, workspace_id, document_id, document_version_id),
    CHECK (approval_status <> 'APPROVED' OR (approved_by_employee_id IS NOT NULL AND approved_at IS NOT NULL))
);

-- Mutable: knowledge_chunks
CREATE TABLE workweave.knowledge_chunks (
    chunk_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    document_version_id uuid NOT NULL,
    source_id uuid NOT NULL,
    parent_chunk_id uuid,
    section_path jsonb NOT NULL DEFAULT '[]'::jsonb,
    heading text,
    content text NOT NULL,
    chunk_index integer NOT NULL CHECK (chunk_index >= 0),
    source_span jsonb NOT NULL DEFAULT '{}'::jsonb,
    embedding public.vector,
    embedding_model text,
    embedding_dimension integer CHECK (embedding_dimension > 0),
    index_generation text,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    UNIQUE (organization_id, workspace_id, chunk_id),
    FOREIGN KEY (organization_id, workspace_id) REFERENCES workweave.workspaces (organization_id, workspace_id),
    UNIQUE (organization_id, workspace_id, document_version_id, chunk_index),
    UNIQUE (organization_id, workspace_id, document_version_id, chunk_id),
    CHECK (parent_chunk_id IS NULL OR parent_chunk_id <> chunk_id),
    CHECK (embedding IS NULL OR (embedding_model IS NOT NULL AND embedding_dimension IS NOT NULL AND public.vector_dims(embedding) = embedding_dimension))
);

-- Mutable: knowledge_mappings
CREATE TABLE workweave.knowledge_mappings (
    mapping_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    document_id uuid NOT NULL,
    document_version_id uuid,
    section_ref text,
    entity_type text NOT NULL CHECK (entity_type IN ('COMPETENCY', 'CURRICULUM_TOPIC', 'CURRICULUM_SUBTOPIC', 'LEARNING_OBJECTIVE', 'ROLE')),
    entity_id uuid NOT NULL,
    relationship_type text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    UNIQUE (organization_id, workspace_id, mapping_id),
    FOREIGN KEY (organization_id, workspace_id) REFERENCES workweave.workspaces (organization_id, workspace_id)
);

-- Mutable: memory_drafts
CREATE TABLE workweave.memory_drafts (
    draft_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    owner_employee_id uuid NOT NULL,
    consent_session_id uuid,
    content text NOT NULL,
    evidence_refs jsonb NOT NULL DEFAULT '[]'::jsonb,
    requested_audience jsonb NOT NULL DEFAULT '[]'::jsonb,
    status text NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT', 'PENDING_REVIEW', 'APPROVED', 'REJECTED')),
    submitted_revision bigint CHECK (submitted_revision > 0),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    UNIQUE (organization_id, workspace_id, draft_id),
    FOREIGN KEY (organization_id, workspace_id) REFERENCES workweave.workspaces (organization_id, workspace_id)
);

-- Append-only/immutable: memory_records
CREATE TABLE workweave.memory_records (
    memory_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    originating_draft_id uuid NOT NULL,
    approved_content_revision bigint NOT NULL CHECK (approved_content_revision > 0),
    content text NOT NULL,
    evidence_type text NOT NULL CHECK (evidence_type IN ('OBSERVED', 'REPORTED', 'INFERRED', 'UNKNOWN')),
    source_refs jsonb NOT NULL DEFAULT '[]'::jsonb,
    approved_audience jsonb NOT NULL DEFAULT '[]'::jsonb,
    approved_by uuid NOT NULL,
    approved_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (organization_id, workspace_id, memory_id),
    FOREIGN KEY (organization_id, workspace_id) REFERENCES workweave.workspaces (organization_id, workspace_id),
    UNIQUE (organization_id, workspace_id, originating_draft_id, approved_content_revision)
);

-- Mutable: competencies
CREATE TABLE workweave.competencies (
    competency_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    code text NOT NULL,
    name text NOT NULL,
    description text,
    category text,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    UNIQUE (organization_id, workspace_id, competency_id),
    FOREIGN KEY (organization_id, workspace_id) REFERENCES workweave.workspaces (organization_id, workspace_id),
    UNIQUE (organization_id, workspace_id, code)
);

-- Mutable: role_competency_requirements
CREATE TABLE workweave.role_competency_requirements (
    requirement_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    role_id uuid NOT NULL,
    competency_id uuid NOT NULL,
    required_level integer CHECK (required_level >= 0),
    is_mandatory boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    UNIQUE (organization_id, workspace_id, requirement_id),
    FOREIGN KEY (organization_id, workspace_id) REFERENCES workweave.workspaces (organization_id, workspace_id),
    UNIQUE (organization_id, workspace_id, role_id, competency_id)
);

-- Mutable: employee_competency_evidence
CREATE TABLE workweave.employee_competency_evidence (
    evidence_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    employee_id uuid NOT NULL,
    competency_id uuid NOT NULL,
    evidence_type text NOT NULL CHECK (evidence_type IN ('ASSESSMENT', 'WORK_COMPLETION', 'ASSISTANCE_REQUEST', 'SUPERVISOR_VALIDATION', 'KT_VALIDATION')),
    source_type text NOT NULL CHECK (source_type IN ('ONBOARDING', 'WORK_ITEM', 'WORK_EVENT', 'HANDOVER', 'EXIT_KT', 'MANUAL')),
    source_id uuid,
    evidence_strength numeric CHECK (evidence_strength BETWEEN 0 AND 1),
    description text,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    observed_at timestamptz NOT NULL,
    validation_status text NOT NULL DEFAULT 'UNVALIDATED' CHECK (validation_status IN ('UNVALIDATED', 'VALIDATED', 'REJECTED')),
    validated_by uuid,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    UNIQUE (organization_id, workspace_id, evidence_id),
    FOREIGN KEY (organization_id, workspace_id) REFERENCES workweave.workspaces (organization_id, workspace_id),
    CHECK (validation_status <> 'VALIDATED' OR validated_by IS NOT NULL)
);

-- Mutable: employee_competency_state
CREATE TABLE workweave.employee_competency_state (
    employee_competency_state_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    employee_id uuid NOT NULL,
    competency_id uuid NOT NULL,
    current_level integer CHECK (current_level >= 0),
    confidence numeric CHECK (confidence BETWEEN 0 AND 1),
    last_evaluated_at timestamptz,
    policy_version text NOT NULL,
    evidence_refs jsonb NOT NULL DEFAULT '[]'::jsonb,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    UNIQUE (organization_id, workspace_id, employee_competency_state_id),
    FOREIGN KEY (organization_id, workspace_id) REFERENCES workweave.workspaces (organization_id, workspace_id),
    UNIQUE (organization_id, workspace_id, employee_id, competency_id)
);

-- Mutable: curricula
CREATE TABLE workweave.curricula (
    curriculum_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    name text NOT NULL,
    description text,
    version text NOT NULL,
    status text NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT', 'PUBLISHED', 'ARCHIVED')),
    published_at timestamptz,
    completion_policy_version text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    UNIQUE (organization_id, workspace_id, curriculum_id),
    FOREIGN KEY (organization_id, workspace_id) REFERENCES workweave.workspaces (organization_id, workspace_id),
    UNIQUE (organization_id, workspace_id, name, version),
    CHECK (status <> 'PUBLISHED' OR published_at IS NOT NULL)
);

-- Mutable: curriculum_assignments
CREATE TABLE workweave.curriculum_assignments (
    assignment_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    curriculum_id uuid NOT NULL,
    employee_id uuid,
    role_id uuid,
    assigned_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    assigned_by_employee_id uuid,
    status text NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'COMPLETED', 'CANCELLED')),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    UNIQUE (organization_id, workspace_id, assignment_id),
    FOREIGN KEY (organization_id, workspace_id) REFERENCES workweave.workspaces (organization_id, workspace_id),
    UNIQUE (organization_id, workspace_id, assignment_id, curriculum_id),
    CHECK (employee_id IS NOT NULL OR role_id IS NOT NULL)
);

-- Mutable: learning_assignments
CREATE TABLE workweave.learning_assignments (
    learning_assignment_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    employee_id uuid NOT NULL,
    curriculum_id uuid NOT NULL,
    originating_assignment_id uuid NOT NULL,
    assignment_kind text NOT NULL DEFAULT 'INITIAL' CHECK (assignment_kind IN ('INITIAL', 'REFRESHER', 'REVIEW')),
    status text NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'COMPLETED', 'CANCELLED')),
    cursor_revision bigint NOT NULL DEFAULT 1 CHECK (cursor_revision > 0),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    UNIQUE (organization_id, workspace_id, learning_assignment_id),
    FOREIGN KEY (organization_id, workspace_id) REFERENCES workweave.workspaces (organization_id, workspace_id),
    UNIQUE (organization_id, workspace_id, learning_assignment_id, employee_id),
    UNIQUE (organization_id, workspace_id, learning_assignment_id, curriculum_id),
    UNIQUE (organization_id, workspace_id, employee_id, curriculum_id, originating_assignment_id, assignment_kind)
);

-- Mutable: curriculum_topics
CREATE TABLE workweave.curriculum_topics (
    topic_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    curriculum_id uuid NOT NULL,
    name text NOT NULL,
    description text,
    order_index integer NOT NULL CHECK (order_index >= 0),
    active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    UNIQUE (organization_id, workspace_id, topic_id),
    FOREIGN KEY (organization_id, workspace_id) REFERENCES workweave.workspaces (organization_id, workspace_id),
    UNIQUE (organization_id, workspace_id, curriculum_id, order_index),
    UNIQUE (organization_id, workspace_id, curriculum_id, topic_id)
);

-- Mutable: curriculum_subtopics
CREATE TABLE workweave.curriculum_subtopics (
    subtopic_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    topic_id uuid NOT NULL,
    name text NOT NULL,
    description text,
    order_index integer NOT NULL CHECK (order_index >= 0),
    active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    UNIQUE (organization_id, workspace_id, subtopic_id),
    FOREIGN KEY (organization_id, workspace_id) REFERENCES workweave.workspaces (organization_id, workspace_id),
    UNIQUE (organization_id, workspace_id, topic_id, order_index),
    UNIQUE (organization_id, workspace_id, topic_id, subtopic_id)
);

-- Mutable: curriculum_prerequisites
CREATE TABLE workweave.curriculum_prerequisites (
    prerequisite_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    subtopic_id uuid NOT NULL,
    prerequisite_subtopic_id uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    UNIQUE (organization_id, workspace_id, prerequisite_id),
    FOREIGN KEY (organization_id, workspace_id) REFERENCES workweave.workspaces (organization_id, workspace_id),
    UNIQUE (organization_id, workspace_id, subtopic_id, prerequisite_subtopic_id),
    CHECK (subtopic_id <> prerequisite_subtopic_id)
);

-- Mutable: learning_objectives
CREATE TABLE workweave.learning_objectives (
    objective_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    subtopic_id uuid NOT NULL,
    description text NOT NULL,
    assessment_criteria jsonb NOT NULL DEFAULT '{}'::jsonb,
    criteria_version text NOT NULL,
    required boolean NOT NULL DEFAULT true,
    hint_policy jsonb NOT NULL DEFAULT '{}'::jsonb,
    competency_id uuid,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    UNIQUE (organization_id, workspace_id, objective_id),
    FOREIGN KEY (organization_id, workspace_id) REFERENCES workweave.workspaces (organization_id, workspace_id)
);

-- Mutable: employee_learning_progress
CREATE TABLE workweave.employee_learning_progress (
    progress_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    employee_id uuid NOT NULL,
    learning_assignment_id uuid NOT NULL,
    subtopic_id uuid NOT NULL,
    status text NOT NULL DEFAULT 'NOT_STARTED' CHECK (status IN ('NOT_STARTED', 'IN_PROGRESS', 'COMPLETED')),
    started_at timestamptz,
    completed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    UNIQUE (organization_id, workspace_id, progress_id),
    FOREIGN KEY (organization_id, workspace_id) REFERENCES workweave.workspaces (organization_id, workspace_id),
    UNIQUE (organization_id, workspace_id, learning_assignment_id, subtopic_id),
    CHECK ((status = 'NOT_STARTED' AND started_at IS NULL AND completed_at IS NULL) OR (status = 'IN_PROGRESS' AND started_at IS NOT NULL AND completed_at IS NULL) OR (status = 'COMPLETED' AND started_at IS NOT NULL AND completed_at IS NOT NULL AND completed_at >= started_at))
);

-- Mutable: learning_sessions
CREATE TABLE workweave.learning_sessions (
    learning_session_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    employee_id uuid NOT NULL,
    learning_assignment_id uuid NOT NULL,
    curriculum_id uuid NOT NULL,
    current_topic_id uuid,
    current_subtopic_id uuid,
    started_at timestamptz NOT NULL,
    ended_at timestamptz,
    status text NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'PAUSED', 'COMPLETED', 'EXPIRED')),
    langgraph_thread_id text NOT NULL,
    graph_version text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    UNIQUE (organization_id, workspace_id, learning_session_id),
    FOREIGN KEY (organization_id, workspace_id) REFERENCES workweave.workspaces (organization_id, workspace_id),
    UNIQUE (organization_id, workspace_id, langgraph_thread_id),
    UNIQUE (organization_id, workspace_id, learning_session_id, employee_id),
    CHECK (ended_at IS NULL OR ended_at >= started_at)
);

-- Mutable: learning_turns
CREATE TABLE workweave.learning_turns (
    turn_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    learning_session_id uuid NOT NULL,
    client_turn_id uuid NOT NULL,
    input_hash text NOT NULL,
    sequence bigint NOT NULL CHECK (sequence >= 0),
    input_reference jsonb NOT NULL DEFAULT '{}'::jsonb,
    response_envelope jsonb NOT NULL DEFAULT '{}'::jsonb,
    committed_revision bigint NOT NULL CHECK (committed_revision > 0),
    stage text NOT NULL CHECK (stage IN ('RECEIVED', 'COMMITTED', 'FAILED')),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    UNIQUE (organization_id, workspace_id, turn_id),
    FOREIGN KEY (organization_id, workspace_id) REFERENCES workweave.workspaces (organization_id, workspace_id),
    UNIQUE (organization_id, workspace_id, learning_session_id, client_turn_id),
    UNIQUE (organization_id, workspace_id, learning_session_id, sequence)
);

-- Append-only/immutable: employee_learning_events
CREATE TABLE workweave.employee_learning_events (
    learning_event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    learning_session_id uuid NOT NULL,
    employee_id uuid NOT NULL,
    topic_id uuid,
    subtopic_id uuid,
    objective_id uuid,
    event_type text NOT NULL CHECK (event_type IN ('SESSION_STARTED', 'TOPIC_STARTED', 'SUBTOPIC_STARTED', 'EXPLANATION_PROVIDED', 'CLARIFICATION_REQUESTED', 'QUESTION_ASKED', 'EXAMPLE_REQUESTED', 'HINT_PROVIDED', 'COMPREHENSION_QUESTION', 'ASSESSMENT_ATTEMPT', 'ASSESSMENT_RESULT', 'REINFORCEMENT', 'SUBTOPIC_COMPLETED', 'TOPIC_COMPLETED', 'SESSION_PAUSED', 'SESSION_COMPLETED')),
    strategy text,
    event_data jsonb NOT NULL DEFAULT '{}'::jsonb,
    source_refs jsonb NOT NULL DEFAULT '[]'::jsonb,
    operation_key text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (organization_id, workspace_id, learning_event_id),
    FOREIGN KEY (organization_id, workspace_id) REFERENCES workweave.workspaces (organization_id, workspace_id),
    UNIQUE (organization_id, workspace_id, operation_key)
);

-- Append-only/immutable: learning_assessment_attempts
CREATE TABLE workweave.learning_assessment_attempts (
    attempt_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    turn_id uuid NOT NULL,
    pending_question_id uuid NOT NULL,
    objective_id uuid NOT NULL,
    criteria_version text NOT NULL,
    answer_reference jsonb NOT NULL DEFAULT '{}'::jsonb,
    criterion_results jsonb NOT NULL DEFAULT '{}'::jsonb,
    outcome text NOT NULL CHECK (outcome IN ('CORRECT', 'PARTIAL', 'INCORRECT', 'UNASSESSABLE')),
    support_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (organization_id, workspace_id, attempt_id),
    FOREIGN KEY (organization_id, workspace_id) REFERENCES workweave.workspaces (organization_id, workspace_id),
    UNIQUE (organization_id, workspace_id, turn_id, pending_question_id, objective_id),
    UNIQUE (organization_id, workspace_id, attempt_id, objective_id, criteria_version)
);

-- Append-only/immutable: objective_evidence
CREATE TABLE workweave.objective_evidence (
    objective_evidence_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    learning_assignment_id uuid NOT NULL,
    objective_id uuid NOT NULL,
    criteria_version text NOT NULL,
    attempt_id uuid NOT NULL,
    outcome text NOT NULL CHECK (outcome IN ('PASSED', 'NOT_PASSED', 'UNASSESSABLE')),
    accepted_at timestamptz,
    policy_version text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (organization_id, workspace_id, objective_evidence_id),
    FOREIGN KEY (organization_id, workspace_id) REFERENCES workweave.workspaces (organization_id, workspace_id),
    UNIQUE (organization_id, workspace_id, learning_assignment_id, objective_id, attempt_id),
    CHECK (outcome <> 'PASSED' OR accepted_at IS NOT NULL)
);

-- Mutable: work_sessions
CREATE TABLE workweave.work_sessions (
    work_session_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    employee_id uuid NOT NULL,
    shift_instance_id uuid,
    started_at timestamptz NOT NULL,
    ended_at timestamptz,
    langgraph_thread_id text,
    status text NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'PAUSED', 'COMPLETED', 'EXPIRED')),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    UNIQUE (organization_id, workspace_id, work_session_id),
    FOREIGN KEY (organization_id, workspace_id) REFERENCES workweave.workspaces (organization_id, workspace_id),
    CHECK (ended_at IS NULL OR ended_at >= started_at)
);

-- Mutable: work_items
CREATE TABLE workweave.work_items (
    work_item_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    external_system text,
    external_id text,
    work_item_type text NOT NULL CHECK (work_item_type IN ('TASK', 'TICKET', 'INCIDENT', 'CHANGE', 'ACTIVITY', 'WORK_ORDER', 'OTHER')),
    title text NOT NULL,
    description text,
    priority text NOT NULL DEFAULT 'MEDIUM' CHECK (priority IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
    status text NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'IN_PROGRESS', 'BLOCKED', 'COMPLETED', 'CANCELLED', 'CLOSED')),
    due_at timestamptz,
    sla_due_at timestamptz,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    UNIQUE (organization_id, workspace_id, work_item_id),
    FOREIGN KEY (organization_id, workspace_id) REFERENCES workweave.workspaces (organization_id, workspace_id)
);

-- Mutable: work_item_competency_requirements
CREATE TABLE workweave.work_item_competency_requirements (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    work_item_id uuid NOT NULL,
    competency_id uuid NOT NULL,
    required_level integer CHECK (required_level >= 0),
    importance numeric CHECK (importance BETWEEN 0 AND 1),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    UNIQUE (organization_id, workspace_id, id),
    FOREIGN KEY (organization_id, workspace_id) REFERENCES workweave.workspaces (organization_id, workspace_id),
    UNIQUE (organization_id, workspace_id, work_item_id, competency_id)
);

-- Mutable: delegation_proposals
CREATE TABLE workweave.delegation_proposals (
    delegation_proposal_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    shift_instance_id uuid,
    team_id uuid NOT NULL,
    created_by uuid NOT NULL,
    status text NOT NULL DEFAULT 'PROPOSED' CHECK (status IN ('PROPOSED', 'EDITED', 'CONFIRMED', 'REJECTED')),
    confirmed_at timestamptz,
    confirmed_by_employee_id uuid,
    context_revisions jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    UNIQUE (organization_id, workspace_id, delegation_proposal_id),
    FOREIGN KEY (organization_id, workspace_id) REFERENCES workweave.workspaces (organization_id, workspace_id),
    CHECK (status <> 'CONFIRMED' OR (confirmed_at IS NOT NULL AND confirmed_by_employee_id IS NOT NULL))
);

-- Mutable: delegation_proposal_items
CREATE TABLE workweave.delegation_proposal_items (
    proposal_item_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    delegation_proposal_id uuid NOT NULL,
    work_item_id uuid NOT NULL,
    recommended_employee_id uuid NOT NULL,
    final_employee_id uuid,
    recommendation_reason text NOT NULL,
    match_data jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    UNIQUE (organization_id, workspace_id, proposal_item_id),
    FOREIGN KEY (organization_id, workspace_id) REFERENCES workweave.workspaces (organization_id, workspace_id),
    UNIQUE (organization_id, workspace_id, delegation_proposal_id, work_item_id),
    UNIQUE (organization_id, workspace_id, proposal_item_id, work_item_id)
);

-- Mutable: work_item_assignments
CREATE TABLE workweave.work_item_assignments (
    assignment_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    work_item_id uuid NOT NULL,
    employee_id uuid NOT NULL,
    assigned_by_employee_id uuid,
    assignment_source text NOT NULL CHECK (assignment_source IN ('MANUAL', 'AI_RECOMMENDED', 'HANDOVER', 'EXTERNAL_SYSTEM')),
    status text NOT NULL DEFAULT 'ASSIGNED' CHECK (status IN ('ASSIGNED', 'ACCEPTED', 'IN_PROGRESS', 'REPORTED_COMPLETE', 'COMPLETED', 'CANCELLED')),
    assigned_at timestamptz NOT NULL,
    accepted_at timestamptz,
    completed_at timestamptz,
    proposal_item_id uuid,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    UNIQUE (organization_id, workspace_id, assignment_id),
    FOREIGN KEY (organization_id, workspace_id) REFERENCES workweave.workspaces (organization_id, workspace_id),
    UNIQUE (organization_id, workspace_id, proposal_item_id),
    CHECK (status <> 'COMPLETED' OR completed_at IS NOT NULL)
);

-- Append-only/immutable: work_events
CREATE TABLE workweave.work_events (
    work_event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    work_item_id uuid NOT NULL,
    employee_id uuid NOT NULL,
    shift_instance_id uuid,
    event_type text NOT NULL CHECK (event_type IN ('STARTED', 'STATUS_CHANGED', 'INVESTIGATED', 'BLOCKED', 'UNBLOCKED', 'ESCALATED', 'COMMENTED', 'REPORTED_COMPLETE', 'COMPLETED', 'VALIDATED', 'REOPENED')),
    description text,
    event_data jsonb NOT NULL DEFAULT '{}'::jsonb,
    evidence_refs jsonb NOT NULL DEFAULT '[]'::jsonb,
    observed_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (organization_id, workspace_id, work_event_id),
    FOREIGN KEY (organization_id, workspace_id) REFERENCES workweave.workspaces (organization_id, workspace_id)
);

-- Mutable: employee_work_state
CREATE TABLE workweave.employee_work_state (
    employee_work_state_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    employee_id uuid NOT NULL,
    shift_instance_id uuid,
    work_context_key text NOT NULL,
    workload_state text NOT NULL CHECK (workload_state IN ('ON_TRACK', 'NEEDS_FOCUS', 'BLOCKED', 'NEEDS_SUPPORT', 'HIGH_WORKLOAD')),
    momentum_state text,
    assistance_need text,
    active_work_count integer NOT NULL DEFAULT 0 CHECK (active_work_count >= 0),
    blocked_work_count integer NOT NULL DEFAULT 0 CHECK (blocked_work_count >= 0),
    overdue_work_count integer NOT NULL DEFAULT 0 CHECK (overdue_work_count >= 0),
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    UNIQUE (organization_id, workspace_id, employee_work_state_id),
    FOREIGN KEY (organization_id, workspace_id) REFERENCES workweave.workspaces (organization_id, workspace_id),
    UNIQUE (organization_id, workspace_id, employee_id, work_context_key)
);

-- Append-only/immutable: productivity_observations
CREATE TABLE workweave.productivity_observations (
    observation_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    employee_id uuid NOT NULL,
    shift_instance_id uuid,
    observation_type text NOT NULL,
    value jsonb NOT NULL DEFAULT '{}'::jsonb,
    source_type text NOT NULL,
    source_id uuid,
    observed_at timestamptz NOT NULL,
    valid_until timestamptz,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (organization_id, workspace_id, observation_id),
    FOREIGN KEY (organization_id, workspace_id) REFERENCES workweave.workspaces (organization_id, workspace_id),
    CHECK (valid_until IS NULL OR valid_until > observed_at)
);

-- Mutable: handover_templates
CREATE TABLE workweave.handover_templates (
    template_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    team_id uuid,
    name text NOT NULL,
    description text,
    is_default boolean NOT NULL DEFAULT false,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    UNIQUE (organization_id, workspace_id, template_id),
    FOREIGN KEY (organization_id, workspace_id) REFERENCES workweave.workspaces (organization_id, workspace_id)
);

-- Append-only/immutable: handover_template_versions
CREATE TABLE workweave.handover_template_versions (
    template_version_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    template_id uuid NOT NULL,
    version integer NOT NULL CHECK (version > 0),
    published_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (organization_id, workspace_id, template_version_id),
    FOREIGN KEY (organization_id, workspace_id) REFERENCES workweave.workspaces (organization_id, workspace_id),
    UNIQUE (organization_id, workspace_id, template_id, version)
);

-- Append-only/immutable: handover_template_sections
CREATE TABLE workweave.handover_template_sections (
    section_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    template_version_id uuid NOT NULL,
    name text NOT NULL,
    description text,
    order_index integer NOT NULL CHECK (order_index >= 0),
    is_required boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (organization_id, workspace_id, section_id),
    FOREIGN KEY (organization_id, workspace_id) REFERENCES workweave.workspaces (organization_id, workspace_id),
    UNIQUE (organization_id, workspace_id, template_version_id, order_index),
    UNIQUE (organization_id, workspace_id, template_version_id, section_id)
);

-- Mutable: shift_handovers
CREATE TABLE workweave.shift_handovers (
    handover_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    source_shift_instance_id uuid NOT NULL,
    target_shift_instance_id uuid,
    template_version_id uuid NOT NULL,
    status text NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT', 'UNDER_REVIEW', 'PUBLISHED', 'ACKNOWLEDGED')),
    created_by_employee_id uuid NOT NULL,
    published_by_employee_id uuid,
    published_at timestamptz,
    current_publication_id uuid,
    context_as_of timestamptz NOT NULL,
    context_revisions jsonb NOT NULL DEFAULT '{}'::jsonb,
    draft_sections jsonb NOT NULL DEFAULT '[]'::jsonb,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    UNIQUE (organization_id, workspace_id, handover_id),
    FOREIGN KEY (organization_id, workspace_id) REFERENCES workweave.workspaces (organization_id, workspace_id),
    CHECK (target_shift_instance_id IS NULL OR source_shift_instance_id <> target_shift_instance_id),
    CHECK (status NOT IN ('PUBLISHED','ACKNOWLEDGED') OR (published_at IS NOT NULL AND published_by_employee_id IS NOT NULL AND current_publication_id IS NOT NULL))
);

-- Append-only/immutable: handover_publications
CREATE TABLE workweave.handover_publications (
    publication_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    handover_id uuid NOT NULL,
    publication_number integer NOT NULL CHECK (publication_number > 0),
    content_revision bigint NOT NULL CHECK (content_revision > 0),
    scope_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
    template_version_id uuid NOT NULL,
    section_content jsonb NOT NULL DEFAULT '[]'::jsonb,
    source_revisions jsonb NOT NULL DEFAULT '{}'::jsonb,
    published_by uuid NOT NULL,
    published_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (organization_id, workspace_id, publication_id),
    FOREIGN KEY (organization_id, workspace_id) REFERENCES workweave.workspaces (organization_id, workspace_id),
    UNIQUE (organization_id, workspace_id, handover_id, publication_number),
    UNIQUE (organization_id, workspace_id, handover_id, publication_id),
    UNIQUE (organization_id, workspace_id, publication_id, template_version_id)
);

-- Mutable: handover_items
CREATE TABLE workweave.handover_items (
    handover_item_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    work_item_id uuid,
    title text NOT NULL,
    description text,
    originating_shift_instance_id uuid NOT NULL,
    originating_employee_id uuid,
    current_owner_shift_instance_id uuid,
    work_status text NOT NULL DEFAULT 'ACTIVE' CHECK (work_status IN ('ACTIVE', 'IN_PROGRESS', 'BLOCKED', 'COMPLETED', 'CANCELLED', 'CLOSED')),
    acknowledgement_status text NOT NULL DEFAULT 'NOT_REQUIRED' CHECK (acknowledgement_status IN ('NOT_REQUIRED', 'PENDING', 'ACKNOWLEDGED', 'DISPUTED')),
    completion_cycle_id uuid,
    closed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    UNIQUE (organization_id, workspace_id, handover_item_id),
    FOREIGN KEY (organization_id, workspace_id) REFERENCES workweave.workspaces (organization_id, workspace_id),
    UNIQUE (organization_id, workspace_id, handover_item_id, completion_cycle_id),
    CHECK (acknowledgement_status <> 'PENDING' OR (work_status = 'COMPLETED' AND completion_cycle_id IS NOT NULL)),
    CHECK (work_status <> 'CLOSED' OR closed_at IS NOT NULL)
);

-- Append-only/immutable: handover_entries
CREATE TABLE workweave.handover_entries (
    handover_entry_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    publication_id uuid NOT NULL,
    handover_item_id uuid NOT NULL,
    section_id uuid,
    snapshot_work_status text NOT NULL CHECK (snapshot_work_status IN ('ACTIVE', 'IN_PROGRESS', 'BLOCKED', 'COMPLETED', 'CANCELLED', 'CLOSED')),
    snapshot_acknowledgement_status text NOT NULL CHECK (snapshot_acknowledgement_status IN ('NOT_REQUIRED', 'PENDING', 'ACKNOWLEDGED', 'DISPUTED')),
    snapshot_description text,
    snapshot_source_refs jsonb NOT NULL DEFAULT '[]'::jsonb,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (organization_id, workspace_id, handover_entry_id),
    FOREIGN KEY (organization_id, workspace_id) REFERENCES workweave.workspaces (organization_id, workspace_id),
    UNIQUE (organization_id, workspace_id, publication_id, handover_item_id)
);

-- Mutable: handover_suggestions
CREATE TABLE workweave.handover_suggestions (
    suggestion_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    handover_id uuid NOT NULL,
    handover_item_id uuid,
    suggestion_type text NOT NULL CHECK (suggestion_type IN ('MISSING_ITEM', 'STATUS_UPDATE', 'SCHEDULE_CHANGE', 'POSSIBLE_DUPLICATE', 'STALE_INFORMATION')),
    suggested_data jsonb NOT NULL DEFAULT '{}'::jsonb,
    reason text,
    source_refs jsonb NOT NULL DEFAULT '[]'::jsonb,
    context_revisions jsonb NOT NULL DEFAULT '{}'::jsonb,
    status text NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'ACCEPTED', 'IGNORED')),
    reviewed_by_employee_id uuid,
    reviewed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    UNIQUE (organization_id, workspace_id, suggestion_id),
    FOREIGN KEY (organization_id, workspace_id) REFERENCES workweave.workspaces (organization_id, workspace_id),
    CHECK (status = 'PENDING' OR (reviewed_by_employee_id IS NOT NULL AND reviewed_at IS NOT NULL))
);

-- Mutable: handover_item_sources
CREATE TABLE workweave.handover_item_sources (
    source_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    handover_item_id uuid,
    suggestion_id uuid,
    source_type text NOT NULL CHECK (source_type IN ('MANUAL', 'EMAIL', 'CALENDAR', 'WORK_EVENT', 'TICKET', 'INCIDENT', 'DOCUMENT')),
    external_system text,
    external_id text,
    source_reference text,
    extracted_data jsonb NOT NULL DEFAULT '{}'::jsonb,
    detected_by_ai boolean NOT NULL DEFAULT false,
    confirmed_by_employee_id uuid,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    UNIQUE (organization_id, workspace_id, source_id),
    FOREIGN KEY (organization_id, workspace_id) REFERENCES workweave.workspaces (organization_id, workspace_id),
    CHECK (handover_item_id IS NOT NULL OR suggestion_id IS NOT NULL)
);

-- Mutable: handover_completion_cycles
CREATE TABLE workweave.handover_completion_cycles (
    completion_cycle_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    handover_item_id uuid NOT NULL,
    completed_in_shift_instance_id uuid NOT NULL,
    confirmed_by_employee_id uuid NOT NULL,
    completion_event_id uuid NOT NULL,
    status text NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'ACKNOWLEDGED', 'DISPUTED', 'OBSOLETE')),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    UNIQUE (organization_id, workspace_id, completion_cycle_id),
    FOREIGN KEY (organization_id, workspace_id) REFERENCES workweave.workspaces (organization_id, workspace_id),
    UNIQUE (organization_id, workspace_id, handover_item_id, completion_cycle_id)
);

-- Append-only/immutable: handover_item_events
CREATE TABLE workweave.handover_item_events (
    event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    handover_item_id uuid NOT NULL,
    employee_id uuid,
    shift_instance_id uuid,
    event_type text NOT NULL CHECK (event_type IN ('CREATED', 'UPDATED', 'DELEGATED', 'REPORTED_COMPLETE', 'CONFIRMED_COMPLETE', 'CANCELLED', 'ACKNOWLEDGED', 'DISPUTED', 'REOPENED', 'CLOSED')),
    previous_status text,
    new_status text,
    details jsonb NOT NULL DEFAULT '{}'::jsonb,
    completion_cycle_id uuid,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (organization_id, workspace_id, event_id),
    FOREIGN KEY (organization_id, workspace_id) REFERENCES workweave.workspaces (organization_id, workspace_id)
);

-- Mutable: handover_acknowledgements
CREATE TABLE workweave.handover_acknowledgements (
    acknowledgement_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    handover_item_id uuid NOT NULL,
    completion_cycle_id uuid NOT NULL,
    requested_from_shift_instance_id uuid NOT NULL,
    requested_from_employee_id uuid,
    status text NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'ACKNOWLEDGED', 'DISPUTED')),
    comment text,
    requested_at timestamptz NOT NULL,
    responded_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    UNIQUE (organization_id, workspace_id, acknowledgement_id),
    FOREIGN KEY (organization_id, workspace_id) REFERENCES workweave.workspaces (organization_id, workspace_id),
    UNIQUE (organization_id, workspace_id, handover_item_id, completion_cycle_id, requested_from_shift_instance_id),
    CHECK (status = 'PENDING' OR responded_at IS NOT NULL)
);

-- Append-only/immutable: handover_receipts
CREATE TABLE workweave.handover_receipts (
    receipt_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    publication_id uuid NOT NULL,
    recipient_shift_instance_id uuid NOT NULL,
    recipient_employee_id uuid NOT NULL,
    received_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (organization_id, workspace_id, receipt_id),
    FOREIGN KEY (organization_id, workspace_id) REFERENCES workweave.workspaces (organization_id, workspace_id),
    UNIQUE (organization_id, workspace_id, publication_id, recipient_employee_id)
);

-- Mutable: exit_kt_cases
CREATE TABLE workweave.exit_kt_cases (
    exit_kt_case_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    employee_id uuid NOT NULL,
    case_kind text NOT NULL CHECK (case_kind IN ('DEPARTURE', 'ROLE_TRANSITION')),
    final_working_date date,
    status text NOT NULL DEFAULT 'DISCOVERY' CHECK (status IN ('DISCOVERY', 'IN_PROGRESS', 'PENDING_REVIEW', 'COMPLETE')),
    initiated_by_employee_id uuid NOT NULL,
    reviewer_employee_id uuid,
    started_at timestamptz NOT NULL,
    completed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    UNIQUE (organization_id, workspace_id, exit_kt_case_id),
    FOREIGN KEY (organization_id, workspace_id) REFERENCES workweave.workspaces (organization_id, workspace_id),
    CHECK (case_kind <> 'DEPARTURE' OR final_working_date IS NOT NULL),
    CHECK (status <> 'COMPLETE' OR completed_at IS NOT NULL)
);

-- Mutable: exit_kt_knowledge_items
CREATE TABLE workweave.exit_kt_knowledge_items (
    kt_item_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    exit_kt_case_id uuid NOT NULL,
    competency_id uuid,
    title text NOT NULL,
    description text,
    category text,
    documentation_status text NOT NULL CHECK (documentation_status IN ('DOCUMENTED', 'MISSING', 'OUTDATED', 'NEEDS_REVIEW')),
    kt_status text NOT NULL DEFAULT 'NOT_STARTED' CHECK (kt_status IN ('NOT_STARTED', 'EXISTING_KNOWLEDGE', 'INTERVIEW_REQUIRED', 'INTERVIEW_IN_PROGRESS', 'DRAFT_CREATED', 'PENDING_REVIEW', 'COMPLETE')),
    risk_level text NOT NULL DEFAULT 'MEDIUM' CHECK (risk_level IN ('LOW', 'MEDIUM', 'HIGH')),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    UNIQUE (organization_id, workspace_id, kt_item_id),
    FOREIGN KEY (organization_id, workspace_id) REFERENCES workweave.workspaces (organization_id, workspace_id)
);

-- Mutable: exit_kt_sources
CREATE TABLE workweave.exit_kt_sources (
    source_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    kt_item_id uuid NOT NULL,
    source_type text NOT NULL CHECK (source_type IN ('WORK_HISTORY', 'DOCUMENT', 'EMAIL', 'TICKET', 'CALENDAR', 'EMPLOYEE_ADDED')),
    source_reference text NOT NULL,
    relevance_data jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    UNIQUE (organization_id, workspace_id, source_id),
    FOREIGN KEY (organization_id, workspace_id) REFERENCES workweave.workspaces (organization_id, workspace_id)
);

-- Mutable: exit_kt_findings
CREATE TABLE workweave.exit_kt_findings (
    finding_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    exit_kt_case_id uuid NOT NULL,
    kt_item_id uuid,
    finding_type text NOT NULL CHECK (finding_type IN ('UNDOCUMENTED_KNOWLEDGE', 'OUTDATED_DOCUMENTATION', 'SOLE_KNOWLEDGE_HOLDER', 'MISSING_SUCCESSOR', 'PROCESS_DISCREPANCY')),
    description text NOT NULL,
    evidence_refs jsonb NOT NULL DEFAULT '[]'::jsonb,
    status text NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN', 'CONFIRMED', 'DISMISSED', 'RESOLVED')),
    reviewed_at timestamptz,
    reviewed_by uuid,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    UNIQUE (organization_id, workspace_id, finding_id),
    FOREIGN KEY (organization_id, workspace_id) REFERENCES workweave.workspaces (organization_id, workspace_id)
);

-- Mutable: exit_kt_interviews
CREATE TABLE workweave.exit_kt_interviews (
    interview_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    kt_item_id uuid NOT NULL,
    employee_id uuid NOT NULL,
    consent_session_id uuid NOT NULL,
    status text NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'PAUSED', 'COMPLETED', 'CANCELLED')),
    started_at timestamptz NOT NULL,
    completed_at timestamptz,
    langgraph_thread_id text,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    UNIQUE (organization_id, workspace_id, interview_id),
    FOREIGN KEY (organization_id, workspace_id) REFERENCES workweave.workspaces (organization_id, workspace_id)
);

-- Append-only/immutable: exit_kt_interview_messages
CREATE TABLE workweave.exit_kt_interview_messages (
    message_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    interview_id uuid NOT NULL,
    sender_type text NOT NULL CHECK (sender_type IN ('EMPLOYEE', 'AI', 'REVIEWER')),
    message_type text,
    content text NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    source_refs jsonb NOT NULL DEFAULT '[]'::jsonb,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (organization_id, workspace_id, message_id),
    FOREIGN KEY (organization_id, workspace_id) REFERENCES workweave.workspaces (organization_id, workspace_id)
);

-- Mutable: exit_kt_artifacts
CREATE TABLE workweave.exit_kt_artifacts (
    artifact_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    kt_item_id uuid NOT NULL,
    artifact_type text NOT NULL CHECK (artifact_type IN ('PROCEDURE', 'PROCESS', 'TROUBLESHOOTING_GUIDE', 'CONTACT_GUIDE', 'CHECKLIST', 'REFERENCE', 'SOP_UPDATE_PROPOSAL')),
    title text NOT NULL,
    current_revision_id uuid,
    generated_from_interview_id uuid,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    UNIQUE (organization_id, workspace_id, artifact_id),
    FOREIGN KEY (organization_id, workspace_id) REFERENCES workweave.workspaces (organization_id, workspace_id)
);

-- Mutable: exit_kt_artifact_revisions
CREATE TABLE workweave.exit_kt_artifact_revisions (
    artifact_revision_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    artifact_id uuid NOT NULL,
    version integer NOT NULL CHECK (version > 0),
    content text NOT NULL,
    status text NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT', 'PENDING_REVIEW', 'APPROVED', 'REJECTED', 'REVISION_REQUIRED')),
    source_refs jsonb NOT NULL DEFAULT '[]'::jsonb,
    submitted_at timestamptz,
    employee_reviewed_by uuid,
    employee_reviewed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    UNIQUE (organization_id, workspace_id, artifact_revision_id),
    FOREIGN KEY (organization_id, workspace_id) REFERENCES workweave.workspaces (organization_id, workspace_id),
    UNIQUE (organization_id, workspace_id, artifact_id, version),
    UNIQUE (organization_id, workspace_id, artifact_id, artifact_revision_id),
    CHECK (status <> 'PENDING_REVIEW' OR (submitted_at IS NOT NULL AND employee_reviewed_by IS NOT NULL AND employee_reviewed_at IS NOT NULL))
);

-- Mutable: knowledge_approvals
CREATE TABLE workweave.knowledge_approvals (
    approval_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    artifact_revision_id uuid NOT NULL,
    reviewer_employee_id uuid NOT NULL,
    status text NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'APPROVED', 'REJECTED', 'REVISION_REQUIRED')),
    review_comment text,
    reviewed_at timestamptz,
    context_revisions jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    UNIQUE (organization_id, workspace_id, approval_id),
    FOREIGN KEY (organization_id, workspace_id) REFERENCES workweave.workspaces (organization_id, workspace_id),
    UNIQUE (organization_id, workspace_id, artifact_revision_id, reviewer_employee_id),
    CHECK (status = 'PENDING' OR reviewed_at IS NOT NULL)
);

-- Mutable: knowledge_promotions
CREATE TABLE workweave.knowledge_promotions (
    promotion_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    artifact_revision_id uuid NOT NULL,
    document_version_id uuid NOT NULL,
    approved_by uuid NOT NULL,
    promoted_at timestamptz NOT NULL,
    index_status text NOT NULL DEFAULT 'PENDING' CHECK (index_status IN ('PENDING', 'READY', 'FAILED', 'REVOKED')),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    UNIQUE (organization_id, workspace_id, promotion_id),
    FOREIGN KEY (organization_id, workspace_id) REFERENCES workweave.workspaces (organization_id, workspace_id),
    UNIQUE (organization_id, workspace_id, artifact_revision_id),
    UNIQUE (organization_id, workspace_id, document_version_id)
);

-- Mutable: responsibilities
CREATE TABLE workweave.responsibilities (
    responsibility_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    responsibility_type text NOT NULL CHECK (responsibility_type IN ('PROJECT', 'SYSTEM', 'PROCESS', 'RECURRING_TASK', 'VENDOR_RELATIONSHIP', 'WORK_ITEM', 'OTHER')),
    resource_reference_id uuid,
    title text NOT NULL,
    description text,
    owner_employee_id uuid NOT NULL,
    ownership_revision bigint NOT NULL DEFAULT 1 CHECK (ownership_revision > 0),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    UNIQUE (organization_id, workspace_id, responsibility_id),
    FOREIGN KEY (organization_id, workspace_id) REFERENCES workweave.workspaces (organization_id, workspace_id)
);

-- Mutable: responsibility_transfers
CREATE TABLE workweave.responsibility_transfers (
    transfer_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    exit_kt_case_id uuid NOT NULL,
    responsibility_id uuid NOT NULL,
    current_owner_employee_id uuid NOT NULL,
    recommended_owner_employee_id uuid,
    final_owner_employee_id uuid,
    recommendation_reason text,
    recommendation_data jsonb NOT NULL DEFAULT '{}'::jsonb,
    status text NOT NULL DEFAULT 'DISCOVERED' CHECK (status IN ('DISCOVERED', 'PROPOSED', 'EDITED', 'CONFIRMED', 'TRANSFERRED')),
    approved_by_employee_id uuid,
    effective_at timestamptz NOT NULL,
    expected_owner_revision bigint NOT NULL CHECK (expected_owner_revision > 0),
    completed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    UNIQUE (organization_id, workspace_id, transfer_id),
    FOREIGN KEY (organization_id, workspace_id) REFERENCES workweave.workspaces (organization_id, workspace_id),
    CHECK (status <> 'TRANSFERRED' OR (final_owner_employee_id IS NOT NULL AND approved_by_employee_id IS NOT NULL AND completed_at IS NOT NULL)),
    CHECK (final_owner_employee_id IS NULL OR final_owner_employee_id <> current_owner_employee_id)
);

-- Mutable: exit_kt_packages
CREATE TABLE workweave.exit_kt_packages (
    package_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    exit_kt_case_id uuid NOT NULL,
    successor_employee_id uuid NOT NULL,
    status text NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT', 'PENDING_REVIEW', 'APPROVED', 'REVISION_REQUIRED')),
    current_approved_version_id uuid,
    effective_at timestamptz NOT NULL,
    context_revisions jsonb NOT NULL DEFAULT '{}'::jsonb,
    draft_sections jsonb NOT NULL DEFAULT '[]'::jsonb,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    UNIQUE (organization_id, workspace_id, package_id),
    FOREIGN KEY (organization_id, workspace_id) REFERENCES workweave.workspaces (organization_id, workspace_id)
);

-- Mutable: exit_kt_package_responsibilities
CREATE TABLE workweave.exit_kt_package_responsibilities (
    package_responsibility_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    package_id uuid NOT NULL,
    responsibility_id uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    UNIQUE (organization_id, workspace_id, package_responsibility_id),
    FOREIGN KEY (organization_id, workspace_id) REFERENCES workweave.workspaces (organization_id, workspace_id),
    UNIQUE (organization_id, workspace_id, package_id, responsibility_id)
);

-- Append-only/immutable: exit_kt_package_versions
CREATE TABLE workweave.exit_kt_package_versions (
    package_version_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    package_id uuid NOT NULL,
    content_revision bigint NOT NULL CHECK (content_revision > 0),
    sections jsonb NOT NULL DEFAULT '[]'::jsonb,
    artifact_revision_refs jsonb NOT NULL DEFAULT '[]'::jsonb,
    source_revisions jsonb NOT NULL DEFAULT '{}'::jsonb,
    approved_by uuid NOT NULL,
    approved_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (organization_id, workspace_id, package_version_id),
    FOREIGN KEY (organization_id, workspace_id) REFERENCES workweave.workspaces (organization_id, workspace_id),
    UNIQUE (organization_id, workspace_id, package_id, content_revision),
    UNIQUE (organization_id, workspace_id, package_id, package_version_id)
);

-- Append-only/immutable: successor_receipts
CREATE TABLE workweave.successor_receipts (
    receipt_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    package_version_id uuid NOT NULL,
    successor_employee_id uuid NOT NULL,
    received_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (organization_id, workspace_id, receipt_id),
    FOREIGN KEY (organization_id, workspace_id) REFERENCES workweave.workspaces (organization_id, workspace_id),
    UNIQUE (organization_id, workspace_id, package_version_id, successor_employee_id)
);

-- Mutable: kt_checklist_items
CREATE TABLE workweave.kt_checklist_items (
    checklist_item_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    exit_kt_case_id uuid NOT NULL,
    knowledge_item_id uuid,
    responsibility_id uuid,
    required boolean NOT NULL DEFAULT true,
    status text NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN', 'IN_PROGRESS', 'RESOLVED')),
    evidence_refs jsonb NOT NULL DEFAULT '[]'::jsonb,
    reviewed_by uuid,
    resolved_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    UNIQUE (organization_id, workspace_id, checklist_item_id),
    FOREIGN KEY (organization_id, workspace_id) REFERENCES workweave.workspaces (organization_id, workspace_id),
    CHECK (status <> 'RESOLVED' OR (reviewed_by IS NOT NULL AND resolved_at IS NOT NULL AND jsonb_array_length(evidence_refs) > 0))
);

-- Append-only/immutable: command_receipts
CREATE TABLE workweave.command_receipts (
    command_receipt_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    actor_id uuid NOT NULL,
    command text NOT NULL,
    idempotency_key text NOT NULL,
    payload_hash text NOT NULL,
    status text NOT NULL CHECK (status IN ('COMMITTED', 'FAILED')),
    response jsonb NOT NULL DEFAULT '{}'::jsonb,
    committed_revision bigint CHECK (committed_revision > 0),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (organization_id, workspace_id, command_receipt_id),
    FOREIGN KEY (organization_id, workspace_id) REFERENCES workweave.workspaces (organization_id, workspace_id),
    UNIQUE (organization_id, workspace_id, actor_id, command, idempotency_key)
);

-- Append-only/immutable: audit_events
CREATE TABLE workweave.audit_events (
    audit_event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    actor_id uuid,
    action text NOT NULL,
    resource_type text NOT NULL,
    resource_id uuid,
    resource_revision bigint,
    result text NOT NULL,
    source_refs jsonb NOT NULL DEFAULT '[]'::jsonb,
    request_id uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (organization_id, workspace_id, audit_event_id),
    FOREIGN KEY (organization_id, workspace_id) REFERENCES workweave.workspaces (organization_id, workspace_id)
);

-- Mutable: outbox_events
CREATE TABLE workweave.outbox_events (
    event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    business_operation_id uuid NOT NULL,
    recipient_employee_id uuid NOT NULL,
    resource_type text NOT NULL,
    resource_id uuid NOT NULL,
    resource_revision bigint NOT NULL CHECK (resource_revision > 0),
    event_type text NOT NULL,
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    status text NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'PROCESSING', 'DELIVERED', 'FAILED', 'DEAD')),
    next_attempt_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    attempt_count integer NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    locked_at timestamptz,
    locked_by text,
    delivered_at timestamptz,
    last_error text,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    UNIQUE (organization_id, workspace_id, event_id),
    FOREIGN KEY (organization_id, workspace_id) REFERENCES workweave.workspaces (organization_id, workspace_id),
    UNIQUE (organization_id, workspace_id, business_operation_id, recipient_employee_id, event_type)
);

-- Append-only/immutable: delivery_attempts
CREATE TABLE workweave.delivery_attempts (
    delivery_attempt_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    event_id uuid NOT NULL,
    attempt integer NOT NULL CHECK (attempt > 0),
    result text NOT NULL CHECK (result IN ('SUCCESS', 'RETRYABLE_FAILURE', 'PERMANENT_FAILURE')),
    error text,
    attempted_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (organization_id, workspace_id, delivery_attempt_id),
    FOREIGN KEY (organization_id, workspace_id) REFERENCES workweave.workspaces (organization_id, workspace_id),
    UNIQUE (organization_id, workspace_id, event_id, attempt)
);

-- Mutable: operations
CREATE TABLE workweave.operations (
    operation_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    kind text NOT NULL,
    owner_employee_id uuid NOT NULL,
    stage text NOT NULL CHECK (stage IN ('PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED', 'CANCELLED')),
    result_ref jsonb NOT NULL DEFAULT '{}'::jsonb,
    error text,
    executor_ref text,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    UNIQUE (organization_id, workspace_id, operation_id),
    FOREIGN KEY (organization_id, workspace_id) REFERENCES workweave.workspaces (organization_id, workspace_id)
);

-- Mutable: scenario_catalog
CREATE TABLE workweave.scenario_catalog (
    scenario_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    company_key text NOT NULL,
    name text NOT NULL,
    industry text NOT NULL,
    pack_version text NOT NULL,
    content_hash text NOT NULL,
    synthetic boolean NOT NULL DEFAULT true,
    provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
    status text NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT', 'VALIDATED', 'READY', 'ARCHIVED')),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    UNIQUE (organization_id, workspace_id, scenario_id),
    FOREIGN KEY (organization_id, workspace_id) REFERENCES workweave.workspaces (organization_id, workspace_id),
    UNIQUE (organization_id, workspace_id, company_key, pack_version)
);

-- Mutable: import_runs
CREATE TABLE workweave.import_runs (
    import_run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    scenario_id uuid NOT NULL,
    content_hash text NOT NULL,
    status text NOT NULL DEFAULT 'PLANNED' CHECK (status IN ('PLANNED', 'RUNNING', 'COMPLETE', 'FAILED')),
    cursor jsonb NOT NULL DEFAULT '{}'::jsonb,
    started_at timestamptz,
    completed_at timestamptz,
    error text,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    UNIQUE (organization_id, workspace_id, import_run_id),
    FOREIGN KEY (organization_id, workspace_id) REFERENCES workweave.workspaces (organization_id, workspace_id)
);

-- Mutable: demo_sessions
CREATE TABLE workweave.demo_sessions (
    demo_session_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    scenario_id uuid NOT NULL,
    token_hash text NOT NULL,
    status text NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'EXPIRED', 'REVOKED')),
    expires_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    UNIQUE (organization_id, workspace_id, demo_session_id),
    FOREIGN KEY (organization_id, workspace_id) REFERENCES workweave.workspaces (organization_id, workspace_id),
    UNIQUE (organization_id, workspace_id, token_hash)
);

-- Mutable: demo_persona_grants
CREATE TABLE workweave.demo_persona_grants (
    demo_persona_grant_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    demo_session_id uuid NOT NULL,
    employee_id uuid NOT NULL,
    allowed_actions jsonb NOT NULL DEFAULT '[]'::jsonb,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    UNIQUE (organization_id, workspace_id, demo_persona_grant_id),
    FOREIGN KEY (organization_id, workspace_id) REFERENCES workweave.workspaces (organization_id, workspace_id),
    UNIQUE (organization_id, workspace_id, demo_session_id, employee_id)
);

-- Foreign keys created after ALL tables, including circular version pointers.
ALTER TABLE workweave.teams ADD CONSTRAINT fk_teams_1
    FOREIGN KEY (organization_id, workspace_id, department_id)
    REFERENCES workweave.departments (organization_id, workspace_id, department_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_teams_fk_1 ON workweave.teams (organization_id, workspace_id, department_id);
ALTER TABLE workweave.employees ADD CONSTRAINT fk_employees_2
    FOREIGN KEY (organization_id, workspace_id, role_id)
    REFERENCES workweave.roles (organization_id, workspace_id, role_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_employees_fk_2 ON workweave.employees (organization_id, workspace_id, role_id);
ALTER TABLE workweave.employee_team_memberships ADD CONSTRAINT fk_employee_team_memberships_3
    FOREIGN KEY (organization_id, workspace_id, employee_id)
    REFERENCES workweave.employees (organization_id, workspace_id, employee_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_employee_team_memberships_fk_3 ON workweave.employee_team_memberships (organization_id, workspace_id, employee_id);
ALTER TABLE workweave.employee_team_memberships ADD CONSTRAINT fk_employee_team_memberships_4
    FOREIGN KEY (organization_id, workspace_id, team_id)
    REFERENCES workweave.teams (organization_id, workspace_id, team_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_employee_team_memberships_fk_4 ON workweave.employee_team_memberships (organization_id, workspace_id, team_id);
ALTER TABLE workweave.auth_identity_links ADD CONSTRAINT fk_auth_identity_links_5
    FOREIGN KEY (organization_id, workspace_id, employee_id)
    REFERENCES workweave.employees (organization_id, workspace_id, employee_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_auth_identity_links_fk_5 ON workweave.auth_identity_links (organization_id, workspace_id, employee_id);
ALTER TABLE workweave.permission_grants ADD CONSTRAINT fk_permission_grants_6
    FOREIGN KEY (organization_id, workspace_id, actor_id)
    REFERENCES workweave.employees (organization_id, workspace_id, employee_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_permission_grants_fk_6 ON workweave.permission_grants (organization_id, workspace_id, actor_id);
ALTER TABLE workweave.permission_grants ADD CONSTRAINT fk_permission_grants_7
    FOREIGN KEY (organization_id, workspace_id, granted_by)
    REFERENCES workweave.employees (organization_id, workspace_id, employee_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_permission_grants_fk_7 ON workweave.permission_grants (organization_id, workspace_id, granted_by);
ALTER TABLE workweave.shifts ADD CONSTRAINT fk_shifts_8
    FOREIGN KEY (organization_id, workspace_id, team_id)
    REFERENCES workweave.teams (organization_id, workspace_id, team_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_shifts_fk_8 ON workweave.shifts (organization_id, workspace_id, team_id);
ALTER TABLE workweave.shift_instances ADD CONSTRAINT fk_shift_instances_9
    FOREIGN KEY (organization_id, workspace_id, shift_id)
    REFERENCES workweave.shifts (organization_id, workspace_id, shift_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_shift_instances_fk_9 ON workweave.shift_instances (organization_id, workspace_id, shift_id);
ALTER TABLE workweave.shift_instances ADD CONSTRAINT fk_shift_instances_10
    FOREIGN KEY (organization_id, workspace_id, shift_lead_employee_id)
    REFERENCES workweave.employees (organization_id, workspace_id, employee_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_shift_instances_fk_10 ON workweave.shift_instances (organization_id, workspace_id, shift_lead_employee_id);
ALTER TABLE workweave.shift_instance_memberships ADD CONSTRAINT fk_shift_instance_memberships_11
    FOREIGN KEY (organization_id, workspace_id, shift_instance_id)
    REFERENCES workweave.shift_instances (organization_id, workspace_id, shift_instance_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_shift_instance_memberships_fk_11 ON workweave.shift_instance_memberships (organization_id, workspace_id, shift_instance_id);
ALTER TABLE workweave.shift_instance_memberships ADD CONSTRAINT fk_shift_instance_memberships_12
    FOREIGN KEY (organization_id, workspace_id, employee_id)
    REFERENCES workweave.employees (organization_id, workspace_id, employee_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_shift_instance_memberships_fk_12 ON workweave.shift_instance_memberships (organization_id, workspace_id, employee_id);
ALTER TABLE workweave.employee_availability ADD CONSTRAINT fk_employee_availability_13
    FOREIGN KEY (organization_id, workspace_id, employee_id)
    REFERENCES workweave.employees (organization_id, workspace_id, employee_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_employee_availability_fk_13 ON workweave.employee_availability (organization_id, workspace_id, employee_id);
ALTER TABLE workweave.consent_sessions ADD CONSTRAINT fk_consent_sessions_14
    FOREIGN KEY (organization_id, workspace_id, owner_employee_id)
    REFERENCES workweave.employees (organization_id, workspace_id, employee_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_consent_sessions_fk_14 ON workweave.consent_sessions (organization_id, workspace_id, owner_employee_id);
ALTER TABLE workweave.source_records ADD CONSTRAINT fk_source_records_15
    FOREIGN KEY (organization_id, workspace_id, owner_employee_id)
    REFERENCES workweave.employees (organization_id, workspace_id, employee_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_source_records_fk_15 ON workweave.source_records (organization_id, workspace_id, owner_employee_id);
ALTER TABLE workweave.source_records ADD CONSTRAINT fk_source_records_16
    FOREIGN KEY (organization_id, workspace_id, consent_session_id)
    REFERENCES workweave.consent_sessions (organization_id, workspace_id, consent_session_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_source_records_fk_16 ON workweave.source_records (organization_id, workspace_id, consent_session_id);
ALTER TABLE workweave.knowledge_document_versions ADD CONSTRAINT fk_knowledge_document_versions_17
    FOREIGN KEY (organization_id, workspace_id, document_id)
    REFERENCES workweave.knowledge_documents (organization_id, workspace_id, document_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_knowledge_document_versions_fk_17 ON workweave.knowledge_document_versions (organization_id, workspace_id, document_id);
ALTER TABLE workweave.knowledge_document_versions ADD CONSTRAINT fk_knowledge_document_versions_18
    FOREIGN KEY (organization_id, workspace_id, source_id)
    REFERENCES workweave.source_records (organization_id, workspace_id, source_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_knowledge_document_versions_fk_18 ON workweave.knowledge_document_versions (organization_id, workspace_id, source_id);
ALTER TABLE workweave.knowledge_document_versions ADD CONSTRAINT fk_knowledge_document_versions_19
    FOREIGN KEY (organization_id, workspace_id, approved_by_employee_id)
    REFERENCES workweave.employees (organization_id, workspace_id, employee_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_knowledge_document_versions_fk_19 ON workweave.knowledge_document_versions (organization_id, workspace_id, approved_by_employee_id);
ALTER TABLE workweave.knowledge_chunks ADD CONSTRAINT fk_knowledge_chunks_20
    FOREIGN KEY (organization_id, workspace_id, document_version_id)
    REFERENCES workweave.knowledge_document_versions (organization_id, workspace_id, document_version_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_knowledge_chunks_fk_20 ON workweave.knowledge_chunks (organization_id, workspace_id, document_version_id);
ALTER TABLE workweave.knowledge_chunks ADD CONSTRAINT fk_knowledge_chunks_21
    FOREIGN KEY (organization_id, workspace_id, source_id)
    REFERENCES workweave.source_records (organization_id, workspace_id, source_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_knowledge_chunks_fk_21 ON workweave.knowledge_chunks (organization_id, workspace_id, source_id);
ALTER TABLE workweave.knowledge_mappings ADD CONSTRAINT fk_knowledge_mappings_22
    FOREIGN KEY (organization_id, workspace_id, document_id)
    REFERENCES workweave.knowledge_documents (organization_id, workspace_id, document_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_knowledge_mappings_fk_22 ON workweave.knowledge_mappings (organization_id, workspace_id, document_id);
ALTER TABLE workweave.memory_drafts ADD CONSTRAINT fk_memory_drafts_23
    FOREIGN KEY (organization_id, workspace_id, owner_employee_id)
    REFERENCES workweave.employees (organization_id, workspace_id, employee_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_memory_drafts_fk_23 ON workweave.memory_drafts (organization_id, workspace_id, owner_employee_id);
ALTER TABLE workweave.memory_drafts ADD CONSTRAINT fk_memory_drafts_24
    FOREIGN KEY (organization_id, workspace_id, consent_session_id)
    REFERENCES workweave.consent_sessions (organization_id, workspace_id, consent_session_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_memory_drafts_fk_24 ON workweave.memory_drafts (organization_id, workspace_id, consent_session_id);
ALTER TABLE workweave.memory_records ADD CONSTRAINT fk_memory_records_25
    FOREIGN KEY (organization_id, workspace_id, originating_draft_id)
    REFERENCES workweave.memory_drafts (organization_id, workspace_id, draft_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_memory_records_fk_25 ON workweave.memory_records (organization_id, workspace_id, originating_draft_id);
ALTER TABLE workweave.memory_records ADD CONSTRAINT fk_memory_records_26
    FOREIGN KEY (organization_id, workspace_id, approved_by)
    REFERENCES workweave.employees (organization_id, workspace_id, employee_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_memory_records_fk_26 ON workweave.memory_records (organization_id, workspace_id, approved_by);
ALTER TABLE workweave.role_competency_requirements ADD CONSTRAINT fk_role_competency_requirements_27
    FOREIGN KEY (organization_id, workspace_id, role_id)
    REFERENCES workweave.roles (organization_id, workspace_id, role_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_role_competency_requirements_fk_27 ON workweave.role_competency_requirements (organization_id, workspace_id, role_id);
ALTER TABLE workweave.role_competency_requirements ADD CONSTRAINT fk_role_competency_requirements_28
    FOREIGN KEY (organization_id, workspace_id, competency_id)
    REFERENCES workweave.competencies (organization_id, workspace_id, competency_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_role_competency_requirements_fk_28 ON workweave.role_competency_requirements (organization_id, workspace_id, competency_id);
ALTER TABLE workweave.employee_competency_evidence ADD CONSTRAINT fk_employee_competency_evidence_29
    FOREIGN KEY (organization_id, workspace_id, employee_id)
    REFERENCES workweave.employees (organization_id, workspace_id, employee_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_employee_competency_evidence_fk_29 ON workweave.employee_competency_evidence (organization_id, workspace_id, employee_id);
ALTER TABLE workweave.employee_competency_evidence ADD CONSTRAINT fk_employee_competency_evidence_30
    FOREIGN KEY (organization_id, workspace_id, competency_id)
    REFERENCES workweave.competencies (organization_id, workspace_id, competency_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_employee_competency_evidence_fk_30 ON workweave.employee_competency_evidence (organization_id, workspace_id, competency_id);
ALTER TABLE workweave.employee_competency_evidence ADD CONSTRAINT fk_employee_competency_evidence_31
    FOREIGN KEY (organization_id, workspace_id, validated_by)
    REFERENCES workweave.employees (organization_id, workspace_id, employee_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_employee_competency_evidence_fk_31 ON workweave.employee_competency_evidence (organization_id, workspace_id, validated_by);
ALTER TABLE workweave.employee_competency_state ADD CONSTRAINT fk_employee_competency_state_32
    FOREIGN KEY (organization_id, workspace_id, employee_id)
    REFERENCES workweave.employees (organization_id, workspace_id, employee_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_employee_competency_state_fk_32 ON workweave.employee_competency_state (organization_id, workspace_id, employee_id);
ALTER TABLE workweave.employee_competency_state ADD CONSTRAINT fk_employee_competency_state_33
    FOREIGN KEY (organization_id, workspace_id, competency_id)
    REFERENCES workweave.competencies (organization_id, workspace_id, competency_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_employee_competency_state_fk_33 ON workweave.employee_competency_state (organization_id, workspace_id, competency_id);
ALTER TABLE workweave.curriculum_assignments ADD CONSTRAINT fk_curriculum_assignments_34
    FOREIGN KEY (organization_id, workspace_id, curriculum_id)
    REFERENCES workweave.curricula (organization_id, workspace_id, curriculum_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_curriculum_assignments_fk_34 ON workweave.curriculum_assignments (organization_id, workspace_id, curriculum_id);
ALTER TABLE workweave.curriculum_assignments ADD CONSTRAINT fk_curriculum_assignments_35
    FOREIGN KEY (organization_id, workspace_id, employee_id)
    REFERENCES workweave.employees (organization_id, workspace_id, employee_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_curriculum_assignments_fk_35 ON workweave.curriculum_assignments (organization_id, workspace_id, employee_id);
ALTER TABLE workweave.curriculum_assignments ADD CONSTRAINT fk_curriculum_assignments_36
    FOREIGN KEY (organization_id, workspace_id, role_id)
    REFERENCES workweave.roles (organization_id, workspace_id, role_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_curriculum_assignments_fk_36 ON workweave.curriculum_assignments (organization_id, workspace_id, role_id);
ALTER TABLE workweave.curriculum_assignments ADD CONSTRAINT fk_curriculum_assignments_37
    FOREIGN KEY (organization_id, workspace_id, assigned_by_employee_id)
    REFERENCES workweave.employees (organization_id, workspace_id, employee_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_curriculum_assignments_fk_37 ON workweave.curriculum_assignments (organization_id, workspace_id, assigned_by_employee_id);
ALTER TABLE workweave.learning_assignments ADD CONSTRAINT fk_learning_assignments_38
    FOREIGN KEY (organization_id, workspace_id, employee_id)
    REFERENCES workweave.employees (organization_id, workspace_id, employee_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_learning_assignments_fk_38 ON workweave.learning_assignments (organization_id, workspace_id, employee_id);
ALTER TABLE workweave.learning_assignments ADD CONSTRAINT fk_learning_assignments_39
    FOREIGN KEY (organization_id, workspace_id, curriculum_id)
    REFERENCES workweave.curricula (organization_id, workspace_id, curriculum_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_learning_assignments_fk_39 ON workweave.learning_assignments (organization_id, workspace_id, curriculum_id);
ALTER TABLE workweave.curriculum_topics ADD CONSTRAINT fk_curriculum_topics_40
    FOREIGN KEY (organization_id, workspace_id, curriculum_id)
    REFERENCES workweave.curricula (organization_id, workspace_id, curriculum_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_curriculum_topics_fk_40 ON workweave.curriculum_topics (organization_id, workspace_id, curriculum_id);
ALTER TABLE workweave.curriculum_subtopics ADD CONSTRAINT fk_curriculum_subtopics_41
    FOREIGN KEY (organization_id, workspace_id, topic_id)
    REFERENCES workweave.curriculum_topics (organization_id, workspace_id, topic_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_curriculum_subtopics_fk_41 ON workweave.curriculum_subtopics (organization_id, workspace_id, topic_id);
ALTER TABLE workweave.curriculum_prerequisites ADD CONSTRAINT fk_curriculum_prerequisites_42
    FOREIGN KEY (organization_id, workspace_id, subtopic_id)
    REFERENCES workweave.curriculum_subtopics (organization_id, workspace_id, subtopic_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_curriculum_prerequisites_fk_42 ON workweave.curriculum_prerequisites (organization_id, workspace_id, subtopic_id);
ALTER TABLE workweave.curriculum_prerequisites ADD CONSTRAINT fk_curriculum_prerequisites_43
    FOREIGN KEY (organization_id, workspace_id, prerequisite_subtopic_id)
    REFERENCES workweave.curriculum_subtopics (organization_id, workspace_id, subtopic_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_curriculum_prerequisites_fk_43 ON workweave.curriculum_prerequisites (organization_id, workspace_id, prerequisite_subtopic_id);
ALTER TABLE workweave.learning_objectives ADD CONSTRAINT fk_learning_objectives_44
    FOREIGN KEY (organization_id, workspace_id, subtopic_id)
    REFERENCES workweave.curriculum_subtopics (organization_id, workspace_id, subtopic_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_learning_objectives_fk_44 ON workweave.learning_objectives (organization_id, workspace_id, subtopic_id);
ALTER TABLE workweave.learning_objectives ADD CONSTRAINT fk_learning_objectives_45
    FOREIGN KEY (organization_id, workspace_id, competency_id)
    REFERENCES workweave.competencies (organization_id, workspace_id, competency_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_learning_objectives_fk_45 ON workweave.learning_objectives (organization_id, workspace_id, competency_id);
ALTER TABLE workweave.employee_learning_progress ADD CONSTRAINT fk_employee_learning_progress_46
    FOREIGN KEY (organization_id, workspace_id, employee_id)
    REFERENCES workweave.employees (organization_id, workspace_id, employee_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_employee_learning_progress_fk_46 ON workweave.employee_learning_progress (organization_id, workspace_id, employee_id);
ALTER TABLE workweave.employee_learning_progress ADD CONSTRAINT fk_employee_learning_progress_47
    FOREIGN KEY (organization_id, workspace_id, subtopic_id)
    REFERENCES workweave.curriculum_subtopics (organization_id, workspace_id, subtopic_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_employee_learning_progress_fk_47 ON workweave.employee_learning_progress (organization_id, workspace_id, subtopic_id);
ALTER TABLE workweave.learning_sessions ADD CONSTRAINT fk_learning_sessions_48
    FOREIGN KEY (organization_id, workspace_id, employee_id)
    REFERENCES workweave.employees (organization_id, workspace_id, employee_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_learning_sessions_fk_48 ON workweave.learning_sessions (organization_id, workspace_id, employee_id);
ALTER TABLE workweave.learning_sessions ADD CONSTRAINT fk_learning_sessions_49
    FOREIGN KEY (organization_id, workspace_id, curriculum_id)
    REFERENCES workweave.curricula (organization_id, workspace_id, curriculum_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_learning_sessions_fk_49 ON workweave.learning_sessions (organization_id, workspace_id, curriculum_id);
ALTER TABLE workweave.learning_turns ADD CONSTRAINT fk_learning_turns_50
    FOREIGN KEY (organization_id, workspace_id, learning_session_id)
    REFERENCES workweave.learning_sessions (organization_id, workspace_id, learning_session_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_learning_turns_fk_50 ON workweave.learning_turns (organization_id, workspace_id, learning_session_id);
ALTER TABLE workweave.employee_learning_events ADD CONSTRAINT fk_employee_learning_events_51
    FOREIGN KEY (organization_id, workspace_id, topic_id)
    REFERENCES workweave.curriculum_topics (organization_id, workspace_id, topic_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_employee_learning_events_fk_51 ON workweave.employee_learning_events (organization_id, workspace_id, topic_id);
ALTER TABLE workweave.employee_learning_events ADD CONSTRAINT fk_employee_learning_events_52
    FOREIGN KEY (organization_id, workspace_id, subtopic_id)
    REFERENCES workweave.curriculum_subtopics (organization_id, workspace_id, subtopic_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_employee_learning_events_fk_52 ON workweave.employee_learning_events (organization_id, workspace_id, subtopic_id);
ALTER TABLE workweave.employee_learning_events ADD CONSTRAINT fk_employee_learning_events_53
    FOREIGN KEY (organization_id, workspace_id, objective_id)
    REFERENCES workweave.learning_objectives (organization_id, workspace_id, objective_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_employee_learning_events_fk_53 ON workweave.employee_learning_events (organization_id, workspace_id, objective_id);
ALTER TABLE workweave.learning_assessment_attempts ADD CONSTRAINT fk_learning_assessment_attempts_54
    FOREIGN KEY (organization_id, workspace_id, turn_id)
    REFERENCES workweave.learning_turns (organization_id, workspace_id, turn_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_learning_assessment_attempts_fk_54 ON workweave.learning_assessment_attempts (organization_id, workspace_id, turn_id);
ALTER TABLE workweave.learning_assessment_attempts ADD CONSTRAINT fk_learning_assessment_attempts_55
    FOREIGN KEY (organization_id, workspace_id, objective_id)
    REFERENCES workweave.learning_objectives (organization_id, workspace_id, objective_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_learning_assessment_attempts_fk_55 ON workweave.learning_assessment_attempts (organization_id, workspace_id, objective_id);
ALTER TABLE workweave.objective_evidence ADD CONSTRAINT fk_objective_evidence_56
    FOREIGN KEY (organization_id, workspace_id, learning_assignment_id)
    REFERENCES workweave.learning_assignments (organization_id, workspace_id, learning_assignment_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_objective_evidence_fk_56 ON workweave.objective_evidence (organization_id, workspace_id, learning_assignment_id);
ALTER TABLE workweave.objective_evidence ADD CONSTRAINT fk_objective_evidence_57
    FOREIGN KEY (organization_id, workspace_id, objective_id)
    REFERENCES workweave.learning_objectives (organization_id, workspace_id, objective_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_objective_evidence_fk_57 ON workweave.objective_evidence (organization_id, workspace_id, objective_id);
ALTER TABLE workweave.work_sessions ADD CONSTRAINT fk_work_sessions_58
    FOREIGN KEY (organization_id, workspace_id, employee_id)
    REFERENCES workweave.employees (organization_id, workspace_id, employee_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_work_sessions_fk_58 ON workweave.work_sessions (organization_id, workspace_id, employee_id);
ALTER TABLE workweave.work_sessions ADD CONSTRAINT fk_work_sessions_59
    FOREIGN KEY (organization_id, workspace_id, shift_instance_id)
    REFERENCES workweave.shift_instances (organization_id, workspace_id, shift_instance_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_work_sessions_fk_59 ON workweave.work_sessions (organization_id, workspace_id, shift_instance_id);
ALTER TABLE workweave.work_item_competency_requirements ADD CONSTRAINT fk_work_item_competency_requirements_60
    FOREIGN KEY (organization_id, workspace_id, work_item_id)
    REFERENCES workweave.work_items (organization_id, workspace_id, work_item_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_work_item_competency_requirements_fk_60 ON workweave.work_item_competency_requirements (organization_id, workspace_id, work_item_id);
ALTER TABLE workweave.work_item_competency_requirements ADD CONSTRAINT fk_work_item_competency_requirements_61
    FOREIGN KEY (organization_id, workspace_id, competency_id)
    REFERENCES workweave.competencies (organization_id, workspace_id, competency_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_work_item_competency_requirements_fk_61 ON workweave.work_item_competency_requirements (organization_id, workspace_id, competency_id);
ALTER TABLE workweave.delegation_proposals ADD CONSTRAINT fk_delegation_proposals_62
    FOREIGN KEY (organization_id, workspace_id, shift_instance_id)
    REFERENCES workweave.shift_instances (organization_id, workspace_id, shift_instance_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_delegation_proposals_fk_62 ON workweave.delegation_proposals (organization_id, workspace_id, shift_instance_id);
ALTER TABLE workweave.delegation_proposals ADD CONSTRAINT fk_delegation_proposals_63
    FOREIGN KEY (organization_id, workspace_id, team_id)
    REFERENCES workweave.teams (organization_id, workspace_id, team_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_delegation_proposals_fk_63 ON workweave.delegation_proposals (organization_id, workspace_id, team_id);
ALTER TABLE workweave.delegation_proposals ADD CONSTRAINT fk_delegation_proposals_64
    FOREIGN KEY (organization_id, workspace_id, created_by)
    REFERENCES workweave.employees (organization_id, workspace_id, employee_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_delegation_proposals_fk_64 ON workweave.delegation_proposals (organization_id, workspace_id, created_by);
ALTER TABLE workweave.delegation_proposals ADD CONSTRAINT fk_delegation_proposals_65
    FOREIGN KEY (organization_id, workspace_id, confirmed_by_employee_id)
    REFERENCES workweave.employees (organization_id, workspace_id, employee_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_delegation_proposals_fk_65 ON workweave.delegation_proposals (organization_id, workspace_id, confirmed_by_employee_id);
ALTER TABLE workweave.delegation_proposal_items ADD CONSTRAINT fk_delegation_proposal_items_66
    FOREIGN KEY (organization_id, workspace_id, delegation_proposal_id)
    REFERENCES workweave.delegation_proposals (organization_id, workspace_id, delegation_proposal_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_delegation_proposal_items_fk_66 ON workweave.delegation_proposal_items (organization_id, workspace_id, delegation_proposal_id);
ALTER TABLE workweave.delegation_proposal_items ADD CONSTRAINT fk_delegation_proposal_items_67
    FOREIGN KEY (organization_id, workspace_id, work_item_id)
    REFERENCES workweave.work_items (organization_id, workspace_id, work_item_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_delegation_proposal_items_fk_67 ON workweave.delegation_proposal_items (organization_id, workspace_id, work_item_id);
ALTER TABLE workweave.delegation_proposal_items ADD CONSTRAINT fk_delegation_proposal_items_68
    FOREIGN KEY (organization_id, workspace_id, recommended_employee_id)
    REFERENCES workweave.employees (organization_id, workspace_id, employee_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_delegation_proposal_items_fk_68 ON workweave.delegation_proposal_items (organization_id, workspace_id, recommended_employee_id);
ALTER TABLE workweave.delegation_proposal_items ADD CONSTRAINT fk_delegation_proposal_items_69
    FOREIGN KEY (organization_id, workspace_id, final_employee_id)
    REFERENCES workweave.employees (organization_id, workspace_id, employee_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_delegation_proposal_items_fk_69 ON workweave.delegation_proposal_items (organization_id, workspace_id, final_employee_id);
ALTER TABLE workweave.work_item_assignments ADD CONSTRAINT fk_work_item_assignments_70
    FOREIGN KEY (organization_id, workspace_id, work_item_id)
    REFERENCES workweave.work_items (organization_id, workspace_id, work_item_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_work_item_assignments_fk_70 ON workweave.work_item_assignments (organization_id, workspace_id, work_item_id);
ALTER TABLE workweave.work_item_assignments ADD CONSTRAINT fk_work_item_assignments_71
    FOREIGN KEY (organization_id, workspace_id, employee_id)
    REFERENCES workweave.employees (organization_id, workspace_id, employee_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_work_item_assignments_fk_71 ON workweave.work_item_assignments (organization_id, workspace_id, employee_id);
ALTER TABLE workweave.work_item_assignments ADD CONSTRAINT fk_work_item_assignments_72
    FOREIGN KEY (organization_id, workspace_id, assigned_by_employee_id)
    REFERENCES workweave.employees (organization_id, workspace_id, employee_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_work_item_assignments_fk_72 ON workweave.work_item_assignments (organization_id, workspace_id, assigned_by_employee_id);
ALTER TABLE workweave.work_events ADD CONSTRAINT fk_work_events_73
    FOREIGN KEY (organization_id, workspace_id, work_item_id)
    REFERENCES workweave.work_items (organization_id, workspace_id, work_item_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_work_events_fk_73 ON workweave.work_events (organization_id, workspace_id, work_item_id);
ALTER TABLE workweave.work_events ADD CONSTRAINT fk_work_events_74
    FOREIGN KEY (organization_id, workspace_id, employee_id)
    REFERENCES workweave.employees (organization_id, workspace_id, employee_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_work_events_fk_74 ON workweave.work_events (organization_id, workspace_id, employee_id);
ALTER TABLE workweave.work_events ADD CONSTRAINT fk_work_events_75
    FOREIGN KEY (organization_id, workspace_id, shift_instance_id)
    REFERENCES workweave.shift_instances (organization_id, workspace_id, shift_instance_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_work_events_fk_75 ON workweave.work_events (organization_id, workspace_id, shift_instance_id);
ALTER TABLE workweave.employee_work_state ADD CONSTRAINT fk_employee_work_state_76
    FOREIGN KEY (organization_id, workspace_id, employee_id)
    REFERENCES workweave.employees (organization_id, workspace_id, employee_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_employee_work_state_fk_76 ON workweave.employee_work_state (organization_id, workspace_id, employee_id);
ALTER TABLE workweave.employee_work_state ADD CONSTRAINT fk_employee_work_state_77
    FOREIGN KEY (organization_id, workspace_id, shift_instance_id)
    REFERENCES workweave.shift_instances (organization_id, workspace_id, shift_instance_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_employee_work_state_fk_77 ON workweave.employee_work_state (organization_id, workspace_id, shift_instance_id);
ALTER TABLE workweave.productivity_observations ADD CONSTRAINT fk_productivity_observations_78
    FOREIGN KEY (organization_id, workspace_id, employee_id)
    REFERENCES workweave.employees (organization_id, workspace_id, employee_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_productivity_observations_fk_78 ON workweave.productivity_observations (organization_id, workspace_id, employee_id);
ALTER TABLE workweave.productivity_observations ADD CONSTRAINT fk_productivity_observations_79
    FOREIGN KEY (organization_id, workspace_id, shift_instance_id)
    REFERENCES workweave.shift_instances (organization_id, workspace_id, shift_instance_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_productivity_observations_fk_79 ON workweave.productivity_observations (organization_id, workspace_id, shift_instance_id);
ALTER TABLE workweave.handover_templates ADD CONSTRAINT fk_handover_templates_80
    FOREIGN KEY (organization_id, workspace_id, team_id)
    REFERENCES workweave.teams (organization_id, workspace_id, team_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_handover_templates_fk_80 ON workweave.handover_templates (organization_id, workspace_id, team_id);
ALTER TABLE workweave.handover_template_versions ADD CONSTRAINT fk_handover_template_versions_81
    FOREIGN KEY (organization_id, workspace_id, template_id)
    REFERENCES workweave.handover_templates (organization_id, workspace_id, template_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_handover_template_versions_fk_81 ON workweave.handover_template_versions (organization_id, workspace_id, template_id);
ALTER TABLE workweave.handover_template_sections ADD CONSTRAINT fk_handover_template_sections_82
    FOREIGN KEY (organization_id, workspace_id, template_version_id)
    REFERENCES workweave.handover_template_versions (organization_id, workspace_id, template_version_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_handover_template_sections_fk_82 ON workweave.handover_template_sections (organization_id, workspace_id, template_version_id);
ALTER TABLE workweave.shift_handovers ADD CONSTRAINT fk_shift_handovers_83
    FOREIGN KEY (organization_id, workspace_id, source_shift_instance_id)
    REFERENCES workweave.shift_instances (organization_id, workspace_id, shift_instance_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_shift_handovers_fk_83 ON workweave.shift_handovers (organization_id, workspace_id, source_shift_instance_id);
ALTER TABLE workweave.shift_handovers ADD CONSTRAINT fk_shift_handovers_84
    FOREIGN KEY (organization_id, workspace_id, target_shift_instance_id)
    REFERENCES workweave.shift_instances (organization_id, workspace_id, shift_instance_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_shift_handovers_fk_84 ON workweave.shift_handovers (organization_id, workspace_id, target_shift_instance_id);
ALTER TABLE workweave.shift_handovers ADD CONSTRAINT fk_shift_handovers_85
    FOREIGN KEY (organization_id, workspace_id, template_version_id)
    REFERENCES workweave.handover_template_versions (organization_id, workspace_id, template_version_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_shift_handovers_fk_85 ON workweave.shift_handovers (organization_id, workspace_id, template_version_id);
ALTER TABLE workweave.shift_handovers ADD CONSTRAINT fk_shift_handovers_86
    FOREIGN KEY (organization_id, workspace_id, created_by_employee_id)
    REFERENCES workweave.employees (organization_id, workspace_id, employee_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_shift_handovers_fk_86 ON workweave.shift_handovers (organization_id, workspace_id, created_by_employee_id);
ALTER TABLE workweave.shift_handovers ADD CONSTRAINT fk_shift_handovers_87
    FOREIGN KEY (organization_id, workspace_id, published_by_employee_id)
    REFERENCES workweave.employees (organization_id, workspace_id, employee_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_shift_handovers_fk_87 ON workweave.shift_handovers (organization_id, workspace_id, published_by_employee_id);
ALTER TABLE workweave.handover_publications ADD CONSTRAINT fk_handover_publications_88
    FOREIGN KEY (organization_id, workspace_id, handover_id)
    REFERENCES workweave.shift_handovers (organization_id, workspace_id, handover_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_handover_publications_fk_88 ON workweave.handover_publications (organization_id, workspace_id, handover_id);
ALTER TABLE workweave.handover_publications ADD CONSTRAINT fk_handover_publications_89
    FOREIGN KEY (organization_id, workspace_id, template_version_id)
    REFERENCES workweave.handover_template_versions (organization_id, workspace_id, template_version_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_handover_publications_fk_89 ON workweave.handover_publications (organization_id, workspace_id, template_version_id);
ALTER TABLE workweave.handover_publications ADD CONSTRAINT fk_handover_publications_90
    FOREIGN KEY (organization_id, workspace_id, published_by)
    REFERENCES workweave.employees (organization_id, workspace_id, employee_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_handover_publications_fk_90 ON workweave.handover_publications (organization_id, workspace_id, published_by);
ALTER TABLE workweave.handover_items ADD CONSTRAINT fk_handover_items_91
    FOREIGN KEY (organization_id, workspace_id, work_item_id)
    REFERENCES workweave.work_items (organization_id, workspace_id, work_item_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_handover_items_fk_91 ON workweave.handover_items (organization_id, workspace_id, work_item_id);
ALTER TABLE workweave.handover_items ADD CONSTRAINT fk_handover_items_92
    FOREIGN KEY (organization_id, workspace_id, originating_shift_instance_id)
    REFERENCES workweave.shift_instances (organization_id, workspace_id, shift_instance_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_handover_items_fk_92 ON workweave.handover_items (organization_id, workspace_id, originating_shift_instance_id);
ALTER TABLE workweave.handover_items ADD CONSTRAINT fk_handover_items_93
    FOREIGN KEY (organization_id, workspace_id, originating_employee_id)
    REFERENCES workweave.employees (organization_id, workspace_id, employee_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_handover_items_fk_93 ON workweave.handover_items (organization_id, workspace_id, originating_employee_id);
ALTER TABLE workweave.handover_items ADD CONSTRAINT fk_handover_items_94
    FOREIGN KEY (organization_id, workspace_id, current_owner_shift_instance_id)
    REFERENCES workweave.shift_instances (organization_id, workspace_id, shift_instance_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_handover_items_fk_94 ON workweave.handover_items (organization_id, workspace_id, current_owner_shift_instance_id);
ALTER TABLE workweave.handover_entries ADD CONSTRAINT fk_handover_entries_95
    FOREIGN KEY (organization_id, workspace_id, publication_id)
    REFERENCES workweave.handover_publications (organization_id, workspace_id, publication_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_handover_entries_fk_95 ON workweave.handover_entries (organization_id, workspace_id, publication_id);
ALTER TABLE workweave.handover_entries ADD CONSTRAINT fk_handover_entries_96
    FOREIGN KEY (organization_id, workspace_id, handover_item_id)
    REFERENCES workweave.handover_items (organization_id, workspace_id, handover_item_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_handover_entries_fk_96 ON workweave.handover_entries (organization_id, workspace_id, handover_item_id);
ALTER TABLE workweave.handover_entries ADD CONSTRAINT fk_handover_entries_97
    FOREIGN KEY (organization_id, workspace_id, section_id)
    REFERENCES workweave.handover_template_sections (organization_id, workspace_id, section_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_handover_entries_fk_97 ON workweave.handover_entries (organization_id, workspace_id, section_id);
ALTER TABLE workweave.handover_suggestions ADD CONSTRAINT fk_handover_suggestions_98
    FOREIGN KEY (organization_id, workspace_id, handover_id)
    REFERENCES workweave.shift_handovers (organization_id, workspace_id, handover_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_handover_suggestions_fk_98 ON workweave.handover_suggestions (organization_id, workspace_id, handover_id);
ALTER TABLE workweave.handover_suggestions ADD CONSTRAINT fk_handover_suggestions_99
    FOREIGN KEY (organization_id, workspace_id, handover_item_id)
    REFERENCES workweave.handover_items (organization_id, workspace_id, handover_item_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_handover_suggestions_fk_99 ON workweave.handover_suggestions (organization_id, workspace_id, handover_item_id);
ALTER TABLE workweave.handover_suggestions ADD CONSTRAINT fk_handover_suggestions_100
    FOREIGN KEY (organization_id, workspace_id, reviewed_by_employee_id)
    REFERENCES workweave.employees (organization_id, workspace_id, employee_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_handover_suggestions_fk_100 ON workweave.handover_suggestions (organization_id, workspace_id, reviewed_by_employee_id);
ALTER TABLE workweave.handover_item_sources ADD CONSTRAINT fk_handover_item_sources_101
    FOREIGN KEY (organization_id, workspace_id, handover_item_id)
    REFERENCES workweave.handover_items (organization_id, workspace_id, handover_item_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_handover_item_sources_fk_101 ON workweave.handover_item_sources (organization_id, workspace_id, handover_item_id);
ALTER TABLE workweave.handover_item_sources ADD CONSTRAINT fk_handover_item_sources_102
    FOREIGN KEY (organization_id, workspace_id, suggestion_id)
    REFERENCES workweave.handover_suggestions (organization_id, workspace_id, suggestion_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_handover_item_sources_fk_102 ON workweave.handover_item_sources (organization_id, workspace_id, suggestion_id);
ALTER TABLE workweave.handover_item_sources ADD CONSTRAINT fk_handover_item_sources_103
    FOREIGN KEY (organization_id, workspace_id, confirmed_by_employee_id)
    REFERENCES workweave.employees (organization_id, workspace_id, employee_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_handover_item_sources_fk_103 ON workweave.handover_item_sources (organization_id, workspace_id, confirmed_by_employee_id);
ALTER TABLE workweave.handover_completion_cycles ADD CONSTRAINT fk_handover_completion_cycles_104
    FOREIGN KEY (organization_id, workspace_id, handover_item_id)
    REFERENCES workweave.handover_items (organization_id, workspace_id, handover_item_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_handover_completion_cycles_fk_104 ON workweave.handover_completion_cycles (organization_id, workspace_id, handover_item_id);
ALTER TABLE workweave.handover_completion_cycles ADD CONSTRAINT fk_handover_completion_cycles_105
    FOREIGN KEY (organization_id, workspace_id, completed_in_shift_instance_id)
    REFERENCES workweave.shift_instances (organization_id, workspace_id, shift_instance_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_handover_completion_cycles_fk_105 ON workweave.handover_completion_cycles (organization_id, workspace_id, completed_in_shift_instance_id);
ALTER TABLE workweave.handover_completion_cycles ADD CONSTRAINT fk_handover_completion_cycles_106
    FOREIGN KEY (organization_id, workspace_id, confirmed_by_employee_id)
    REFERENCES workweave.employees (organization_id, workspace_id, employee_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_handover_completion_cycles_fk_106 ON workweave.handover_completion_cycles (organization_id, workspace_id, confirmed_by_employee_id);
ALTER TABLE workweave.handover_completion_cycles ADD CONSTRAINT fk_handover_completion_cycles_107
    FOREIGN KEY (organization_id, workspace_id, completion_event_id)
    REFERENCES workweave.work_events (organization_id, workspace_id, work_event_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_handover_completion_cycles_fk_107 ON workweave.handover_completion_cycles (organization_id, workspace_id, completion_event_id);
ALTER TABLE workweave.handover_item_events ADD CONSTRAINT fk_handover_item_events_108
    FOREIGN KEY (organization_id, workspace_id, handover_item_id)
    REFERENCES workweave.handover_items (organization_id, workspace_id, handover_item_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_handover_item_events_fk_108 ON workweave.handover_item_events (organization_id, workspace_id, handover_item_id);
ALTER TABLE workweave.handover_item_events ADD CONSTRAINT fk_handover_item_events_109
    FOREIGN KEY (organization_id, workspace_id, employee_id)
    REFERENCES workweave.employees (organization_id, workspace_id, employee_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_handover_item_events_fk_109 ON workweave.handover_item_events (organization_id, workspace_id, employee_id);
ALTER TABLE workweave.handover_item_events ADD CONSTRAINT fk_handover_item_events_110
    FOREIGN KEY (organization_id, workspace_id, shift_instance_id)
    REFERENCES workweave.shift_instances (organization_id, workspace_id, shift_instance_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_handover_item_events_fk_110 ON workweave.handover_item_events (organization_id, workspace_id, shift_instance_id);
ALTER TABLE workweave.handover_acknowledgements ADD CONSTRAINT fk_handover_acknowledgements_111
    FOREIGN KEY (organization_id, workspace_id, requested_from_shift_instance_id)
    REFERENCES workweave.shift_instances (organization_id, workspace_id, shift_instance_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_handover_acknowledgements_fk_111 ON workweave.handover_acknowledgements (organization_id, workspace_id, requested_from_shift_instance_id);
ALTER TABLE workweave.handover_acknowledgements ADD CONSTRAINT fk_handover_acknowledgements_112
    FOREIGN KEY (organization_id, workspace_id, requested_from_employee_id)
    REFERENCES workweave.employees (organization_id, workspace_id, employee_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_handover_acknowledgements_fk_112 ON workweave.handover_acknowledgements (organization_id, workspace_id, requested_from_employee_id);
ALTER TABLE workweave.handover_receipts ADD CONSTRAINT fk_handover_receipts_113
    FOREIGN KEY (organization_id, workspace_id, publication_id)
    REFERENCES workweave.handover_publications (organization_id, workspace_id, publication_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_handover_receipts_fk_113 ON workweave.handover_receipts (organization_id, workspace_id, publication_id);
ALTER TABLE workweave.handover_receipts ADD CONSTRAINT fk_handover_receipts_114
    FOREIGN KEY (organization_id, workspace_id, recipient_shift_instance_id)
    REFERENCES workweave.shift_instances (organization_id, workspace_id, shift_instance_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_handover_receipts_fk_114 ON workweave.handover_receipts (organization_id, workspace_id, recipient_shift_instance_id);
ALTER TABLE workweave.handover_receipts ADD CONSTRAINT fk_handover_receipts_115
    FOREIGN KEY (organization_id, workspace_id, recipient_employee_id)
    REFERENCES workweave.employees (organization_id, workspace_id, employee_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_handover_receipts_fk_115 ON workweave.handover_receipts (organization_id, workspace_id, recipient_employee_id);
ALTER TABLE workweave.exit_kt_cases ADD CONSTRAINT fk_exit_kt_cases_116
    FOREIGN KEY (organization_id, workspace_id, employee_id)
    REFERENCES workweave.employees (organization_id, workspace_id, employee_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_exit_kt_cases_fk_116 ON workweave.exit_kt_cases (organization_id, workspace_id, employee_id);
ALTER TABLE workweave.exit_kt_cases ADD CONSTRAINT fk_exit_kt_cases_117
    FOREIGN KEY (organization_id, workspace_id, initiated_by_employee_id)
    REFERENCES workweave.employees (organization_id, workspace_id, employee_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_exit_kt_cases_fk_117 ON workweave.exit_kt_cases (organization_id, workspace_id, initiated_by_employee_id);
ALTER TABLE workweave.exit_kt_cases ADD CONSTRAINT fk_exit_kt_cases_118
    FOREIGN KEY (organization_id, workspace_id, reviewer_employee_id)
    REFERENCES workweave.employees (organization_id, workspace_id, employee_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_exit_kt_cases_fk_118 ON workweave.exit_kt_cases (organization_id, workspace_id, reviewer_employee_id);
ALTER TABLE workweave.exit_kt_knowledge_items ADD CONSTRAINT fk_exit_kt_knowledge_items_119
    FOREIGN KEY (organization_id, workspace_id, exit_kt_case_id)
    REFERENCES workweave.exit_kt_cases (organization_id, workspace_id, exit_kt_case_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_exit_kt_knowledge_items_fk_119 ON workweave.exit_kt_knowledge_items (organization_id, workspace_id, exit_kt_case_id);
ALTER TABLE workweave.exit_kt_knowledge_items ADD CONSTRAINT fk_exit_kt_knowledge_items_120
    FOREIGN KEY (organization_id, workspace_id, competency_id)
    REFERENCES workweave.competencies (organization_id, workspace_id, competency_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_exit_kt_knowledge_items_fk_120 ON workweave.exit_kt_knowledge_items (organization_id, workspace_id, competency_id);
ALTER TABLE workweave.exit_kt_sources ADD CONSTRAINT fk_exit_kt_sources_121
    FOREIGN KEY (organization_id, workspace_id, kt_item_id)
    REFERENCES workweave.exit_kt_knowledge_items (organization_id, workspace_id, kt_item_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_exit_kt_sources_fk_121 ON workweave.exit_kt_sources (organization_id, workspace_id, kt_item_id);
ALTER TABLE workweave.exit_kt_findings ADD CONSTRAINT fk_exit_kt_findings_122
    FOREIGN KEY (organization_id, workspace_id, exit_kt_case_id)
    REFERENCES workweave.exit_kt_cases (organization_id, workspace_id, exit_kt_case_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_exit_kt_findings_fk_122 ON workweave.exit_kt_findings (organization_id, workspace_id, exit_kt_case_id);
ALTER TABLE workweave.exit_kt_findings ADD CONSTRAINT fk_exit_kt_findings_123
    FOREIGN KEY (organization_id, workspace_id, kt_item_id)
    REFERENCES workweave.exit_kt_knowledge_items (organization_id, workspace_id, kt_item_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_exit_kt_findings_fk_123 ON workweave.exit_kt_findings (organization_id, workspace_id, kt_item_id);
ALTER TABLE workweave.exit_kt_findings ADD CONSTRAINT fk_exit_kt_findings_124
    FOREIGN KEY (organization_id, workspace_id, reviewed_by)
    REFERENCES workweave.employees (organization_id, workspace_id, employee_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_exit_kt_findings_fk_124 ON workweave.exit_kt_findings (organization_id, workspace_id, reviewed_by);
ALTER TABLE workweave.exit_kt_interviews ADD CONSTRAINT fk_exit_kt_interviews_125
    FOREIGN KEY (organization_id, workspace_id, kt_item_id)
    REFERENCES workweave.exit_kt_knowledge_items (organization_id, workspace_id, kt_item_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_exit_kt_interviews_fk_125 ON workweave.exit_kt_interviews (organization_id, workspace_id, kt_item_id);
ALTER TABLE workweave.exit_kt_interviews ADD CONSTRAINT fk_exit_kt_interviews_126
    FOREIGN KEY (organization_id, workspace_id, employee_id)
    REFERENCES workweave.employees (organization_id, workspace_id, employee_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_exit_kt_interviews_fk_126 ON workweave.exit_kt_interviews (organization_id, workspace_id, employee_id);
ALTER TABLE workweave.exit_kt_interviews ADD CONSTRAINT fk_exit_kt_interviews_127
    FOREIGN KEY (organization_id, workspace_id, consent_session_id)
    REFERENCES workweave.consent_sessions (organization_id, workspace_id, consent_session_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_exit_kt_interviews_fk_127 ON workweave.exit_kt_interviews (organization_id, workspace_id, consent_session_id);
ALTER TABLE workweave.exit_kt_interview_messages ADD CONSTRAINT fk_exit_kt_interview_messages_128
    FOREIGN KEY (organization_id, workspace_id, interview_id)
    REFERENCES workweave.exit_kt_interviews (organization_id, workspace_id, interview_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_exit_kt_interview_messages_fk_128 ON workweave.exit_kt_interview_messages (organization_id, workspace_id, interview_id);
ALTER TABLE workweave.exit_kt_artifacts ADD CONSTRAINT fk_exit_kt_artifacts_129
    FOREIGN KEY (organization_id, workspace_id, kt_item_id)
    REFERENCES workweave.exit_kt_knowledge_items (organization_id, workspace_id, kt_item_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_exit_kt_artifacts_fk_129 ON workweave.exit_kt_artifacts (organization_id, workspace_id, kt_item_id);
ALTER TABLE workweave.exit_kt_artifacts ADD CONSTRAINT fk_exit_kt_artifacts_130
    FOREIGN KEY (organization_id, workspace_id, generated_from_interview_id)
    REFERENCES workweave.exit_kt_interviews (organization_id, workspace_id, interview_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_exit_kt_artifacts_fk_130 ON workweave.exit_kt_artifacts (organization_id, workspace_id, generated_from_interview_id);
ALTER TABLE workweave.exit_kt_artifact_revisions ADD CONSTRAINT fk_exit_kt_artifact_revisions_131
    FOREIGN KEY (organization_id, workspace_id, artifact_id)
    REFERENCES workweave.exit_kt_artifacts (organization_id, workspace_id, artifact_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_exit_kt_artifact_revisions_fk_131 ON workweave.exit_kt_artifact_revisions (organization_id, workspace_id, artifact_id);
ALTER TABLE workweave.exit_kt_artifact_revisions ADD CONSTRAINT fk_exit_kt_artifact_revisions_132
    FOREIGN KEY (organization_id, workspace_id, employee_reviewed_by)
    REFERENCES workweave.employees (organization_id, workspace_id, employee_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_exit_kt_artifact_revisions_fk_132 ON workweave.exit_kt_artifact_revisions (organization_id, workspace_id, employee_reviewed_by);
ALTER TABLE workweave.knowledge_approvals ADD CONSTRAINT fk_knowledge_approvals_133
    FOREIGN KEY (organization_id, workspace_id, artifact_revision_id)
    REFERENCES workweave.exit_kt_artifact_revisions (organization_id, workspace_id, artifact_revision_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_knowledge_approvals_fk_133 ON workweave.knowledge_approvals (organization_id, workspace_id, artifact_revision_id);
ALTER TABLE workweave.knowledge_approvals ADD CONSTRAINT fk_knowledge_approvals_134
    FOREIGN KEY (organization_id, workspace_id, reviewer_employee_id)
    REFERENCES workweave.employees (organization_id, workspace_id, employee_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_knowledge_approvals_fk_134 ON workweave.knowledge_approvals (organization_id, workspace_id, reviewer_employee_id);
ALTER TABLE workweave.knowledge_promotions ADD CONSTRAINT fk_knowledge_promotions_135
    FOREIGN KEY (organization_id, workspace_id, artifact_revision_id)
    REFERENCES workweave.exit_kt_artifact_revisions (organization_id, workspace_id, artifact_revision_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_knowledge_promotions_fk_135 ON workweave.knowledge_promotions (organization_id, workspace_id, artifact_revision_id);
ALTER TABLE workweave.knowledge_promotions ADD CONSTRAINT fk_knowledge_promotions_136
    FOREIGN KEY (organization_id, workspace_id, document_version_id)
    REFERENCES workweave.knowledge_document_versions (organization_id, workspace_id, document_version_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_knowledge_promotions_fk_136 ON workweave.knowledge_promotions (organization_id, workspace_id, document_version_id);
ALTER TABLE workweave.knowledge_promotions ADD CONSTRAINT fk_knowledge_promotions_137
    FOREIGN KEY (organization_id, workspace_id, approved_by)
    REFERENCES workweave.employees (organization_id, workspace_id, employee_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_knowledge_promotions_fk_137 ON workweave.knowledge_promotions (organization_id, workspace_id, approved_by);
ALTER TABLE workweave.responsibilities ADD CONSTRAINT fk_responsibilities_138
    FOREIGN KEY (organization_id, workspace_id, owner_employee_id)
    REFERENCES workweave.employees (organization_id, workspace_id, employee_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_responsibilities_fk_138 ON workweave.responsibilities (organization_id, workspace_id, owner_employee_id);
ALTER TABLE workweave.responsibility_transfers ADD CONSTRAINT fk_responsibility_transfers_139
    FOREIGN KEY (organization_id, workspace_id, exit_kt_case_id)
    REFERENCES workweave.exit_kt_cases (organization_id, workspace_id, exit_kt_case_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_responsibility_transfers_fk_139 ON workweave.responsibility_transfers (organization_id, workspace_id, exit_kt_case_id);
ALTER TABLE workweave.responsibility_transfers ADD CONSTRAINT fk_responsibility_transfers_140
    FOREIGN KEY (organization_id, workspace_id, responsibility_id)
    REFERENCES workweave.responsibilities (organization_id, workspace_id, responsibility_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_responsibility_transfers_fk_140 ON workweave.responsibility_transfers (organization_id, workspace_id, responsibility_id);
ALTER TABLE workweave.responsibility_transfers ADD CONSTRAINT fk_responsibility_transfers_141
    FOREIGN KEY (organization_id, workspace_id, current_owner_employee_id)
    REFERENCES workweave.employees (organization_id, workspace_id, employee_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_responsibility_transfers_fk_141 ON workweave.responsibility_transfers (organization_id, workspace_id, current_owner_employee_id);
ALTER TABLE workweave.responsibility_transfers ADD CONSTRAINT fk_responsibility_transfers_142
    FOREIGN KEY (organization_id, workspace_id, recommended_owner_employee_id)
    REFERENCES workweave.employees (organization_id, workspace_id, employee_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_responsibility_transfers_fk_142 ON workweave.responsibility_transfers (organization_id, workspace_id, recommended_owner_employee_id);
ALTER TABLE workweave.responsibility_transfers ADD CONSTRAINT fk_responsibility_transfers_143
    FOREIGN KEY (organization_id, workspace_id, final_owner_employee_id)
    REFERENCES workweave.employees (organization_id, workspace_id, employee_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_responsibility_transfers_fk_143 ON workweave.responsibility_transfers (organization_id, workspace_id, final_owner_employee_id);
ALTER TABLE workweave.responsibility_transfers ADD CONSTRAINT fk_responsibility_transfers_144
    FOREIGN KEY (organization_id, workspace_id, approved_by_employee_id)
    REFERENCES workweave.employees (organization_id, workspace_id, employee_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_responsibility_transfers_fk_144 ON workweave.responsibility_transfers (organization_id, workspace_id, approved_by_employee_id);
ALTER TABLE workweave.exit_kt_packages ADD CONSTRAINT fk_exit_kt_packages_145
    FOREIGN KEY (organization_id, workspace_id, exit_kt_case_id)
    REFERENCES workweave.exit_kt_cases (organization_id, workspace_id, exit_kt_case_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_exit_kt_packages_fk_145 ON workweave.exit_kt_packages (organization_id, workspace_id, exit_kt_case_id);
ALTER TABLE workweave.exit_kt_packages ADD CONSTRAINT fk_exit_kt_packages_146
    FOREIGN KEY (organization_id, workspace_id, successor_employee_id)
    REFERENCES workweave.employees (organization_id, workspace_id, employee_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_exit_kt_packages_fk_146 ON workweave.exit_kt_packages (organization_id, workspace_id, successor_employee_id);
ALTER TABLE workweave.exit_kt_package_responsibilities ADD CONSTRAINT fk_exit_kt_package_responsibilities_147
    FOREIGN KEY (organization_id, workspace_id, package_id)
    REFERENCES workweave.exit_kt_packages (organization_id, workspace_id, package_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_exit_kt_package_responsibilities_fk_147 ON workweave.exit_kt_package_responsibilities (organization_id, workspace_id, package_id);
ALTER TABLE workweave.exit_kt_package_responsibilities ADD CONSTRAINT fk_exit_kt_package_responsibilities_148
    FOREIGN KEY (organization_id, workspace_id, responsibility_id)
    REFERENCES workweave.responsibilities (organization_id, workspace_id, responsibility_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_exit_kt_package_responsibilities_fk_148 ON workweave.exit_kt_package_responsibilities (organization_id, workspace_id, responsibility_id);
ALTER TABLE workweave.exit_kt_package_versions ADD CONSTRAINT fk_exit_kt_package_versions_149
    FOREIGN KEY (organization_id, workspace_id, package_id)
    REFERENCES workweave.exit_kt_packages (organization_id, workspace_id, package_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_exit_kt_package_versions_fk_149 ON workweave.exit_kt_package_versions (organization_id, workspace_id, package_id);
ALTER TABLE workweave.exit_kt_package_versions ADD CONSTRAINT fk_exit_kt_package_versions_150
    FOREIGN KEY (organization_id, workspace_id, approved_by)
    REFERENCES workweave.employees (organization_id, workspace_id, employee_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_exit_kt_package_versions_fk_150 ON workweave.exit_kt_package_versions (organization_id, workspace_id, approved_by);
ALTER TABLE workweave.successor_receipts ADD CONSTRAINT fk_successor_receipts_151
    FOREIGN KEY (organization_id, workspace_id, package_version_id)
    REFERENCES workweave.exit_kt_package_versions (organization_id, workspace_id, package_version_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_successor_receipts_fk_151 ON workweave.successor_receipts (organization_id, workspace_id, package_version_id);
ALTER TABLE workweave.successor_receipts ADD CONSTRAINT fk_successor_receipts_152
    FOREIGN KEY (organization_id, workspace_id, successor_employee_id)
    REFERENCES workweave.employees (organization_id, workspace_id, employee_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_successor_receipts_fk_152 ON workweave.successor_receipts (organization_id, workspace_id, successor_employee_id);
ALTER TABLE workweave.kt_checklist_items ADD CONSTRAINT fk_kt_checklist_items_153
    FOREIGN KEY (organization_id, workspace_id, exit_kt_case_id)
    REFERENCES workweave.exit_kt_cases (organization_id, workspace_id, exit_kt_case_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_kt_checklist_items_fk_153 ON workweave.kt_checklist_items (organization_id, workspace_id, exit_kt_case_id);
ALTER TABLE workweave.kt_checklist_items ADD CONSTRAINT fk_kt_checklist_items_154
    FOREIGN KEY (organization_id, workspace_id, knowledge_item_id)
    REFERENCES workweave.exit_kt_knowledge_items (organization_id, workspace_id, kt_item_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_kt_checklist_items_fk_154 ON workweave.kt_checklist_items (organization_id, workspace_id, knowledge_item_id);
ALTER TABLE workweave.kt_checklist_items ADD CONSTRAINT fk_kt_checklist_items_155
    FOREIGN KEY (organization_id, workspace_id, responsibility_id)
    REFERENCES workweave.responsibilities (organization_id, workspace_id, responsibility_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_kt_checklist_items_fk_155 ON workweave.kt_checklist_items (organization_id, workspace_id, responsibility_id);
ALTER TABLE workweave.kt_checklist_items ADD CONSTRAINT fk_kt_checklist_items_156
    FOREIGN KEY (organization_id, workspace_id, reviewed_by)
    REFERENCES workweave.employees (organization_id, workspace_id, employee_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_kt_checklist_items_fk_156 ON workweave.kt_checklist_items (organization_id, workspace_id, reviewed_by);
ALTER TABLE workweave.command_receipts ADD CONSTRAINT fk_command_receipts_157
    FOREIGN KEY (organization_id, workspace_id, actor_id)
    REFERENCES workweave.employees (organization_id, workspace_id, employee_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_command_receipts_fk_157 ON workweave.command_receipts (organization_id, workspace_id, actor_id);
ALTER TABLE workweave.audit_events ADD CONSTRAINT fk_audit_events_158
    FOREIGN KEY (organization_id, workspace_id, actor_id)
    REFERENCES workweave.employees (organization_id, workspace_id, employee_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_audit_events_fk_158 ON workweave.audit_events (organization_id, workspace_id, actor_id);
ALTER TABLE workweave.outbox_events ADD CONSTRAINT fk_outbox_events_159
    FOREIGN KEY (organization_id, workspace_id, recipient_employee_id)
    REFERENCES workweave.employees (organization_id, workspace_id, employee_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_outbox_events_fk_159 ON workweave.outbox_events (organization_id, workspace_id, recipient_employee_id);
ALTER TABLE workweave.delivery_attempts ADD CONSTRAINT fk_delivery_attempts_160
    FOREIGN KEY (organization_id, workspace_id, event_id)
    REFERENCES workweave.outbox_events (organization_id, workspace_id, event_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_delivery_attempts_fk_160 ON workweave.delivery_attempts (organization_id, workspace_id, event_id);
ALTER TABLE workweave.operations ADD CONSTRAINT fk_operations_161
    FOREIGN KEY (organization_id, workspace_id, owner_employee_id)
    REFERENCES workweave.employees (organization_id, workspace_id, employee_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_operations_fk_161 ON workweave.operations (organization_id, workspace_id, owner_employee_id);
ALTER TABLE workweave.import_runs ADD CONSTRAINT fk_import_runs_162
    FOREIGN KEY (organization_id, workspace_id, scenario_id)
    REFERENCES workweave.scenario_catalog (organization_id, workspace_id, scenario_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_import_runs_fk_162 ON workweave.import_runs (organization_id, workspace_id, scenario_id);
ALTER TABLE workweave.demo_sessions ADD CONSTRAINT fk_demo_sessions_163
    FOREIGN KEY (organization_id, workspace_id, scenario_id)
    REFERENCES workweave.scenario_catalog (organization_id, workspace_id, scenario_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_demo_sessions_fk_163 ON workweave.demo_sessions (organization_id, workspace_id, scenario_id);
ALTER TABLE workweave.demo_persona_grants ADD CONSTRAINT fk_demo_persona_grants_164
    FOREIGN KEY (organization_id, workspace_id, demo_session_id)
    REFERENCES workweave.demo_sessions (organization_id, workspace_id, demo_session_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_demo_persona_grants_fk_164 ON workweave.demo_persona_grants (organization_id, workspace_id, demo_session_id);
ALTER TABLE workweave.demo_persona_grants ADD CONSTRAINT fk_demo_persona_grants_165
    FOREIGN KEY (organization_id, workspace_id, employee_id)
    REFERENCES workweave.employees (organization_id, workspace_id, employee_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_demo_persona_grants_fk_165 ON workweave.demo_persona_grants (organization_id, workspace_id, employee_id);
ALTER TABLE workweave.knowledge_documents ADD CONSTRAINT fk_knowledge_documents_166
    FOREIGN KEY (organization_id, workspace_id, document_id, current_version_id)
    REFERENCES workweave.knowledge_document_versions (organization_id, workspace_id, document_id, document_version_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_knowledge_documents_fk_166 ON workweave.knowledge_documents (organization_id, workspace_id, document_id, current_version_id);
ALTER TABLE workweave.knowledge_chunks ADD CONSTRAINT fk_knowledge_chunks_167
    FOREIGN KEY (organization_id, workspace_id, document_version_id, parent_chunk_id)
    REFERENCES workweave.knowledge_chunks (organization_id, workspace_id, document_version_id, chunk_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_knowledge_chunks_fk_167 ON workweave.knowledge_chunks (organization_id, workspace_id, document_version_id, parent_chunk_id);
ALTER TABLE workweave.knowledge_mappings ADD CONSTRAINT fk_knowledge_mappings_168
    FOREIGN KEY (organization_id, workspace_id, document_id, document_version_id)
    REFERENCES workweave.knowledge_document_versions (organization_id, workspace_id, document_id, document_version_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_knowledge_mappings_fk_168 ON workweave.knowledge_mappings (organization_id, workspace_id, document_id, document_version_id);
ALTER TABLE workweave.learning_assignments ADD CONSTRAINT fk_learning_assignments_169
    FOREIGN KEY (organization_id, workspace_id, originating_assignment_id, curriculum_id)
    REFERENCES workweave.curriculum_assignments (organization_id, workspace_id, assignment_id, curriculum_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_learning_assignments_fk_169 ON workweave.learning_assignments (organization_id, workspace_id, originating_assignment_id, curriculum_id);
ALTER TABLE workweave.employee_learning_progress ADD CONSTRAINT fk_employee_learning_progress_170
    FOREIGN KEY (organization_id, workspace_id, learning_assignment_id, employee_id)
    REFERENCES workweave.learning_assignments (organization_id, workspace_id, learning_assignment_id, employee_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_employee_learning_progress_fk_170 ON workweave.employee_learning_progress (organization_id, workspace_id, learning_assignment_id, employee_id);
ALTER TABLE workweave.learning_sessions ADD CONSTRAINT fk_learning_sessions_171
    FOREIGN KEY (organization_id, workspace_id, learning_assignment_id, employee_id)
    REFERENCES workweave.learning_assignments (organization_id, workspace_id, learning_assignment_id, employee_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_learning_sessions_fk_171 ON workweave.learning_sessions (organization_id, workspace_id, learning_assignment_id, employee_id);
ALTER TABLE workweave.learning_sessions ADD CONSTRAINT fk_learning_sessions_172
    FOREIGN KEY (organization_id, workspace_id, learning_assignment_id, curriculum_id)
    REFERENCES workweave.learning_assignments (organization_id, workspace_id, learning_assignment_id, curriculum_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_learning_sessions_fk_172 ON workweave.learning_sessions (organization_id, workspace_id, learning_assignment_id, curriculum_id);
ALTER TABLE workweave.learning_sessions ADD CONSTRAINT fk_learning_sessions_173
    FOREIGN KEY (organization_id, workspace_id, curriculum_id, current_topic_id)
    REFERENCES workweave.curriculum_topics (organization_id, workspace_id, curriculum_id, topic_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_learning_sessions_fk_173 ON workweave.learning_sessions (organization_id, workspace_id, curriculum_id, current_topic_id);
ALTER TABLE workweave.learning_sessions ADD CONSTRAINT fk_learning_sessions_174
    FOREIGN KEY (organization_id, workspace_id, current_topic_id, current_subtopic_id)
    REFERENCES workweave.curriculum_subtopics (organization_id, workspace_id, topic_id, subtopic_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_learning_sessions_fk_174 ON workweave.learning_sessions (organization_id, workspace_id, current_topic_id, current_subtopic_id);
ALTER TABLE workweave.employee_learning_events ADD CONSTRAINT fk_employee_learning_events_175
    FOREIGN KEY (organization_id, workspace_id, learning_session_id, employee_id)
    REFERENCES workweave.learning_sessions (organization_id, workspace_id, learning_session_id, employee_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_employee_learning_events_fk_175 ON workweave.employee_learning_events (organization_id, workspace_id, learning_session_id, employee_id);
ALTER TABLE workweave.objective_evidence ADD CONSTRAINT fk_objective_evidence_176
    FOREIGN KEY (organization_id, workspace_id, attempt_id, objective_id, criteria_version)
    REFERENCES workweave.learning_assessment_attempts (organization_id, workspace_id, attempt_id, objective_id, criteria_version)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_objective_evidence_fk_176 ON workweave.objective_evidence (organization_id, workspace_id, attempt_id, objective_id, criteria_version);
ALTER TABLE workweave.work_item_assignments ADD CONSTRAINT fk_work_item_assignments_177
    FOREIGN KEY (organization_id, workspace_id, proposal_item_id, work_item_id)
    REFERENCES workweave.delegation_proposal_items (organization_id, workspace_id, proposal_item_id, work_item_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_work_item_assignments_fk_177 ON workweave.work_item_assignments (organization_id, workspace_id, proposal_item_id, work_item_id);
ALTER TABLE workweave.shift_handovers ADD CONSTRAINT fk_shift_handovers_178
    FOREIGN KEY (organization_id, workspace_id, handover_id, current_publication_id)
    REFERENCES workweave.handover_publications (organization_id, workspace_id, handover_id, publication_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_shift_handovers_fk_178 ON workweave.shift_handovers (organization_id, workspace_id, handover_id, current_publication_id);
ALTER TABLE workweave.handover_items ADD CONSTRAINT fk_handover_items_179
    FOREIGN KEY (organization_id, workspace_id, handover_item_id, completion_cycle_id)
    REFERENCES workweave.handover_completion_cycles (organization_id, workspace_id, handover_item_id, completion_cycle_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_handover_items_fk_179 ON workweave.handover_items (organization_id, workspace_id, handover_item_id, completion_cycle_id);
ALTER TABLE workweave.handover_item_events ADD CONSTRAINT fk_handover_item_events_180
    FOREIGN KEY (organization_id, workspace_id, handover_item_id, completion_cycle_id)
    REFERENCES workweave.handover_completion_cycles (organization_id, workspace_id, handover_item_id, completion_cycle_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_handover_item_events_fk_180 ON workweave.handover_item_events (organization_id, workspace_id, handover_item_id, completion_cycle_id);
ALTER TABLE workweave.handover_acknowledgements ADD CONSTRAINT fk_handover_acknowledgements_181
    FOREIGN KEY (organization_id, workspace_id, handover_item_id, completion_cycle_id)
    REFERENCES workweave.handover_completion_cycles (organization_id, workspace_id, handover_item_id, completion_cycle_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_handover_acknowledgements_fk_181 ON workweave.handover_acknowledgements (organization_id, workspace_id, handover_item_id, completion_cycle_id);
ALTER TABLE workweave.exit_kt_artifacts ADD CONSTRAINT fk_exit_kt_artifacts_182
    FOREIGN KEY (organization_id, workspace_id, artifact_id, current_revision_id)
    REFERENCES workweave.exit_kt_artifact_revisions (organization_id, workspace_id, artifact_id, artifact_revision_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_exit_kt_artifacts_fk_182 ON workweave.exit_kt_artifacts (organization_id, workspace_id, artifact_id, current_revision_id);
ALTER TABLE workweave.exit_kt_packages ADD CONSTRAINT fk_exit_kt_packages_183
    FOREIGN KEY (organization_id, workspace_id, package_id, current_approved_version_id)
    REFERENCES workweave.exit_kt_package_versions (organization_id, workspace_id, package_id, package_version_id)
    DEFERRABLE INITIALLY IMMEDIATE;
CREATE INDEX ix_exit_kt_packages_fk_183 ON workweave.exit_kt_packages (organization_id, workspace_id, package_id, current_approved_version_id);

ALTER TABLE workweave.learning_sessions ADD CONSTRAINT learning_position_pair CHECK (current_subtopic_id IS NULL OR current_topic_id IS NOT NULL);
CREATE UNIQUE INDEX employees_scoped_email ON workweave.employees (organization_id, workspace_id, lower(email));
CREATE UNIQUE INDEX work_items_external_identity ON workweave.work_items (organization_id, workspace_id, external_system, external_id) WHERE external_system IS NOT NULL AND external_id IS NOT NULL;
CREATE UNIQUE INDEX active_work_item_assignment ON workweave.work_item_assignments (organization_id, workspace_id, work_item_id, employee_id) WHERE status NOT IN ('COMPLETED','CANCELLED');
CREATE UNIQUE INDEX one_current_approved_document ON workweave.knowledge_document_versions (organization_id, workspace_id, document_id) WHERE approval_status = 'APPROVED' AND temporal_status = 'CURRENT';
CREATE INDEX outbox_due_dispatch ON workweave.outbox_events (status, next_attempt_at) WHERE status IN ('PENDING','FAILED');
CREATE INDEX knowledge_lexical_content ON workweave.knowledge_chunks USING gin (to_tsvector('simple', content));
-- No vector ANN index: embedding model/dimension/configuration require separate approval.
CREATE INDEX ix_departments_scope_time ON workweave.departments (organization_id, workspace_id, created_at);
CREATE INDEX ix_teams_scope_time ON workweave.teams (organization_id, workspace_id, created_at);
CREATE INDEX ix_roles_scope_time ON workweave.roles (organization_id, workspace_id, created_at);
CREATE INDEX ix_employees_scope_time ON workweave.employees (organization_id, workspace_id, created_at);
CREATE INDEX ix_employee_team_memberships_scope_time ON workweave.employee_team_memberships (organization_id, workspace_id, created_at);
CREATE INDEX ix_auth_identity_links_scope_time ON workweave.auth_identity_links (organization_id, workspace_id, created_at);
CREATE INDEX ix_permission_grants_scope_time ON workweave.permission_grants (organization_id, workspace_id, created_at);
CREATE INDEX ix_shifts_scope_time ON workweave.shifts (organization_id, workspace_id, created_at);
CREATE INDEX ix_shift_instances_scope_time ON workweave.shift_instances (organization_id, workspace_id, created_at);
CREATE INDEX ix_shift_instance_memberships_scope_time ON workweave.shift_instance_memberships (organization_id, workspace_id, created_at);
CREATE INDEX ix_employee_availability_scope_time ON workweave.employee_availability (organization_id, workspace_id, created_at);
CREATE INDEX ix_consent_sessions_scope_time ON workweave.consent_sessions (organization_id, workspace_id, created_at);
CREATE INDEX ix_source_records_scope_time ON workweave.source_records (organization_id, workspace_id, created_at);
CREATE INDEX ix_knowledge_documents_scope_time ON workweave.knowledge_documents (organization_id, workspace_id, created_at);
CREATE INDEX ix_knowledge_document_versions_scope_time ON workweave.knowledge_document_versions (organization_id, workspace_id, created_at);
CREATE INDEX ix_knowledge_chunks_scope_time ON workweave.knowledge_chunks (organization_id, workspace_id, created_at);
CREATE INDEX ix_knowledge_mappings_scope_time ON workweave.knowledge_mappings (organization_id, workspace_id, created_at);
CREATE INDEX ix_memory_drafts_scope_time ON workweave.memory_drafts (organization_id, workspace_id, created_at);
CREATE INDEX ix_memory_records_scope_time ON workweave.memory_records (organization_id, workspace_id, created_at);
CREATE INDEX ix_competencies_scope_time ON workweave.competencies (organization_id, workspace_id, created_at);
CREATE INDEX ix_role_competency_requirements_scope_time ON workweave.role_competency_requirements (organization_id, workspace_id, created_at);
CREATE INDEX ix_employee_competency_evidence_scope_time ON workweave.employee_competency_evidence (organization_id, workspace_id, created_at);
CREATE INDEX ix_employee_competency_state_scope_time ON workweave.employee_competency_state (organization_id, workspace_id, created_at);
CREATE INDEX ix_curricula_scope_time ON workweave.curricula (organization_id, workspace_id, created_at);
CREATE INDEX ix_curriculum_assignments_scope_time ON workweave.curriculum_assignments (organization_id, workspace_id, created_at);
CREATE INDEX ix_learning_assignments_scope_time ON workweave.learning_assignments (organization_id, workspace_id, created_at);
CREATE INDEX ix_curriculum_topics_scope_time ON workweave.curriculum_topics (organization_id, workspace_id, created_at);
CREATE INDEX ix_curriculum_subtopics_scope_time ON workweave.curriculum_subtopics (organization_id, workspace_id, created_at);
CREATE INDEX ix_curriculum_prerequisites_scope_time ON workweave.curriculum_prerequisites (organization_id, workspace_id, created_at);
CREATE INDEX ix_learning_objectives_scope_time ON workweave.learning_objectives (organization_id, workspace_id, created_at);
CREATE INDEX ix_employee_learning_progress_scope_time ON workweave.employee_learning_progress (organization_id, workspace_id, created_at);
CREATE INDEX ix_learning_sessions_scope_time ON workweave.learning_sessions (organization_id, workspace_id, created_at);
CREATE INDEX ix_learning_turns_scope_time ON workweave.learning_turns (organization_id, workspace_id, created_at);
CREATE INDEX ix_employee_learning_events_scope_time ON workweave.employee_learning_events (organization_id, workspace_id, created_at);
CREATE INDEX ix_learning_assessment_attempts_scope_time ON workweave.learning_assessment_attempts (organization_id, workspace_id, created_at);
CREATE INDEX ix_objective_evidence_scope_time ON workweave.objective_evidence (organization_id, workspace_id, created_at);
CREATE INDEX ix_work_sessions_scope_time ON workweave.work_sessions (organization_id, workspace_id, created_at);
CREATE INDEX ix_work_items_scope_time ON workweave.work_items (organization_id, workspace_id, created_at);
CREATE INDEX ix_work_item_competency_requirements_scope_time ON workweave.work_item_competency_requirements (organization_id, workspace_id, created_at);
CREATE INDEX ix_delegation_proposals_scope_time ON workweave.delegation_proposals (organization_id, workspace_id, created_at);
CREATE INDEX ix_delegation_proposal_items_scope_time ON workweave.delegation_proposal_items (organization_id, workspace_id, created_at);
CREATE INDEX ix_work_item_assignments_scope_time ON workweave.work_item_assignments (organization_id, workspace_id, created_at);
CREATE INDEX ix_work_events_scope_time ON workweave.work_events (organization_id, workspace_id, created_at);
CREATE INDEX ix_employee_work_state_scope_time ON workweave.employee_work_state (organization_id, workspace_id, created_at);
CREATE INDEX ix_productivity_observations_scope_time ON workweave.productivity_observations (organization_id, workspace_id, created_at);
CREATE INDEX ix_handover_templates_scope_time ON workweave.handover_templates (organization_id, workspace_id, created_at);
CREATE INDEX ix_handover_template_versions_scope_time ON workweave.handover_template_versions (organization_id, workspace_id, created_at);
CREATE INDEX ix_handover_template_sections_scope_time ON workweave.handover_template_sections (organization_id, workspace_id, created_at);
CREATE INDEX ix_shift_handovers_scope_time ON workweave.shift_handovers (organization_id, workspace_id, created_at);
CREATE INDEX ix_handover_publications_scope_time ON workweave.handover_publications (organization_id, workspace_id, created_at);
CREATE INDEX ix_handover_items_scope_time ON workweave.handover_items (organization_id, workspace_id, created_at);
CREATE INDEX ix_handover_entries_scope_time ON workweave.handover_entries (organization_id, workspace_id, created_at);
CREATE INDEX ix_handover_suggestions_scope_time ON workweave.handover_suggestions (organization_id, workspace_id, created_at);
CREATE INDEX ix_handover_item_sources_scope_time ON workweave.handover_item_sources (organization_id, workspace_id, created_at);
CREATE INDEX ix_handover_completion_cycles_scope_time ON workweave.handover_completion_cycles (organization_id, workspace_id, created_at);
CREATE INDEX ix_handover_item_events_scope_time ON workweave.handover_item_events (organization_id, workspace_id, created_at);
CREATE INDEX ix_handover_acknowledgements_scope_time ON workweave.handover_acknowledgements (organization_id, workspace_id, created_at);
CREATE INDEX ix_handover_receipts_scope_time ON workweave.handover_receipts (organization_id, workspace_id, created_at);
CREATE INDEX ix_exit_kt_cases_scope_time ON workweave.exit_kt_cases (organization_id, workspace_id, created_at);
CREATE INDEX ix_exit_kt_knowledge_items_scope_time ON workweave.exit_kt_knowledge_items (organization_id, workspace_id, created_at);
CREATE INDEX ix_exit_kt_sources_scope_time ON workweave.exit_kt_sources (organization_id, workspace_id, created_at);
CREATE INDEX ix_exit_kt_findings_scope_time ON workweave.exit_kt_findings (organization_id, workspace_id, created_at);
CREATE INDEX ix_exit_kt_interviews_scope_time ON workweave.exit_kt_interviews (organization_id, workspace_id, created_at);
CREATE INDEX ix_exit_kt_interview_messages_scope_time ON workweave.exit_kt_interview_messages (organization_id, workspace_id, created_at);
CREATE INDEX ix_exit_kt_artifacts_scope_time ON workweave.exit_kt_artifacts (organization_id, workspace_id, created_at);
CREATE INDEX ix_exit_kt_artifact_revisions_scope_time ON workweave.exit_kt_artifact_revisions (organization_id, workspace_id, created_at);
CREATE INDEX ix_knowledge_approvals_scope_time ON workweave.knowledge_approvals (organization_id, workspace_id, created_at);
CREATE INDEX ix_knowledge_promotions_scope_time ON workweave.knowledge_promotions (organization_id, workspace_id, created_at);
CREATE INDEX ix_responsibilities_scope_time ON workweave.responsibilities (organization_id, workspace_id, created_at);
CREATE INDEX ix_responsibility_transfers_scope_time ON workweave.responsibility_transfers (organization_id, workspace_id, created_at);
CREATE INDEX ix_exit_kt_packages_scope_time ON workweave.exit_kt_packages (organization_id, workspace_id, created_at);
CREATE INDEX ix_exit_kt_package_responsibilities_scope_time ON workweave.exit_kt_package_responsibilities (organization_id, workspace_id, created_at);
CREATE INDEX ix_exit_kt_package_versions_scope_time ON workweave.exit_kt_package_versions (organization_id, workspace_id, created_at);
CREATE INDEX ix_successor_receipts_scope_time ON workweave.successor_receipts (organization_id, workspace_id, created_at);
CREATE INDEX ix_kt_checklist_items_scope_time ON workweave.kt_checklist_items (organization_id, workspace_id, created_at);
CREATE INDEX ix_command_receipts_scope_time ON workweave.command_receipts (organization_id, workspace_id, created_at);
CREATE INDEX ix_audit_events_scope_time ON workweave.audit_events (organization_id, workspace_id, created_at);
CREATE INDEX ix_outbox_events_scope_time ON workweave.outbox_events (organization_id, workspace_id, created_at);
CREATE INDEX ix_delivery_attempts_scope_time ON workweave.delivery_attempts (organization_id, workspace_id, created_at);
CREATE INDEX ix_operations_scope_time ON workweave.operations (organization_id, workspace_id, created_at);
CREATE INDEX ix_scenario_catalog_scope_time ON workweave.scenario_catalog (organization_id, workspace_id, created_at);
CREATE INDEX ix_import_runs_scope_time ON workweave.import_runs (organization_id, workspace_id, created_at);
CREATE INDEX ix_demo_sessions_scope_time ON workweave.demo_sessions (organization_id, workspace_id, created_at);
CREATE INDEX ix_demo_persona_grants_scope_time ON workweave.demo_persona_grants (organization_id, workspace_id, created_at);

-- Optimistic revision support, not a replacement for expected-revision service checks.
CREATE FUNCTION workweave.touch_revision() RETURNS trigger LANGUAGE plpgsql AS $body$
BEGIN
    IF NEW.revision = OLD.revision THEN
        NEW.revision := OLD.revision + 1;
    ELSIF NEW.revision <> OLD.revision + 1 THEN
        RAISE EXCEPTION 'Revision must advance by exactly one for %', TG_TABLE_NAME;
    END IF;
    NEW.updated_at := clock_timestamp();
    RETURN NEW;
END;
$body$;
CREATE FUNCTION workweave.reject_history_mutation() RETURNS trigger LANGUAGE plpgsql AS $body$
BEGIN
    RAISE EXCEPTION '% is append-only: updates/deletes require a separately reviewed retention migration', TG_TABLE_NAME;
END;
$body$;
CREATE TRIGGER touch_organizations BEFORE UPDATE ON workweave.organizations FOR EACH ROW EXECUTE FUNCTION workweave.touch_revision();
CREATE TRIGGER touch_workspaces BEFORE UPDATE ON workweave.workspaces FOR EACH ROW EXECUTE FUNCTION workweave.touch_revision();
CREATE TRIGGER touch_departments BEFORE UPDATE ON workweave.departments FOR EACH ROW EXECUTE FUNCTION workweave.touch_revision();
CREATE TRIGGER touch_teams BEFORE UPDATE ON workweave.teams FOR EACH ROW EXECUTE FUNCTION workweave.touch_revision();
CREATE TRIGGER touch_roles BEFORE UPDATE ON workweave.roles FOR EACH ROW EXECUTE FUNCTION workweave.touch_revision();
CREATE TRIGGER touch_employees BEFORE UPDATE ON workweave.employees FOR EACH ROW EXECUTE FUNCTION workweave.touch_revision();
CREATE TRIGGER touch_employee_team_memberships BEFORE UPDATE ON workweave.employee_team_memberships FOR EACH ROW EXECUTE FUNCTION workweave.touch_revision();
CREATE TRIGGER touch_auth_identity_links BEFORE UPDATE ON workweave.auth_identity_links FOR EACH ROW EXECUTE FUNCTION workweave.touch_revision();
CREATE TRIGGER touch_permission_grants BEFORE UPDATE ON workweave.permission_grants FOR EACH ROW EXECUTE FUNCTION workweave.touch_revision();
CREATE TRIGGER touch_shifts BEFORE UPDATE ON workweave.shifts FOR EACH ROW EXECUTE FUNCTION workweave.touch_revision();
CREATE TRIGGER touch_shift_instances BEFORE UPDATE ON workweave.shift_instances FOR EACH ROW EXECUTE FUNCTION workweave.touch_revision();
CREATE TRIGGER touch_shift_instance_memberships BEFORE UPDATE ON workweave.shift_instance_memberships FOR EACH ROW EXECUTE FUNCTION workweave.touch_revision();
CREATE TRIGGER touch_employee_availability BEFORE UPDATE ON workweave.employee_availability FOR EACH ROW EXECUTE FUNCTION workweave.touch_revision();
CREATE TRIGGER touch_consent_sessions BEFORE UPDATE ON workweave.consent_sessions FOR EACH ROW EXECUTE FUNCTION workweave.touch_revision();
CREATE TRIGGER touch_source_records BEFORE UPDATE ON workweave.source_records FOR EACH ROW EXECUTE FUNCTION workweave.touch_revision();
CREATE TRIGGER touch_knowledge_documents BEFORE UPDATE ON workweave.knowledge_documents FOR EACH ROW EXECUTE FUNCTION workweave.touch_revision();
CREATE TRIGGER touch_knowledge_document_versions BEFORE UPDATE ON workweave.knowledge_document_versions FOR EACH ROW EXECUTE FUNCTION workweave.touch_revision();
CREATE TRIGGER touch_knowledge_chunks BEFORE UPDATE ON workweave.knowledge_chunks FOR EACH ROW EXECUTE FUNCTION workweave.touch_revision();
CREATE TRIGGER touch_knowledge_mappings BEFORE UPDATE ON workweave.knowledge_mappings FOR EACH ROW EXECUTE FUNCTION workweave.touch_revision();
CREATE TRIGGER touch_memory_drafts BEFORE UPDATE ON workweave.memory_drafts FOR EACH ROW EXECUTE FUNCTION workweave.touch_revision();
CREATE TRIGGER preserve_memory_records BEFORE UPDATE OR DELETE ON workweave.memory_records FOR EACH ROW EXECUTE FUNCTION workweave.reject_history_mutation();
CREATE TRIGGER touch_competencies BEFORE UPDATE ON workweave.competencies FOR EACH ROW EXECUTE FUNCTION workweave.touch_revision();
CREATE TRIGGER touch_role_competency_requirements BEFORE UPDATE ON workweave.role_competency_requirements FOR EACH ROW EXECUTE FUNCTION workweave.touch_revision();
CREATE TRIGGER touch_employee_competency_evidence BEFORE UPDATE ON workweave.employee_competency_evidence FOR EACH ROW EXECUTE FUNCTION workweave.touch_revision();
CREATE TRIGGER touch_employee_competency_state BEFORE UPDATE ON workweave.employee_competency_state FOR EACH ROW EXECUTE FUNCTION workweave.touch_revision();
CREATE TRIGGER touch_curricula BEFORE UPDATE ON workweave.curricula FOR EACH ROW EXECUTE FUNCTION workweave.touch_revision();
CREATE TRIGGER touch_curriculum_assignments BEFORE UPDATE ON workweave.curriculum_assignments FOR EACH ROW EXECUTE FUNCTION workweave.touch_revision();
CREATE TRIGGER touch_learning_assignments BEFORE UPDATE ON workweave.learning_assignments FOR EACH ROW EXECUTE FUNCTION workweave.touch_revision();
CREATE TRIGGER touch_curriculum_topics BEFORE UPDATE ON workweave.curriculum_topics FOR EACH ROW EXECUTE FUNCTION workweave.touch_revision();
CREATE TRIGGER touch_curriculum_subtopics BEFORE UPDATE ON workweave.curriculum_subtopics FOR EACH ROW EXECUTE FUNCTION workweave.touch_revision();
CREATE TRIGGER touch_curriculum_prerequisites BEFORE UPDATE ON workweave.curriculum_prerequisites FOR EACH ROW EXECUTE FUNCTION workweave.touch_revision();
CREATE TRIGGER touch_learning_objectives BEFORE UPDATE ON workweave.learning_objectives FOR EACH ROW EXECUTE FUNCTION workweave.touch_revision();
CREATE TRIGGER touch_employee_learning_progress BEFORE UPDATE ON workweave.employee_learning_progress FOR EACH ROW EXECUTE FUNCTION workweave.touch_revision();
CREATE TRIGGER touch_learning_sessions BEFORE UPDATE ON workweave.learning_sessions FOR EACH ROW EXECUTE FUNCTION workweave.touch_revision();
CREATE TRIGGER touch_learning_turns BEFORE UPDATE ON workweave.learning_turns FOR EACH ROW EXECUTE FUNCTION workweave.touch_revision();
CREATE TRIGGER preserve_employee_learning_events BEFORE UPDATE OR DELETE ON workweave.employee_learning_events FOR EACH ROW EXECUTE FUNCTION workweave.reject_history_mutation();
CREATE TRIGGER preserve_learning_assessment_attempts BEFORE UPDATE OR DELETE ON workweave.learning_assessment_attempts FOR EACH ROW EXECUTE FUNCTION workweave.reject_history_mutation();
CREATE TRIGGER preserve_objective_evidence BEFORE UPDATE OR DELETE ON workweave.objective_evidence FOR EACH ROW EXECUTE FUNCTION workweave.reject_history_mutation();
CREATE TRIGGER touch_work_sessions BEFORE UPDATE ON workweave.work_sessions FOR EACH ROW EXECUTE FUNCTION workweave.touch_revision();
CREATE TRIGGER touch_work_items BEFORE UPDATE ON workweave.work_items FOR EACH ROW EXECUTE FUNCTION workweave.touch_revision();
CREATE TRIGGER touch_work_item_competency_requirements BEFORE UPDATE ON workweave.work_item_competency_requirements FOR EACH ROW EXECUTE FUNCTION workweave.touch_revision();
CREATE TRIGGER touch_delegation_proposals BEFORE UPDATE ON workweave.delegation_proposals FOR EACH ROW EXECUTE FUNCTION workweave.touch_revision();
CREATE TRIGGER touch_delegation_proposal_items BEFORE UPDATE ON workweave.delegation_proposal_items FOR EACH ROW EXECUTE FUNCTION workweave.touch_revision();
CREATE TRIGGER touch_work_item_assignments BEFORE UPDATE ON workweave.work_item_assignments FOR EACH ROW EXECUTE FUNCTION workweave.touch_revision();
CREATE TRIGGER preserve_work_events BEFORE UPDATE OR DELETE ON workweave.work_events FOR EACH ROW EXECUTE FUNCTION workweave.reject_history_mutation();
CREATE TRIGGER touch_employee_work_state BEFORE UPDATE ON workweave.employee_work_state FOR EACH ROW EXECUTE FUNCTION workweave.touch_revision();
CREATE TRIGGER preserve_productivity_observations BEFORE UPDATE OR DELETE ON workweave.productivity_observations FOR EACH ROW EXECUTE FUNCTION workweave.reject_history_mutation();
CREATE TRIGGER touch_handover_templates BEFORE UPDATE ON workweave.handover_templates FOR EACH ROW EXECUTE FUNCTION workweave.touch_revision();
CREATE TRIGGER preserve_handover_template_versions BEFORE UPDATE OR DELETE ON workweave.handover_template_versions FOR EACH ROW EXECUTE FUNCTION workweave.reject_history_mutation();
CREATE TRIGGER preserve_handover_template_sections BEFORE UPDATE OR DELETE ON workweave.handover_template_sections FOR EACH ROW EXECUTE FUNCTION workweave.reject_history_mutation();
CREATE TRIGGER touch_shift_handovers BEFORE UPDATE ON workweave.shift_handovers FOR EACH ROW EXECUTE FUNCTION workweave.touch_revision();
CREATE TRIGGER preserve_handover_publications BEFORE UPDATE OR DELETE ON workweave.handover_publications FOR EACH ROW EXECUTE FUNCTION workweave.reject_history_mutation();
CREATE TRIGGER touch_handover_items BEFORE UPDATE ON workweave.handover_items FOR EACH ROW EXECUTE FUNCTION workweave.touch_revision();
CREATE TRIGGER preserve_handover_entries BEFORE UPDATE OR DELETE ON workweave.handover_entries FOR EACH ROW EXECUTE FUNCTION workweave.reject_history_mutation();
CREATE TRIGGER touch_handover_suggestions BEFORE UPDATE ON workweave.handover_suggestions FOR EACH ROW EXECUTE FUNCTION workweave.touch_revision();
CREATE TRIGGER touch_handover_item_sources BEFORE UPDATE ON workweave.handover_item_sources FOR EACH ROW EXECUTE FUNCTION workweave.touch_revision();
CREATE TRIGGER touch_handover_completion_cycles BEFORE UPDATE ON workweave.handover_completion_cycles FOR EACH ROW EXECUTE FUNCTION workweave.touch_revision();
CREATE TRIGGER preserve_handover_item_events BEFORE UPDATE OR DELETE ON workweave.handover_item_events FOR EACH ROW EXECUTE FUNCTION workweave.reject_history_mutation();
CREATE TRIGGER touch_handover_acknowledgements BEFORE UPDATE ON workweave.handover_acknowledgements FOR EACH ROW EXECUTE FUNCTION workweave.touch_revision();
CREATE TRIGGER preserve_handover_receipts BEFORE UPDATE OR DELETE ON workweave.handover_receipts FOR EACH ROW EXECUTE FUNCTION workweave.reject_history_mutation();
CREATE TRIGGER touch_exit_kt_cases BEFORE UPDATE ON workweave.exit_kt_cases FOR EACH ROW EXECUTE FUNCTION workweave.touch_revision();
CREATE TRIGGER touch_exit_kt_knowledge_items BEFORE UPDATE ON workweave.exit_kt_knowledge_items FOR EACH ROW EXECUTE FUNCTION workweave.touch_revision();
CREATE TRIGGER touch_exit_kt_sources BEFORE UPDATE ON workweave.exit_kt_sources FOR EACH ROW EXECUTE FUNCTION workweave.touch_revision();
CREATE TRIGGER touch_exit_kt_findings BEFORE UPDATE ON workweave.exit_kt_findings FOR EACH ROW EXECUTE FUNCTION workweave.touch_revision();
CREATE TRIGGER touch_exit_kt_interviews BEFORE UPDATE ON workweave.exit_kt_interviews FOR EACH ROW EXECUTE FUNCTION workweave.touch_revision();
CREATE TRIGGER preserve_exit_kt_interview_messages BEFORE UPDATE OR DELETE ON workweave.exit_kt_interview_messages FOR EACH ROW EXECUTE FUNCTION workweave.reject_history_mutation();
CREATE TRIGGER touch_exit_kt_artifacts BEFORE UPDATE ON workweave.exit_kt_artifacts FOR EACH ROW EXECUTE FUNCTION workweave.touch_revision();
CREATE TRIGGER touch_exit_kt_artifact_revisions BEFORE UPDATE ON workweave.exit_kt_artifact_revisions FOR EACH ROW EXECUTE FUNCTION workweave.touch_revision();
CREATE TRIGGER touch_knowledge_approvals BEFORE UPDATE ON workweave.knowledge_approvals FOR EACH ROW EXECUTE FUNCTION workweave.touch_revision();
CREATE TRIGGER touch_knowledge_promotions BEFORE UPDATE ON workweave.knowledge_promotions FOR EACH ROW EXECUTE FUNCTION workweave.touch_revision();
CREATE TRIGGER touch_responsibilities BEFORE UPDATE ON workweave.responsibilities FOR EACH ROW EXECUTE FUNCTION workweave.touch_revision();
CREATE TRIGGER touch_responsibility_transfers BEFORE UPDATE ON workweave.responsibility_transfers FOR EACH ROW EXECUTE FUNCTION workweave.touch_revision();
CREATE TRIGGER touch_exit_kt_packages BEFORE UPDATE ON workweave.exit_kt_packages FOR EACH ROW EXECUTE FUNCTION workweave.touch_revision();
CREATE TRIGGER touch_exit_kt_package_responsibilities BEFORE UPDATE ON workweave.exit_kt_package_responsibilities FOR EACH ROW EXECUTE FUNCTION workweave.touch_revision();
CREATE TRIGGER preserve_exit_kt_package_versions BEFORE UPDATE OR DELETE ON workweave.exit_kt_package_versions FOR EACH ROW EXECUTE FUNCTION workweave.reject_history_mutation();
CREATE TRIGGER preserve_successor_receipts BEFORE UPDATE OR DELETE ON workweave.successor_receipts FOR EACH ROW EXECUTE FUNCTION workweave.reject_history_mutation();
CREATE TRIGGER touch_kt_checklist_items BEFORE UPDATE ON workweave.kt_checklist_items FOR EACH ROW EXECUTE FUNCTION workweave.touch_revision();
CREATE TRIGGER preserve_command_receipts BEFORE UPDATE OR DELETE ON workweave.command_receipts FOR EACH ROW EXECUTE FUNCTION workweave.reject_history_mutation();
CREATE TRIGGER preserve_audit_events BEFORE UPDATE OR DELETE ON workweave.audit_events FOR EACH ROW EXECUTE FUNCTION workweave.reject_history_mutation();
CREATE TRIGGER touch_outbox_events BEFORE UPDATE ON workweave.outbox_events FOR EACH ROW EXECUTE FUNCTION workweave.touch_revision();
CREATE TRIGGER preserve_delivery_attempts BEFORE UPDATE OR DELETE ON workweave.delivery_attempts FOR EACH ROW EXECUTE FUNCTION workweave.reject_history_mutation();
CREATE TRIGGER touch_operations BEFORE UPDATE ON workweave.operations FOR EACH ROW EXECUTE FUNCTION workweave.touch_revision();
CREATE TRIGGER touch_scenario_catalog BEFORE UPDATE ON workweave.scenario_catalog FOR EACH ROW EXECUTE FUNCTION workweave.touch_revision();
CREATE TRIGGER touch_import_runs BEFORE UPDATE ON workweave.import_runs FOR EACH ROW EXECUTE FUNCTION workweave.touch_revision();
CREATE TRIGGER touch_demo_sessions BEFORE UPDATE ON workweave.demo_sessions FOR EACH ROW EXECUTE FUNCTION workweave.touch_revision();
CREATE TRIGGER touch_demo_persona_grants BEFORE UPDATE ON workweave.demo_persona_grants FOR EACH ROW EXECUTE FUNCTION workweave.touch_revision();

-- The workspace scenario pointer must stay inside its organization/workspace.
ALTER TABLE workweave.workspaces ADD CONSTRAINT workspace_scenario_scope_fk
    FOREIGN KEY (organization_id, workspace_id, scenario_id)
    REFERENCES workweave.scenario_catalog (organization_id, workspace_id, scenario_id)
    DEFERRABLE INITIALLY IMMEDIATE;

-- Approved content does not become editable merely because its status is changed.
CREATE FUNCTION workweave.protect_approved_content() RETURNS trigger LANGUAGE plpgsql AS $body$
BEGIN
    IF (TG_TABLE_NAME = 'knowledge_document_versions' AND OLD.approval_status = 'APPROVED') THEN
        IF NEW.approval_status IS DISTINCT FROM OLD.approval_status OR NEW.content IS DISTINCT FROM OLD.content OR NEW.document_id IS DISTINCT FROM OLD.document_id OR NEW.version IS DISTINCT FROM OLD.version OR NEW.source_id IS DISTINCT FROM OLD.source_id THEN
            RAISE EXCEPTION 'Create a new document version instead of editing approved content';
        END IF;
    END IF;
    RETURN NEW;
END;
$body$;
CREATE TRIGGER approved_document_content BEFORE UPDATE ON workweave.knowledge_document_versions FOR EACH ROW EXECUTE FUNCTION workweave.protect_approved_content();
CREATE FUNCTION workweave.protect_approved_artifact() RETURNS trigger LANGUAGE plpgsql AS $body$
BEGIN
    IF OLD.status = 'APPROVED' AND (NEW.status IS DISTINCT FROM OLD.status OR NEW.content IS DISTINCT FROM OLD.content OR NEW.artifact_id IS DISTINCT FROM OLD.artifact_id OR NEW.version IS DISTINCT FROM OLD.version OR NEW.source_refs IS DISTINCT FROM OLD.source_refs) THEN
        RAISE EXCEPTION 'Create a new artifact revision instead of editing approved content';
    END IF;
    RETURN NEW;
END;
$body$;
CREATE TRIGGER approved_artifact_content BEFORE UPDATE ON workweave.exit_kt_artifact_revisions FOR EACH ROW EXECUTE FUNCTION workweave.protect_approved_artifact();

-- Embeddings can be refreshed without silently rewriting an approved source excerpt.
CREATE FUNCTION workweave.protect_approved_chunk() RETURNS trigger LANGUAGE plpgsql AS $body$
BEGIN
    IF EXISTS (
        SELECT 1 FROM workweave.knowledge_document_versions v
        WHERE (v.organization_id,v.workspace_id,v.document_version_id) =
              (OLD.organization_id,OLD.workspace_id,OLD.document_version_id)
          AND v.approval_status = 'APPROVED'
    ) AND (NEW.content IS DISTINCT FROM OLD.content
        OR NEW.document_version_id IS DISTINCT FROM OLD.document_version_id
        OR NEW.source_id IS DISTINCT FROM OLD.source_id
        OR NEW.section_path IS DISTINCT FROM OLD.section_path
        OR NEW.source_span IS DISTINCT FROM OLD.source_span
        OR NEW.organization_id IS DISTINCT FROM OLD.organization_id
        OR NEW.workspace_id IS DISTINCT FROM OLD.workspace_id) THEN
        RAISE EXCEPTION 'Re-ingest a new document version instead of editing an approved excerpt';
    END IF;
    RETURN NEW;
END;
$body$;
CREATE TRIGGER approved_chunk_content BEFORE UPDATE ON workweave.knowledge_chunks FOR EACH ROW EXECUTE FUNCTION workweave.protect_approved_chunk();

-- Scoped operational projection. Linked work_items own operational status.
CREATE VIEW workweave.handover_current_items AS
SELECT h.*, COALESCE(w.status, h.work_status) AS effective_work_status
FROM workweave.handover_items h
LEFT JOIN workweave.work_items w
  ON (w.organization_id, w.workspace_id, w.work_item_id) = (h.organization_id, h.workspace_id, h.work_item_id);

-- Approval/currentness are necessary, not sufficient, for retrieval permission.
-- Service must additionally check audience/authorization and mapped curriculum context.
CREATE VIEW workweave.current_approved_knowledge AS
SELECT d.organization_id, d.workspace_id, d.document_id, d.title, v.document_version_id,
       v.version, c.chunk_id, c.section_path, c.content, c.source_id
FROM workweave.knowledge_documents d
JOIN workweave.knowledge_document_versions v
  ON (v.organization_id,v.workspace_id,v.document_id,v.document_version_id) =
     (d.organization_id,d.workspace_id,d.document_id,d.current_version_id)
JOIN workweave.knowledge_chunks c
  ON (c.organization_id,c.workspace_id,c.document_version_id) = (v.organization_id,v.workspace_id,v.document_version_id)
JOIN workweave.source_records s
  ON (s.organization_id,s.workspace_id,s.source_id) = (c.organization_id,c.workspace_id,c.source_id)
JOIN workweave.source_records original_source
  ON (original_source.organization_id,original_source.workspace_id,original_source.source_id) =
     (v.organization_id,v.workspace_id,v.source_id)
LEFT JOIN workweave.knowledge_promotions promotion
  ON (promotion.organization_id,promotion.workspace_id,promotion.document_version_id) =
     (v.organization_id,v.workspace_id,v.document_version_id)
WHERE v.approval_status = 'APPROVED' AND v.temporal_status = 'CURRENT'
  AND (v.effective_at IS NULL OR v.effective_at <= CURRENT_TIMESTAMP)
  AND original_source.revoked_at IS NULL
  AND (original_source.retention_until IS NULL OR original_source.retention_until > CURRENT_TIMESTAMP)
  AND (promotion.promotion_id IS NULL OR promotion.index_status = 'READY')
  AND s.revoked_at IS NULL AND (s.retention_until IS NULL OR s.retention_until > CURRENT_TIMESTAMP)
  AND s.access_partition IN ('ORGANIZATION','TEAM');

-- Deliberately NOT implemented here: application authentication/RLS policy,
-- human approval commands, deterministic progression, outbox execution,
-- source retention/revocation executor, AI checkpoint tables or vector generation.
COMMIT;
