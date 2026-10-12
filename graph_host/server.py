"""Serves the AI engineer's four LangGraph graphs inside the API container (ADR-052).

Locally each graph runs in its own `langgraph dev`. In the cloud this process loads the same graph
files from ../ai unchanged, compiles them with a PostgreSQL checkpointer (private `langgraph` schema)
and answers the part of the LangGraph API the backend adapters use, on 127.0.0.1 only:

    POST /threads                       {"thread_id", "if_exists": "do_nothing"}
    GET  /threads/{id}                  {"thread_id", "status": "busy" | "idle"}
    GET  /threads/{id}/state            {"values", "next", "tasks": [{"interrupts": [...]}]}
    POST /threads/{id}/state            {"values", "as_node"}
    POST /threads/{id}/runs/wait        {"assistant_id", "input" | "command", "config", "interrupt_before"}
    POST /threads/{id}/runs/stream      same, plus "stream_mode": ["updates"], "stream_subgraphs"; SSE
    DELETE /threads/{id}

A thread runs one request at a time; a second one gets 409 (multitask "reject"). Threads not used
for GRAPH_THREAD_TTL_HOURS are deleted, so demo conversations don't outlive the demo data.

No AI logic lives here: no prompts, no model calls, no routing. The graphs' own database engines are
pointed at DATABASE_URL (Cloud SQL socket) instead of the localhost address built from their .env.
"""

from __future__ import annotations

import dataclasses
import importlib.util
import logging
import os
import sys
import threading
import uuid
from collections.abc import Callable, Iterator
from contextlib import asynccontextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Any

import orjson
from fastapi import Body, FastAPI, HTTPException, Response
from fastapi.responses import StreamingResponse
from langgraph.types import Command

_log = logging.getLogger("graph_host")

AI_DIR = Path(os.environ.get("GRAPH_HOST_AI_DIR", Path(__file__).resolve().parent.parent / "ai"))
GRAPHS = {  # assistant ID (the backend's *_ASSISTANT settings) -> graph file
    "ai_adaptive_onboarding": "ai_adaptive_onboarding/ai_adaptive_onboarding.py",
    "ai_work_companion": "ai_work_companion/ai_work_companion.py",
    "ai_shift_handover": "ai_shift_handover/ai_shift_handover.py",
    "ai_exit_knowledge_transfer": "ai_exit_knowledge_transfer/ai_exit_knowledge_transfer.py",
}
SCHEMA = "langgraph"


# ---------------------------------------------------------------- JSON
def _default(o: Any) -> Any:
    if hasattr(o, "model_dump"):
        return o.model_dump(mode="json")
    if dataclasses.is_dataclass(o) and not isinstance(o, type):
        return {f.name: getattr(o, f.name) for f in dataclasses.fields(o)}
    if isinstance(o, (set, frozenset, tuple)):
        return list(o)
    if isinstance(o, (datetime, date)):
        return o.isoformat()
    if isinstance(o, uuid.UUID):
        return str(o)
    if isinstance(o, bytes):
        return None
    return str(o)


def dumps(o: Any) -> bytes:
    return orjson.dumps(o, default=_default, option=orjson.OPT_NON_STR_KEYS)


# ---------------------------------------------------------------- graphs
class Host:
    """The compiled graphs, the checkpointer and the per-thread run locks."""

    def __init__(self, graphs: dict[str, Any], checkpointer: Any, touch: Callable[[str, str], None] | None = None):
        self.graphs = {name: g.builder.compile(checkpointer=checkpointer) for name, g in graphs.items()}
        self.checkpointer = checkpointer
        self._touch = touch
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()

    def graph(self, assistant: str) -> Any:
        g = self.graphs.get(assistant)
        if g is None:
            raise HTTPException(503, "This assistant isn't available.")
        return g

    @staticmethod
    def key(assistant: str, thread_id: str) -> str:
        # Thread IDs come from different modules; keep each graph's checkpoints apart.
        return f"{assistant}:{thread_id}"

    def lock(self, thread_id: str) -> threading.Lock:
        with self._guard:
            return self._locks.setdefault(thread_id, threading.Lock())

    def busy(self, thread_id: str) -> bool:
        return self.lock(thread_id).locked()

    def config(self, assistant: str, thread_id: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        cfg = dict((body or {}).get("config") or {})
        configurable = {**(cfg.get("configurable") or {}), "thread_id": self.key(assistant, thread_id)}
        out: dict[str, Any] = {"configurable": configurable}
        if isinstance(cfg.get("recursion_limit"), int):
            out["recursion_limit"] = cfg["recursion_limit"]
        return out

    def assistant_for(self, thread_id: str) -> str | None:
        """The graph that has this thread (state reads don't name the assistant)."""
        for name, g in self.graphs.items():
            if g.get_state({"configurable": {"thread_id": self.key(name, thread_id)}}).values:
                return name
        return None

    def state(self, thread_id: str) -> dict[str, Any]:
        name = self.assistant_for(thread_id)
        if name is None:
            return {"values": {}, "next": [], "tasks": []}
        st = self.graphs[name].get_state({"configurable": {"thread_id": self.key(name, thread_id)}})
        tasks = [{"id": t.id, "name": t.name, "interrupts": [{"value": i.value, "id": getattr(i, "id", None)} for i in t.interrupts]} for t in st.tasks]
        return {"values": st.values, "next": list(st.next), "tasks": tasks}

    def update_state(self, thread_id: str, values: dict[str, Any], as_node: str | None) -> dict[str, Any]:
        name = self.assistant_for(thread_id)
        if name is None:
            raise HTTPException(404, "Thread not found.")
        cfg = self.graphs[name].update_state({"configurable": {"thread_id": self.key(name, thread_id)}}, values, as_node=as_node)
        return {"configurable": cfg.get("configurable", {})}

    def run(self, thread_id: str, body: dict[str, Any]) -> Iterator[tuple[tuple[str, ...], dict[str, Any]]]:
        """Runs the graph; yields (namespace, update) per finished step. Caller holds the lock."""
        assistant = str(body.get("assistant_id") or "")
        g = self.graph(assistant)
        cmd = body.get("command")
        arg: Any = Command(resume=cmd.get("resume")) if isinstance(cmd, dict) and "resume" in cmd else body.get("input")
        if self._touch:
            self._touch(self.key(assistant, thread_id), assistant)
        kwargs: dict[str, Any] = {"stream_mode": ["updates"], "subgraphs": True}
        if body.get("interrupt_before"):
            kwargs["interrupt_before"] = body["interrupt_before"]
        for ns, _mode, update in g.stream(arg, self.config(assistant, thread_id, body), **kwargs):
            yield tuple(ns), update if isinstance(update, dict) else {}

    def delete(self, thread_id: str) -> None:
        for name in self.graphs:
            self.checkpointer.delete_thread(self.key(name, thread_id))


# ---------------------------------------------------------------- PostgreSQL
def _plain(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


def postgres(url: str):  # pragma: no cover - exercised by the container smoke test
    """Checkpointer in the private `langgraph` schema, plus the thread registry used for expiry."""
    import psycopg
    from langgraph.checkpoint.postgres import PostgresSaver
    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool

    with psycopg.connect(_plain(url), autocommit=True) as c:
        c.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
        c.execute(f"""CREATE TABLE IF NOT EXISTS {SCHEMA}.graph_threads (
                        thread_key text PRIMARY KEY, assistant text NOT NULL, last_used_at timestamptz NOT NULL DEFAULT now())""")
    pool = ConnectionPool(_plain(url), min_size=1, max_size=int(os.environ.get("GRAPH_HOST_POOL", "3")), open=True,
                          kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row, "options": f"-c search_path={SCHEMA}"})
    saver = PostgresSaver(pool)
    saver.setup()

    def touch(key: str, assistant: str) -> None:
        with pool.connection() as c:
            c.execute("""INSERT INTO graph_threads (thread_key, assistant) VALUES (%s, %s)
                         ON CONFLICT (thread_key) DO UPDATE SET last_used_at = now()""", (key, assistant))

    def expire(hours: float) -> int:
        with pool.connection() as c:
            keys = [r["thread_key"] for r in c.execute("SELECT thread_key FROM graph_threads WHERE last_used_at < now() - make_interval(secs => %s)", (hours * 3600,))]
        for k in keys:
            saver.delete_thread(k)
            with pool.connection() as c:
                c.execute("DELETE FROM graph_threads WHERE thread_key = %s", (k,))
        return len(keys)

    return saver, touch, expire, pool


def load_graphs(database_url: str | None) -> dict[str, Any]:
    """Imports each graph file; points its database engine at database_url. A graph that fails to
    load is left out (its assistant answers 503) so the others keep working."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    out: dict[str, Any] = {}
    for name, rel in GRAPHS.items():
        path = AI_DIR / rel
        try:
            sys.path.insert(0, str(path.parent))
            spec = importlib.util.spec_from_file_location(name, path)
            assert spec and spec.loader
            mod = importlib.util.module_from_spec(spec)
            sys.modules[name] = mod
            spec.loader.exec_module(mod)
            if database_url and hasattr(mod, "engine"):
                mod.engine = create_engine(database_url, pool_pre_ping=True, pool_size=1, max_overflow=2)
                for attr in ("SessionLocal", "session_local"):
                    if hasattr(mod, attr):
                        setattr(mod, attr, sessionmaker(bind=mod.engine, autoflush=False, autocommit=False))
            out[name] = mod.graph
            _log.info("loaded graph %s", name)
        except Exception:  # noqa: BLE001 - one broken graph must not stop the others
            _log.exception("couldn't load graph %s", name)
    return out


# ---------------------------------------------------------------- HTTP
def create_app(host_factory: Callable[[], tuple[Host, Callable[[], None] | None]]) -> FastAPI:
    state: dict[str, Any] = {}

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        host, stop = host_factory()
        state["host"] = host
        yield
        if stop:
            stop()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    def h() -> Host:
        return state["host"]

    @app.get("/ok")
    def ok() -> dict[str, Any]:
        return {"ok": True, "graphs": sorted(h().graphs)}

    @app.post("/threads")
    def create_thread(body: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
        return {"thread_id": body.get("thread_id") or str(uuid.uuid4())}

    @app.get("/threads/{thread_id}")
    def get_thread(thread_id: str) -> dict[str, Any]:
        return {"thread_id": thread_id, "status": "busy" if h().busy(thread_id) else "idle"}

    @app.delete("/threads/{thread_id}", status_code=204)
    def delete_thread(thread_id: str) -> Response:
        h().delete(thread_id)
        return Response(status_code=204)

    @app.get("/threads/{thread_id}/state")
    def get_state(thread_id: str) -> Response:
        return Response(dumps(h().state(thread_id)), media_type="application/json")

    @app.post("/threads/{thread_id}/state")
    def post_state(thread_id: str, body: dict[str, Any] = Body(...)) -> Response:
        lock = h().lock(thread_id)
        if not lock.acquire(blocking=False):
            raise HTTPException(409, "Thread is busy.")
        try:
            return Response(dumps(h().update_state(thread_id, body.get("values") or {}, body.get("as_node"))), media_type="application/json")
        finally:
            lock.release()

    @app.post("/threads/{thread_id}/runs/wait")
    def run_wait(thread_id: str, body: dict[str, Any] = Body(...)) -> Response:
        host = h()
        assistant = str(body.get("assistant_id") or "")
        host.graph(assistant)
        lock = host.lock(thread_id)
        if not lock.acquire(blocking=False):
            raise HTTPException(409, "Thread is busy.")
        try:
            for _ in host.run(thread_id, body):
                pass
            values = host.graphs[assistant].get_state(host.config(assistant, thread_id)).values
        except HTTPException:
            raise
        except Exception as e:  # noqa: BLE001 - reported like the LangGraph API does; details stay in this log
            _log.exception("run failed on %s", assistant)
            values = {"__error__": {"error": type(e).__name__}}
        finally:
            lock.release()
        return Response(dumps(values), media_type="application/json")

    @app.post("/threads/{thread_id}/runs/stream")
    def run_stream(thread_id: str, body: dict[str, Any] = Body(...)) -> StreamingResponse:
        host = h()
        assistant = str(body.get("assistant_id") or "")
        host.graph(assistant)
        lock = host.lock(thread_id)
        if not lock.acquire(blocking=False):
            raise HTTPException(409, "Thread is busy.")

        def events() -> Iterator[bytes]:
            try:
                yield b"event: metadata\ndata: " + dumps({"run_id": str(uuid.uuid4())}) + b"\n\n"
                for ns, update in host.run(thread_id, body):
                    name = "updates" if not ns else "updates|" + "|".join(ns)
                    yield f"event: {name}\ndata: ".encode() + dumps(update) + b"\n\n"
            except Exception as e:  # noqa: BLE001 - details stay in this log
                _log.exception("run failed on %s", assistant)
                yield b"event: error\ndata: " + dumps({"error": type(e).__name__}) + b"\n\n"
            finally:
                lock.release()
            yield b"event: end\ndata: null\n\n"

        return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-store"})

    return app


def _production() -> tuple[Host, Callable[[], None] | None]:  # pragma: no cover - container only
    url = os.environ.get("WORKWEAVE_DATABASE_URL") or os.environ["DATABASE_URL"]
    saver, touch, expire, pool = postgres(url)
    host = Host(load_graphs(url), saver, touch)
    ttl = float(os.environ.get("GRAPH_THREAD_TTL_HOURS", "24"))
    stop = threading.Event()

    def sweep() -> None:
        while not stop.wait(3600):
            try:
                n = expire(ttl)
                if n:
                    _log.info("deleted %d expired graph threads", n)
            except Exception:  # noqa: BLE001
                _log.exception("thread expiry failed")

    threading.Thread(target=sweep, name="graph-thread-expiry", daemon=True).start()

    def close() -> None:
        stop.set()
        pool.close()

    return host, close


def production_app() -> FastAPI:  # pragma: no cover - `uvicorn --factory server:production_app`
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    return create_app(_production)
