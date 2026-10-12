"""Onboarding tutor turns with an injected deterministic engine (disposable workweave_test only).

Covers a cited teaching turn, a qualifying answer, insufficient answers, duplicate retry, stale
revision, invalid/cross-workspace/revoked citations, engine failure, refresh/resume, supervisor
privacy and the default not-connected path.
"""

import uuid

import pytest
from sqlalchemy import text

from app.config import get_settings
from app.integrations import tutor as tutor_mod
from app.integrations.tutor import TutorResult, install_test_tutor
from tests.test_demo_slice import code, open_company, pick
from tests.tutor_fakes import ScriptedTutor, answer, check_for, cite, ok, teaching

def some_unmet(L: dict) -> dict:
    return {**L["all_met"], L["checks"][-1]: False}


@pytest.fixture()
def tutor(engine):
    t = ScriptedTutor(engine)
    install_test_tutor(t)
    yield t
    install_test_tutor(None)


def q(engine, sql: str, **p):
    with engine.connect() as c:
        return c.execute(text(sql), p).scalar_one()


def add_sources(engine, ws: str) -> dict:
    """A parsed section and an approved chunk of the run's current SOP-001 v3.4 (the session's permitted source)."""
    with engine.begin() as c:
        org = c.execute(text("SELECT organization_id FROM workweave.workspaces WHERE workspace_id=:w"), {"w": ws}).scalar_one()
        ver, src = c.execute(
            text("""SELECT v.document_version_id, v.source_id FROM workweave.knowledge_documents d
                    JOIN workweave.knowledge_document_versions v ON v.document_version_id = d.current_version_id
                    WHERE d.workspace_id=:w AND d.document_code='SOP-001'"""), {"w": ws}).one()
        old = c.execute(text("""SELECT v.document_version_id FROM workweave.knowledge_document_versions v JOIN workweave.knowledge_documents d USING (document_id)
                                WHERE v.workspace_id=:w AND d.document_code='SOP-001' AND v.document_version_id <> d.current_version_id LIMIT 1"""), {"w": ws}).scalar()
        # The run's own copy of the real v3.4 ingestion output (scripts 14/15): sections, chunks and embeddings.
        sec = c.execute(text("SELECT section_id FROM workweave.knowledge_sections WHERE workspace_id=:w AND document_version_id=:v AND section_key='h2:1/h3:1'"), {"w": ws, "v": ver}).scalar_one()
        other_sec = c.execute(text("SELECT section_id FROM workweave.knowledge_sections WHERE workspace_id=:w AND document_version_id=:v AND section_key='h2:2/h3:1'"), {"w": ws, "v": ver}).scalar_one()
        chunk, chunk_text = c.execute(text("SELECT chunk_id, content FROM workweave.knowledge_chunks WHERE workspace_id=:w AND source_section_id=:s AND embedding IS NOT NULL ORDER BY chunk_index LIMIT 1"), {"w": ws, "s": sec}).one()
        # A section that really belongs to the superseded version (so only the current-version rule rejects it).
        old_sec = c.execute(text("""INSERT INTO workweave.knowledge_sections (organization_id, workspace_id, document_version_id, section_key, topic_heading, subtopic_heading, topic_order_index, subtopic_order_index)
                                    VALUES (:o, :w, :v, 'h2:1/h3:1', 'Fundamentals', 'Old wording', 1, 1) RETURNING section_id"""), {"o": org, "w": ws, "v": old}).scalar_one()
        # An approved, current document in the same workspace that isn't a source of this curriculum.
        approver = c.execute(text("SELECT employee_id FROM workweave.employees WHERE workspace_id=:w LIMIT 1"), {"w": ws}).scalar_one()
        src2 = c.execute(text("""INSERT INTO workweave.source_records (organization_id, workspace_id, source_type, storage_object, checksum, owner_employee_id, evidence_type, access_partition, metadata)
                                 SELECT organization_id, workspace_id, source_type, storage_object || '#unrelated', checksum, owner_employee_id, evidence_type, access_partition, metadata
                                 FROM workweave.source_records WHERE source_id = :s RETURNING source_id"""), {"s": src}).scalar_one()
        doc2 = c.execute(text("INSERT INTO workweave.knowledge_documents (organization_id, workspace_id, document_code, title, document_type) VALUES (:o, :w, 'SOP-099', 'Unrelated procedure', 'SOP') RETURNING document_id"), {"o": org, "w": ws}).scalar_one()
        ver2 = c.execute(text("""INSERT INTO workweave.knowledge_document_versions (organization_id, workspace_id, document_id, version, content, source_id, approval_status, temporal_status, approved_by_employee_id, approved_at)
                                 VALUES (:o, :w, :d, '1.0', 'Unrelated', :s, 'APPROVED', 'CURRENT', :e, now()) RETURNING document_version_id"""), {"o": org, "w": ws, "d": doc2, "s": src2, "e": approver}).scalar_one()
        c.execute(text("UPDATE workweave.knowledge_documents SET current_version_id=:v WHERE document_id=:d"), {"v": ver2, "d": doc2})
        unrelated_sec = c.execute(text("""INSERT INTO workweave.knowledge_sections (organization_id, workspace_id, document_version_id, section_key, topic_heading, subtopic_heading, topic_order_index, subtopic_order_index)
                                          VALUES (:o, :w, :v, 'h2:1/h3:1', 'Other', 'Other', 1, 1) RETURNING section_id"""), {"o": org, "w": ws, "v": ver2}).scalar_one()
    return {"org": org, "version": ver, "source": src, "section": sec, "other_section": other_sec, "chunk": chunk, "chunk_text": chunk_text, "old_version": old, "old_section": old_sec,
            "unrelated_version": ver2, "unrelated_section": unrelated_sec}


def learner(client, engine, who: str = "Sam") -> dict:
    ws = open_company(client, "northstar", intent="FRESH")["workspace_id"]
    pick(client, who)
    v = client.post("/api/onboarding/sessions").json()["data"]
    src = add_sources(engine, ws)
    with engine.connect() as c:
        sub, obj, cv, criteria = c.execute(
            text("""SELECT s.current_subtopic_id, lo.objective_id, lo.criteria_version, lo.assessment_criteria FROM workweave.learning_sessions s
                    JOIN workweave.learning_objectives lo ON lo.subtopic_id = s.current_subtopic_id WHERE s.learning_session_id=:s"""), {"s": v["learning_session_id"]}).one()
    checks = criteria["required_checks"]
    return {"ws": ws, "sid": v["learning_session_id"], "rev": v["revision"], "subtopic": sub, "objective": obj, "cv": cv, "checks": checks, "all_met": dict.fromkeys(checks, True), **src}


def send(client, L: dict, msg: str, rev: int | None = None, cid: str | None = None):
    r = client.post(f"/api/onboarding/sessions/{L['sid']}/turns", json={"client_turn_id": cid or str(uuid.uuid4()), "expected_revision": rev if rev is not None else L["rev"], "text": msg, "input_kind": "TEXT"})
    if r.status_code == 200:
        L["rev"] = r.json()["data"]["revision"]
    return r


def progress(engine, L: dict, subtopic=None) -> str:
    return q(engine, """SELECT p.status FROM workweave.employee_learning_progress p JOIN workweave.learning_sessions s ON s.learning_assignment_id = p.learning_assignment_id
                        WHERE s.learning_session_id=:s AND p.subtopic_id=:st""", s=L["sid"], st=subtopic or L["subtopic"])


def counts(engine, L: dict) -> dict:
    s = {"s": L["sid"]}
    return {
        "committed": q(engine, "SELECT count(*) FROM workweave.learning_turns WHERE learning_session_id=:s AND stage='COMMITTED'", **s),
        "attempts": q(engine, "SELECT count(*) FROM workweave.learning_assessment_attempts a JOIN workweave.learning_turns t ON t.turn_id = a.turn_id WHERE t.learning_session_id=:s", **s),
        "evidence": q(engine, "SELECT count(*) FROM workweave.objective_evidence e JOIN workweave.learning_sessions s ON s.learning_assignment_id = e.learning_assignment_id WHERE s.learning_session_id=:s", **s),
        "events": q(engine, "SELECT count(*) FROM workweave.employee_learning_events WHERE learning_session_id=:s", **s),
        "revision": q(engine, "SELECT revision FROM workweave.learning_sessions WHERE learning_session_id=:s", **s),
    }


def teach_with_check(client, tutor, L: dict) -> str:
    qid = uuid.uuid4()
    tutor.then(ok(teaching([cite(L["version"], L["section"], L["chunk"])], check_for(L["objective"], L["cv"], qid))))
    r = send(client, L, "How do I know which procedure to use?")
    assert r.status_code == 200, r.text
    return str(qid)


# ---------------------------------------------------------------- teaching and assessment
def test_a_cited_teaching_turn_commits_reply_check_and_starts_the_subtopic(client, engine, tutor):
    L = learner(client, engine)
    rev0 = L["rev"]
    assert progress(engine, L) == "NOT_STARTED"
    qid = teach_with_check(client, tutor, L)
    v = client.get(f"/api/onboarding/sessions/{L['sid']}").json()["data"]
    assert v["revision"] == rev0 + 1 and v["tutor"]["status"] == "ok"
    learner_msg, reply = v["transcript"]
    assert (learner_msg["sender"], learner_msg["text"]) == ("EMPLOYEE", "How do I know which procedure to use?")
    assert reply["sender"] == "AI" and reply["provenance"] == "TUTOR_ENGINE" and reply["kind"] == "TEACHING"
    (c,) = reply["citations"]
    assert c["label"] == "SOP-001 v3.4 · h2:1/h3:1" and c["excerpt"]["text"] == L["chunk_text"]  # the real ingested v3.4 chunk
    assert c["excerpt"]["heading_path"] == ["Fundamentals", "Find the current procedure"]
    assert v["pending_check"]["question_id"] == qid and v["awaiting_continue"] is False
    assert progress(engine, L) == "IN_PROGRESS"
    # The engine got server-established scope: permitted current version, objectives with reviewed checks.
    ctx = tutor.contexts[0]
    assert str(L["version"]) in ctx.permitted_document_version_ids and ctx.objectives[0].required_checks == L["checks"]
    with engine.connect() as cn:
        events = [r[0] for r in cn.execute(text("SELECT event_type FROM workweave.employee_learning_events WHERE learning_session_id=:s ORDER BY created_at, event_type"), {"s": L["sid"]})]
    assert sorted(events) == ["COMPREHENSION_QUESTION", "EXPLANATION_PROVIDED", "SUBTOPIC_STARTED"]


def test_one_qualifying_answer_completes_only_the_current_subtopic(client, engine, tutor):
    L = learner(client, engine)
    qid = teach_with_check(client, tutor, L)
    tutor.then(ok(answer(qid, L["objective"], L["cv"], "CORRECT", L["all_met"])))
    r = send(client, L, "Follow the current approved version and note what's unknown.")
    assert r.status_code == 200, r.text
    v = r.json()["data"]
    assert progress(engine, L) == "COMPLETED"
    assert v["awaiting_continue"] is True and v["pending_check"] is None
    assert v["transcript"][-2]["assessment"]["outcome"] == "CORRECT"
    assert v["transcript"][-1]["kind"] == "COMPLETION" and v["transcript"][-1]["provenance"] == "BACKEND_RECORD"
    nxt = [s for t in v["overview"]["topics"] for s in t["subtopics"]][1]
    assert nxt["status"] == "NOT_STARTED"  # the next item waits for explicit continuation
    assert q(engine, "SELECT count(*) FROM workweave.objective_evidence e JOIN workweave.learning_sessions s ON s.learning_assignment_id = e.learning_assignment_id WHERE s.learning_session_id=:s AND e.outcome='PASSED' AND e.accepted_at IS NOT NULL", s=L["sid"]) == 1
    assert q(engine, "SELECT count(*) FROM workweave.employee_learning_events WHERE learning_session_id=:s AND event_type='SUBTOPIC_COMPLETED'", s=L["sid"]) == 1


@pytest.mark.parametrize(
    "label,build,evidence",
    [
        ("partial", lambda qid, L: answer(qid, L["objective"], L["cv"], "PARTIAL", some_unmet(L)), "NOT_PASSED"),
        ("incorrect", lambda qid, L: answer(qid, L["objective"], L["cv"], "INCORRECT", dict.fromkeys(L["checks"], False)), "NOT_PASSED"),
        ("correct but hinted", lambda qid, L: answer(qid, L["objective"], L["cv"], "CORRECT", L["all_met"], hints_used=1), "NOT_PASSED"),
        ("unassessable", lambda qid, L: answer(qid, L["objective"], L["cv"], "UNASSESSABLE", {}), "UNASSESSABLE"),
        ("'I understand' with model confidence, no assessment", lambda qid, L: teaching([cite(L["version"], L["section"])], metadata={"confidence": "0.99", "learner_says": "I understand"}), None),
    ],
)
def test_insufficient_answers_never_advance_progress(client, engine, tutor, label, build, evidence):
    L = learner(client, engine)
    qid = teach_with_check(client, tutor, L)
    tutor.then(ok(build(qid, L)))
    r = send(client, L, "I understand, next please.")
    assert r.status_code == 200, (label, r.text)
    assert progress(engine, L) == "IN_PROGRESS", label
    v = r.json()["data"]
    assert v["awaiting_continue"] is False and v["pending_check"]["question_id"] == qid, label  # the check stays open
    got = q(engine, "SELECT string_agg(e.outcome, ',') FROM workweave.objective_evidence e JOIN workweave.learning_sessions s ON s.learning_assignment_id = e.learning_assignment_id WHERE s.learning_session_id=:s", s=L["sid"])
    assert got == evidence, label


@pytest.mark.parametrize(
    "label,build",
    [
        ("CORRECT with an unmet criterion", lambda qid, L: answer(qid, L["objective"], L["cv"], "CORRECT", some_unmet(L))),
        ("CORRECT missing a reviewed criterion", lambda qid, L: answer(qid, L["objective"], L["cv"], "CORRECT", {L["checks"][0]: True})),
        ("CORRECT with an invented criterion", lambda qid, L: answer(qid, L["objective"], L["cv"], "CORRECT", {**L["all_met"], "sounds_confident": True})),
        ("assessment of a question that isn't pending", lambda qid, L: answer(uuid.uuid4(), L["objective"], L["cv"], "CORRECT", L["all_met"])),
        ("stale criteria version", lambda qid, L: answer(qid, L["objective"], "old-criteria", "CORRECT", L["all_met"])),
        ("unknown field (e.g. completed=true)", lambda qid, L: {**answer(qid, L["objective"], L["cv"], "CORRECT", L["all_met"]), "completed": True}),
        ("teaching without a citation", lambda qid, L: teaching([])),
    ],
)
def test_proposed_outcomes_that_fail_validation_store_nothing(client, engine, tutor, label, build):
    L = learner(client, engine)
    qid = teach_with_check(client, tutor, L)
    before = counts(engine, L)
    tutor.then(ok(build(qid, L)))
    r = send(client, L, "Follow the current approved version.")
    assert r.status_code == 503 and code(r) == "DEPENDENCY_UNAVAILABLE", (label, r.text)
    assert counts(engine, L) == before, label
    assert progress(engine, L) == "IN_PROGRESS", label


def test_an_assessment_without_any_pending_question_is_rejected(client, engine, tutor):
    L = learner(client, engine)
    tutor.then(ok(answer(uuid.uuid4(), L["objective"], L["cv"], "CORRECT", L["all_met"])))
    before = counts(engine, L)
    assert send(client, L, "I already know this.").status_code == 503
    assert counts(engine, L) == before and progress(engine, L) == "NOT_STARTED"


# ---------------------------------------------------------------- idempotency and revisions
def test_a_duplicate_retry_returns_the_committed_turn_without_a_second_engine_call(client, engine, tutor):
    L = learner(client, engine)
    cid, rev = str(uuid.uuid4()), L["rev"]
    tutor.then(ok(teaching([cite(L["version"], L["section"])])))
    first = send(client, L, "What's the current version?", rev=rev, cid=cid)
    again = send(client, L, "What's the current version?", rev=rev, cid=cid)
    assert first.status_code == again.status_code == 200
    assert again.json()["data"]["transcript"] == first.json()["data"]["transcript"]
    assert len(tutor.contexts) == 1 and counts(engine, L)["committed"] == 1
    other = send(client, L, "A different message", rev=rev, cid=cid)
    assert other.status_code == 422 and code(other) == "MALFORMED_INPUT"


def test_a_stale_revision_is_rejected_before_the_engine_runs(client, engine, tutor):
    L = learner(client, engine)
    r = send(client, L, "Hello", rev=L["rev"] - 1 if L["rev"] > 1 else L["rev"] + 5)
    assert r.status_code == 409 and code(r) == "REVISION_CONFLICT"
    assert tutor.contexts == []


def test_a_revision_change_during_the_engine_call_commits_nothing(client, engine, tutor):
    L = learner(client, engine)

    def concurrent_change(ctx):
        with engine.begin() as c:  # e.g. another tab paused and resumed meanwhile
            c.execute(text("UPDATE workweave.learning_sessions SET status = status WHERE learning_session_id=:s"), {"s": L["sid"]})
        return ok(teaching([cite(L["version"], L["section"])], check_for(L["objective"], L["cv"])))

    tutor.then(concurrent_change)
    before = counts(engine, L)
    r = send(client, L, "Hello")
    assert r.status_code == 409 and code(r) == "REVISION_CONFLICT"
    after = counts(engine, L)
    assert {k: after[k] for k in ("committed", "attempts", "evidence", "events")} == {k: before[k] for k in ("committed", "attempts", "evidence", "events")}
    assert progress(engine, L) == "NOT_STARTED"


# ---------------------------------------------------------------- citations
def test_invalid_cross_workspace_superseded_and_revoked_citations_are_rejected(client, other_client, engine, tutor):
    L = learner(client, engine)
    M = learner(other_client, engine, "Jamie")  # another visitor's workspace
    cases = {
        "unknown version": cite(uuid.uuid4(), uuid.uuid4()),
        "another workspace's version": cite(M["version"], M["section"]),
        "this version, another workspace's section": cite(L["version"], M["section"]),
        "superseded version (v3.3), with its own section": cite(L["old_version"], L["old_section"]),
        "approved current document that isn't a curriculum source": cite(L["unrelated_version"], L["unrelated_section"]),
        "chunk outside the cited section": cite(L["version"], L["other_section"], L["chunk"]),
    }
    for label, c in cases.items():
        before = counts(engine, L)
        tutor.then(ok(teaching([c])))
        r = send(client, L, f"Case: {label}")
        assert r.status_code == 503, (label, r.text)
        assert counts(engine, L) == before, label

    # Revoked while the engine was replying: the commit-time recheck rejects it.
    def revoke_then_cite(ctx):
        with engine.begin() as cn:
            cn.execute(text("UPDATE workweave.source_records SET revoked_at = now() WHERE source_id=:s"), {"s": L["source"]})
        return ok(teaching([cite(L["version"], L["section"])]))  # section only: the version rule must catch it

    tutor.then(revoke_then_cite)
    assert send(client, L, "And now?").status_code == 503
    assert counts(engine, L)["committed"] == 0


def test_a_failed_turn_can_be_retried_with_the_same_id(client, engine, tutor):
    L = learner(client, engine)
    cid = str(uuid.uuid4())
    tutor.then(ok(teaching([cite(uuid.uuid4(), uuid.uuid4())])), ok(teaching([cite(L["version"], L["section"])])))
    assert send(client, L, "Explain please", cid=cid).status_code == 503
    assert q(engine, "SELECT input_reference::text FROM workweave.learning_turns WHERE learning_session_id=:s", s=L["sid"]) == "{}"  # no text kept on failure
    r = send(client, L, "Explain please", cid=cid)
    assert r.status_code == 200 and counts(engine, L)["committed"] == 1


# ---------------------------------------------------------------- engine failure
@pytest.mark.parametrize(
    "label,step,status,err",
    [
        ("exception", RuntimeError("model crashed"), 503, "DEPENDENCY_UNAVAILABLE"),
        ("timeout", TutorResult("timeout", provider="test-scripted"), 503, "DEPENDENCY_UNAVAILABLE"),
        ("unavailable", TutorResult("unavailable", provider="test-scripted"), 503, "DEPENDENCY_UNAVAILABLE"),
        ("invalid_output", TutorResult("invalid_output", provider="test-scripted"), 503, "DEPENDENCY_UNAVAILABLE"),
        ("unsupported", TutorResult("unsupported_capability", provider="test-scripted"), 501, "CAPABILITY_UNAVAILABLE"),
        ("ok without output", TutorResult("ok", provider="test-scripted"), 503, "DEPENDENCY_UNAVAILABLE"),
    ],
)
def test_engine_failures_store_no_reply_or_progress(client, engine, tutor, label, step, status, err):
    L = learner(client, engine)
    before = counts(engine, L)
    tutor.then(step)
    r = send(client, L, "Hello")
    assert r.status_code == status and code(r) == err, (label, r.text)
    assert counts(engine, L) == before and progress(engine, L) == "NOT_STARTED", label


# ---------------------------------------------------------------- refresh, resume, privacy, default path
def test_refresh_and_resume_show_the_same_committed_state(client, engine, tutor):
    L = learner(client, engine)
    qid = teach_with_check(client, tutor, L)
    tutor.then(ok(answer(qid, L["objective"], L["cv"], "PARTIAL", some_unmet(L))))
    posted = send(client, L, "Use the newest one.").json()["data"]
    refreshed = client.get(f"/api/onboarding/sessions/{L['sid']}").json()["data"]
    assert refreshed["transcript"] == posted["transcript"] and refreshed["pending_check"] == posted["pending_check"]
    paused = client.post(f"/api/onboarding/sessions/{L['sid']}/pause", json={"client_turn_id": f"pause-{uuid.uuid4()}", "expected_revision": refreshed["revision"]}).json()["data"]
    assert paused["status"] == "PAUSED" and paused["transcript"] == posted["transcript"]
    resumed = client.post("/api/onboarding/sessions").json()["data"]
    assert resumed["learning_session_id"] == L["sid"] and resumed["status"] == "ACTIVE"
    assert resumed["transcript"] == posted["transcript"] and resumed["pending_check"]["question_id"] == qid
    assert progress(engine, L) == "IN_PROGRESS"


def test_supervisor_projection_carries_no_private_learning_details(client, other_client, engine, tutor):
    L = learner(client, engine)
    qid = teach_with_check(client, tutor, L)
    tutor.then(ok(answer(qid, L["objective"], L["cv"], "CORRECT", L["all_met"])))
    send(client, L, "PRIVATE-ANSWER-TEXT: follow the current version")
    # Same run, supervisor persona.
    pick(client, "Morgan")
    r = client.get("/api/onboarding/progress")
    assert r.status_code == 200
    body = r.text
    assert "Completed" in body or "COMPLETED" in body
    for private in ("PRIVATE-ANSWER-TEXT", L["checks"][0], "CORRECT", "criteria", qid, "Two procedure versions"):
        assert private not in body, private


def test_the_default_not_connected_path_stores_nothing(client, engine):
    assert tutor_mod.get_tutor().provider == "none"
    ws = open_company(client, "northstar", intent="FRESH")["workspace_id"]
    pick(client, "Sam")
    v = client.post("/api/onboarding/sessions").json()["data"]
    L = {"sid": v["learning_session_id"], "rev": v["revision"]}
    r = send(client, L, "Hello?")
    assert r.status_code == 501 and code(r) == "CAPABILITY_UNAVAILABLE"
    assert q(engine, "SELECT count(*) FROM workweave.learning_turns WHERE learning_session_id=:s", s=L["sid"]) == 0
    assert q(engine, "SELECT count(*) FROM workweave.employee_learning_events WHERE learning_session_id=:s", s=L["sid"]) == 0
    assert q(engine, "SELECT count(*) FROM workweave.objective_evidence e JOIN workweave.learning_assignments a USING (learning_assignment_id) WHERE a.workspace_id=:w", w=ws) == 0
    view = client.get(f"/api/onboarding/sessions/{L['sid']}").json()["data"]
    assert view["transcript"] == [] and view["tutor"]["status"] == "unavailable"


def test_a_test_engine_cannot_be_installed_outside_the_test_environment(monkeypatch, engine):
    monkeypatch.setattr(get_settings(), "workweave_env", "development")
    with pytest.raises(RuntimeError, match="WORKWEAVE_ENV=test"):
        install_test_tutor(ScriptedTutor(engine))
    monkeypatch.setattr(tutor_mod, "_installed", ScriptedTutor(engine))  # even if one were left installed
    assert tutor_mod.get_tutor().provider == "none"


def test_an_optional_reference_aid_completes_on_its_own_objective(client, engine, tutor):
    """Once the three required Fundamentals are complete the curriculum counts as complete; a Reference
    aid (optional objective) can still be studied, and completes when its own objective is passed."""
    ws = open_company(client, "northstar", intent="FRESH")["workspace_id"]
    pick(client, "Sam")
    with engine.begin() as c:  # Sam has finished the Fundamentals (seeded directly for this test)
        c.execute(text("""UPDATE workweave.employee_learning_progress p SET status='COMPLETED', started_at=now() - interval '1 hour', completed_at=now()
                          FROM workweave.curriculum_subtopics s JOIN workweave.curriculum_topics t ON t.topic_id = s.topic_id
                          WHERE p.subtopic_id = s.subtopic_id AND p.workspace_id=:w AND t.name='Fundamentals'"""), {"w": ws})
    ov = client.get("/api/onboarding").json()["data"]
    assert ov["session_status"] == "COMPLETED"  # required subtopics done
    v = client.post("/api/onboarding/sessions").json()["data"]  # optional items can still be studied
    L = {"sid": v["learning_session_id"], "rev": v["revision"]}
    with engine.connect() as c:
        sub, obj, cv, criteria, required = c.execute(text("""SELECT s.current_subtopic_id, lo.objective_id, lo.criteria_version, lo.assessment_criteria, lo.required
                                                             FROM workweave.learning_sessions s JOIN workweave.learning_objectives lo ON lo.subtopic_id = s.current_subtopic_id
                                                             WHERE s.learning_session_id=:s"""), {"s": L["sid"]}).one()
        name = c.execute(text("SELECT name FROM workweave.curriculum_subtopics WHERE subtopic_id=:s"), {"s": sub}).scalar_one()
        ver, sec = c.execute(text("""SELECT ks.document_version_id, ks.section_id FROM workweave.curriculum_source_sections css JOIN workweave.knowledge_sections ks ON ks.section_id = css.section_id
                                     WHERE css.subtopic_id=:s"""), {"s": sub}).one()
    assert name == "Source-selection checklist" and required is False
    qid = uuid.uuid4()
    tutor.then(ok(teaching([cite(ver, sec)], check_for(obj, cv, qid))), ok(answer(qid, obj, cv, "CORRECT", dict.fromkeys(criteria["required_checks"], True))))
    assert send(client, L, "Walk me through the checklist.").status_code == 200
    r = send(client, L, "Open the controlled record, exclude superseded and draft versions, send discrepancies to a reviewer.")
    assert r.status_code == 200, r.text
    L["subtopic"] = sub
    assert progress(engine, L) == "COMPLETED"
    assert r.json()["data"]["awaiting_continue"] is True


def test_an_interrupted_reply_is_flagged_to_the_engine_and_stored_with_the_turn(client, engine, tutor):
    L = learner(client, engine)
    tutor.then(ok(teaching([cite(L["version"], L["section"])])), ok(teaching([cite(L["version"], L["section"])])))
    cid = str(uuid.uuid4())
    body = {"client_turn_id": cid, "expected_revision": L["rev"], "text": "Wait, which version?", "input_kind": "VOICE_TRANSCRIPT", "interrupted_previous_reply": True}
    r = client.post(f"/api/onboarding/sessions/{L['sid']}/turns", json=body)
    assert r.status_code == 200, r.text
    assert tutor.contexts[-1].previous_reply_interrupted is True
    stored = q(engine, "SELECT input_reference::text FROM workweave.learning_turns WHERE learning_session_id=:s", s=L["sid"])
    assert '"interrupted_previous_reply": true' in stored and '"input_kind": "VOICE_TRANSCRIPT"' in stored
    # The flag is part of the request identity: the same ID without it is a different request.
    again = client.post(f"/api/onboarding/sessions/{L['sid']}/turns", json={**body, "interrupted_previous_reply": False})
    assert again.status_code == 422 and code(again) == "MALFORMED_INPUT"
    # A normal turn tells the engine nothing was interrupted.
    L["rev"] = r.json()["data"]["revision"]
    assert send(client, L, "Thanks").status_code == 200
    assert tutor.contexts[-1].previous_reply_interrupted is False


def test_the_release_profile_requires_secure_cookies():
    from pydantic import ValidationError

    from app.config import Settings

    with pytest.raises(ValidationError, match="COOKIE_SECURE"):
        Settings(workweave_env="release", cookie_secure=False, _env_file=None)
    assert Settings(workweave_env="release", cookie_secure=True, _env_file=None).cookie_secure is True
