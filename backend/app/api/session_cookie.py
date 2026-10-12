"""The visitor's session cookie.

Firebase Hosting forwards only a cookie named `__session` to Cloud Run (it strips all others), so
the whole browser session lives in one HttpOnly, SameSite=Lax cookie scoped to the API path:

    __session = base64url(JSON {"c": <current run token>, "r": {<company key>: <run token>, ...}, "a": <access code>})

"c" is the run currently in use; "r" lets each company resume its own run; "a" is an evaluator
access code (normalized, ADR-029) so new runs in this browser inherit the evaluator tier. The code
is re-checked server-side on use; a revoked or expired code is simply ignored. The value is untrusted
input: it's size-capped, keys and tokens are validated, and anything malformed is ignored. Tokens
are opaque random secrets checked server-side by their hash, so the cookie needs no signature:
editing it can only swap in tokens the browser already holds (and a token is bound to its scenario).
The old `ww_session` / `ww_run_<key>` cookies are still read once and cleared on the next write.
"""

import base64
import json
import re
from dataclasses import dataclass, field

from fastapi import Request, Response

from app.config import get_settings

COOKIE = "__session"
LEGACY_CURRENT = "ww_session"
LEGACY_RUN_PREFIX = "ww_run_"
KEY_RE = re.compile(r"^[a-z0-9-]{1,40}$")
TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{16,128}$")
ACCESS_RE = re.compile(r"^[0-9A-Z]{16}$")
MAX_BYTES = 3000
MAX_RUNS = 12


@dataclass
class SessionCookie:
    current: str | None = None
    runs: dict[str, str] = field(default_factory=dict)
    access: str | None = None
    legacy_names: list[str] = field(default_factory=list)


def _token(v: object) -> str | None:
    return v if isinstance(v, str) and TOKEN_RE.match(v) else None


def read(request: Request) -> SessionCookie:
    raw = request.cookies.get(COOKIE)
    legacy = [k for k in request.cookies if k == LEGACY_CURRENT or k.startswith(LEGACY_RUN_PREFIX)]
    if raw and len(raw) <= MAX_BYTES:
        try:
            data = json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
        except (ValueError, TypeError):
            data = None
        if isinstance(data, dict):
            runs = data.get("r") if isinstance(data.get("r"), dict) else {}
            clean = {k: t for k, v in list(runs.items())[:MAX_RUNS] if isinstance(k, str) and KEY_RE.match(k) and (t := _token(v))}
            a = data.get("a")
            return SessionCookie(_token(data.get("c")), clean, a if isinstance(a, str) and ACCESS_RE.match(a) else None, legacy)
    # Fallback: the pre-__session cookies (cleared on the next write).
    runs = {k[len(LEGACY_RUN_PREFIX):]: t for k, v in request.cookies.items() if k.startswith(LEGACY_RUN_PREFIX) and KEY_RE.match(k[len(LEGACY_RUN_PREFIX):]) and (t := _token(v))}
    return SessionCookie(_token(request.cookies.get(LEGACY_CURRENT)), runs, None, legacy)


def write(response: Response, cookie: SessionCookie) -> None:
    s = get_settings()
    data: dict[str, object] = {"c": cookie.current, "r": dict(list(cookie.runs.items())[-MAX_RUNS:])}
    if cookie.access:
        data["a"] = cookie.access
    payload = json.dumps(data, separators=(",", ":"))
    value = base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")
    response.set_cookie(COOKIE, value, max_age=s.session_ttl_minutes * 60, httponly=True, samesite="lax", secure=s.cookie_secure, path=s.api_prefix)
    for name in cookie.legacy_names:
        response.delete_cookie(name, path=s.api_prefix)
