"""Notification delivery (ADR-048): outbox → dispatcher → recipient inbox, read through the backend."""

import uuid

import pytest
from sqlalchemy import text

from app.integrations.notifications import MemoryInbox, install_test_inbox
from app.services import notifications
from tests.test_companion_commands import confirm, emp, fresh
from tests.test_demo_slice import code, pick

H = {"X-WorkWeave-Client": "web"}


@pytest.fixture()
def inbox(engine):
    with engine.begin() as c:  # only this test's events are due
        c.execute(text("UPDATE workweave.outbox_events SET status='DELIVERED' WHERE status IN ('PENDING', 'FAILED', 'PROCESSING')"))
    box = MemoryInbox()
    install_test_inbox(box)
    yield box
    install_test_inbox(None)


def outbox_row(engine, ws: str, event_id: str) -> dict:
    with engine.connect() as c:
        return dict(c.execute(text("SELECT * FROM workweave.outbox_events WHERE workspace_id=:w AND event_id=:e"), {"w": ws, "e": event_id}).mappings().one())


def test_a_confirmed_assignment_reaches_only_the_assignees_inbox_once(client, engine, inbox):
    ws = fresh(client, "Alex")
    assert confirm(client).status_code == 200  # the seeded proposal: #829 and #910 to teammates
    assert notifications.dispatch_once()["delivered"] >= 2
    jamie = emp(engine, ws, "Jamie")
    mine = [d for (w, e, _), d in inbox.docs.items() if w == ws and e == jamie]
    assert mine and all(d["type"] == "work.assigned" and d["message"].endswith("was assigned to you.") and d["href"] == "/companion/" for d in mine)
    assert set(mine[0]) >= {"recipient_employee_id", "resource_type", "resource_id", "source_revision", "created_at"}

    pick(client, "Jamie")
    got = client.get("/api/notifications").json()["data"]
    assert [n["minimal_message"] for n in got] == [d["message"] for d in sorted(mine, key=lambda d: d["created_at"], reverse=True)]
    n = got[0]
    r = client.patch(f"/api/notifications/{n['notification_id']}/read", headers=H)
    assert r.status_code == 200 and r.json()["data"]["read_at"]

    # A repeated delivery (retry, or a second worker) rewrites the same document and keeps the read marker.
    with engine.begin() as c:
        c.execute(text("UPDATE workweave.outbox_events SET status='PENDING' WHERE event_id=:e"), {"e": n["notification_id"]})
    notifications.dispatch_once()
    again = client.get("/api/notifications").json()["data"]
    assert len(again) == len(got) and next(x for x in again if x["notification_id"] == n["notification_id"])["read_at"]

    pick(client, "Sam")  # someone else's inbox is never visible, and their ID can't be marked read
    assert all(x["notification_id"] != n["notification_id"] for x in client.get("/api/notifications").json()["data"])
    assert code(client.patch(f"/api/notifications/{n['notification_id']}/read", headers=H)) == "NOT_FOUND"


def test_an_outage_only_delays_delivery_and_retries_back_off_then_give_up(client, engine, inbox):
    ws = fresh(client, "Alex")
    assert confirm(client).status_code == 200  # the business change is committed whatever happens next
    inbox.fail = True
    assert notifications.dispatch_once()["retry"] >= 1
    with engine.connect() as c:
        row = dict(c.execute(text("SELECT * FROM workweave.outbox_events WHERE workspace_id=:w AND event_type='work.assigned' LIMIT 1"), {"w": ws}).mappings().one())
        tries = c.execute(text("SELECT result FROM workweave.delivery_attempts WHERE event_id=:e"), {"e": row["event_id"]}).scalars().all()
    assert row["status"] == "FAILED" and row["attempt_count"] == 1 and row["next_attempt_at"] > row["updated_at"] and tries == ["RETRYABLE_FAILURE"]
    assert notifications.dispatch_once()["retry"] == 0  # not due again yet

    with engine.begin() as c:  # pretend the waits have passed, up to the last attempt
        c.execute(text("UPDATE workweave.outbox_events SET attempt_count=:n, next_attempt_at=now() WHERE event_id=:e"), {"n": notifications.MAX_ATTEMPTS - 1, "e": row["event_id"]})
    notifications.dispatch_once()
    assert outbox_row(engine, ws, str(row["event_id"]))["status"] == "DEAD"

    inbox.fail = False  # once Firestore is back, what's still due is delivered
    with engine.begin() as c:
        c.execute(text("UPDATE workweave.outbox_events SET next_attempt_at=now() WHERE workspace_id=:w AND status='FAILED'"), {"w": ws})
    assert notifications.dispatch_once()["delivered"] >= 1


def test_an_older_revision_never_replaces_a_newer_notification():
    box = MemoryInbox()
    base = {"type": "work.assigned", "message": "new", "href": "/companion/", "created_at": 1}
    assert box.upsert("w", "e", "n", {**base, "source_revision": 3})
    assert not box.upsert("w", "e", "n", {**base, "message": "old", "source_revision": 2})
    assert box.docs[("w", "e", "n")]["message"] == "new"


def test_messages_never_carry_private_text():
    msg, href = notifications.message_for("knowledge.note_decided", {"status": "APPROVED", "note": "private words", "description": "secret"})
    assert msg == "Your knowledge note was approved." and href == "/memory/"
    assert notifications.message_for("unknown.type", {"text": "x"}) == ("You have an update in WorkWeave.", "/home/")
    assert notifications.message_for("work.assigned", {})[0] == "A ticket was assigned to you."


def test_the_inbox_says_when_it_isnt_switched_on(client):
    fresh(client, "Alex")
    r = client.get("/api/notifications")
    assert r.status_code in (501, 503) and code(r) == "CAPABILITY_UNAVAILABLE"
    assert code(client.patch(f"/api/notifications/{uuid.uuid4()}/read", headers=H)) == "CAPABILITY_UNAVAILABLE"


def _emulator() -> bool:
    import socket

    try:
        socket.create_connection(("127.0.0.1", 8085), timeout=0.5).close()
        return True
    except OSError:
        return False


@pytest.mark.skipif(not _emulator(), reason="Firestore emulator not running (docker compose up -d firestore)")
def test_the_firestore_inbox_keeps_the_same_rules_on_the_emulator():
    from datetime import UTC, datetime

    from app.integrations.notifications import FirestoreInbox

    fs = FirestoreInbox("workweave-test", "127.0.0.1:8085")
    ws, who, nid = f"ws-{uuid.uuid4().hex[:8]}", "emp-1", str(uuid.uuid4())
    doc = {"type": "work.assigned", "message": "Ticket #829 was assigned to you.", "href": "/companion/", "source_revision": 2, "created_at": datetime.now(UTC)}
    assert fs.upsert(ws, who, nid, doc)
    assert fs.mark_read(ws, who, nid, datetime.now(UTC))["read_at"]
    assert fs.upsert(ws, who, nid, doc)  # a retry keeps the read marker
    assert not fs.upsert(ws, who, nid, {**doc, "message": "old", "source_revision": 1})
    [got] = fs.list(ws, who)
    assert got["message"] == "Ticket #829 was assigned to you." and got["read_at"] and got["notification_id"] == nid
    assert fs.list(ws, "someone-else") == [] and fs.mark_read(ws, "someone-else", nid, datetime.now(UTC)) is None


def test_a_release_build_never_uses_the_firestore_emulator(monkeypatch):
    from app.config import get_settings
    from app.integrations import notifications as inbox

    seen = []
    monkeypatch.setattr(inbox, "FirestoreInbox", lambda project, emulator_host: seen.append((project, emulator_host)) or object())
    monkeypatch.setattr(inbox, "_cached", None)
    monkeypatch.setattr(inbox, "_test", None)
    monkeypatch.setattr(get_settings(), "notifications", "firestore")
    monkeypatch.setattr(get_settings(), "firestore_project", "workweave-cloud")
    monkeypatch.setattr(get_settings(), "workweave_env", "release")
    inbox.get_inbox()
    assert seen == [("workweave-cloud", None)]
