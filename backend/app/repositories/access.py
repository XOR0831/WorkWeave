"""Evaluator access codes (migration 0005). Only hashes of codes are stored."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Connection, text

W = "workweave"


def create(conn: Connection, label: str, code_hash: str, hint: str, expires_at: datetime, max_runs_per_day: int) -> uuid.UUID:
    return conn.execute(
        text(
            f"""INSERT INTO {W}.demo_access_codes (label, code_hash, code_hint, expires_at, max_runs_per_day)
                VALUES (:l, :h, :hint, :exp, :m) RETURNING access_code_id"""
        ),
        {"l": label, "h": code_hash, "hint": hint, "exp": expires_at, "m": max_runs_per_day},
    ).scalar_one()


def valid_by_hash(conn: Connection, code_hash: str) -> dict[str, Any] | None:
    r = conn.execute(
        text(f"SELECT * FROM {W}.demo_access_codes WHERE code_hash = :h AND revoked_at IS NULL AND expires_at > now()"),
        {"h": code_hash},
    ).first()
    return dict(r._mapping) if r else None


def valid_by_id(conn: Connection, access_code_id: uuid.UUID | None) -> dict[str, Any] | None:
    if access_code_id is None:
        return None
    r = conn.execute(
        text(f"SELECT * FROM {W}.demo_access_codes WHERE access_code_id = :id AND revoked_at IS NULL AND expires_at > now()"),
        {"id": access_code_id},
    ).first()
    return dict(r._mapping) if r else None


def touch(conn: Connection, access_code_id: uuid.UUID) -> None:
    conn.execute(text(f"UPDATE {W}.demo_access_codes SET last_used_at = now() WHERE access_code_id = :id"), {"id": access_code_id})


def attach(conn: Connection, token_hashes: list[str], access_code_id: uuid.UUID | None) -> None:
    """Upgrade (or, with None, downgrade) this browser's visitor runs."""
    if token_hashes:
        conn.execute(
            text(f"UPDATE {W}.demo_visitor_sessions SET access_code_id = :c, updated_at = now(), revision = revision + 1 WHERE token_hash = ANY(:t)"),
            {"c": access_code_id, "t": token_hashes},
        )


def revoke(conn: Connection, label: str) -> bool:
    return conn.execute(
        text(f"UPDATE {W}.demo_access_codes SET revoked_at = now() WHERE label = :l AND revoked_at IS NULL RETURNING access_code_id"), {"l": label}
    ).first() is not None


def listing(conn: Connection) -> list[dict[str, Any]]:
    return [
        dict(r._mapping)
        for r in conn.execute(
            text(
                f"""SELECT c.label, c.code_hint, c.expires_at, c.revoked_at, c.max_runs_per_day, c.created_at, c.last_used_at,
                           coalesce(u.used, 0) AS runs_today
                    FROM {W}.demo_access_codes c
                    LEFT JOIN {W}.demo_usage u ON u.scope_type = 'ACCESS_CODE' AND u.scope_key = c.access_code_id::text
                         AND u.usage_kind = 'DEMO_RUN' AND u.usage_day = (now() AT TIME ZONE 'UTC')::date
                    ORDER BY c.created_at"""
            )
        )
    ]
