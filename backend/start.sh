#!/usr/bin/env bash
# Cloud Run service entrypoint (ADR-052). One container, three processes:
#   graph host  127.0.0.1:8123  the AI engineer's four LangGraph graphs (graph_host/server.py)
#   calendar    127.0.0.1:8001  her Google Calendar sign-in service (only when the OAuth client is set)
#   API         0.0.0.0:$PORT   FastAPI, the only port Cloud Run routes to
# Each process gets only the settings it needs. If any of them stops, the container exits and Cloud Run
# starts a new one. The migration and cleanup jobs use the same image with their own command.
set -euo pipefail

AI_PY=/srv/graph_host/.venv/bin
API_PORT="${PORT:-8080}"
pids=()

stop() {
  for p in "${pids[@]}"; do kill -TERM "$p" 2>/dev/null || true; done
  wait || true
}
trap 'stop; exit 0' TERM INT

# Gemini for the graphs: their API key (default) or Vertex AI with the service account (AI_GEMINI=vertex).
if [ "${AI_GEMINI:-api_key}" = "vertex" ]; then
  gemini=(-u GEMINI_API_KEY -u GEMINI_EVALUATOR_API_KEY)
else
  gemini=(-u GOOGLE_GENAI_USE_VERTEXAI -u GEMINI_EVALUATOR_API_KEY)
fi

# The graphs read PORT as their database port (her .env convention) when they are imported; the host then
# re-points their engines at DATABASE_URL. Cloud Run's PORT (8080) is replaced so the address still parses.
(cd /srv/graph_host && exec env -u GOOGLE_CLIENT_ID -u GOOGLE_CLIENT_SECRET "${gemini[@]}" PORT=5432 \
  "$AI_PY/uvicorn" --factory server:production_app --host 127.0.0.1 --port 8123 --no-server-header --log-level warning) &
pids+=($!)

if [ -n "${GOOGLE_CLIENT_ID:-}" ] && [ -n "${GOOGLE_CLIENT_SECRET:-}" ] && [ "${COMPANION_CALENDAR:-true}" = "true" ]; then
  (cd /srv/ai/ai_work_companion && exec env -u PORT -u DATABASE_URL -u GEMINI_API_KEY -u GEMINI_EVALUATOR_API_KEY \
    "$AI_PY/uvicorn" google_calendar_auth:app --host 127.0.0.1 --port 8001 --no-server-header --log-level warning) &
  pids+=($!)
fi

# Start the API once the graphs have loaded, so the startup probe passes only when the AI is ready.
"$AI_PY/python" - <<'PY'
import time, urllib.request
for _ in range(120):
    try:
        urllib.request.urlopen("http://127.0.0.1:8123/ok", timeout=2)
        break
    except Exception:
        time.sleep(1)
PY

(cd /srv/backend && exec env -u GOOGLE_CLIENT_ID -u GOOGLE_CLIENT_SECRET \
  uvicorn app.main:app --host 0.0.0.0 --port "$API_PORT" --proxy-headers --forwarded-allow-ips='*' --no-server-header) &
pids+=($!)

# Any process stopping ends the container.
set +e
wait -n
code=$?
stop
exit "$code"
