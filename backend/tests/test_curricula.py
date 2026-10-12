"""Read-only curricula catalog and detail: authorized reads, denial and workspace isolation.

Runs on the disposable workweave_test database, which carries the SOP-001 v3.4 sample (scripts 14
and 15: Machine Fundamentals 1.1 built from the ingested v3.4 topics; 1.0 archived). Extra fixtures
(a pending draft version) are inserted only into visitor runs created by these tests.
"""

import json
import uuid

import pytest
from sqlalchemy import text

from tests.test_demo_slice import code, open_company, pick

PACK_CURRICULUM_WS = "00000001-0000-4000-8000-000000000002"


def reviewer_run(client, key="northstar", reviewer="Morgan") -> str:
    ws = open_company(client, key, intent="FRESH")["workspace_id"]
    pick(client, reviewer)
    return ws


def catalog(client) -> dict:
    r = client.get("/api/curricula")
    assert r.status_code == 200, r.text
    return r.json()["data"]


def link_sources(engine, ws: str) -> dict:
    """The run's Machine Fundamentals 1.1 with its real v3.4 links, plus a PENDING_REVIEW draft version
    linked as SUPPORTS that has one parsed section with no subtopic link."""
    with engine.begin() as c:
        p = {"w": ws}
        p["o"] = c.execute(text("SELECT organization_id FROM workweave.workspaces WHERE workspace_id=:w"), p).scalar_one()
        cur = c.execute(text("SELECT curriculum_id FROM workweave.curricula WHERE workspace_id=:w AND version='1.1'"), p).scalar_one()
        cs, doc, ver = c.execute(text("SELECT curriculum_source_id, document_id, document_version_id FROM workweave.curriculum_sources WHERE workspace_id=:w AND curriculum_id=:c"), {**p, "c": cur}).one()
        src = c.execute(text("SELECT source_id FROM workweave.knowledge_document_versions WHERE document_version_id=:v"), {"v": ver}).scalar_one()
        s1, topic, sub = c.execute(
            text("""SELECT css.section_id, css.topic_id, css.subtopic_id FROM workweave.curriculum_source_sections css
                    JOIN workweave.knowledge_sections ks ON ks.section_id = css.section_id
                    WHERE css.workspace_id=:w AND css.curriculum_id=:c AND ks.section_key='h2:1/h3:1'"""), {**p, "c": cur}).one()
        src2 = c.execute(text("""INSERT INTO workweave.source_records (organization_id, workspace_id, source_type, storage_object, checksum, owner_employee_id, evidence_type, access_partition, metadata)
                                 SELECT organization_id, workspace_id, source_type, storage_object || '#draft', checksum, owner_employee_id, evidence_type, access_partition, metadata
                                 FROM workweave.source_records WHERE source_id = :s RETURNING source_id"""), {"s": src}).scalar_one()
        ver2 = c.execute(text("""INSERT INTO workweave.knowledge_document_versions (organization_id, workspace_id, document_id, version, content, source_id, approval_status, temporal_status)
                                 VALUES (:o, :w, :d, '9.0-draft', 'UNAPPROVED DRAFT BODY', :s, 'PENDING_REVIEW', 'CURRENT') RETURNING document_version_id"""), {**p, "d": doc, "s": src2}).scalar_one()
        cs2 = c.execute(text("""INSERT INTO workweave.curriculum_sources (organization_id, workspace_id, curriculum_id, document_id, document_version_id, relationship_type)
                                VALUES (:o, :w, :c, :d, :v, 'SUPPORTS') RETURNING curriculum_source_id"""), {**p, "c": cur, "d": doc, "v": ver2}).scalar_one()
        s2 = c.execute(text("""INSERT INTO workweave.knowledge_sections (organization_id, workspace_id, document_version_id, section_key, topic_heading, subtopic_heading, topic_order_index, subtopic_order_index)
                               VALUES (:o, :w, :v, 'h2:9/h3:1', 'Draft', 'Unlinked draft section', 9, 1) RETURNING section_id"""), {**p, "v": ver2}).scalar_one()
    return {"curriculum_id": str(cur), "approved_cs": str(cs), "pending_cs": str(cs2), "linked_section": str(s1), "draft_section": str(s2), "subtopic": str(sub), "topic": str(topic), "approved_source": src}


# ---------------------------------------------------------------- authorized reads
def test_reviewer_reads_the_workspace_catalog(client, engine):
    ws = reviewer_run(client)
    ids = link_sources(engine, ws)
    data = catalog(client)
    assert data["receipts"] == [] and data["sample_available"] is False
    by_version = {c["version"]: c for c in data["curricula"]}
    assert set(by_version) == {"1.0", "1.1"}
    assert by_version["1.1"] == {
        "curriculum_id": ids["curriculum_id"],
        "name": "Machine Fundamentals",
        "version": "1.1",
        "status": "PUBLISHED",
        "topic_count": 2,  # Fundamentals, Reference aids (SOP-001 v3.4 H2s)
        "subtopic_count": 7,
        "source_count": 2,  # v3.4 (TEACHES) + the pending draft (SUPPORTS)
        "pending_review_count": 1,
    }
    assert by_version["1.0"]["status"] == "ARCHIVED"  # kept, frozen, no longer assigned


def test_reviewer_reads_detail_exactly_as_stored(client, engine):
    ws = reviewer_run(client)
    ids = link_sources(engine, ws)
    r = client.get(f"/api/curricula/{ids['curriculum_id']}")
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert (d["name"], d["version"], d["status"], d["sources"]) == ("Machine Fundamentals", "1.1", "PUBLISHED", [])
    fundamentals, reference = d["topics"]
    assert (fundamentals["name"], reference["name"]) == ("Fundamentals", "Reference aids")
    assert fundamentals["document_version_id"] and fundamentals["document_version_id"] == reference["document_version_id"]  # bound to v3.4
    assert [s["name"] for s in fundamentals["subtopics"]] == ["Find the current procedure", "Separate history from evidence", "Ask a clearer question"]
    assert [s["name"] for s in reference["subtopics"]] == ["Source-selection checklist", "Work-evidence note template", "Training checks", "Version and publication boundary"]
    obj = fundamentals["subtopics"][0]["objectives"][0]
    assert obj["required"] is True and obj["criteria_version"] == "sop001-v3.4-criteria-draft-1"
    assert "verify_approved_current_version" in json.loads(obj["assessment_criteria"])["required_checks"]
    assert all(not s["objectives"][0]["required"] for s in reference["subtopics"])  # reference aids are optional

    by_id = {s["curriculum_source_id"]: s for s in d["linked_sources"]}
    approved, pending = by_id[ids["approved_cs"]], by_id[ids["pending_cs"]]
    assert (approved["relationship_type"], approved["approval_status"], approved["is_current_version"], approved["source_revoked"]) == ("TEACHES", "APPROVED", True, False)
    assert approved["approved_by"] and approved["approved_at"]
    assert (pending["relationship_type"], pending["approval_status"], pending["is_current_version"], pending["approved_by"]) == ("SUPPORTS", "PENDING_REVIEW", False, None)
    sections = {s["section_id"]: s for s in approved["sections"]}
    assert len(sections) == 7 and all(len(s["links"]) == 1 for s in sections.values())  # every v3.4 section teaches its own subtopic
    assert sections[ids["linked_section"]]["links"] == [{"topic_id": ids["topic"], "subtopic_id": ids["subtopic"], "relationship_type": "TEACHES"}]
    assert [s["links"] for s in pending["sections"]] == [[]]  # no row: reported as unlinked, never guessed
    # Headings only: no document, section or chunk content is ever returned.
    assert "UNAPPROVED DRAFT BODY" not in r.text and '"content"' not in r.text and '"excerpt"' not in r.text


def test_revoked_source_headings_are_withheld(client, engine):
    ws = reviewer_run(client)
    ids = link_sources(engine, ws)
    with engine.begin() as c:
        c.execute(text("UPDATE workweave.source_records SET revoked_at = now() WHERE source_id = :s"), {"s": ids["approved_source"]})
    d = client.get(f"/api/curricula/{ids['curriculum_id']}").json()["data"]
    approved = next(s for s in d["linked_sources"] if s["curriculum_source_id"] == ids["approved_cs"])
    assert approved["source_revoked"] is True and approved["sections"] is None
    assert "Find the current procedure" not in json.dumps(approved)


def test_each_pack_lists_only_its_own_curriculum(client):
    for key, reviewer, name in (("northstar", "Morgan", "Machine Fundamentals"), ("acme", "Morgan", "Deployment Fundamentals"), ("harbor", "Ravi", "Account Support Fundamentals")):
        reviewer_run(client, key, reviewer)
        assert {c["name"] for c in catalog(client)["curricula"]} == {name}


def test_reads_write_nothing(client, engine):
    ws = reviewer_run(client)
    ids = link_sources(engine, ws)
    q = "SELECT (SELECT count(*) FROM workweave.audit_events) + (SELECT count(*) FROM workweave.command_receipts) + (SELECT sum(revision) FROM workweave.curricula)"
    with engine.connect() as c:
        before = c.execute(text(q)).scalar_one()
    catalog(client)
    client.get(f"/api/curricula/{ids['curriculum_id']}")
    with engine.connect() as c:
        assert c.execute(text(q)).scalar_one() == before


# ---------------------------------------------------------------- denial and isolation
def test_personas_without_curriculum_read_are_forbidden(client, engine):
    ws = reviewer_run(client)
    ids = link_sources(engine, ws)
    for persona in ("Jamie", "Alex", "Sam"):  # learner, shift lead, learner
        pick(client, persona)
        for path in ("/api/curricula", f"/api/curricula/{ids['curriculum_id']}"):
            r = client.get(path)
            assert r.status_code == 403 and code(r) == "FORBIDDEN", (persona, path)
            assert "Machine Fundamentals" not in r.text


def test_an_expired_grant_no_longer_authorizes(client, engine):
    ws = reviewer_run(client)
    with engine.begin() as c:
        c.execute(text("UPDATE workweave.permission_grants SET valid_until = now() - interval '1 minute' WHERE workspace_id=:w AND action='curriculum:read'"), {"w": ws})
    assert client.get("/api/curricula").status_code == 403


def test_another_workspaces_curriculum_is_not_found(client, other_client, engine):
    ws_a = reviewer_run(client)
    ids_a = link_sources(engine, ws_a)
    reviewer_run(other_client)  # a second visitor, separate run of the same pack, also a reviewer
    r = other_client.get(f"/api/curricula/{ids_a['curriculum_id']}")
    assert r.status_code == 404 and code(r) == "NOT_FOUND"
    assert ids_a["curriculum_id"] not in [c["curriculum_id"] for c in catalog(other_client)["curricula"]]
    with engine.connect() as c:
        baseline = c.execute(text("SELECT curriculum_id FROM workweave.curricula WHERE workspace_id=:w AND version='1.1'"), {"w": PACK_CURRICULUM_WS}).scalar_one()
    assert other_client.get(f"/api/curricula/{baseline}").status_code == 404  # pack originals aren't readable either
    assert other_client.get(f"/api/curricula/{uuid.uuid4()}").status_code == 404


def test_session_persona_and_input_errors_are_distinct(client):
    assert code(client.get("/api/curricula")) == "SESSION_EXPIRED"  # no session cookie
    open_company(client, "northstar", intent="FRESH")
    r = client.get("/api/curricula")
    assert r.status_code == 409 and code(r) == "GUARD_FAILED"  # no persona chosen yet
    pick(client, "Morgan")
    r = client.get("/api/curricula/not-a-uuid")
    assert r.status_code == 422 and code(r) == "MALFORMED_INPUT"



# ---------------------------------------------------------------- curriculum:read scope
def change_curriculum_read(engine, ws: str, persona: str, assignments: str) -> None:
    """Edit only this persona's curriculum:read grant in this visitor workspace."""
    with engine.begin() as c:
        c.execute(
            text(
                f"""UPDATE workweave.permission_grants g SET {assignments} FROM workweave.employees e
                    WHERE e.employee_id = g.actor_id AND g.workspace_id = :w AND e.first_name = :p AND g.action = 'curriculum:read'"""
            ),
            {"w": ws, "p": persona},
        )


def add_team(engine, ws: str, name: str) -> str:
    with engine.begin() as c:
        org, dept = c.execute(text("SELECT organization_id, department_id FROM workweave.teams WHERE workspace_id=:w LIMIT 1"), {"w": ws}).one()
        return str(c.execute(text("INSERT INTO workweave.teams (organization_id, workspace_id, department_id, name) VALUES (:o, :w, :d, :n) RETURNING team_id"), {"o": org, "w": ws, "d": dept, "n": name}).scalar_one())


def test_a_team_scoped_knowledge_review_grant_alone_is_denied(client, engine):
    """Morgan keeps a valid knowledge:review grant scoped to the Maintenance team but loses curriculum:read."""
    ws = reviewer_run(client)
    with engine.connect() as c:
        scope = c.execute(text("""SELECT g.resource_scope FROM workweave.permission_grants g JOIN workweave.employees e ON e.employee_id = g.actor_id
                                  WHERE g.workspace_id=:w AND e.first_name='Morgan' AND g.action='knowledge:review'"""), {"w": ws}).scalar_one()
    assert "team_id" in scope
    with engine.begin() as c:
        c.execute(text("""DELETE FROM workweave.permission_grants g USING workweave.employees e
                          WHERE e.employee_id = g.actor_id AND g.workspace_id=:w AND e.first_name='Morgan' AND g.action='curriculum:read'"""), {"w": ws})
    for path in ("/api/curricula", f"/api/curricula/{uuid.uuid4()}"):
        r = client.get(path)
        assert r.status_code == 403 and code(r) == "FORBIDDEN", path
    pick(client, "Morgan")  # display grants follow the authoritative grants
    assert "curriculum.read" not in next(p for p in client.get("/api/personas").json()["data"] if p["first_name"] == "Morgan")["grants"]


def test_a_valid_workspace_scoped_curriculum_read_grant_succeeds_across_teams(client, engine):
    """Workspace scope means every curriculum in the workspace, whatever team its learners are on."""
    ws = reviewer_run(client)
    add_team(engine, ws, "Quality")  # a second team with no assignments
    data = catalog(client)
    assert [(c["name"], c["version"]) for c in data["curricula"]] == [("Machine Fundamentals", "1.0"), ("Machine Fundamentals", "1.1")]
    assert client.get(f"/api/curricula/{data['curricula'][0]['curriculum_id']}").status_code == 200
    me = next(p for p in client.get("/api/personas").json()["data"] if p["first_name"] == "Morgan")
    assert "curriculum.read" in me["grants"]


def test_curriculum_read_without_explicit_workspace_scope_is_denied(client, engine):
    ws = reviewer_run(client)
    quality = add_team(engine, ws, "Quality")
    cases = {
        "team-scoped": f"""resource_scope = '{{"scope": "WORKSPACE", "team_id": "{quality}"}}'::jsonb""",
        "no scope marker": """resource_scope = '{"synthetic": true}'::jsonb""",
        "expired": "valid_until = now() - interval '1 minute', valid_from = now() - interval '1 day'",
        "not yet valid": "valid_from = now() + interval '1 day', valid_until = NULL",
    }
    with engine.connect() as c:
        original = c.execute(text("""SELECT g.resource_scope, g.valid_from, g.valid_until FROM workweave.permission_grants g JOIN workweave.employees e ON e.employee_id = g.actor_id
                                     WHERE g.workspace_id=:w AND e.first_name='Morgan' AND g.action='curriculum:read'"""), {"w": ws}).one()
    for label, change in cases.items():
        change_curriculum_read(engine, ws, "Morgan", change)
        r = client.get("/api/curricula")
        assert r.status_code == 403 and code(r) == "FORBIDDEN", label
        with engine.begin() as c:  # restore before the next case
            c.execute(
                text("""UPDATE workweave.permission_grants g SET resource_scope = CAST(:s AS jsonb), valid_from = :f, valid_until = :u
                        FROM workweave.employees e WHERE e.employee_id = g.actor_id AND g.workspace_id=:w AND e.first_name='Morgan' AND g.action='curriculum:read'"""),
                {"s": json.dumps(original.resource_scope), "f": original.valid_from, "u": original.valid_until, "w": ws},
            )
        assert client.get("/api/curricula").status_code == 200, f"restore after {label}"


def test_only_the_intended_coordinators_hold_curriculum_read(client):
    expected = {"northstar": "Morgan", "acme": "Morgan", "harbor": "Ravi"}
    for key, first in expected.items():
        open_company(client, key, intent="FRESH")
        holders = [p["first_name"] for p in client.get("/api/personas").json()["data"] if "curriculum.read" in p["grants"]]
        assert holders == [first], key
