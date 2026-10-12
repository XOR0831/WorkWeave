#!/usr/bin/env bash
# Build the static site in API mode and deploy it to the Firebase Hosting site created by Terraform.
# Usage: PROJECT_ID=... SITE_ID=... ./deploy_frontend.sh
set -euo pipefail
: "${PROJECT_ID:?set PROJECT_ID}"
: "${SITE_ID:?set SITE_ID}"
FRONTEND="$(cd "$(dirname "$0")/../../frontend" && pwd)"
cd "${FRONTEND}"
npm ci
npm run build:http
# firebase.json targets the default site; deploy to the Terraform-managed site instead.
python3 - "$SITE_ID" <<'PY'
import json, sys
cfg = json.load(open("firebase.json"))
cfg["hosting"]["site"] = sys.argv[1]
json.dump(cfg, open(".firebase.deploy.json", "w"), indent=2)
PY
trap 'rm -f .firebase.deploy.json' EXIT
npx --yes firebase-tools@14 deploy --only hosting --project "${PROJECT_ID}" --config .firebase.deploy.json
