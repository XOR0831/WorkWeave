"""The recipient notification inbox (blueprint/19, ADR-048): a minimal Firestore projection.

Firestore holds only what an inbox row needs: who it's for, a short message with no private text, the
resource to open (the backend re-checks access when it's opened), the source revision and the read
marker. It is never a business record: reading a notification accepts, acknowledges or approves nothing.

Documents live at workspaces/{workspace_id}/inboxes/{employee_id}/notifications/{notification_id}, so
a workspace's and a person's notifications never mix. The notification ID is the outbox event's ID,
so a retried delivery rewrites the same document; it never creates a second one, never clears the
read marker and never lets an older source revision replace a newer one.

Locally the Firestore emulator runs in Docker (local/compose.yaml, FIRESTORE_EMULATOR_HOST); in the
cloud the client uses the service's own credentials. NOTIFICATIONS=none turns the inbox off.
"""

import os
import threading
from datetime import datetime
from typing import Any, Protocol

from app.config import get_settings


class InboxUnavailable(Exception):
    """Firestore couldn't be reached or refused the call (the dispatcher retries later)."""


class Inbox(Protocol):
    available: bool

    def upsert(self, workspace_id: str, employee_id: str, notification_id: str, doc: dict[str, Any]) -> bool: ...
    def list(self, workspace_id: str, employee_id: str, limit: int = 50) -> list[dict[str, Any]]: ...
    def mark_read(self, workspace_id: str, employee_id: str, notification_id: str, at: datetime) -> dict[str, Any] | None: ...


TIMEOUT = 10.0  # seconds per Firestore call: an outage fails fast and the dispatcher retries later


class FirestoreInbox:
    available = True

    def __init__(self, project: str, emulator_host: str | None):
        if emulator_host:
            os.environ["FIRESTORE_EMULATOR_HOST"] = emulator_host  # the client library reads it from here
        else:
            os.environ.pop("FIRESTORE_EMULATOR_HOST", None)  # even an empty value would mean "emulator"
        from google.cloud import firestore  # imported here so the API starts without it when NOTIFICATIONS=none

        self._fs = firestore
        self._db = firestore.Client(project=project)

    def _ref(self, ws: str, emp: str, nid: str):
        return self._db.collection("workspaces").document(ws).collection("inboxes").document(emp).collection("notifications").document(nid)

    def upsert(self, workspace_id: str, employee_id: str, notification_id: str, doc: dict[str, Any]) -> bool:
        ref = self._ref(workspace_id, employee_id, notification_id)

        @self._fs.transactional
        def write(t) -> bool:
            snap = ref.get(transaction=t, timeout=TIMEOUT)
            old = snap.to_dict() if snap.exists else None
            if old and int(old.get("source_revision", 0)) > int(doc["source_revision"]):
                return False  # a newer state of this notification is already there
            t.set(ref, {**doc, "read_at": (old or {}).get("read_at")})
            return True

        try:
            return write(self._db.transaction())
        except Exception as e:  # noqa: BLE001 - any client/transport failure is retried by the dispatcher
            raise InboxUnavailable(f"{type(e).__name__}: {str(e)[:160]}") from None

    def list(self, workspace_id: str, employee_id: str, limit: int = 50) -> list[dict[str, Any]]:
        try:
            col = self._db.collection("workspaces").document(workspace_id).collection("inboxes").document(employee_id).collection("notifications")
            docs = col.order_by("created_at", direction=self._fs.Query.DESCENDING).limit(limit).stream(timeout=TIMEOUT)
            return [{**d.to_dict(), "notification_id": d.id} for d in docs]
        except Exception as e:  # noqa: BLE001
            raise InboxUnavailable(f"{type(e).__name__}: {str(e)[:160]}") from None

    def mark_read(self, workspace_id: str, employee_id: str, notification_id: str, at: datetime) -> dict[str, Any] | None:
        ref = self._ref(workspace_id, employee_id, notification_id)
        try:
            snap = ref.get(timeout=TIMEOUT)
            if not snap.exists:
                return None
            data = snap.to_dict()
            if not data.get("read_at"):
                ref.update({"read_at": at}, timeout=TIMEOUT)  # the only field a reader may change
                data["read_at"] = at
            return {**data, "notification_id": notification_id}
        except Exception as e:  # noqa: BLE001
            raise InboxUnavailable(f"{type(e).__name__}: {str(e)[:160]}") from None


class MemoryInbox:
    """Tests only: the same rules as FirestoreInbox, kept in memory."""

    available = True

    def __init__(self):
        self.docs: dict[tuple[str, str, str], dict[str, Any]] = {}
        self.fail = False
        self._lock = threading.Lock()

    def upsert(self, workspace_id, employee_id, notification_id, doc):
        if self.fail:
            raise InboxUnavailable("test outage")
        with self._lock:
            key = (workspace_id, employee_id, notification_id)
            old = self.docs.get(key)
            if old and int(old["source_revision"]) > int(doc["source_revision"]):
                return False
            self.docs[key] = {**doc, "read_at": (old or {}).get("read_at")}
            return True

    def list(self, workspace_id, employee_id, limit=50):
        if self.fail:
            raise InboxUnavailable("test outage")
        rows = [{**d, "notification_id": k[2]} for k, d in self.docs.items() if k[0] == workspace_id and k[1] == employee_id]
        return sorted(rows, key=lambda d: d["created_at"], reverse=True)[:limit]

    def mark_read(self, workspace_id, employee_id, notification_id, at):
        d = self.docs.get((workspace_id, employee_id, notification_id))
        if not d:
            return None
        d["read_at"] = d.get("read_at") or at
        return {**d, "notification_id": notification_id}


class _Off:
    available = False


_test: Any = None
_cached: Any = None
_lock = threading.Lock()


def install_test_inbox(inbox: Any) -> None:
    global _test
    _test = inbox


def get_inbox() -> Any:
    """The configured inbox, or an unavailable stand-in when NOTIFICATIONS=none."""
    global _cached
    if _test is not None:
        return _test
    s = get_settings()
    if s.notifications == "none":
        return _Off()
    with _lock:
        if _cached is None:
            # A release build always talks to real Firestore, whatever the local default says.
            _cached = FirestoreInbox(s.firestore_project, None if s.workweave_env == "release" else s.firestore_emulator_host)
        return _cached
