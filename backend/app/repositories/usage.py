"""Demo usage counters and limits (migration 0005). No content or personal data: counts only."""

from typing import Any

from sqlalchemy import Connection, text

W = "workweave"
TODAY = "(now() AT TIME ZONE 'UTC')::date"


def try_increment(conn: Connection, scope_type: str, scope_key: str, kind: str, limit: int) -> bool:
    """Adds one use for today (UTC) unless the bucket already reached `limit`. Row-locked, so
    concurrent callers can't overshoot. The caller's transaction decides whether it sticks."""
    row = conn.execute(
        text(
            f"""
            INSERT INTO {W}.demo_usage (scope_type, scope_key, usage_kind, usage_day, used)
            VALUES (:t, :k, :kind, {TODAY}, 1)
            ON CONFLICT (scope_type, scope_key, usage_kind, usage_day) DO UPDATE
               SET used = {W}.demo_usage.used + 1, updated_at = now()
             WHERE {W}.demo_usage.used < :limit
            RETURNING used
            """
        ),
        {"t": scope_type, "k": scope_key, "kind": kind, "limit": limit},
    ).first()
    return row is not None


def used_today(conn: Connection, scope_type: str, scope_key: str, kind: str) -> int:
    return conn.execute(
        text(f"SELECT used FROM {W}.demo_usage WHERE scope_type = :t AND scope_key = :k AND usage_kind = :kind AND usage_day = {TODAY}"),
        {"t": scope_type, "k": scope_key, "kind": kind},
    ).scalar_one_or_none() or 0


def reset_today(conn: Connection, kind: str | None = None) -> int:
    """Clears today's counters (all visitors), optionally for one kind. Returns rows removed."""
    return conn.execute(
        text(f"DELETE FROM {W}.demo_usage WHERE usage_day = {TODAY} AND (CAST(:k AS text) IS NULL OR usage_kind = :k)"),
        {"k": kind},
    ).rowcount


def prune_before(conn: Connection, keep_days: int) -> int:
    """Removes counters older than keep_days (housekeeping; past days never limit anything)."""
    return conn.execute(
        text(f"DELETE FROM {W}.demo_usage WHERE usage_day < {TODAY} - CAST(:d AS integer)"), {"d": keep_days}
    ).rowcount


def count_before(conn: Connection, keep_days: int) -> int:
    return conn.execute(text(f"SELECT count(*) FROM {W}.demo_usage WHERE usage_day < {TODAY} - CAST(:d AS integer)"), {"d": keep_days}).scalar_one()


def limits(conn: Connection) -> dict[tuple[str, str, str], int]:
    """{(tier, scope_type, kind): daily_limit}. A missing row means no cap."""
    return {(r.tier, r.scope_type, r.usage_kind): r.daily_limit for r in conn.execute(text(f"SELECT tier, scope_type, usage_kind, daily_limit FROM {W}.demo_usage_limits"))}


def limit_rows(conn: Connection) -> list[dict[str, Any]]:
    return [dict(r._mapping) for r in conn.execute(text(f"SELECT * FROM {W}.demo_usage_limits ORDER BY tier DESC, scope_type DESC, usage_kind"))]


def set_limit(conn: Connection, tier: str, scope_type: str, kind: str, daily_limit: int, by: str) -> None:
    conn.execute(
        text(
            f"""INSERT INTO {W}.demo_usage_limits (tier, scope_type, usage_kind, daily_limit, updated_by) VALUES (:t, :s, :k, :n, :by)
                ON CONFLICT (tier, scope_type, usage_kind) DO UPDATE SET daily_limit = EXCLUDED.daily_limit, updated_by = EXCLUDED.updated_by, updated_at = now()"""
        ),
        {"t": tier, "s": scope_type, "k": kind, "n": daily_limit, "by": by},
    )
