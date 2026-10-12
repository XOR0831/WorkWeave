"""Build the disposable workweave_test database (also used by the frontend HTTP e2e run).

    uv run python -m tests.prepare_db

Drops and recreates ONLY disposable databases (workweave_test*, workweave_scratch*): applies the
immutable baseline SQL scripts in their documented order, runs Alembic (0001, 0002), then syncs
and activates the three reviewed packs. Never touches the local `workweave` dev database.
"""

from pathlib import Path

import psycopg
from alembic import command
from alembic.config import Config

from app import cli
from app.ops.baseline import SCRIPTS as BASELINE_SCRIPTS
from app.config import get_settings

ROOT = Path(__file__).resolve().parents[2]
SQL = ROOT / "local" / "postgres"
PACKS = ROOT / "seed" / "packs"
SCRIPTS = BASELINE_SCRIPTS  # single source: app/ops/baseline.py
TEST_DB = "workweave_test"


def _plain(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://")


def alembic_config(url: str) -> Config:
    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    cfg.attributes["url"] = url
    return cfg


def recreate(name: str) -> str:
    """Drop and recreate one disposable database; never the configured main database."""
    s = get_settings()
    if name == s.postgres_db or not (name.startswith("workweave_test") or name.startswith("workweave_scratch")):
        raise SystemExit(f"Refusing to recreate {name!r}: only workweave_test* / workweave_scratch* databases are disposable.")
    with psycopg.connect(_plain(s.url("postgres")), autocommit=True) as c:
        c.execute(f"DROP DATABASE IF EXISTS {name} WITH (FORCE)")
        c.execute(f"CREATE DATABASE {name}")
    return s.url(name)


def drop(name: str) -> None:
    if not name.startswith("workweave_scratch"):
        raise SystemExit(f"Refusing to drop {name!r}.")
    with psycopg.connect(_plain(get_settings().url("postgres")), autocommit=True) as c:
        c.execute(f"DROP DATABASE IF EXISTS {name} WITH (FORCE)")


def build(name: str = TEST_DB, revision: str = "head", catalog: bool = True) -> str:
    """Immutable baseline SQL (01_schema.sql ... 10_*.sql), then Alembic up to `revision`."""
    url = recreate(name)
    with psycopg.connect(_plain(url), autocommit=True) as c:
        for script in SCRIPTS:
            c.execute((SQL / script).read_text())
    command.upgrade(alembic_config(url), revision)
    if catalog:
        cli.main(["sync-catalog", *(str(PACKS / p) for p in ("northstar-manufacturing", "acme-infrastructure", "harbor-support"))], url=url)
        cli.main(["activate", "northstar", "acme", "harbor", "--confirm-reviewed"], url=url)
    return url


if __name__ == "__main__":
    build()
    print(f"{TEST_DB}: ready")
