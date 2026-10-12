# WorkWeave API image (Cloud Run service + jobs). Build from the repository root:
#   docker build -f backend/Dockerfile -t workweave-api .
# The service runs backend/start.sh: the API, the graph host with the AI engineer's graphs and her
# calendar sign-in service (ADR-052). Jobs run their own command with the same image:
#   python -m app.ops.migrate [--activate-reviewed-packs]   and   python -m app.workers.cleanup --confirm
FROM python:3.13-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.8.22 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /srv/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY backend/app ./app
COPY backend/migrations ./migrations
COPY backend/alembic.ini ./
# The AI process's own environment, from the hashed lock (graph_host/requirements.in).
COPY graph_host/requirements.lock /tmp/graph_host.lock
RUN uv venv /srv/graph_host/.venv && \
    uv pip install --python /srv/graph_host/.venv/bin/python --require-hashes --no-deps -r /tmp/graph_host.lock

FROM python:3.13-slim
RUN useradd --system --uid 10001 --no-create-home workweave
WORKDIR /srv/backend
COPY --from=build /srv/backend /srv/backend
COPY --from=build /srv/graph_host/.venv /srv/graph_host/.venv
# Reviewed baseline SQL and synthetic scenario packs, for the migration job only.
COPY local/postgres/*.sql /srv/local/postgres/
COPY seed/packs /srv/seed/packs
# The AI engineer's graphs, calendar service and ingestion package, unchanged; only what runs.
COPY ai/ai_adaptive_onboarding/ai_adaptive_onboarding.py /srv/ai/ai_adaptive_onboarding/
COPY ai/ai_work_companion/ai_work_companion.py ai/ai_work_companion/google_calendar_auth.py /srv/ai/ai_work_companion/
COPY ai/ai_shift_handover/ai_shift_handover.py /srv/ai/ai_shift_handover/
COPY ai/ai_exit_knowledge_transfer/ai_exit_knowledge_transfer.py /srv/ai/ai_exit_knowledge_transfer/
COPY ai/vector_embedding/database.py ai/vector_embedding/ingestion.py /srv/ai/vector_embedding/
COPY graph_host/server.py /srv/graph_host/
COPY --chmod=0755 backend/start.sh /srv/start.sh
ENV PATH=/srv/backend/.venv/bin:$PATH PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    WORKWEAVE_SRC=/srv WORKWEAVE_ENV=release COOKIE_SECURE=true \
    GRAPH_HOST_AI_DIR=/srv/ai \
    INGESTION_PYTHON=/srv/graph_host/.venv/bin/python INGESTION_DIR=/srv/ai/vector_embedding INGESTION_PASS_GEMINI_ENV=true
USER workweave
EXPOSE 8080
CMD ["/srv/start.sh"]
