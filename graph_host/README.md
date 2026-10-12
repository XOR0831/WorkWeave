# Graph host

Runs the four LangGraph graphs from [`../ai`](../ai) inside the API container (ADR-052). Locally each graph runs in its own `langgraph dev` (ports 5678–5681). In the cloud, `server.py` serves them all from one process on `127.0.0.1:8123`:

- It loads each graph file unchanged and compiles it with a **PostgreSQL checkpointer** in a private `langgraph` schema, so conversations survive restarts.
- It answers only the LangGraph API calls the backend adapters make: create a thread, read its status and state, update its state, and run (`runs/wait`, or `runs/stream` with step updates).
- A thread runs one request at a time. A second request gets `409`, matching `multitask_strategy: "reject"`.
- Each graph's checkpoints are kept apart by prefixing the thread ID with the graph name.
- Threads unused for `GRAPH_THREAD_TTL_HOURS` (default 24) are deleted.
- The graphs' own database engines are pointed at `DATABASE_URL` (the Cloud SQL socket), instead of the `localhost` address they build from their `.env`.
- A graph that fails to load answers `503`; the other graphs keep working.

There is no AI logic here: no prompts, no model calls and no routing.

`backend/start.sh` starts the graph host, then the AI engineer's calendar sign-in service (`127.0.0.1:8001`), then the API.

## Dependencies

`requirements.in` pins the versions from the AI engineer's tested environment. `requirements.lock` is fully resolved with hashes for the image (Linux, Python 3.13):

```sh
uv pip compile requirements.in -o requirements.lock --python-version 3.13 --python-platform x86_64-manylinux_2_28 --generate-hashes
```

## Tests

```sh
uv venv .venv --python 3.13 && uv pip install --python .venv/bin/python -r requirements.in pytest httpx
.venv/bin/python -m pytest -q tests
```

## Run it locally (optional)

Point it at a database you're allowed to write to; it creates the `langgraph` schema there:

```sh
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@127.0.0.1:5432/DB \
  .venv/bin/uvicorn --factory server:production_app --host 127.0.0.1 --port 8123
```

Then set `LANGGRAPH_URL`, `LANGGRAPH_COMPANION_URL`, `LANGGRAPH_HANDOVER_URL` and `LANGGRAPH_EXIT_KT_URL` to `http://127.0.0.1:8123`.
