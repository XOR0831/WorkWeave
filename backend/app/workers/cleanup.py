"""Purge expired demo visitor runs (bounded worker job; never an HTTP endpoint).

    uv run python -m app.workers.cleanup                 # dry run: list what would be purged
    uv run python -m app.workers.cleanup --confirm       # purge, one run per transaction
    uv run python -m app.workers.cleanup --grace-minutes 120 --limit 20

Locally this is a privileged command. In the cloud it runs as a Cloud Run Job built from the API
image and invoked by Cloud Scheduler, under its own least-privilege cleanup identity
(blueprint/15; build_spec "reuse image with different entry commands").

A run is eligible only with positive evidence that it is a visitor run: a DEMO workspace in a
visitor organization (company_key NULL), not a pack original, with a demo_visitor_runs proof row
(migration 0004; before 0004, a demo_visitor_sessions row is the evidence) and at least one
session. None of its sessions may be ACTIVE and unexpired, and no session may have changed for
--grace-minutes. Every other non-pack DEMO workspace is never purged automatically: it is reported
separately for review, including runs with proof but no remaining session (age alone never
qualifies a run). With 0004, PostgreSQL itself rejects any purge deletion without valid proof.

Each purge locks the workspace, then every one of its sessions, and only then re-checks
eligibility, so a session reactivated concurrently is seen and the run is skipped. (Locking the
workspace also blocks new sessions, whose foreign key needs a share lock on it.) It then sets the
transaction-local retention flags from migration 0003, deletes every scoped row, logs a
content-free record in demo_workspace_purges and commits; any failure rolls that run back.
"""

import argparse
import json
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Connection, Engine, create_engine, text

from app.config import get_settings
from app.repositories import usage
from app.repositories.demo import visitor_run_proof_enabled

W = "workweave"

ELIGIBLE = """
SELECT w.organization_id, w.workspace_id,
       (SELECT s.scenario_id FROM {W}.demo_visitor_sessions s WHERE s.workspace_id = w.workspace_id LIMIT 1) AS scenario_id,
       CASE WHEN EXISTS (SELECT 1 FROM {W}.demo_visitor_sessions s WHERE s.workspace_id = w.workspace_id AND s.status = 'REVOKED')
                 AND NOT EXISTS (SELECT 1 FROM {W}.demo_visitor_sessions s WHERE s.workspace_id = w.workspace_id AND s.status <> 'REVOKED')
            THEN 'REVOKED'
            ELSE 'EXPIRED' END AS reason
FROM {W}.workspaces w
JOIN {W}.organizations o ON o.organization_id = w.organization_id AND o.company_key IS NULL
WHERE w.kind = 'DEMO'
  AND (CAST(:only AS uuid) IS NULL OR w.workspace_id = CAST(:only AS uuid))
  AND NOT EXISTS (SELECT 1 FROM {W}.scenario_catalog c WHERE c.organization_id = w.organization_id AND c.workspace_id = w.workspace_id)
  {proof}
  -- Activity evidence: at least one visitor session exists.
  AND EXISTS (SELECT 1 FROM {W}.demo_visitor_sessions s WHERE s.organization_id = w.organization_id AND s.workspace_id = w.workspace_id)
  AND NOT EXISTS (SELECT 1 FROM {W}.demo_visitor_sessions s
                  WHERE s.workspace_id = w.workspace_id AND s.status = 'ACTIVE' AND s.expires_at > now())
  -- Last activity: a session's last change, or its expiry if it ran out while ACTIVE.
  -- (workspaces.updated_at is trigger-maintained, not visitor activity.)
  AND (SELECT max(CASE WHEN s.status = 'ACTIVE' THEN GREATEST(s.updated_at, s.expires_at) ELSE s.updated_at END)
       FROM {W}.demo_visitor_sessions s WHERE s.workspace_id = w.workspace_id)
      < now() - make_interval(mins => :grace)
ORDER BY w.created_at
LIMIT :limit
"""
# Positive proof of a visitor run (migration 0004).
PROOF = "AND EXISTS (SELECT 1 FROM {W}.demo_visitor_runs r WHERE r.organization_id = w.organization_id AND r.workspace_id = w.workspace_id)"

# Every non-pack DEMO workspace with its evidence, to find the ones that need a human decision.
DEMO_WORKSPACES = """
SELECT w.organization_id, w.workspace_id, o.company_key IS NULL AS visitor_org,
       EXISTS (SELECT 1 FROM {W}.demo_visitor_sessions s WHERE s.organization_id = w.organization_id AND s.workspace_id = w.workspace_id) AS has_sessions,
       {has_proof} AS has_proof
FROM {W}.workspaces w
JOIN {W}.organizations o ON o.organization_id = w.organization_id
WHERE w.kind = 'DEMO'
  AND NOT EXISTS (SELECT 1 FROM {W}.scenario_catalog c WHERE c.organization_id = w.organization_id AND c.workspace_id = w.workspace_id)
ORDER BY w.created_at
"""


@dataclass
class Candidate:
    organization_id: uuid.UUID
    workspace_id: uuid.UUID
    scenario_id: uuid.UUID | None
    reason: str


def scoped_tables(conn: Connection) -> list[str]:
    """Every business table carrying a workspace_id, except the workspace row itself."""
    rows = conn.execute(
        text(
            """SELECT c.table_name FROM information_schema.columns c
               JOIN information_schema.tables t ON t.table_schema = c.table_schema AND t.table_name = c.table_name
               WHERE c.table_schema = 'workweave' AND c.column_name = 'workspace_id' AND t.table_type = 'BASE TABLE'
                 AND c.table_name NOT IN ('workspaces', 'demo_workspace_purges')
               ORDER BY c.table_name"""
        )
    )
    return [r[0] for r in rows]


def delete_order(conn: Connection, tables: Sequence[str]) -> list[str]:
    """The scoped tables with each child before any parent it references through a foreign key
    that can't be deferred, so the purge never depends on every key being deferrable (a table
    added later with an ordinary key once made every purge fail). Ties keep name order."""
    scoped = set(tables)
    edges = conn.execute(
        text(
            """SELECT DISTINCT ch.relname AS child, pa.relname AS parent
               FROM pg_constraint k
               JOIN pg_class ch ON ch.oid = k.conrelid
               JOIN pg_class pa ON pa.oid = k.confrelid
               WHERE k.contype = 'f' AND NOT k.condeferrable AND k.conrelid <> k.confrelid
                 AND k.connamespace = 'workweave'::regnamespace"""
        )
    )
    parents_of: dict[str, set[str]] = {t: set() for t in scoped}
    for child, parent in edges:
        if child in scoped and parent in scoped:
            parents_of[child].add(parent)
    # A table may go once every table that references it has gone.
    children_left = {t: sum(t in ps for ps in parents_of.values()) for t in scoped}
    order: list[str] = []
    ready = sorted(t for t, n in children_left.items() if n == 0)
    while ready:
        t = ready.pop(0)
        order.append(t)
        for parent in parents_of[t]:
            children_left[parent] -= 1
            if children_left[parent] == 0:
                ready.append(parent)
        ready.sort()
    # A cycle of immediate keys can't be ordered; leave those last and let the purge report it.
    return order + sorted(scoped - set(order))


def usage_table_exists(engine: Engine) -> bool:
    """Migration 0005 may not be applied yet on an older database."""
    with engine.connect() as conn:
        return conn.execute(text(f"SELECT to_regclass('{W}.demo_usage') IS NOT NULL")).scalar_one()


def proof_enabled(conn: Connection) -> bool:
    return visitor_run_proof_enabled(conn)


def candidates(conn: Connection, grace_minutes: int, limit: int, only: uuid.UUID | None = None) -> list[Candidate]:
    sql = ELIGIBLE.format(W=W, proof=PROOF.format(W=W) if proof_enabled(conn) else "")
    rows = conn.execute(text(sql), {"grace": grace_minutes, "limit": limit, "only": str(only) if only else None})
    return [Candidate(**dict(r._mapping)) for r in rows]


def needs_review(conn: Connection) -> list[dict[str, Any]]:
    """Non-pack DEMO workspaces without full evidence of a visitor run. Never purged automatically."""
    proof = proof_enabled(conn)
    has_proof = (
        f"EXISTS (SELECT 1 FROM {W}.demo_visitor_runs r WHERE r.organization_id = w.organization_id AND r.workspace_id = w.workspace_id)" if proof else "false"
    )
    out = []
    for r in conn.execute(text(DEMO_WORKSPACES.format(W=W, has_proof=has_proof))):
        if not r.visitor_org:
            reason = "NOT_VISITOR_ORG"
        elif proof and r.has_proof and not r.has_sessions:
            reason = "PROOF_WITHOUT_SESSION"
        elif proof and r.has_sessions and not r.has_proof:
            reason = "SESSIONS_WITHOUT_PROOF"
        elif not r.has_sessions:
            reason = "NO_PROOF_NO_SESSION" if proof else "NO_SESSION"
        else:
            continue  # a provable visitor run: a candidate now or once it goes quiet
        out.append({"organization_id": r.organization_id, "workspace_id": r.workspace_id, "reason": reason})
    return out


def counts(conn: Connection, tables: Sequence[str], ws: uuid.UUID) -> dict[str, int]:
    out = {}
    for t in tables:
        n = conn.execute(text(f"SELECT count(*) FROM {W}.{t} WHERE workspace_id = :w"), {"w": ws}).scalar_one()
        if n:
            out[t] = n
    return out


def purge_one(engine: Engine, cand: Candidate, grace_minutes: int) -> dict[str, int] | None:
    """Purge one run atomically. Returns row counts, or None if it was no longer eligible."""
    with engine.begin() as conn:
        # 1. Lock the workspace (this also blocks new sessions: their FK needs a share lock on it).
        locked = conn.execute(
            text(f"SELECT 1 FROM {W}.workspaces WHERE organization_id=:o AND workspace_id=:w AND kind='DEMO' FOR UPDATE"),
            {"o": cand.organization_id, "w": cand.workspace_id},
        ).first()
        if not locked:
            return None
        proof = proof_enabled(conn)
        if proof:
            conn.execute(text(f"SELECT 1 FROM {W}.demo_visitor_runs WHERE organization_id=:o AND workspace_id=:w FOR UPDATE"), {"o": cand.organization_id, "w": cand.workspace_id})
        # 2. Lock every session of the run, waiting for any in-flight change (e.g. a resume).
        conn.execute(
            text(f"SELECT 1 FROM {W}.demo_visitor_sessions WHERE organization_id=:o AND workspace_id=:w ORDER BY demo_visitor_session_id FOR UPDATE"),
            {"o": cand.organization_id, "w": cand.workspace_id},
        )
        # 3. Only now re-check: under READ COMMITTED this new statement sees every committed change,
        #    and the locks keep it true until commit.
        if not candidates(conn, grace_minutes, 1, cand.workspace_id):
            return None
        tables = scoped_tables(conn)
        before = counts(conn, tables, cand.workspace_id)
        conn.execute(text("SET CONSTRAINTS ALL DEFERRED"))
        conn.execute(text("SELECT set_config('workweave.retention_purge', 'demo-visitor', true)"))
        conn.execute(text("SELECT set_config('workweave.retention_purge_workspace', :w, true)"), {"w": str(cand.workspace_id)})
        scope = {"o": cand.organization_id, "w": cand.workspace_id}
        # Sessions first (their FKs to employees aren't deferrable), then every scoped table (children before parents), then the
        # workspace, then its proof row: with 0004, PostgreSQL checks the proof on each of these deletes.
        conn.execute(text(f"DELETE FROM {W}.demo_visitor_sessions WHERE organization_id=:o AND workspace_id=:w"), scope)
        conn.execute(text(f"UPDATE {W}.knowledge_documents SET current_version_id = NULL WHERE organization_id=:o AND workspace_id=:w AND current_version_id IS NOT NULL"), scope)
        for t in delete_order(conn, tables):
            if t not in ("demo_visitor_sessions", "demo_visitor_runs"):
                conn.execute(text(f"DELETE FROM {W}.{t} WHERE organization_id=:o AND workspace_id=:w"), scope)
        conn.execute(text(f"DELETE FROM {W}.workspaces WHERE organization_id=:o AND workspace_id=:w"), scope)
        if proof:
            conn.execute(text(f"DELETE FROM {W}.demo_visitor_runs WHERE organization_id=:o AND workspace_id=:w"), scope)
        # The visitor's own organization goes too, unless something else still uses it.
        conn.execute(
            text(
                f"""DELETE FROM {W}.organizations o WHERE o.organization_id = :o AND o.company_key IS NULL
                    AND NOT EXISTS (SELECT 1 FROM {W}.workspaces x WHERE x.organization_id = o.organization_id)"""
            ),
            {"o": cand.organization_id},
        )
        conn.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))  # surface any FK problem before commit
        conn.execute(
            text(f"INSERT INTO {W}.demo_workspace_purges (organization_id, workspace_id, scenario_id, reason, row_counts) VALUES (:o, :w, :s, :r, CAST(:c AS jsonb))"),
            {"o": cand.organization_id, "w": cand.workspace_id, "s": cand.scenario_id, "r": cand.reason, "c": json.dumps(before)},
        )
        return before


def run(engine: Engine, confirm: bool, grace_minutes: int, limit: int) -> list[dict[str, Any]]:
    with engine.connect() as conn:
        found = candidates(conn, grace_minutes, limit)
        tables = scoped_tables(conn)
        plan = [{"workspace_id": str(c.workspace_id), "reason": c.reason, "rows": counts(conn, tables, c.workspace_id)} for c in found]
        review = [
            {"workspace_id": str(r["workspace_id"]), "reason": r["reason"], "rows": counts(conn, tables, r["workspace_id"]), "action": "needs review"}
            for r in needs_review(conn)
        ]
    if not confirm:
        return [{**p, "action": "would purge"} for p in plan] + review
    results = []
    for c, p in zip(found, plan, strict=True):
        purged = purge_one(engine, c, grace_minutes)
        results.append({**p, "action": "purged" if purged is not None else "skipped (no longer eligible)"})
    return results + review


def main(argv: list[str] | None = None, url: str | None = None) -> list[dict[str, Any]]:
    ap = argparse.ArgumentParser(prog="app.workers.cleanup")
    ap.add_argument("--confirm", action="store_true", help="Actually purge (default is a dry run)")
    ap.add_argument("--grace-minutes", type=int, default=60, help="Minimum quiet time before a run can be purged")
    ap.add_argument("--limit", type=int, default=50, help="Maximum runs per invocation (bounded job)")
    ap.add_argument("--keep-usage-days", type=int, default=7, help="Demo usage counters older than this are removed")
    args = ap.parse_args(argv)
    if args.grace_minutes < 0 or args.limit < 1 or args.keep_usage_days < 1:
        ap.error("--grace-minutes must be >= 0, --limit >= 1 and --keep-usage-days >= 1")
    engine = create_engine(url or get_settings().url())
    results = run(engine, args.confirm, args.grace_minutes, args.limit)
    for r in results:
        print(f"{r['action']:>28}  {r['workspace_id']}  {r['reason']:<19}  {sum(r['rows'].values())} rows")
    acted = [r for r in results if r["action"] in ("purged", "would purge")]
    review = [r for r in results if r["action"] == "needs review"]
    total = sum(sum(r["rows"].values()) for r in acted)
    print(f"{'purged' if args.confirm else 'dry run'}: {len(acted)} run(s), {total} rows" + ("" if args.confirm else "  (re-run with --confirm to purge)"))
    if review:
        print(f"needs review: {len(review)} DEMO workspace(s) without full visitor-run evidence; never purged automatically")
    # Housekeeping: daily demo-usage counters from past days no longer limit anything (they hold counts only).
    if usage_table_exists(engine):
        with engine.begin() as conn:
            if args.confirm:
                n = usage.prune_before(conn, args.keep_usage_days)
                print(f"usage counters: removed {n} older than {args.keep_usage_days} days")
            else:
                print(f"usage counters: {usage.count_before(conn, args.keep_usage_days)} older than {args.keep_usage_days} days would be removed")
    engine.dispose()
    return results


if __name__ == "__main__":
    main()
