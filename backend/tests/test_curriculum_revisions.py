"""Curriculum revisions (ADR-050): a published curriculum changes only through a draft revision."""

from sqlalchemy import text

from tests.test_companion_commands import emp, fresh
from tests.test_curriculum_authoring import DOC, H, create, detail, ingest, k, review, upload  # noqa: F401 (fixture)
from tests.test_demo_slice import code


def publish(client, c: dict):
    return client.post(f"/api/curricula/{c['curriculum_id']}/publish", json={"idempotency_key": k(), "expected_revision": c["revision"]}, headers=H)


def objectives(client, cid: str) -> dict:
    c = detail(client, cid)
    for t in c["topics"]:
        for s in t["subtopics"]:
            if not s["objectives"] and not s.get("left_out"):
                c = detail(client, cid)
                r = client.put(f"/api/curricula/{cid}/subtopics/{s['subtopic_id']}/objective",
                               json={"idempotency_key": k(), "expected_revision": c["revision"], "description": f"Explain {s['name']}.", "assessment_criteria": "States the steps."}, headers=H)
                assert r.status_code == 200, r.text
    return detail(client, cid)


def published(client) -> dict:
    c = create(client)
    assert upload(client, c).status_code == 200
    c = detail(client, c["curriculum_id"])
    assert review(client, c, reviewed_exact_version=True).status_code == 200
    c = objectives(client, c["curriculum_id"])
    assert publish(client, c).status_code == 200
    return detail(client, c["curriculum_id"])


def revise(client, c: dict) -> dict:
    r = client.post(f"/api/curricula/{c['curriculum_id']}/revisions", json={"idempotency_key": k()}, headers=H)
    assert r.status_code == 200, r.text
    return detail(client, r.json()["data"]["curriculum_id"])


def names(c: dict) -> list[str]:
    return [f"{t['name']} › {s['name']}" for t in c["topics"] for s in t["subtopics"] if not s.get("left_out")]


def test_a_revision_copies_the_published_version_and_is_ready_to_publish(client, ingest):  # noqa: F811
    fresh(client, "Morgan")
    v1 = published(client)
    v2 = revise(client, v1)
    assert v2["status"] == "DRAFT" and v2["version"] == "1.1" and v2["name"] == v1["name"]
    assert names(v2) == names(v1) and {t["topic_id"] for t in v2["topics"]}.isdisjoint({t["topic_id"] for t in v1["topics"]})  # copies, new IDs
    assert all(s["objectives"] for t in v2["topics"] for s in t["subtopics"])  # objectives came along
    assert [s["document_version_id"] for s in v2["linked_sources"]] == [s["document_version_id"] for s in v1["linked_sources"]]
    assert all(x["passed"] for x in v2["readiness"])  # already-ingested versions count
    assert any(s["links"] for s in v2["linked_sources"][0]["sections"])  # section links re-pointed to the copies
    again = client.post(f"/api/curricula/{v1['curriculum_id']}/revisions", json={"idempotency_key": k()}, headers=H).json()["data"]
    assert again["curriculum_id"] == v2["curriculum_id"] and again["existing"]  # one open draft revision
    assert detail(client, v1["curriculum_id"])["draft_revision"]["version"] == "1.1"
    assert code(client.post(f"/api/curricula/{v2['curriculum_id']}/revisions", json={"idempotency_key": k()}, headers=H)) == "GUARD_FAILED"  # a draft is edited directly


def test_a_newer_document_version_replaces_the_old_one_and_objectives_follow_their_headings(client, ingest):  # noqa: F811
    fresh(client, "Morgan")
    v2 = revise(client, published(client))
    old_version = v2["linked_sources"][0]["document_version_id"]
    newer = DOC.replace("### 2. Starting the line", "### 2. Ramping up the line").replace("## 2. Shutdown", "## 2. Shutdown\n\n### 0. Lockout first\nLock out before any stop.\n")
    newer = newer.replace("### 0. Lockout first", "### 1. Lockout first").replace("### 1. Normal stop", "### 2. Normal stop")
    before = names(v2)
    assert upload(client, v2, version="1.1", content=newer).status_code == 200
    v2 = detail(client, v2["curriculum_id"])
    assert sorted(s["version"] for s in v2["linked_sources"]) == ["1.0", "1.1"] and names(v2) == before  # the old path stays until the new one is ready
    new_src = next(s for s in v2["linked_sources"] if s["version"] == "1.1")
    r = client.post(f"/api/curricula/{v2['curriculum_id']}/sources/{new_src['curriculum_source_id']}/review",
                    json={"idempotency_key": k(), "expected_revision": v2["revision"], "decision": "APPROVED", "reviewed_exact_version": True}, headers=H)
    assert r.status_code == 200, r.text
    v2 = detail(client, v2["curriculum_id"])
    assert [s["version"] for s in v2["linked_sources"]] == ["1.1"] and all(s["document_version_id"] != old_version for s in v2["linked_sources"])  # replaced
    subs = {s["name"]: s for t in v2["topics"] for s in t["subtopics"]}
    assert subs["Pre-start checks"]["objectives"] and subs["Normal stop"]["objectives"]  # same heading: carried over
    assert not subs["Ramping up the line"]["objectives"] and not subs["Lockout first"]["objectives"]  # renamed or new: needs one
    assert next(x for x in v2["readiness"] if x["key"] == "OBJECTIVES")["passed"] is False


def test_the_path_can_leave_out_subtopics_and_reorder_topics(client, ingest):  # noqa: F811
    fresh(client, "Morgan")
    v2 = revise(client, published(client))
    start = next(s for t in v2["topics"] for s in t["subtopics"] if s["name"] == "Starting the line")
    r = client.post(f"/api/curricula/{v2['curriculum_id']}/subtopics/{start['subtopic_id']}/inclusion", json={"idempotency_key": k(), "expected_revision": v2["revision"], "included": False}, headers=H)
    assert r.status_code == 200, r.text
    v2 = detail(client, v2["curriculum_id"])
    assert "Line start-up › Starting the line" not in names(v2)
    assert next(s for t in v2["topics"] for s in t["subtopics"] if s["subtopic_id"] == start["subtopic_id"])["left_out"]  # still shown to the editor
    assert next(x for x in v2["readiness"] if x["key"] == "PATH")["detail"] == "2 topics, 2 subtopics"
    shutdown = next(t for t in v2["topics"] if t["name"] == "Shutdown")
    r = client.post(f"/api/curricula/{v2['curriculum_id']}/topics/{shutdown['topic_id']}/move", json={"idempotency_key": k(), "expected_revision": v2["revision"], "direction": "UP"}, headers=H)
    assert r.status_code == 200, r.text
    v2 = detail(client, v2["curriculum_id"])
    assert [t["name"] for t in v2["topics"]] == ["Shutdown", "Line start-up"]
    assert code(client.post(f"/api/curricula/{v2['curriculum_id']}/topics/{shutdown['topic_id']}/move", json={"idempotency_key": k(), "expected_revision": v2["revision"], "direction": "UP"}, headers=H)) == "GUARD_FAILED"
    src = v2["linked_sources"][0]
    r = client.request("DELETE", f"/api/curricula/{v2['curriculum_id']}/sources/{src['curriculum_source_id']}", json={"idempotency_key": k(), "expected_revision": v2["revision"]}, headers=H)
    assert r.status_code == 200, r.text
    v2 = detail(client, v2["curriculum_id"])
    assert v2["linked_sources"] == [] and v2["topics"] == []


def test_publishing_a_revision_archives_the_old_version_and_moves_only_unstarted_assignments(client, engine, ingest):  # noqa: F811
    ws = fresh(client, "Morgan")
    v1 = published(client)
    with engine.begin() as c:  # two people assigned v1.0: Jamie has started, Sam hasn't
        org = c.execute(text("SELECT organization_id FROM workweave.workspaces WHERE workspace_id=:w"), {"w": ws}).scalar_one()
        la = {}
        for who in ("Jamie", "Sam"):
            ca = c.execute(text("""INSERT INTO workweave.curriculum_assignments (organization_id, workspace_id, curriculum_id, employee_id, assigned_at, status)
                                   VALUES (:o, :w, :c, :e, now(), 'ACTIVE') RETURNING assignment_id"""), {"o": org, "w": ws, "e": emp(engine, ws, who), "c": v1["curriculum_id"]}).scalar_one()
            la[who] = c.execute(text("""INSERT INTO workweave.learning_assignments (organization_id, workspace_id, employee_id, curriculum_id, originating_assignment_id, assignment_kind, status)
                                        VALUES (:o, :w, :e, :c, :ca, 'INITIAL', 'ACTIVE') RETURNING learning_assignment_id"""),
                                {"o": org, "w": ws, "e": emp(engine, ws, who), "c": v1["curriculum_id"], "ca": ca}).scalar_one()
        sub = v1["topics"][0]["subtopics"][0]["subtopic_id"]
        c.execute(text("""INSERT INTO workweave.employee_learning_progress (organization_id, workspace_id, employee_id, learning_assignment_id, subtopic_id, status, started_at)
                          VALUES (:o, :w, :e, :la, :s, 'IN_PROGRESS', now())"""), {"o": org, "w": ws, "e": emp(engine, ws, "Jamie"), "la": la["Jamie"], "s": sub})
    v2 = revise(client, v1)
    assert publish(client, v2).status_code == 200
    assert detail(client, v1["curriculum_id"])["status"] == "ARCHIVED" and detail(client, v2["curriculum_id"])["status"] == "PUBLISHED"
    with engine.connect() as c:
        on = {who: str(c.execute(text("SELECT curriculum_id FROM workweave.learning_assignments WHERE learning_assignment_id=:l"), {"l": la[who]}).scalar_one()) for who in la}
    assert on == {"Jamie": v1["curriculum_id"], "Sam": v2["curriculum_id"]}  # started stays; not started moves
    assert {v["version"]: v["status"] for v in detail(client, v2["curriculum_id"])["other_versions"]} == {"1.0": "ARCHIVED"}


def test_only_managers_create_revisions(client, ingest):  # noqa: F811
    from tests.test_demo_slice import pick

    fresh(client, "Morgan")
    v1 = published(client)
    pick(client, "Jamie")
    assert code(client.post(f"/api/curricula/{v1['curriculum_id']}/revisions", json={"idempotency_key": k()}, headers=H)) == "FORBIDDEN"
