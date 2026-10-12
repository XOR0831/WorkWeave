"""Notification delivery (blueprint/19, ADR-048): a retrying, deduplicated outbox dispatcher, and the
recipient's inbox read through the backend.

Business commands already commit an outbox row with their change (who to tell, about which resource,
at which revision). The dispatcher claims due rows, writes one minimal inbox document per row to
Firestore (outside any database transaction), then records the attempt:
- success: the row is DELIVERED;
- failure: it is retried later with growing waits, and after MAX_ATTEMPTS it is DEAD (kept for review).
Every attempt is logged in delivery_attempts (append-only). A row stuck in PROCESSING (a worker that
stopped) is picked up again after LOCK_TIMEOUT. A Firestore outage only delays notifications; the business
change was committed long before.

Messages are fixed per event type and never carry private text (no conversation, interview or learning
content). Opening a notification goes to the module's page, which reads PostgreSQL with the viewer's own
permissions; reading it changes nothing but its read marker.
"""

import logging
import threading
import uuid as _uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import text

from app.config import get_settings
from app.db import transaction
from app.errors import ApiError
from app.integrations.notifications import InboxUnavailable, get_inbox
from app.services.onboarding import _persona

log = logging.getLogger("workweave.notifications")
W = "workweave"
MAX_ATTEMPTS = 8
LOCK_TIMEOUT = timedelta(minutes=2)  # a worker that stopped mid-delivery (crash, redeploy, local reload)

# event type -> (message, where it opens). {placeholders} come from the outbox payload's safe fields.
MESSAGES: dict[str, tuple[str, str]] = {
    "work.assigned": ("{external_id} was assigned to you.", "/companion/"),
    "work.unassigned": ("{external_id} was moved to someone else.", "/companion/"),
    "work.reported_done": ("{external_id} was reported done; the ticket system confirms it.", "/companion/"),
    "work.report_needs_review": ("A report on {external_id} needs your review.", "/companion/"),
    "handover.published": ("Handover #{publication_number} was published for your shift.", "/handover/"),
    "handover.ack_requested": ("A completed handover item is waiting for your acknowledgement.", "/handover/"),
    "handover.completion_disputed": ("A completion on a handover item was disputed.", "/handover/"),
    "knowledge.note_awaiting_review": ("A knowledge note is waiting for your review.", "/reviews/"),
    "knowledge.note_decided": ("Your knowledge note was {status}.", "/memory/"),
    "exit_kt.case_opened": ("A knowledge-transfer case was opened for you.", "/exit-kt/"),
    "exit_kt.successor_assigned": ("You were named the successor in a knowledge transfer.", "/exit-kt/"),
    "exit_kt.review_requested": ("A knowledge-transfer artifact is waiting for your review.", "/reviews/"),
    "exit_kt.review_decided": ("Your knowledge-transfer artifact was {status}.", "/exit-kt/"),
    "exit_kt.package_review_requested": ("A successor package is waiting for your review.", "/reviews/"),
    "exit_kt.package_returned": ("Your successor package was returned for changes.", "/exit-kt/"),
    "exit_kt.package_approved": ("A successor package is ready for you.", "/exit-kt/"),
    "exit_kt.package_received": ("The successor confirmed they received the package.", "/exit-kt/"),
    "exit_kt.responsibility_transferred": ("A responsibility was transferred to you.", "/exit-kt/"),
}
SAFE_FIELDS = ("external_id", "publication_number", "status")


def message_for(event_type: str, payload: dict[str, Any]) -> tuple[str, str]:
    template, href = MESSAGES.get(event_type, ("You have an update in WorkWeave.", "/home/"))
    values = {k: str(payload.get(k) or "") for k in SAFE_FIELDS}
    values["external_id"] = values["external_id"] or "A ticket"
    values["status"] = values["status"].replace("_", " ").lower() or "decided"
    text_ = template.format(**values)
    return text_[0].upper() + text_[1:], href


def _doc(e: dict[str, Any]) -> dict[str, Any]:
    msg, href = message_for(e["event_type"], e["payload"] or {})
    return {
        "organization_id": str(e["organization_id"]),
        "workspace_id": str(e["workspace_id"]),
        "recipient_employee_id": str(e["recipient_employee_id"]),
        "type": e["event_type"],
        "message": msg,
        "href": href,
        "resource_type": e["resource_type"],
        "resource_id": str(e["resource_id"]),
        "source_revision": int(e["resource_revision"]),
        "created_at": e["created_at"],
    }


def _claim(worker: str, batch: int) -> list[dict[str, Any]]:
    with transaction() as conn:
        rows = conn.execute(
            text(f"""UPDATE {W}.outbox_events SET status='PROCESSING', locked_at=now(), locked_by=:me, updated_at=now()
                     WHERE event_id IN (
                       SELECT event_id FROM {W}.outbox_events
                       WHERE (status IN ('PENDING', 'FAILED') AND next_attempt_at <= now())
                          OR (status = 'PROCESSING' AND locked_at < now() - CAST(:stale AS interval))
                       ORDER BY created_at LIMIT :n FOR UPDATE SKIP LOCKED)
                     RETURNING *"""),
            {"me": worker, "n": batch, "stale": f"{int(LOCK_TIMEOUT.total_seconds())} seconds"},
        ).mappings().all()
    return [dict(r) for r in rows]


def _record(e: dict[str, Any], ok: bool, error: str | None) -> str:
    attempt = int(e["attempt_count"]) + 1
    dead = not ok and attempt >= MAX_ATTEMPTS
    status = "DELIVERED" if ok else "DEAD" if dead else "FAILED"
    wait = timedelta(seconds=min(600, 5 * 2 ** (attempt - 1)))  # 5 s, 10 s, 20 s ... up to 10 min
    with transaction() as conn:
        conn.execute(
            text(f"""UPDATE {W}.outbox_events SET status=:s, attempt_count=:a, locked_at=NULL, locked_by=NULL, updated_at=now(),
                       delivered_at=CASE WHEN :ok THEN now() ELSE delivered_at END, last_error=:err,
                       next_attempt_at=CASE WHEN :ok THEN next_attempt_at ELSE now() + CAST(:wait AS interval) END
                     WHERE organization_id=:o AND workspace_id=:w AND event_id=:id"""),
            {"s": status, "a": attempt, "ok": ok, "err": error, "wait": f"{int(wait.total_seconds())} seconds", "o": e["organization_id"], "w": e["workspace_id"], "id": e["event_id"]},
        )
        conn.execute(
            text(f"""INSERT INTO {W}.delivery_attempts (organization_id, workspace_id, event_id, attempt, result, error, attempted_at)
                     VALUES (:o, :w, :id, :a, :r, :err, now())"""),
            {"o": e["organization_id"], "w": e["workspace_id"], "id": e["event_id"], "a": attempt,
             "r": "SUCCESS" if ok else "PERMANENT_FAILURE" if dead else "RETRYABLE_FAILURE", "err": error},
        )
    return status


def dispatch_once(worker: str = "api", batch: int = 25) -> dict[str, int]:
    """Delivers the due outbox rows once. Returns how many were delivered, retried and given up on."""
    inbox = get_inbox()
    counts = {"delivered": 0, "retry": 0, "dead": 0}
    if not inbox.available:
        return counts
    for e in _claim(worker, batch):
        try:
            inbox.upsert(str(e["workspace_id"]), str(e["recipient_employee_id"]), str(e["event_id"]), _doc(e))
            status = _record(e, True, None)
        except InboxUnavailable as err:
            status = _record(e, False, str(err)[:500])
        counts["delivered" if status == "DELIVERED" else "dead" if status == "DEAD" else "retry"] += 1
    return counts


# ---------------------------------------------------------------- in-process worker (local development)
_stop = threading.Event()
_thread: threading.Thread | None = None


def start_worker() -> None:
    """Delivers every few seconds from the API process (DISPATCHER_IN_PROCESS). Errors never reach requests."""
    global _thread
    s = get_settings()
    if s.notifications == "none" or not s.dispatcher_in_process or (_thread and _thread.is_alive()):
        return
    _stop.clear()

    def loop() -> None:
        while not _stop.wait(s.dispatcher_interval_seconds):
            try:
                dispatch_once(worker=f"api-{_uuid.uuid4().hex[:6]}")
            except Exception:  # noqa: BLE001 - keep the worker alive; the rows stay due
                log.exception("notification dispatch failed")

    _thread = threading.Thread(target=loop, name="notification-dispatcher", daemon=True)
    _thread.start()


def stop_worker() -> None:
    _stop.set()


# ---------------------------------------------------------------- the recipient's inbox (backend-mediated)
def _who(token: str | None) -> tuple[str, str]:
    with transaction() as conn:
        conn.execute(text("SET TRANSACTION READ ONLY"))
        r, me = _persona(conn, token)
        return str(r.session["workspace_id"]), str(me)


def _out(d: dict[str, Any]) -> dict[str, Any]:
    created, read = d.get("created_at"), d.get("read_at")
    iso = lambda v: v.isoformat() if isinstance(v, datetime) else (str(v) if v else None)  # noqa: E731
    return {"notification_id": d["notification_id"], "type": d.get("type", ""), "minimal_message": d.get("message", ""),
            "resource_href": d.get("href", "/home/"), "created_at": iso(created), "read_at": iso(read)}


def _inbox_or_raise():
    inbox = get_inbox()
    if not inbox.available:
        raise ApiError("CAPABILITY_UNAVAILABLE", "Notifications aren't switched on for this server.")
    return inbox


def list_mine(token: str | None) -> list[dict[str, Any]]:
    ws, me = _who(token)
    try:
        return [_out(d) for d in _inbox_or_raise().list(ws, me)]
    except InboxUnavailable:
        raise ApiError("DEPENDENCY_UNAVAILABLE", "Notifications can't be loaded right now. Your work isn't affected; try again shortly.", retryable=True) from None


def mark_read(token: str | None, notification_id: str) -> dict[str, Any]:
    ws, me = _who(token)
    try:
        _uuid.UUID(notification_id)
    except ValueError:
        raise ApiError("MALFORMED_INPUT", "Unknown notification.") from None
    try:
        d = _inbox_or_raise().mark_read(ws, me, notification_id, datetime.now(UTC))  # only this person's own inbox
    except InboxUnavailable:
        raise ApiError("DEPENDENCY_UNAVAILABLE", "The notification couldn't be marked as read right now.", retryable=True) from None
    if not d:
        raise ApiError("NOT_FOUND", "That notification isn't in your inbox.")
    return _out(d)
