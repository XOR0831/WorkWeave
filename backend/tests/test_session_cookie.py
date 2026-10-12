"""The single __session cookie (Firebase Hosting forwards only this cookie to Cloud Run)."""

import base64
import json

from tests.test_demo_slice import decode_session, encode_session, open_company, pick, scenarios


def test_one_cookie_carries_the_current_run_and_each_companys_run(client):
    ns = open_company(client, "northstar")
    acme = open_company(client, "acme")
    jar = decode_session(client)
    assert set(jar["r"]) == {"northstar", "acme"} and jar["c"] == jar["r"]["acme"]
    # Switching back resumes Northstar's own run from the same cookie.
    back = open_company(client, "northstar")
    assert back["workspace_id"] == ns["workspace_id"] and back["resumed"] is True
    assert decode_session(client)["c"] == decode_session(client)["r"]["northstar"]
    assert acme["workspace_id"] != ns["workspace_id"]


def test_cookie_attributes(client):
    r = client.post("/api/demo-sessions", json={"scenario_id": scenarios(client)["northstar"]["scenario_id"], "intent": "FRESH"})
    header = r.headers["set-cookie"]
    assert header.startswith("__session=") and "HttpOnly" in header and "SameSite=lax" in header and "Path=/api" in header


def test_leaving_keeps_the_run_resumable(client):
    s = open_company(client, "northstar")
    client.delete("/api/demo-sessions/current")
    jar = decode_session(client)
    assert jar["c"] is None and "northstar" in jar["r"]
    assert client.get("/api/demo-sessions/current").json()["data"] is None
    assert open_company(client, "northstar")["workspace_id"] == s["workspace_id"]


def test_malformed_cookies_are_ignored(client):
    for bad in ("not-base64!!", base64.urlsafe_b64encode(b"[1,2]").decode(), encode_session({"c": "short", "r": {"Bad Key": "x" * 40}}), "x" * 5000):
        client.cookies.set("__session", bad, path="/api")
        assert client.get("/api/demo-sessions/current").json()["data"] is None
        assert client.get("/api/demo-sessions/runs").json()["data"] == []


def test_legacy_cookies_still_work_once_and_are_cleared(client):
    s = open_company(client, "northstar")
    token = decode_session(client)["c"]
    client.cookies.clear()
    client.cookies.set("ww_session", token, path="/api")
    client.cookies.set("ww_run_northstar", token, path="/api")
    assert client.get("/api/demo-sessions/current").json()["data"]["workspace_id"] == s["workspace_id"]
    r = client.post("/api/demo-sessions", json={"scenario_id": scenarios(client)["northstar"]["scenario_id"], "intent": "RESUME"})
    assert r.json()["data"]["workspace_id"] == s["workspace_id"]
    cleared = r.headers.get_list("set-cookie")
    assert any(h.startswith("ww_session=") and "Max-Age=0" in h for h in cleared)
    assert any(h.startswith("__session=") for h in cleared)
    pick(client, "Sam")
    assert json.dumps(decode_session(client))  # still decodable after the migration
