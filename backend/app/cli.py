"""Privileged local catalog CLI (not an HTTP endpoint).

    uv run python -m app.cli status
    uv run python -m app.cli sync-catalog ../seed/packs/northstar-manufacturing
    uv run python -m app.cli activate northstar --confirm-reviewed
    uv run python -m app.cli deactivate northstar

Evaluator access and demo caps (ADR-029):

    uv run python -m app.cli create-access-code --label "Judge - Panel A" --expires 2026-11-15
    uv run python -m app.cli list-access-codes
    uv run python -m app.cli revoke-access-code "Judge - Panel A"
    uv run python -m app.cli show-limits
    uv run python -m app.cli set-limit EVALUATOR POOL TUTOR_TURN 5000
    uv run python -m app.cli reset-usage --confirm [--kind TUTOR_TURN]   # clear today's counters now

sync-catalog validates a reviewed catalog.json against the existing baseline records and marks
the pack VALIDATED. activate re-verifies it, records the baseline content hash and marks it READY,
which makes it visible in GET /scenarios. Nothing here seeds, resets or deletes data.
"""

import argparse
import getpass
import json
import sys
from datetime import UTC, datetime, time
from pathlib import Path
from typing import Any

from sqlalchemy import Connection, Engine, create_engine, text

from app.config import get_settings
from app.repositories import access as access_repo
from app.repositories import demo as demo_repo
from app.repositories import usage as usage_repo
from app.services import access
from app.services.demo import baseline_hash

W = "workweave"


def _catalog_row(conn: Connection, company_key: str, pack_version: str | None = None) -> dict[str, Any]:
    sql = f"SELECT c.*, o.name AS company_name, o.industry FROM {W}.scenario_catalog c JOIN {W}.organizations o USING (organization_id) WHERE c.company_key=:k"
    params: dict[str, Any] = {"k": company_key}
    if pack_version:
        sql += " AND c.pack_version=:v"
        params["v"] = pack_version
    rows = [dict(r._mapping) for r in conn.execute(text(sql), params)]
    if len(rows) != 1:
        raise SystemExit(f"Expected exactly one catalog row for {company_key} {pack_version or ''}; found {len(rows)}.")
    return rows[0]


def validate_pack(conn: Connection, pack: dict[str, Any]) -> list[str]:
    problems = []
    if pack.get("schema") != "workweave.pack-catalog/1":
        problems.append("schema must be workweave.pack-catalog/1")
    if pack.get("synthetic") is not True:
        problems.append("only synthetic packs can enter the public catalog")
    pres = pack.get("presentation") or {}
    for f in ("story", "role_in_review", "terminology"):
        if not pres.get(f):
            problems.append(f"presentation.{f} is required")
    if not isinstance(pres.get("catalog_order"), int) or pres["catalog_order"] < 1:
        problems.append("presentation.catalog_order must be a positive integer")
    personas = pack.get("personas") or []
    if len(personas) < 4:
        problems.append("at least four functional personas are required (blueprint 16)")
    orders = [p.get("display_order") for p in personas]
    if sorted(orders) != list(range(1, len(personas) + 1)):
        problems.append("display_order must be 1..n without gaps")
    row = _catalog_row(conn, pack["company_key"], pack["pack_version"])
    for p in personas:
        e = conn.execute(
            text(f"SELECT first_name || ' ' || last_name FROM {W}.employees WHERE employee_id=:e AND organization_id=:o AND workspace_id=:w"),
            {"e": p["baseline_employee_id"], "o": row["organization_id"], "w": row["workspace_id"]},
        ).scalar()
        if e is None:
            problems.append(f"{p.get('display_name')}: baseline employee isn't in this pack's workspace")
        elif e != p.get("display_name"):
            problems.append(f"{p['baseline_employee_id']}: name mismatch ({e} vs {p.get('display_name')})")
        if not (p.get("scenario_note") or "").strip():
            problems.append(f"{p.get('display_name')}: scenario_note is required")
        problems += _showcase_problems(p)
    featured = [p for p in personas if p.get("featured")]
    if not 1 <= len(featured) <= 4:
        problems.append("feature one to four personas on the demo page (featured: true)")
    return problems


SHOWCASE_MODULES = {"ONBOARDING", "COMPANION", "HANDOVER", "EXIT_KT", "REVIEWS", "CURRICULA"}


def _showcase_problems(p: dict[str, Any]) -> list[str]:
    """A featured persona says what a visitor can try with it (owner decision 2026-10-10); the others
    may too, shown when the visitor opens all personas (owner request 2026-10-10)."""
    name, show = p.get("display_name"), p.get("showcase")
    if not isinstance(p.get("featured", False), bool):
        return [f"{name}: featured must be true or false"]
    if show is None:
        return [f"{name}: a featured persona needs a showcase"] if p.get("featured") else []
    if not isinstance(show, dict):
        return [f"{name}: showcase must be an object"]
    out = []
    for f in ("label", "headline"):
        if not (isinstance(show.get(f), str) and 0 < len(show[f].strip()) <= 80):
            out.append(f"{name}: showcase.{f} is required (at most 80 characters)")
    feats = show.get("features")
    if not isinstance(feats, list) or not 1 <= len(feats) <= 5:
        out.append(f"{name}: showcase.features needs one to five entries")
    else:
        for f in feats:
            if not isinstance(f, dict) or f.get("module") not in SHOWCASE_MODULES or not (isinstance(f.get("text"), str) and 0 < len(f["text"].strip()) <= 160):
                out.append(f"{name}: each showcase feature needs a module ({', '.join(sorted(SHOWCASE_MODULES))}) and text of at most 160 characters")
                break
    return out


def sync_catalog(engine: Engine, pack_dir: Path) -> None:
    pack = json.loads((pack_dir / "catalog.json").read_text())
    with engine.begin() as conn:
        problems = validate_pack(conn, pack)
        if problems:
            raise SystemExit("Pack not valid:\n- " + "\n- ".join(problems))
        row = _catalog_row(conn, pack["company_key"], pack["pack_version"])
        if row["status"] == "READY":
            raise SystemExit(f"{pack['company_key']} is READY; deactivate it before changing its metadata.")
        sid = row["scenario_id"]
        conn.execute(text(f"UPDATE {W}.scenario_catalog SET presentation=CAST(:p AS jsonb), status='VALIDATED', updated_at=now(), revision=revision+1 WHERE scenario_id=:s"), {"p": json.dumps(pack["presentation"]), "s": sid})
        conn.execute(text(f"DELETE FROM {W}.scenario_personas WHERE scenario_id=:s"), {"s": sid})
        showcase = demo_repo.has_showcase(conn)  # older databases (before migration 0011) keep loading
        for p in pack["personas"]:
            conn.execute(
                text(f"""INSERT INTO {W}.scenario_personas (scenario_id, baseline_employee_id, display_order, scenario_note, featured, showcase)
                         VALUES (:s, :e, :d, :n, :f, CAST(:sh AS jsonb))""")
                if showcase
                else text(f"INSERT INTO {W}.scenario_personas (scenario_id, baseline_employee_id, display_order, scenario_note) VALUES (:s, :e, :d, :n)"),
                {"s": sid, "e": p["baseline_employee_id"], "d": p["display_order"], "n": p["scenario_note"], "f": bool(p.get("featured")), "sh": json.dumps(p.get("showcase") or {})},
            )
    print(f"{pack['company_key']} {pack['pack_version']}: VALIDATED ({len(pack['personas'])} personas, {sum(1 for p in pack['personas'] if p.get('featured'))} featured)")


def activate(engine: Engine, company_key: str) -> None:
    with engine.begin() as conn:
        row = _catalog_row(conn, company_key)
        if row["status"] not in ("VALIDATED", "READY"):
            raise SystemExit(f"{company_key} is {row['status']}; run sync-catalog first.")
        if not conn.execute(text(f"SELECT count(*) FROM {W}.scenario_personas WHERE scenario_id=:s"), {"s": row["scenario_id"]}).scalar_one():
            raise SystemExit(f"{company_key} has no reviewed personas.")
        h = baseline_hash(conn, row)
        conn.execute(text(f"UPDATE {W}.scenario_catalog SET status='READY', content_hash=:h, updated_at=now(), revision=revision+1 WHERE scenario_id=:s"), {"h": h, "s": row["scenario_id"]})
    print(f"{company_key}: READY ({h[:19]}…)")


def deactivate(engine: Engine, company_key: str) -> None:
    with engine.begin() as conn:
        row = _catalog_row(conn, company_key)
        conn.execute(text(f"UPDATE {W}.scenario_catalog SET status='VALIDATED', updated_at=now(), revision=revision+1 WHERE scenario_id=:s"), {"s": row["scenario_id"]})
    print(f"{company_key}: VALIDATED (hidden from the catalog; existing runs end at their next request)")


def status(engine: Engine) -> None:
    with engine.connect() as conn:
        for r in conn.execute(text(f"SELECT company_key, pack_version, status, left(content_hash, 19) FROM {W}.scenario_catalog ORDER BY company_key")):
            print(" ".join(str(x) for x in r))


# ---------------------------------------------------------------- evaluator access and caps
TIERS, SCOPES = ("PUBLIC", "EVALUATOR"), ("RUN", "POOL")
KINDS = ("DEMO_RUN", "TUTOR_TURN", "VOICE_LISTEN", "VOICE_SPEECH", "ACCESS_ATTEMPT_FAILED")


def _expiry(day: str) -> datetime:
    """--expires YYYY-MM-DD: valid through the end of that day (UTC)."""
    try:
        d = datetime.strptime(day, "%Y-%m-%d").date()
    except ValueError:
        raise SystemExit("--expires must be a date like 2026-11-15.") from None
    at = datetime.combine(d, time(23, 59, 59), UTC)
    if at <= datetime.now(UTC):
        raise SystemExit("--expires must be in the future.")
    return at


def create_access_code(engine: Engine, label: str, expires: str, max_runs: int) -> str:
    with engine.begin() as conn:
        return access.create(conn, label, _expiry(expires), max_runs)


def list_access_codes(engine: Engine) -> None:
    with engine.connect() as conn:
        rows = access_repo.listing(conn)
    if not rows:
        print("No access codes.")
    for r in rows:
        state = "REVOKED" if r["revoked_at"] else ("EXPIRED" if r["expires_at"] <= datetime.now(UTC) else "ACTIVE")
        last = r["last_used_at"].strftime("%Y-%m-%d %H:%M UTC") if r["last_used_at"] else "never"
        print(f"{r['label']}  …{r['code_hint']}  {state}  expires {r['expires_at']:%Y-%m-%d}  last used {last}  workspaces today {r['runs_today']}/{r['max_runs_per_day']}")


def show_limits(engine: Engine) -> None:
    with engine.connect() as conn:
        for r in usage_repo.limit_rows(conn):
            print(f"{r['tier']:<9} {r['scope_type']:<4} {r['usage_kind']:<21} {r['daily_limit'] or 'off':>6}  (by {r['updated_by']}, {r['updated_at']:%Y-%m-%d %H:%M})")


def dispatch(loop: bool) -> None:
    """One delivery pass, or (--loop) the worker: delivers, then waits DISPATCHER_INTERVAL_SECONDS."""
    import time

    from app.services import notifications

    while True:
        n = notifications.dispatch_once(worker=f"cli-{getpass.getuser()}")
        if not loop:
            print(f"Delivered {n['delivered']}, will retry {n['retry']}, gave up on {n['dead']}.")
            return
        time.sleep(get_settings().dispatcher_interval_seconds)


def main(argv: list[str] | None = None, url: str | None = None) -> None:
    ap = argparse.ArgumentParser(prog="app.cli")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    s = sub.add_parser("sync-catalog")
    s.add_argument("pack_dir", type=Path, nargs="+")
    a = sub.add_parser("activate")
    a.add_argument("company_key", nargs="+")
    a.add_argument("--confirm-reviewed", action="store_true", help="Confirm a human reviewed this synthetic pack")
    d = sub.add_parser("deactivate")
    d.add_argument("company_key", nargs="+")
    c = sub.add_parser("create-access-code", help="Create an evaluator code (shown once)")
    c.add_argument("--label", required=True, help='Who it is for, e.g. "Judge - Panel A"')
    c.add_argument("--expires", required=True, help="Last valid day (UTC), YYYY-MM-DD")
    c.add_argument("--max-runs-per-day", type=int, default=50)
    sub.add_parser("list-access-codes")
    r = sub.add_parser("revoke-access-code")
    r.add_argument("label")
    sub.add_parser("show-limits")
    ru = sub.add_parser("reset-usage", help="Clear today's demo usage counters (caps reset by themselves at 00:00 UTC)")
    ru.add_argument("--kind", choices=KINDS, help="Only this kind (default: all)")
    ru.add_argument("--confirm", action="store_true", help="Required: this lifts today's spending protection")
    lim = sub.add_parser("set-limit", help="Daily cap; 0 turns it off")
    lim.add_argument("tier", choices=TIERS)
    lim.add_argument("scope", choices=SCOPES)
    lim.add_argument("kind", choices=KINDS)
    lim.add_argument("daily_limit", type=int)
    dp = sub.add_parser("dispatch", help="Deliver pending notifications to the Firestore inbox (ADR-048)")
    dp.add_argument("--loop", action="store_true", help="Keep delivering (the cloud worker); otherwise one pass")
    args = ap.parse_args(argv)
    if args.cmd == "dispatch":
        dispatch(args.loop)
        return
    engine = create_engine(url or get_settings().url())
    if args.cmd == "status":
        status(engine)
    elif args.cmd == "sync-catalog":
        for p in args.pack_dir:
            sync_catalog(engine, p)
    elif args.cmd == "create-access-code":
        if args.max_runs_per_day < 1:
            sys.exit("--max-runs-per-day must be at least 1.")
        code = create_access_code(engine, args.label, args.expires, args.max_runs_per_day)
        print(f"{args.label}: {code}")
        print("Shown once. Share it privately; only its hash is stored.")
    elif args.cmd == "list-access-codes":
        list_access_codes(engine)
    elif args.cmd == "revoke-access-code":
        with engine.begin() as conn:
            if not access_repo.revoke(conn, args.label):
                sys.exit(f"No active code labelled {args.label!r}.")
        print(f"{args.label}: revoked (effective on the next request).")
    elif args.cmd == "reset-usage":
        if not args.confirm:
            sys.exit("This clears today's usage for every visitor, so the daily caps start over (spending protection resets). Re-run with --confirm.")
        with engine.begin() as conn:
            n = usage_repo.reset_today(conn, args.kind)
        print(f"Cleared {n} of today's usage counters" + (f" for {args.kind}" if args.kind else "") + ". Caps also reset by themselves at 00:00 UTC.")
    elif args.cmd == "show-limits":
        show_limits(engine)
    elif args.cmd == "set-limit":
        if args.daily_limit < 0:
            sys.exit("daily_limit must be 0 (off) or more.")
        with engine.begin() as conn:
            usage_repo.set_limit(conn, args.tier, args.scope, args.kind, args.daily_limit, f"cli:{getpass.getuser()}")
        print(f"{args.tier} {args.scope} {args.kind} = {args.daily_limit or 'off'}")
    elif args.cmd == "activate":
        if not args.confirm_reviewed:
            sys.exit("Activation publishes the pack to the public demo catalog. Re-run with --confirm-reviewed.")
        for k in args.company_key:
            activate(engine, k)
    else:
        for k in args.company_key:
            deactivate(engine, k)


if __name__ == "__main__":
    main()
