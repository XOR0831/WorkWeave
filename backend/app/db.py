"""Engine and transaction helpers. Business SQL lives in repositories."""

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import Connection, Engine, create_engine

from app.config import get_settings


@lru_cache
def get_engine() -> Engine:
    s = get_settings()
    return create_engine(s.url(), pool_pre_ping=True, pool_size=s.db_pool_size, max_overflow=s.db_max_overflow)


@contextmanager
def transaction(engine: Engine | None = None) -> Iterator[Connection]:
    """One atomic unit: state change, audit and session rows commit or roll back together."""
    with (engine or get_engine()).begin() as conn:
        yield conn
