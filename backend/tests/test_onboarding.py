"""Onboarding read paths: GET /onboarding and GET /onboarding/progress (database-backed)."""

import pytest
from sqlalchemy import text

from tests.test_demo_slice import code, open_company, pick


def overview(c) -> dict | None:
    r = c.get("/api/onboarding")
    assert r.status_code == 200, r.text
    return r.json()["data"]


def statuses(ov: dict) -> list[tuple[str, str]]:
    return [(s["name"], s["status"]) for t in ov["topics"] for s in t["subtopics"]]


BASE = {"o": "00000001-0000-4000-8000-000000000001", "w": "00000001-0000-4000-8000-000000000002"}


V34_PATH = [
    ("Find the current procedure", False),
    ("Separate history from evidence", False),
    ("Ask a clearer question", False),
    ("Source-selection checklist", True),
    ("Work-evidence note template", True),
    ("Training checks", True),
    ("Version and publication boundary", True),
]


def test_new_learner_gets_the_sop001_v34_path(client):
    """Machine Fundamentals 1.1: SOP-001 v3.4's ingested topics, Reference aids optional."""
    open_company(client, "northstar", intent="FRESH")
    pick(client, "Sam")
    ov = overview(client)
    assert (ov["curriculum_name"], ov["curriculum_version"]) == ("Machine Fundamentals", "1.1")
    assert [t["name"] for t in ov["topics"]] == ["Fundamentals", "Reference aids"]
    assert [(s["name"], s["optional"]) for t in ov["topics"] for s in t["subtopics"]] == V34_PATH
    assert all(st == "NOT_STARTED" for _, st in statuses(ov))
    assert all(s["objective"] for t in ov["topics"] for s in t["subtopics"])  # every subtopic has an objective
    assert ov["current_subtopic_id"] == ov["topics"][0]["subtopics"][0]["subtopic_id"]
    assert "excluded_document_topic_count" not in ov
    assert ov["session_status"] == "NONE"
    # The real SOP is the source: only the approved, current version (v3.3 and v3.2 are history).
    assert [(v["document_code"], v["version"], v["temporal_status"], v["approval_status"]) for v in ov["source_versions"]] == [("SOP-001", "3.4", "CURRENT", "APPROVED")]


def test_returning_learner_resumes_the_in_progress_subtopic(client):
    open_company(client, "northstar")
    pick(client, "Jamie")
    ov = overview(client)
    assert (ov["curriculum_name"], ov["curriculum_version"]) == ("Machine Fundamentals", "1.1")
    assert statuses(ov) == [("Find the current procedure", "COMPLETED"), ("Separate history from evidence", "IN_PROGRESS")] + [(n, "NOT_STARTED") for n, _ in V34_PATH[2:]]
    current = next(s for t in ov["topics"] for s in t["subtopics"] if s["subtopic_id"] == ov["current_subtopic_id"])
    assert current["name"] == "Separate history from evidence"
    assert ov["saved_at"].startswith("Progress saved")


def test_learner_projection_has_no_private_assessment_data(client):
    open_company(client, "northstar")
    pick(client, "Jamie")
    raw = client.get("/api/onboarding").text.lower()
    for private in ("assessment_criteria", "criteria", "attempt", "hint_policy", "transcript", "turn"):
        assert private not in raw


def test_persona_without_an_assignment_gets_none(client):
    open_company(client, "northstar")
    pick(client, "Alex")
    assert overview(client) is None


def test_each_company_has_its_own_curriculum(client):
    open_company(client, "acme")
    pick(client, "Sam")  # Sam Lim
    assert overview(client)["curriculum_name"] == "Deployment Fundamentals"
    open_company(client, "harbor")
    pick(client, "Nora")
    ov = overview(client)
    assert ov["curriculum_name"] == "Account Support Fundamentals"


def test_persona_must_be_chosen_first(client):
    open_company(client, "northstar", intent="FRESH")
    r = client.get("/api/onboarding")
    assert r.status_code == 409 and code(r) == "GUARD_FAILED"


def test_supervisor_sees_team_progress_by_subtopic_only(client):
    open_company(client, "northstar")
    pick(client, "Morgan")
    r = client.get("/api/onboarding/progress")
    assert r.status_code == 200, r.text
    rows = {row["employee_name"]: row for row in r.json()["data"]}
    assert set(rows) == {"Sam Kim", "Jamie Chen"}
    assert [s["status"] for s in rows["Jamie Chen"]["subtopics"]] == ["COMPLETED", "IN_PROGRESS"] + ["NOT_STARTED"] * 5
    assert set(rows["Jamie Chen"]) == {"employee_name", "curriculum_name", "curriculum_version", "subtopics"}
    me = next(p for p in client.get("/api/personas").json()["data"] if p["first_name"] == "Morgan")
    assert "onboarding.supervise" in me["grants"]


def test_team_progress_requires_an_explicit_grant_not_a_job_title(client):
    open_company(client, "northstar")
    for name in ("Alex", "Sam"):  # Alex is a shift lead; leads don't get supervision implicitly
        pick(client, name)
        r = client.get("/api/onboarding/progress")
        assert r.status_code == 403 and code(r) == "FORBIDDEN"


def test_progress_is_isolated_per_visitor_copy(client, other_client, engine):
    a = open_company(client, "northstar")
    pick(client, "Jamie")
    open_company(other_client, "northstar")
    pick(other_client, "Jamie")
    # Change visitor B's copy directly; visitor A and the pack baseline must not see it.
    other_ws = other_client.get("/api/demo-sessions/current").json()["data"]["workspace_id"]
    with engine.begin() as c:
        c.execute(
            text("UPDATE workweave.employee_learning_progress SET status='COMPLETED', started_at=coalesce(started_at, now()), completed_at=now() WHERE workspace_id=:w"),
            {"w": other_ws},
        )
    assert all(st == "COMPLETED" for _, st in statuses(overview(other_client)))
    assert statuses(overview(client))[1] == ("Separate history from evidence", "IN_PROGRESS")
    with engine.connect() as c:
        base = c.execute(text("SELECT count(*) FROM workweave.employee_learning_progress WHERE workspace_id='00000001-0000-4000-8000-000000000002' AND status='COMPLETED'")).scalar_one()
    assert base == 2  # Jamie's completed subtopic in the baseline (1.0, and carried over to 1.1) is unchanged
    assert a["workspace_id"] != other_ws


def test_materialized_copy_preserves_objective_competencies(client, engine):
    s = open_company(client, "northstar", intent="FRESH")
    with engine.connect() as c:
        missing = c.execute(
            text(
                """SELECT count(*) FROM workweave.learning_objectives lo
                   LEFT JOIN workweave.competencies k ON k.organization_id = lo.organization_id AND k.workspace_id = lo.workspace_id AND k.competency_id = lo.competency_id
                   WHERE lo.workspace_id = :w AND lo.required AND (lo.competency_id IS NULL OR k.competency_id IS NULL)"""
            ),
            {"w": s["workspace_id"]},
        ).scalar_one()
        doc_topics = c.execute(
            text("""SELECT count(*) FROM workweave.curriculum_topics t JOIN workweave.curriculum_sources cs
                    ON cs.organization_id = t.organization_id AND cs.workspace_id = t.workspace_id AND cs.curriculum_id = t.curriculum_id AND cs.document_version_id = t.document_version_id
                    WHERE t.workspace_id=:w"""), {"w": s["workspace_id"]}).scalar_one()
    # Every required objective keeps its competency; document-bound topics are copied with their source link.
    assert missing == 0 and doc_topics == 4  # 1.1's two topics + archived 1.0's two ingested topics


def test_visitor_copy_keeps_the_sop_history_and_current_pointer(client, engine):
    s = open_company(client, "northstar", intent="FRESH")
    with engine.connect() as c:
        versions = c.execute(
            text(
                """SELECT v.version, v.temporal_status, length(v.content) > 10000 AS full_text, d.current_version_id = v.document_version_id AS is_current,
                          v.source_id IS NOT NULL AS has_source
                   FROM workweave.knowledge_document_versions v JOIN workweave.knowledge_documents d
                     ON d.organization_id = v.organization_id AND d.workspace_id = v.workspace_id AND d.document_id = v.document_id
                   WHERE v.workspace_id = :w AND d.document_code = 'SOP-001' ORDER BY v.version"""
            ),
            {"w": s["workspace_id"]},
        ).all()
        mappings = c.execute(text("SELECT count(*) FROM workweave.knowledge_mappings WHERE workspace_id=:w AND entity_type='CURRICULUM_SUBTOPIC'"), {"w": s["workspace_id"]}).scalar_one()
        sources = c.execute(text("SELECT count(*) FROM workweave.curriculum_sources WHERE workspace_id=:w"), {"w": s["workspace_id"]}).scalar_one()
        sections = c.execute(text("SELECT count(*) FROM workweave.knowledge_sections WHERE workspace_id=:w"), {"w": s["workspace_id"]}).scalar_one()
        embedded = c.execute(text("SELECT count(*) FROM workweave.knowledge_chunks WHERE workspace_id=:w AND embedding IS NOT NULL"), {"w": s["workspace_id"]}).scalar_one()
    by_version = {v.version: v for v in versions}
    assert set(by_version) == {"3.2", "3.3", "3.4"}
    assert by_version["3.4"].is_current and by_version["3.4"].full_text and by_version["3.4"].temporal_status == "CURRENT"
    assert by_version["3.3"].temporal_status == "SUPERSEDED" and not by_version["3.3"].is_current
    assert all(v.has_source for v in versions)  # every baseline version has a source record; provenance is copied
    assert mappings == 6  # three subtopics x (v3.3, v3.4), as in repo script 05
    assert (sources, sections, embedded) == (2, 7, 17)  # 1.0 and 1.1 both cite v3.4; its ingestion output is copied


def test_each_company_cites_its_own_current_source(client):
    for company, persona, expected in (("harbor", "Nora", ("BPO-SOP-001", "1.2")), ("acme", "Sam", ("OPS-SOP-001", "1.2"))):
        open_company(client, company)
        pick(client, persona)
        assert [(v["document_code"], v["version"]) for v in overview(client)["source_versions"]] == [expected]
