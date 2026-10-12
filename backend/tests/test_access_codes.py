"""Evaluator access codes (ADR-029, migration 0005): separate tier, pool and voice key."""

import uuid

import pytest
from sqlalchemy import text

from app import cli
from app.integrations.voice import install_test_voice
from app.services import access
from tests.test_demo_slice import code, decode_session, open_company
from tests.test_usage_caps import caps, used  # noqa: F401 (fixture)
from tests.test_voice import FakeVoice, learner_session


def make_code(test_url: str, label: str | None = None, max_runs: int = 50) -> str:
    label = label or f"Judge {uuid.uuid4().hex[:6]}"
    return cli.create_access_code(cli.create_engine(test_url), label, "2099-12-31", max_runs)


def redeem(client, c: str):
    return client.post("/api/demo-access", json={"code": c})


def tier(client) -> str:
    return client.get("/api/demo-sessions/current").json()["data"]["access"]["tier"]


@pytest.fixture()
def voices():
    free, paid = FakeVoice(), FakeVoice()
    install_test_voice(free, paid=paid)
    yield free, paid
    install_test_voice(None)


# ---------------------------------------------------------------- codes
def test_codes_are_random_readable_and_forgiving_to_type():
    display, normalized = access.generate()
    assert display.startswith("WW-") and len(display) == 22 and display.count("-") == 4
    assert access.normalize(display) == normalized
    assert access.normalize(" ww " + normalized.lower()) == normalized
    assert access.normalize(display.replace("0", "O").replace("1", "I")) == normalized  # look-alikes
    for bad in ("", "WW-1234", normalized + "X", "WW-" + "U" * 16, None, "x" * 100):
        assert access.normalize(bad) is None
    assert len({access.generate()[1] for _ in range(200)}) == 200


def test_only_a_hash_is_stored_and_the_listing_never_shows_the_code(engine, test_url, capsys):
    c = make_code(test_url, "Judge - Panel A")
    with engine.connect() as conn:
        row = conn.execute(text("SELECT * FROM workweave.demo_access_codes WHERE label='Judge - Panel A'")).mappings().one()
    normalized = access.normalize(c)
    assert row["code_hash"] == access.code_hash(normalized) and normalized not in str(dict(row)).replace(row["code_hash"], "")
    assert row["code_hint"] == normalized[-4:] and row["max_runs_per_day"] == 50
    cli.list_access_codes(cli.create_engine(test_url))
    out = capsys.readouterr().out
    assert "Judge - Panel A" in out and normalized not in out and "ACTIVE" in out


def test_cli_rejects_past_expiry_and_duplicate_labels(test_url):
    with pytest.raises(SystemExit):
        cli.create_access_code(cli.create_engine(test_url), "Past", "2020-01-01", 50)
    make_code(test_url, "Twice")
    with pytest.raises(Exception):
        make_code(test_url, "Twice")


# ---------------------------------------------------------------- redeeming
def test_a_code_upgrades_this_browser_and_new_runs_inherit_it(client, other_client, test_url):
    open_company(client, "northstar", intent="FRESH")
    assert tier(client) == "PUBLIC"
    r = redeem(client, make_code(test_url))
    assert r.status_code == 200 and r.json()["data"]["tier"] == "EVALUATOR" and r.json()["data"]["expires_at"]
    assert "label" not in r.text and "Judge" not in r.text  # the browser never learns who the code is for
    assert tier(client) == "EVALUATOR"  # the run already open is upgraded
    assert client.get("/api/demo-access").json()["data"]["tier"] == "EVALUATOR"
    assert len(decode_session(client)["a"]) == 16
    open_company(client, "acme", intent="FRESH")
    assert tier(client) == "EVALUATOR"  # and new runs inherit it
    open_company(other_client, "northstar", intent="FRESH")
    assert tier(other_client) == "PUBLIC"  # another browser is unaffected


def test_a_wrong_code_is_refused_and_counted(client, caps):  # noqa: F811
    caps(PUBLIC_POOL_ACCESS_ATTEMPT_FAILED=2)
    for _ in range(2):
        r = redeem(client, "WW-0000-0000-0000-0000")
        assert r.status_code == 422 and "isn't valid" in r.json()["error"]["message"]
    r = redeem(client, "WW-0000-0000-0000-0000")
    assert r.status_code == 429 and code(r) == "LIMIT_REACHED"
    assert redeem(client, "nonsense").status_code == 429  # malformed codes count too


def test_revoked_and_expired_codes_stop_on_the_next_request(client, engine, test_url):
    c = make_code(test_url, "Revoke me")
    open_company(client, "northstar", intent="FRESH")
    redeem(client, c)
    assert tier(client) == "EVALUATOR"
    cli.main(["revoke-access-code", "Revoke me"], url=test_url)
    assert tier(client) == "PUBLIC"
    assert redeem(client, c).status_code == 422

    c2 = make_code(test_url, "Expire me")
    redeem(client, c2)
    assert tier(client) == "EVALUATOR"
    with engine.begin() as conn:
        conn.execute(text("UPDATE workweave.demo_access_codes SET created_at = now() - interval '2 days', expires_at = now() - interval '1 day' WHERE label='Expire me'"))
    assert tier(client) == "PUBLIC"


def test_a_code_can_be_entered_before_any_company_is_opened(client, test_url):
    assert client.get("/api/demo-access").json()["data"]["tier"] == "PUBLIC"
    assert redeem(client, make_code(test_url)).status_code == 200
    assert client.get("/api/demo-access").json()["data"]["tier"] == "EVALUATOR"
    open_company(client, "harbor", intent="FRESH")
    assert tier(client) == "EVALUATOR"


def test_leaving_evaluator_access_makes_runs_public_again(client, test_url):
    open_company(client, "northstar", intent="FRESH")
    redeem(client, make_code(test_url))
    r = client.delete("/api/demo-access")
    assert r.status_code == 200 and r.json()["data"]["tier"] == "PUBLIC"
    assert tier(client) == "PUBLIC" and "a" not in decode_session(client)
    assert client.post("/api/demo-access", json={"code": "x"}, headers={"X-WorkWeave-Client": ""}).status_code == 403


# ---------------------------------------------------------------- separate allowance
def test_evaluators_have_their_own_pool_and_paid_voice_key(client, other_client, test_url, caps, voices):  # noqa: F811
    free, paid = voices
    caps(PUBLIC_POOL_VOICE_LISTEN=1, EVALUATOR_POOL_VOICE_LISTEN=5)
    public = learner_session(other_client)
    url = f"/api/onboarding/sessions/{public['learning_session_id']}/voice/listen"
    assert other_client.post(url, json={"mode": "TAP"}).status_code == 200
    assert other_client.post(url, json={"mode": "TAP"}).status_code == 429  # the public pool is used up

    redeem(client, make_code(test_url))
    judge = learner_session(client)
    url = f"/api/onboarding/sessions/{judge['learning_session_id']}/voice/listen"
    assert client.post(url, json={"mode": "TAP"}).status_code == 200  # judges are unaffected
    assert free.modes == ["TAP"] and paid.modes == ["TAP"]  # evaluator grant used the paid key
    assert judge["demo_limits"]["tier"] == "EVALUATOR" and judge["demo_limits"]["voice_listen"]["remaining"] == 5


def test_each_code_has_its_own_daily_new_workspace_limit(client, test_url, caps):  # noqa: F811
    caps(EVALUATOR_POOL_DEMO_RUN=100)
    redeem(client, make_code(test_url, max_runs=1))
    open_company(client, "northstar", intent="FRESH")
    r = client.post("/api/demo-sessions", json={"scenario_id": client.get("/api/scenarios").json()["data"][0]["scenario_id"], "intent": "FRESH"})
    assert r.status_code == 429 and r.json()["error"]["limit"]["scope"] == "CODE"
    assert tier(client) == "EVALUATOR"  # the existing run is unchanged


def test_limits_are_changed_with_the_cli(engine, test_url, capsys):
    cli.main(["set-limit", "EVALUATOR", "POOL", "TUTOR_TURN", "4321"], url=test_url)
    cli.main(["show-limits"], url=test_url)
    assert "4321" in capsys.readouterr().out
    with engine.connect() as c:
        by = c.execute(text("SELECT updated_by FROM workweave.demo_usage_limits WHERE tier='EVALUATOR' AND scope_type='POOL' AND usage_kind='TUTOR_TURN'")).scalar_one()
    assert by.startswith("cli:")
    with engine.begin() as c:
        c.execute(text("UPDATE workweave.demo_usage_limits SET daily_limit = 0"))
