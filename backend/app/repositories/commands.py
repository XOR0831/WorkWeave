"""Command receipts (idempotency) and audit, committed in the same transaction as the change."""

import hashlib
import json
import uuid
from typing import Any

from sqlalchemy import Connection, text

W = "workweave"


def payload_hash(payload: dict[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def find_receipt(conn: Connection, org: uuid.UUID, ws: uuid.UUID, actor: uuid.UUID, command: str, key: str) -> dict[str, Any] | None:
    r = conn.execute(
        text(
            f"""SELECT payload_hash, response, committed_revision FROM {W}.command_receipts
                WHERE organization_id=:o AND workspace_id=:w AND actor_id=:a AND command=:c AND idempotency_key=:k"""
        ),
        {"o": org, "w": ws, "a": actor, "c": command, "k": key},
    ).first()
    return dict(r._mapping) if r else None


def record_receipt(conn: Connection, org: uuid.UUID, ws: uuid.UUID, actor: uuid.UUID, command: str, key: str, phash: str, response: dict[str, Any], revision: int) -> None:
    conn.execute(
        text(
            f"""INSERT INTO {W}.command_receipts (organization_id, workspace_id, actor_id, command, idempotency_key, payload_hash, status, response, committed_revision)
                VALUES (:o, :w, :a, :c, :k, :h, 'COMMITTED', CAST(:r AS jsonb), :rev)"""
        ),
        {"o": org, "w": ws, "a": actor, "c": command, "k": key, "h": phash, "r": json.dumps(response, default=str), "rev": revision},
    )


def audit(conn: Connection, org: uuid.UUID, ws: uuid.UUID, actor: uuid.UUID | None, action: str, resource_type: str, resource_id: uuid.UUID, revision: int, request_id: uuid.UUID) -> None:
    conn.execute(
        text(
            f"""INSERT INTO {W}.audit_events (organization_id, workspace_id, actor_id, action, resource_type, resource_id, resource_revision, result, request_id)
                VALUES (:o, :w, :a, :act, :rt, :rid, :rev, 'COMMITTED', :req)"""
        ),
        {"o": org, "w": ws, "a": actor, "act": action, "rt": resource_type, "rid": resource_id, "rev": revision, "req": request_id},
    )
