"""Demo entry service (ADR-024; blueprint 07, 12 and 16).

- Catalog: only READY synthetic packs.
- Sessions: opaque random tokens; only SHA-256 hashes are stored. One run per visitor and
  company, held in that company's HttpOnly cookie; the "current" cookie names the company in use.
- Fresh start: materialize a new isolated workspace, then revoke the previous run, in one
  transaction. Any failure rolls back and the previous run stays usable.
- Personas: the selected pack's roster inside this visitor's workspace, authorized server-side.
"""

import hashlib
import json
import logging
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from sqlalchemy import Connection

from app.config import get_settings
from app.domain.grants import ui_grants
from app.errors import ApiError
from app.repositories import demo as repo
from app.services import access, usage

log = logging.getLogger("workweave.demo")


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def content_hash(rows: list[Any], personas: list[dict[str, Any]], presentation: dict[str, Any]) -> str:
    canonical = json.dumps({"identity": rows, "personas": personas, "presentation": presentation}, sort_keys=True, default=str)
    return "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()


def baseline_hash(conn: Connection, scenario: dict[str, Any]) -> str:
    rows = repo.baseline_identity_digest_rows(conn, scenario["organization_id"], scenario["workspace_id"])
    return content_hash(rows, repo.scenario_personas(conn, scenario["scenario_id"]), scenario["presentation"])


# ---------------------------------------------------------------- DTOs (frontend types/contracts.ts)
def scenario_card(s: dict[str, Any]) -> dict[str, Any]:
    p = s["presentation"] or {}
    return {
        "scenario_id": str(s["scenario_id"]),
        "key": s["company_key"],
        "company_name": s["company_name"],
        "industry": s["industry"] or "",
        "story": p.get("story", ""),
        "pack_version": s["pack_version"],
        "status": "READY",
        "role_in_review": p.get("role_in_review", ""),
        "terminology": p.get("terminology", {"workItem": "item", "workItems": "items", "team": "team"}),
    }


def persona_dto(p: dict[str, Any]) -> dict[str, Any]:
    return {
        "employee_id": str(p["employee_id"]),
        "first_name": p["first_name"],
        "last_name": p["last_name"],
        "role_name": p["role_name"] or "",
        "team_name": p["team_name"] or "",
        "team_role": p["team_role"] or "MEMBER",
        "employment_status": p["employment_status"],
        "scenario_note": p["scenario_note"],
        "grants": ui_grants(list(p["actions"] or [])),
        # The demo page shows featured personas with what each lets a visitor try; all stay switchable.
        "featured": bool(p.get("featured")),
        **({"showcase": p["showcase"]} if p.get("featured") and p.get("showcase") else {}),
    }


@dataclass
class Resolved:
    session: dict[str, Any]
    scenario: dict[str, Any]


def session_dto(conn: Connection, r: Resolved) -> dict[str, Any]:
    roster = repo.personas(conn, r.session)
    if not roster:
        raise ApiError("DEPENDENCY_UNAVAILABLE", "This workspace has no personas. Start a fresh demo.", retryable=True)
    active = next((p for p in roster if p["employee_id"] == r.session["active_employee_id"]), None)
    return {
        "session_id": str(r.session["demo_visitor_session_id"]),
        "scenario": scenario_card(r.scenario),
        "workspace_id": str(r.session["workspace_id"]),
        "pack_version": r.session["pack_version"],
        # Until a persona is chosen the pack's first persona is a display placeholder only.
        "persona": persona_dto(active or roster[0]),
        "persona_selected": active is not None,
        "expires_at": r.session["expires_at"].isoformat(),
        # Evaluator access (ADR-029): the tier and until when, never the code itself.
        "access": access.dto(access.code_of_session(conn, r.session)),
    }


# ---------------------------------------------------------------- resolution
def resolve(conn: Connection, token: str | None, *, required: bool = True) -> Resolved | None:
    """Token → ACTIVE, unexpired session of a still-READY scenario.

    Expiry is decided by expires_at at request time; a cleanup job (not in this slice) may later
    mark rows EXPIRED. Read paths never write.
    """
    if not token:
        if required:
            raise ApiError("SESSION_EXPIRED", "No demo session is open. Choose a company in the catalog.")
        return None
    s = repo.session_by_token_hash(conn, hash_token(token))
    if not s or s["status"] == "REVOKED":
        raise ApiError("SESSION_EXPIRED", "This demo session has ended. Choose a company in the catalog.")
    # The database already enforces this (migration 0002); checked again so a demo token can never
    # act on a main-app (OPERATIONAL) workspace even if a constraint were changed.
    if s.get("attached_workspace_kind") != "DEMO":
        log.error("demo session %s is attached to a %s workspace", s.get("demo_visitor_session_id"), s.get("attached_workspace_kind"))
        raise ApiError("FORBIDDEN", "This session isn't attached to a demo workspace.")
    if s["status"] == "EXPIRED" or s["expires_at"] <= datetime.now(UTC):
        raise ApiError("SESSION_EXPIRED", "Your demo session expired. Open the company again to start a new run.")
    scenario = repo.ready_scenario(conn, s["scenario_id"])
    if not scenario:
        raise ApiError("SESSION_EXPIRED", "This company is no longer in the demo catalog.")
    return Resolved(s, scenario)


def try_resolve(conn: Connection, token: str | None) -> Resolved | None:
    try:
        return resolve(conn, token, required=False)
    except ApiError:
        return None


# ---------------------------------------------------------------- commands
@dataclass
class Opened:
    dto: dict[str, Any]
    token: str
    company_key: str
    resumed: bool


def open_session(conn: Connection, scenario_id: str, intent: Literal["RESUME", "FRESH"], pack_version: str | None, run_token: str | None, request_id: uuid.UUID, access_code: dict[str, Any] | None = None) -> Opened:
    """`access_code`: this browser's valid evaluator code, if any; a new run inherits it."""
    try:
        sid = uuid.UUID(scenario_id)
    except ValueError as e:
        raise ApiError("MALFORMED_INPUT", "scenario_id must be a UUID.") from e
    scenario = repo.ready_scenario(conn, sid)
    if not scenario:
        raise ApiError("NOT_FOUND", "This company isn't in the demo catalog.")
    if pack_version and pack_version != scenario["pack_version"]:
        raise ApiError("GUARD_FAILED", f"Pack {pack_version} isn't available; the active version is {scenario['pack_version']}.")
    existing = try_resolve(conn, run_token)
    if existing and existing.scenario["scenario_id"] != sid:
        existing = None  # a run cookie for another company never opens this one
    if intent == "RESUME" and existing:
        return Opened(session_dto(conn, existing), run_token or "", scenario["company_key"], True)

    if baseline_hash(conn, scenario) != scenario["content_hash"]:
        raise ApiError("DEPENDENCY_UNAVAILABLE", "This company's pack changed after activation and must be re-verified before new runs start.")
    usage.charge_new_run(conn, access_code)  # rolls back with the route transaction if materialization fails
    expires = datetime.now(UTC) + timedelta(minutes=get_settings().session_ttl_minutes)
    org, ws, ids = repo.materialize_identity(conn, scenario, expires)
    repo.materialize_learning(conn, scenario, org, ws, ids)
    repo.materialize_knowledge(conn, scenario, org, ws, ids)
    repo.materialize_work(conn, scenario, org, ws, ids, datetime.now(UTC))
    if repo.count_scope(conn, org, ws, "employees") != repo.count_scope(conn, scenario["organization_id"], scenario["workspace_id"], "employees"):
        raise ApiError("DEPENDENCY_UNAVAILABLE", "The workspace copy is incomplete. Nothing was saved; try again.", retryable=True)
    token = secrets.token_urlsafe(32)
    new_id = repo.insert_session(conn, org, ws, scenario, hash_token(token), expires, access_code["access_code_id"] if access_code else None)
    repo.audit(conn, org, ws, "demo_session.created" if not existing else "demo_session.fresh_start", new_id, 1, request_id)
    if existing:
        # Only this visitor's run for this company. Shared baselines and other runs are untouched.
        repo.set_session_status(conn, existing.session, "REVOKED")
    fresh = repo.session_by_token_hash(conn, hash_token(token))
    assert fresh is not None
    return Opened(session_dto(conn, Resolved(fresh, scenario)), token, scenario["company_key"], False)


def list_personas(conn: Connection, token: str | None) -> list[dict[str, Any]]:
    r = resolve(conn, token)
    assert r is not None
    return [persona_dto(p) for p in repo.personas(conn, r.session)]


def switch_persona(conn: Connection, token: str | None, employee_id: str, request_id: uuid.UUID) -> dict[str, Any]:
    r = resolve(conn, token)
    assert r is not None
    try:
        eid = uuid.UUID(employee_id)
    except ValueError as e:
        raise ApiError("MALFORMED_INPUT", "employee_id must be a UUID.") from e
    if not any(p["employee_id"] == eid for p in repo.personas(conn, r.session)):
        raise ApiError("FORBIDDEN", "That persona isn't part of this company's demo workspace.")
    rev = repo.set_active_persona(conn, r.session, eid)
    repo.audit(conn, r.session["organization_id"], r.session["workspace_id"], "demo_session.persona_selected", r.session["demo_visitor_session_id"], rev, request_id, actor=eid)
    r.session["active_employee_id"] = eid
    return session_dto(conn, r)


def runs(conn: Connection, run_tokens: dict[str, str]) -> list[dict[str, Any]]:
    """This visitor's resumable runs, from their per-company cookies (PROPOSED endpoint)."""
    out = []
    for key, token in run_tokens.items():
        r = try_resolve(conn, token)
        if not r or r.scenario["company_key"] != key:
            continue
        dto = session_dto(conn, r)
        out.append(
            {
                "key": key,
                "scenario_id": dto["scenario"]["scenario_id"],
                "workspace_id": dto["workspace_id"],
                "pinned_pack_version": dto["pack_version"],
                "active_pack_version": r.scenario["pack_version"],
                "persona_selected": dto["persona_selected"],
                "persona": dto["persona"] if dto["persona_selected"] else None,
                "is_active_session": False,
            }
        )
    return out
