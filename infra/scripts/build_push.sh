#!/usr/bin/env bash
# Build the API image (linux/amd64 for Cloud Run) and push it; prints the digest-pinned reference
# to put in terraform.tfvars as api_image. Usage: PROJECT_ID=... [REGION=asia-east1] ./build_push.sh
set -euo pipefail
: "${PROJECT_ID:?set PROJECT_ID}"
REGION="${REGION:-asia-east1}"
REPO="${REGION}-docker.pkg.dev/${PROJECT_ID}/workweave/api"
SRC="$(cd "$(dirname "$0")/../.." && pwd)"
TAG="$(date -u +%Y%m%d-%H%M%S)"

gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet
docker build --platform linux/amd64 -f "${SRC}/backend/Dockerfile" -t "${REPO}:${TAG}" "${SRC}"
docker push "${REPO}:${TAG}"
DIGEST="$(gcloud artifacts docker images describe "${REPO}:${TAG}" --format='value(image_summary.digest)')"
echo "api_image = \"${REPO}@${DIGEST}\""
