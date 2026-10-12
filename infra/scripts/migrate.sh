#!/usr/bin/env bash
# Run the migration job and wait. First deploy: ./migrate.sh --activate-reviewed-packs
# (publishes the reviewed synthetic packs to the demo catalog). Usage: PROJECT_ID=... ./migrate.sh [flags]
set -euo pipefail
: "${PROJECT_ID:?set PROJECT_ID}"
REGION="${REGION:-asia-east1}"
ARGS="-m,app.ops.migrate"
for a in "$@"; do ARGS="${ARGS},${a}"; done
gcloud run jobs execute workweave-migrate --project "${PROJECT_ID}" --region "${REGION}" --args="${ARGS}" --wait
