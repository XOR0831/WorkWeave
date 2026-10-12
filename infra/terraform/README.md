# WorkWeave infrastructure (Terraform)

Decisions: ADR-026 and ADR-052 and the local-development/Terraform plan (project design notes, kept outside this repository).
One cloud environment (`submission`) in `asia-east1`: Firebase Hosting -> `/api/**` -> Cloud Run API container
(API, graph host with the four LangGraph graphs, calendar sign-in service) -> Cloud SQL PostgreSQL 16 (business
data plus graph checkpoints in a private `langgraph` schema); Firestore for the notification inbox; Gemini
through the API key (graphs, browser voice tokens) and Vertex AI (server-side speech).

**Nothing here has been applied.** Every `apply`, image push and deploy needs the owner's explicit
approval. Terraform >= 1.11 is required (write-only arguments keep the DB password out of state).

```
bootstrap/                 project, billing link, core APIs, private versioned state bucket (local state)
modules/platform/          APIs, Artifact Registry, 4 service accounts, Firebase project/app/Hosting site
modules/data/              Cloud SQL, database/user (write-only password), Firestore inbox, database-url,
                           gemini-api-key and Google OAuth (calendar) secrets
modules/runtime/           Cloud Run API service (API + graph host + calendar service, ADR-052), migrate +
                           cleanup jobs, cleanup schedule, IAM
modules/operations/        email channel, uptime check + alert, $300 trial budget (usage before credits)
environments/submission/   wires the modules; remote state in the bootstrap bucket
../scripts/                build_push.sh, migrate.sh, deploy_frontend.sh
```

## Sequence (each step is an approval gate)

1. `cd bootstrap && cp terraform.tfvars.example terraform.tfvars && terraform init && terraform plan` -> review -> `apply`.
   If project creation needs an Organization, create the project in the console and `terraform import google_project.main <id>`.
2. `cd ../environments/submission && cp terraform.tfvars.example terraform.tfvars`
   `terraform init -backend-config="bucket=<project_id>-tfstate" && terraform plan` -> review -> `apply`
   (platform, data, budget; no runtime yet).
3. Add the Gemini key without putting it in state: `printf %s "$KEY" | gcloud secrets versions add gemini-api-key --data-file=-`.
   Deployed, the graphs call Gemini through Vertex AI with the service account (`ai_gemini = "vertex"`, the
   default); locally they use the API key. If a graph model isn't available on Vertex AI, set
   `ai_gemini = "api_key"` and apply: the graphs then use this key too.
   Companion calendar (optional): add versions to `google-oauth-client-id` and `google-oauth-client-secret` the
   same way, register `https://<site_id>.web.app/api/calendar/auth/google/callback` as a redirect URI on that
   OAuth client (keep the test account listed as a test user), then set `calendar_oauth_ready = true` and
   `calendar_account_email` in `terraform.tfvars`.
4. `PROJECT_ID=... ../../scripts/build_push.sh` -> set `api_image` (digest) -> `terraform apply` (runtime + uptime).
5. `PROJECT_ID=... ../../scripts/migrate.sh --activate-reviewed-packs` (first time; later without the flag).
6. `PROJECT_ID=... SITE_ID=... ../../scripts/deploy_frontend.sh`, then smoke-test `https://<site_id>.web.app`.
7. Evaluator access (ADR-029), against the Cloud SQL database through the Cloud SQL Auth Proxy with the app's credentials:
   `create-access-code --label "Judge - Panel A" --expires <date>`; tune limits with `set-limit`.
   Optional paid evaluator voice key: add a version to `gemini-api-key-evaluator` (billed to the card),
   then set `evaluator_voice_key_ready = true` and apply.
8. Calendar: after each deploy or restart, open the Companion, select **Connect Google Calendar** and sign in
   with the test account. The sign-in lives in the instance's memory; `max_instances = 1` keeps the callback on
   the same instance, and `min_instances = 1` during judging keeps it signed in.

Cost note: the API keeps CPU allocated between requests (`cpu_always_allocated`, for the notification dispatcher
and background work), so it is billed per instance-second while an instance is up (1 vCPU, 1 GiB). With
`min_instances = 0` it scales to zero when idle; `min_instances = 1` keeps one instance up all the time.

Never commit `*.tfstate`, plans or `terraform.tfvars` (see `.gitignore`). Commit `.terraform.lock.hcl` after the first `init`.
