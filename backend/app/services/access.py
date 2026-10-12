"""Evaluator access codes (ADR-029).

A code gives a browser's demo runs the EVALUATOR tier: higher daily caps in their own pool (and,
when configured, the paid voice-listening key). Codes are reusable until they expire or are
revoked, carry ~80 random bits (Crockford base32, e.g. WW-7K4Q-M9TX-2PLR), and are stored only as a
SHA-256 of their normalized form. The browser keeps the normalized code in its HttpOnly session
cookie so new runs inherit it; every capped action re-checks the code server-side, so revocation
and expiry apply on the next request. Wrong codes count against a shared daily attempt cap.
"""

import hashlib
import re
import secrets
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Connection

from app.db import transaction
from app.errors import ApiError
from app.repositories import access as repo
from app.repositories import usage as usage_repo

ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"  # Crockford base32: no I, L, O, U
CODE_CHARS = 16  # 80 bits
NORMALIZED_RE = re.compile(rf"^[{ALPHABET}]{{{CODE_CHARS}}}$")


def generate() -> tuple[str, str]:
    """(display code, normalized code)."""
    raw = "".join(secrets.choice(ALPHABET) for _ in range(CODE_CHARS))
    return "WW-" + "-".join(raw[i : i + 4] for i in range(0, CODE_CHARS, 4)), raw


def normalize(code: str | None) -> str | None:
    """Accepts any case, spaces and dashes, and the usual look-alikes (O→0, I/L→1)."""
    if not code or len(code) > 64:
        return None
    s = re.sub(r"[^0-9A-Za-z]", "", code).upper()
    if s.startswith("WW") and len(s) == CODE_CHARS + 2:
        s = s[2:]
    s = s.translate(str.maketrans("OIL", "011"))
    return s if NORMALIZED_RE.match(s) else None


def code_hash(normalized: str) -> str:
    return hashlib.sha256(normalized.encode()).hexdigest()


def create(conn: Connection, label: str, expires_at: datetime, max_runs_per_day: int = 50) -> str:
    """Creates a code and returns it. It is shown once; only its hash is stored."""
    display, normalized = generate()
    repo.create(conn, label.strip(), code_hash(normalized), normalized[-4:], expires_at, max_runs_per_day)
    return display


def valid_code(conn: Connection, normalized: str | None) -> dict[str, Any] | None:
    return repo.valid_by_hash(conn, code_hash(normalized)) if normalized else None


def code_of_session(conn: Connection, session: dict[str, Any] | None) -> dict[str, Any] | None:
    """The still-valid evaluator code of a visitor run, if any."""
    return repo.valid_by_id(conn, session.get("access_code_id")) if session else None


def dto(code: dict[str, Any] | None) -> dict[str, Any]:
    """What the browser may know: the tier and until when. Never the code or its label."""
    return {"tier": "EVALUATOR", "expires_at": code["expires_at"].isoformat()} if code else {"tier": "PUBLIC", "expires_at": None}


def redeem(raw_code: str, token_hashes: list[str]) -> tuple[str, dict[str, Any]]:
    """Checks a code and upgrades this browser's runs. Returns (normalized code, code row).

    A wrong code is counted in its own committed transaction before the error, so the attempt cap
    holds even though the request fails."""
    from app.services import usage

    normalized = normalize(raw_code)
    with transaction() as conn:
        code = valid_code(conn, normalized)
        if code:
            repo.attach(conn, token_hashes, code["access_code_id"])
            repo.touch(conn, code["access_code_id"])
            return normalized or "", code
    with transaction() as conn:
        usage.charge_failed_attempt(conn)
    raise ApiError("MALFORMED_INPUT", "That access code isn't valid, or it has expired. Check it and try again.")


def release(token_hashes: list[str]) -> None:
    with transaction() as conn:
        repo.attach(conn, token_hashes, None)


def runs_today(conn: Connection, access_code_id: uuid.UUID) -> int:
    return usage_repo.used_today(conn, "ACCESS_CODE", str(access_code_id), "DEMO_RUN")
