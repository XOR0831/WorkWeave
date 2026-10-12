"""Demo usage caps (ADR-026 free-trial protection, ADR-029 tiers).

Each guarded action is charged before its external call, in the transaction that authorized it
(or a short one right after), against this visitor run's allowance and its tier's shared pool.
PUBLIC runs and EVALUATOR runs (opened with a valid access code) have separate limits and pools,
so public traffic can never use up the judges' allowance. Limits live in demo_usage_limits and are
changed with the CLI; 0 or a missing row turns a cap off. If any bucket is full nothing is counted
and the caller gets LIMIT_REACHED with `limit: {kind, scope, resets_at}`. Failed external calls
still count, which errs on the side of the budget.
"""

import uuid
from datetime import UTC, datetime, time, timedelta
from typing import Any, Literal

from sqlalchemy import Connection

from app.errors import ApiError
from app.repositories import usage
from app.services import access

Kind = Literal["DEMO_RUN", "TUTOR_TURN", "VOICE_LISTEN", "VOICE_SPEECH"]
Tier = Literal["PUBLIC", "EVALUATOR"]
# What the UI is told: this run, the access code (new workspaces), or everyone in the tier.
Scope = Literal["RUN", "CODE", "GLOBAL"]

# The UI adds when the limit resets (in the visitor's time zone) from `resets_at`.
MESSAGES: dict[tuple[str, str], str] = {
    ("DEMO_RUN", "GLOBAL"): "The demo has reached today's limit for new workspaces. You can still continue an existing one.",
    ("DEMO_RUN", "CODE"): "This access code has started its new demo workspaces for today. You can still continue an existing one.",
    ("TUTOR_TURN", "RUN"): "This demo workspace has used its assistant messages for today. Your work is saved; start a fresh demo to keep going.",
    ("TUTOR_TURN", "GLOBAL"): "The demo assistants have reached today's shared limit. Your work is saved.",
    ("VOICE_LISTEN", "RUN"): "Voice input has reached its limit for this demo workspace today. Type your answer instead.",
    ("VOICE_LISTEN", "GLOBAL"): "Voice input has reached today's shared demo limit. Type your answer instead.",
    ("VOICE_SPEECH", "RUN"): "Reading replies aloud has reached its limit for this demo workspace today. Replies stay on screen as text.",
    ("VOICE_SPEECH", "GLOBAL"): "Reading replies aloud has reached today's shared demo limit. Replies stay on screen as text.",
}
POOL = {"PUBLIC": "PUBLIC_POOL", "EVALUATOR": "EVALUATOR_POOL"}


def resets_at(now: datetime | None = None) -> str:
    """Counters are per UTC day: the next 00:00 UTC."""
    now = now or datetime.now(UTC)
    return datetime.combine(now.date() + timedelta(days=1), time(0), UTC).isoformat()


def _refuse(kind: str, scope: Scope) -> ApiError:
    return ApiError("LIMIT_REACHED", MESSAGES[(kind, scope)], details={"limit": {"kind": kind, "scope": scope, "resets_at": resets_at()}})


def tier_of(conn: Connection, session: dict[str, Any] | None) -> tuple[Tier, dict[str, Any] | None]:
    code = access.code_of_session(conn, session)
    return ("EVALUATOR", code) if code else ("PUBLIC", None)


def charge(conn: Connection, kind: Kind, workspace_id: uuid.UUID, session: dict[str, Any]) -> Tier:
    """Counts one use for this run and its tier's pool, or raises LIMIT_REACHED. On raise the
    caller's transaction must roll back (route transactions do), so nothing partial is counted."""
    tier, _ = tier_of(conn, session)
    caps = usage.limits(conn)
    per_run, per_pool = caps.get((tier, "RUN", kind), 0), caps.get((tier, "POOL", kind), 0)
    if per_run > 0 and not usage.try_increment(conn, "RUN", str(workspace_id), kind, per_run):
        raise _refuse(kind, "RUN")
    if per_pool > 0 and not usage.try_increment(conn, POOL[tier], "pool", kind, per_pool):
        raise _refuse(kind, "GLOBAL")
    return tier


def charge_new_run(conn: Connection, code: dict[str, Any] | None) -> None:
    """A new demo workspace: per access code (its own daily maximum) and the tier's pool."""
    tier: Tier = "EVALUATOR" if code else "PUBLIC"
    if code and not usage.try_increment(conn, "ACCESS_CODE", str(code["access_code_id"]), "DEMO_RUN", code["max_runs_per_day"]):
        raise _refuse("DEMO_RUN", "CODE")
    per_pool = usage.limits(conn).get((tier, "POOL", "DEMO_RUN"), 0)
    if per_pool > 0 and not usage.try_increment(conn, POOL[tier], "pool", "DEMO_RUN", per_pool):
        raise _refuse("DEMO_RUN", "GLOBAL")


def charge_failed_attempt(conn: Connection) -> None:
    per_pool = usage.limits(conn).get(("PUBLIC", "POOL", "ACCESS_ATTEMPT_FAILED"), 0)
    if per_pool > 0 and not usage.try_increment(conn, "PUBLIC_POOL", "pool", "ACCESS_ATTEMPT_FAILED", per_pool):
        raise ApiError("LIMIT_REACHED", "Too many incorrect access codes were tried today. Try again tomorrow, or continue as a public visitor.")


def status(conn: Connection, workspace_id: uuid.UUID, session: dict[str, Any] | None) -> dict[str, Any]:
    """What this visitor run can still do today, so the UI can show a limit before anyone hits it.
    `remaining` is the smaller of the run's and the pool's allowance (None when uncapped)."""
    tier, _ = tier_of(conn, session)
    caps = usage.limits(conn)
    out: dict[str, Any] = {"tier": tier, "resets_at": resets_at()}
    for kind, key in (("TUTOR_TURN", "tutor_turn"), ("VOICE_LISTEN", "voice_listen"), ("VOICE_SPEECH", "voice_speech")):
        per_run, per_pool = caps.get((tier, "RUN", kind), 0), caps.get((tier, "POOL", kind), 0)
        left: dict[str, int] = {}
        if per_run > 0:
            left["RUN"] = max(0, per_run - usage.used_today(conn, "RUN", str(workspace_id), kind))
        if per_pool > 0:
            left["GLOBAL"] = max(0, per_pool - usage.used_today(conn, POOL[tier], "pool", kind))
        blocked = next((scope for scope in ("RUN", "GLOBAL") if left.get(scope) == 0), None)
        out[key] = {"available": blocked is None, "scope": blocked, "remaining": min(left.values()) if left else None}
    return out


def summary(conn: Connection, session: dict[str, Any] | None, code: dict[str, Any] | None) -> dict[str, Any]:
    """The visitor's tier and its daily caps, with this run's use when a company is open (the
    entry prompt and the header's limits chip). Counts only; nothing about what was said."""
    tier: Tier = tier_of(conn, session)[0] if session else ("EVALUATOR" if code else "PUBLIC")
    caps = usage.limits(conn)
    items = []
    for kind in ("TUTOR_TURN", "VOICE_LISTEN", "VOICE_SPEECH"):
        per_run, per_pool = caps.get((tier, "RUN", kind), 0), caps.get((tier, "POOL", kind), 0)
        items.append({
            "kind": kind,
            "limit": per_run or None,
            "used": usage.used_today(conn, "RUN", str(session["workspace_id"]), kind) if session else None,
            "shared_full": bool(per_pool and usage.used_today(conn, POOL[tier], "pool", kind) >= per_pool),
        })
    return {"tier": tier, "resets_at": resets_at(), "run_open": session is not None, "items": items,
            "new_workspaces_per_day": (code or {}).get("max_runs_per_day") if tier == "EVALUATOR" else None}
