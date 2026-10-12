"""Database migration job (Cloud Run Job `workweave-migrate`, or locally). Privileged; never an HTTP endpoint.

    python -m app.ops.migrate                       # baseline (fresh database only) + Alembic upgrade
    python -m app.ops.migrate --activate-reviewed-packs   # ... then sync and activate the reviewed packs

Fresh database (no `workweave` schema): apply the reviewed baseline scripts in order, then Alembic.
Existing database (Alembic version present): Alembic only; baseline scripts are never re-run.
Anything else (schema without an Alembic version) is an unknown state: refuse and change nothing.
Catalog activation publishes the synthetic packs to the public demo catalog, so it needs the explicit
flag (the equivalent of the catalog CLI's --confirm-reviewed). Seeding happens here, never in Terraform.
"""

import argparse
import json
import sys

import psycopg
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from app import cli
from app.config import get_settings
from app.ops.baseline import PACK_DIRS, PACKS_DIR, SCRIPTS, SQL_DIR

BACKEND = SQL_DIR.parent.parent / "backend"


def _plain(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


def state(url: str) -> str:
    """'fresh', 'managed' (Alembic present) or 'unknown'."""
    with psycopg.connect(_plain(url)) as c:
        schema = c.execute("SELECT to_regnamespace('workweave') IS NOT NULL").fetchone()[0]
        if not schema:
            return "fresh"
        alembic = c.execute("SELECT to_regclass('workweave.alembic_version') IS NOT NULL").fetchone()[0]
        return "managed" if alembic else "unknown"


def apply_baseline(url: str, log=print) -> None:
    with psycopg.connect(_plain(url), autocommit=True) as c:
        for name in SCRIPTS:
            log(f"baseline: {name}")
            c.execute((SQL_DIR / name).read_text())


def alembic_upgrade(url: str) -> None:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))
    cfg.attributes["url"] = url
    command.upgrade(cfg, "head")


def activate_packs(url: str, log=print) -> None:
    engine = create_engine(url)
    with engine.connect() as c:
        status = {r[0]: r[1] for r in c.execute(text("SELECT company_key, status FROM workweave.scenario_catalog"))}
    engine.dispose()
    for d in PACK_DIRS:
        company = json.loads((PACKS_DIR / d / "catalog.json").read_text())["company_key"]
        if status.get(company) not in ("VALIDATED", "READY"):
            cli.main(["sync-catalog", str(PACKS_DIR / d)], url=url)
        cli.main(["activate", company, "--confirm-reviewed"], url=url)
        log(f"catalog: {company} READY")


def run(url: str, activate: bool, log=print) -> str:
    s = state(url)
    if s == "unknown":
        raise SystemExit("The workweave schema exists but has no Alembic version: unknown state. Nothing was changed.")
    if s == "fresh":
        apply_baseline(url, log)
    alembic_upgrade(url)
    log("alembic: at head")
    if activate:
        activate_packs(url, log)
    return s


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="app.ops.migrate")
    ap.add_argument("--activate-reviewed-packs", action="store_true", help="Sync and activate the reviewed synthetic packs (publishes them to the demo catalog)")
    a = ap.parse_args(argv)
    started = run(get_settings().url(), a.activate_reviewed_packs)
    print(f"migrate: done (database was {started})")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
