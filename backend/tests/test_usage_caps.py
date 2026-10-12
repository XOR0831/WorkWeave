"""Demo spending caps (migration 0005, app/services/usage.py): refuse before any external call."""

import uuid

import pytest
from sqlalchemy import text

from app.integrations.tutor import install_test_tutor
from tests.test_demo_slice import code, open_company, scenarios
from tests.test_voice import fake_voice, learner_session  # noqa: F401 (fixture)
from tests.tutor_fakes import ScriptedTutor, cite, ok, teaching


@pytest.fixture()
def caps(engine):
    """caps(PUBLIC_RUN_TUTOR_TURN=2, ...): set daily limits for this test (all others stay off)."""

    def set_caps(**kw: int) -> None:
        with engine.begin() as c:
            for key, n in kw.items():
                tier, scope, kind = key.split("_", 2)
                c.execute(text("UPDATE workweave.demo_usage_limits SET daily_limit=:n WHERE tier=:t AND scope_type=:s AND usage_kind=:k"), {"n": n, "t": tier, "s": scope, "k": kind})

    with engine.begin() as c:
        c.execute(text("DELETE FROM workweave.demo_usage"))
    yield set_caps
    with engine.begin() as c:
        c.execute(text("DELETE FROM workweave.demo_usage"))
        c.execute(text("UPDATE workweave.demo_usage_limits SET daily_limit = 0"))


def used(engine, scope: str, kind: str) -> int:
    """scope: a workspace ID (RUN) or "global" (the public pool)."""
    t, k = ("PUBLIC_POOL", "pool") if scope == "global" else ("RUN", scope)
    with engine.connect() as c:
        return c.execute(text("SELECT coalesce(sum(used), 0) FROM workweave.demo_usage WHERE scope_type=:t AND scope_key=:k AND usage_kind=:kind"), {"t": t, "k": k, "kind": kind}).scalar_one()


def ws_of(engine, sid: str) -> str:
    with engine.connect() as c:
        return str(c.execute(text("SELECT workspace_id FROM workweave.learning_sessions WHERE learning_session_id=:s"), {"s": sid}).scalar_one())


def turn(client, sid: str, rev: int, msg: str = "Hi"):
    return client.post(f"/api/onboarding/sessions/{sid}/turns", json={"client_turn_id": str(uuid.uuid4()), "expected_revision": rev, "text": msg, "input_kind": "TEXT"})


def citation(engine, sid: str) -> dict:
    with engine.connect() as c:
        ver, sec = c.execute(text("""SELECT ks.document_version_id, ks.section_id FROM workweave.knowledge_sections ks
                                     JOIN workweave.learning_sessions ls ON ls.workspace_id = ks.workspace_id
                                     WHERE ls.learning_session_id=:s AND ks.section_key='h2:1/h3:1'"""), {"s": sid}).one()
    return cite(ver, sec)


@pytest.fixture()
def tutor(engine):
    t = ScriptedTutor(engine)
    install_test_tutor(t)
    yield t
    install_test_tutor(None)


def test_turn_cap_per_run_refuses_before_the_engine_and_stores_nothing(client, engine, caps, tutor):
    caps(PUBLIC_RUN_TUTOR_TURN=2)
    s = learner_session(client)
    sid, rev = s["learning_session_id"], s["revision"]
    for _ in range(2):
        tutor.then(ok(teaching([citation(engine, sid)])))
    for _ in range(2):
        r = turn(client, sid, rev)
        assert r.status_code == 200, r.text
        rev = r.json()["data"]["revision"]
    with engine.connect() as c:
        before = c.execute(text("SELECT count(*) FROM workweave.learning_turns WHERE learning_session_id=:s"), {"s": sid}).scalar_one()
    r = turn(client, sid, rev)
    assert r.status_code == 429 and code(r) == "LIMIT_REACHED" and "start a fresh demo" in r.json()["error"]["message"]
    assert len(tutor.texts) == 2  # the engine was never called for the refused turn
    with engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM workweave.learning_turns WHERE learning_session_id=:s"), {"s": sid}).scalar_one() == before
    assert used(engine, ws_of(engine, sid), "TUTOR_TURN") == 2  # the refusal didn't count

    # A fresh demo is a new workspace with its own allowance.
    s2 = learner_session(client)
    tutor.then(ok(teaching([citation(engine, s2["learning_session_id"])])))
    r = turn(client, s2["learning_session_id"], s2["revision"])
    assert r.status_code == 200, r.text


def test_turn_cap_per_day_is_shared_by_all_visitors(client, other_client, engine, caps, tutor):
    caps(PUBLIC_POOL_TUTOR_TURN=1)
    a, b = learner_session(client), learner_session(other_client)
    tutor.then(ok(teaching([citation(engine, a["learning_session_id"])])))
    assert turn(client, a["learning_session_id"], a["revision"]).status_code == 200
    r = turn(other_client, b["learning_session_id"], b["revision"])
    assert r.status_code == 429 and "shared limit" in r.json()["error"]["message"]
    assert used(engine, "global", "TUTOR_TURN") == 1
    assert used(engine, ws_of(engine, b["learning_session_id"]), "TUTOR_TURN") == 0  # per-run count rolled back too


def test_unconnected_tutor_spends_nothing(client, engine, caps):
    caps(PUBLIC_POOL_TUTOR_TURN=1)
    s = learner_session(client)
    r = turn(client, s["learning_session_id"], s["revision"])
    assert code(r) == "CAPABILITY_UNAVAILABLE"
    assert used(engine, "global", "TUTOR_TURN") == 0


def test_voice_listen_cap_stops_before_minting_a_token(client, engine, caps, fake_voice):  # noqa: F811
    caps(PUBLIC_RUN_VOICE_LISTEN=1)
    sid = learner_session(client)["learning_session_id"]
    url = f"/api/onboarding/sessions/{sid}/voice/listen"
    assert client.post(url, json={"mode": "TAP"}).status_code == 200
    r = client.post(url, json={"mode": "TAP"})
    assert r.status_code == 429 and code(r) == "LIMIT_REACHED" and "Type your answer instead" in r.json()["error"]["message"]
    assert fake_voice.modes == ["TAP"]


def test_speech_cap_stops_before_synthesis(client, engine, caps, fake_voice, tutor):  # noqa: F811
    caps(PUBLIC_POOL_VOICE_SPEECH=1)
    s = learner_session(client)
    sid = s["learning_session_id"]
    tutor.then(ok(teaching([citation(engine, sid)])))
    reply = turn(client, sid, s["revision"]).json()["data"]["transcript"][-1]
    url = f"/api/onboarding/sessions/{sid}/voice/speech/{reply['message_id']}"
    assert client.get(url).status_code == 200
    r = client.get(url)
    assert r.status_code == 429 and "stay on screen as text" in r.json()["error"]["message"]
    assert len(fake_voice.spoken) == 1


def test_new_workspace_cap_still_lets_visitors_resume(client, other_client, engine, caps):
    caps(PUBLIC_POOL_DEMO_RUN=1)
    open_company(client, "northstar", intent="FRESH")
    r = other_client.post("/api/demo-sessions", json={"scenario_id": scenarios(other_client)["northstar"]["scenario_id"], "intent": "FRESH"})
    assert r.status_code == 429 and code(r) == "LIMIT_REACHED"
    open_company(client, "northstar", intent="RESUME")  # continuing an existing run isn't a new workspace
    assert used(engine, "global", "DEMO_RUN") == 1


def test_counter_rows_reject_unexpected_scopes_and_kinds(engine):
    from sqlalchemy.exc import IntegrityError

    for scope_type, scope, kind in (("RUN", "someone@example.com", "TUTOR_TURN"), ("PUBLIC_POOL", "pool", "ANYTHING"), ("PUBLIC_POOL", "x", "TUTOR_TURN"), ("ELSEWHERE", "pool", "TUTOR_TURN")):
        with pytest.raises(IntegrityError), engine.begin() as c:
            c.execute(text("INSERT INTO workweave.demo_usage (scope_type, scope_key, usage_kind, usage_day, used) VALUES (:t, :k, :kind, current_date, 1)"), {"t": scope_type, "k": scope, "kind": kind})


def test_refusal_says_which_limit_and_when_it_resets(client, engine, caps, fake_voice):  # noqa: F811
    caps(PUBLIC_RUN_VOICE_LISTEN=1)
    sid = learner_session(client)["learning_session_id"]
    url = f"/api/onboarding/sessions/{sid}/voice/listen"
    client.post(url, json={"mode": "TAP"})
    err = client.post(url, json={"mode": "TAP"}).json()["error"]
    assert err["limit"]["kind"] == "VOICE_LISTEN" and err["limit"]["scope"] == "RUN"
    assert err["limit"]["resets_at"].endswith("T00:00:00+00:00")


def test_session_view_reports_what_is_left_before_anyone_is_refused(client, engine, caps, fake_voice):  # noqa: F811
    caps(PUBLIC_RUN_VOICE_LISTEN=2, PUBLIC_POOL_VOICE_SPEECH=5)
    s = learner_session(client)
    limits = s["demo_limits"]
    assert limits["voice_listen"] == {"available": True, "scope": None, "remaining": 2}
    assert limits["voice_speech"]["remaining"] == 5 and limits["tutor_turn"]["remaining"] is None  # uncapped here
    url = f"/api/onboarding/sessions/{s['learning_session_id']}/voice/listen"
    client.post(url, json={"mode": "TAP"})
    client.post(url, json={"mode": "TAP"})
    limits = client.get(f"/api/onboarding/sessions/{s['learning_session_id']}").json()["data"]["demo_limits"]
    assert limits["voice_listen"] == {"available": False, "scope": "RUN", "remaining": 0}


# ---------------------------------------------------------------- resetting counters
def test_reset_usage_clears_today_so_a_refused_action_works_again(client, engine, test_url, caps, fake_voice):  # noqa: F811
    from app import cli

    caps(PUBLIC_RUN_VOICE_LISTEN=1, PUBLIC_POOL_DEMO_RUN=100)
    sid = learner_session(client)["learning_session_id"]
    url = f"/api/onboarding/sessions/{sid}/voice/listen"
    client.post(url, json={"mode": "TAP"})
    assert client.post(url, json={"mode": "TAP"}).status_code == 429
    with pytest.raises(SystemExit):
        cli.main(["reset-usage"], url=test_url)  # needs --confirm
    cli.main(["reset-usage", "--confirm", "--kind", "TUTOR_TURN"], url=test_url)  # other kinds untouched
    assert client.post(url, json={"mode": "TAP"}).status_code == 429
    cli.main(["reset-usage", "--confirm"], url=test_url)
    assert client.post(url, json={"mode": "TAP"}).status_code == 200
    assert used(engine, "global", "DEMO_RUN") == 0  # all kinds cleared for today


def test_cleanup_removes_only_old_counters_and_only_with_confirm(engine, test_url, caps, capsys):  # noqa: F811
    from app.workers import cleanup

    with engine.begin() as c:
        for days, kind in ((0, "TUTOR_TURN"), (3, "TUTOR_TURN"), (10, "TUTOR_TURN"), (30, "VOICE_LISTEN")):
            c.execute(text("""INSERT INTO workweave.demo_usage (scope_type, scope_key, usage_kind, usage_day, used)
                              VALUES ('PUBLIC_POOL', 'pool', :k, (now() AT TIME ZONE 'UTC')::date - CAST(:d AS integer), 5)"""), {"k": kind, "d": days})
    cleanup.main([], url=test_url)  # dry run
    assert "2 older than 7 days would be removed" in capsys.readouterr().out
    with engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM workweave.demo_usage")).scalar_one() == 4
    cleanup.main(["--confirm"], url=test_url)
    assert "removed 2 older than 7 days" in capsys.readouterr().out
    with engine.connect() as c:
        ages = sorted(c.execute(text("SELECT (now() AT TIME ZONE 'UTC')::date - usage_day FROM workweave.demo_usage")).scalars())
    assert ages == [0, 3]  # today and recent days are kept


def test_the_usage_summary_shows_the_tier_caps_and_this_runs_use(client, engine, caps, tutor):
    caps(PUBLIC_RUN_TUTOR_TURN=5, PUBLIC_POOL_TUTOR_TURN=1, PUBLIC_RUN_VOICE_LISTEN=3)
    before = client.get("/api/demo-usage").json()["data"]  # no company open yet: the caps, no use
    assert before["tier"] == "PUBLIC" and before["run_open"] is False
    assert {i["kind"]: (i["limit"], i["used"]) for i in before["items"]} == {"TUTOR_TURN": (5, None), "VOICE_LISTEN": (3, None), "VOICE_SPEECH": (None, None)}
    s = learner_session(client)
    turn(client, s["learning_session_id"], s["revision"])  # counted even though this tutor has no reply queued
    after = client.get("/api/demo-usage").json()["data"]
    t = next(i for i in after["items"] if i["kind"] == "TUTOR_TURN")
    assert after["run_open"] and t["used"] == 1 and t["limit"] == 5 and t["shared_full"] is True  # the public pool of 1 is used up
