# WorkWeave

**Weaving Knowledge Into Every Work.**

WorkWeave is a workforce continuity platform. People lose work context when they join a team, when a shift ends and when they move on. WorkWeave keeps that knowledge flowing through four connected modules that share one employee directory, one set of approved procedures and one record of work:

| Module | What it does |
| --- | --- |
| **Adaptive AI Onboarding** | A tutor that starts the conversation, teaches from the company's approved procedures, checks understanding in the chat, and records progress against a published learning path. Supports tap-to-talk, hands-free conversation and replies read aloud. |
| **AI Work Companion** | A chat on the right and a work area on the left. Ask about your tickets, report progress, get guidance grounded in approved procedures, or (as a shift lead) delegate work. The chat chooses which predefined view the work area shows. |
| **Intelligent Shift Handover** | A structured handover document for the shift lead, with a companion that checks for gaps and drafts updates from members' reports. The lead reviews and publishes; published snapshots never change. |
| **Exit Knowledge Transfer** | When someone leaves or changes role: targeted AI interviews capture what they know, the employee reviews the exact text, an authorized reviewer approves it, and responsibilities move to a named successor. Approved knowledge then feeds onboarding and the Companion. |

The AI suggests and explains; people confirm. Delegation, knowledge approval, handover publication and responsibility transfer each need an authorized person's confirmation, and every change is recorded with an audit trail.

Theme: **Future of Work & Enterprise Productivity** (AI Builder Cup 2026). All company data in this repository is synthetic.

## Architecture

```
Browser (static Next.js on Firebase Hosting)
   │  /api/**  (same origin, session cookie)
   ▼
Cloud Run: one container ────────────► Gemini (Gemini API / Vertex AI)
   │   ├─ FastAPI: business rules, permissions, audit, outbox  (tutor, companion, handover,
   │   ├─ graph host: LangGraph graphs (ai/)                    Exit KT, embeddings, speech)
   │   ├─ calendar sign-in service (Companion scheduling) ──► Google Calendar
   │   └─ notification dispatcher ──► Firestore (per-person inbox only)
   ▼
Cloud SQL for PostgreSQL + pgvector
   (authoritative business data, curriculum, progress, approved knowledge, embeddings
    and the graphs' conversation checkpoints in a private schema)
```

- **PostgreSQL is the source of truth.** Every consequential change commits its state, idempotency receipt, audit entry and outbox event in one transaction, and checks the record's revision.
- **Firestore holds only notification projections** delivered by a retrying, deduplicated outbox dispatcher. A Firestore outage never undoes a committed action.
- **The AI layer is a separate package** (`ai/`) behind validated contracts. The app falls back to a truthful "not connected" state when an engine is unavailable; it never substitutes canned AI answers.
- **Errors stay private.** Users see the reason when the AI can't do something (for example, a ticket belongs to someone else). For real failures they see only that an error was encountered; details go to the server log.

### How Gemini is used

| Where | Model use |
| --- | --- |
| Onboarding tutor (`ai/ai_adaptive_onboarding`) | Intent analysis, teaching from retrieved procedure sections, check questions, grading against objectives |
| Work Companion (`ai/ai_work_companion`) | Intent routing to predefined work views, ticket updates, procedure-grounded guidance, scheduling |
| Shift Handover (`ai/ai_shift_handover`) | Gap checks and draft updates from member reports and the handover document |
| Exit KT (`ai/ai_exit_knowledge_transfer`) | Opening brief, targeted interview questions, findings and completeness |
| Ingestion (`ai/vector_embedding`) | Section chunking and `gemini-embedding-2` vectors stored in pgvector |
| Voice (`backend/app/integrations/voice.py`) | Live transcription and text-to-speech; nothing is inferred from how people sound |

## Repository layout

```
frontend/   Next.js (static export) + React + TypeScript; unit (Vitest) and browser (Playwright) tests
backend/    FastAPI + SQLAlchemy Core + Alembic; services, repositories, workers, CLI; pytest suite
ai/         LangGraph graphs for the four modules, ingestion/embeddings and voice helpers
graph_host/ Serves the graphs inside the API container with a PostgreSQL checkpointer (cloud)
local/      Docker Compose (PostgreSQL + pgvector, Firestore emulator) and reviewed baseline SQL
seed/       Synthetic company packs (Northstar Manufacturing, Acme Infrastructure, Harbor Support) and source procedures
infra/      Terraform (bootstrap + submission environment) and build/migrate/deploy scripts
```

## Run locally

**Everything in Docker** (the same images as the cloud):

```sh
cp local/.env.example local/.env && cp ai/.env.example ai/.env     # fill in the placeholders
cd local && docker compose up -d --build --wait
docker compose --profile setup run --rm migrate --activate-reviewed-packs   # first time: schema + demo packs
```

Open http://localhost:3080/demo/. Details: [local/README.md](local/README.md).

**Or for development**, with hot reload. Prerequisites: Docker Desktop, [uv](https://docs.astral.sh/uv/), Python 3.13 (backend) and 3.12 (AI), Node 24.

```sh
# 1. Settings: copy the examples and fill in the placeholders
cp local/.env.example local/.env
cp ai/.env.example ai/.env

# 2. Database and Firestore emulator
cd local && docker compose up -d --wait && cd ..

# 3. Backend: baseline schema + migrations + reviewed demo packs, then the API on :8000
cd backend
uv sync
uv run python -m app.ops.migrate --activate-reviewed-packs
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

AI graphs, one terminal each, using a Python 3.12 environment at `ai/.ai_builder_env` with the AI packages installed (`ai/requirements.txt`):

```sh
cd ai/ai_adaptive_onboarding     && ../.ai_builder_env/bin/langgraph dev --port 5678
cd ai/ai_work_companion          && ../.ai_builder_env/bin/langgraph dev --port 5679
cd ai/ai_shift_handover          && ../.ai_builder_env/bin/langgraph dev --port 5680
cd ai/ai_exit_knowledge_transfer && ../.ai_builder_env/bin/langgraph dev --port 5681
```

Frontend:

```sh
cd frontend
npm ci
npm run dev            # http://localhost:3000/demo/  (API mode, proxies /api to :8000)
npm run dev:preview    # labelled fixture preview, no backend needed
```

Open `/demo/`, pick a company, start a fresh demo and choose a persona. Each visitor gets an isolated workspace; nothing is shared or reset globally. More detail: [backend/README.md](backend/README.md), [local/README.md](local/README.md).

## Tests

```sh
cd backend  && uv run pytest -q                          # API + PostgreSQL (uses a separate workweave_test database)
cd frontend && npx vitest run                            # unit
cd frontend && npm run build && npm run e2e              # browser, fixture preview
cd frontend && npm run build:http && npm run e2e:http    # browser against the real API
cd ai/ai_shift_handover && ../.ai_builder_env/bin/pytest -q   # graph tests (also ai_exit_knowledge_transfer, voice)
cd graph_host && .venv/bin/python -m pytest -q tests          # graph host (see graph_host/README.md)
```

## Deploy to Google Cloud

Terraform for one environment in `asia-east1`: Firebase Hosting, Cloud Run (one container with the API, the graph host and the calendar sign-in service, plus migration and cleanup jobs), Cloud SQL for PostgreSQL 16, Firestore, Secret Manager, Artifact Registry, Vertex AI access, uptime monitoring and a budget alert. The image builds from the repository root: `docker build -f backend/Dockerfile .`. Steps and approval gates: [infra/terraform/README.md](infra/terraform/README.md).

## Security and privacy

- Every query and change is scoped to the visitor's organization and workspace.
- Private learning conversations, interviews and voice are not shown in manager views, shared search or notification previews.
- The public demo uses synthetic data only. Spending caps limit AI use per visitor, and evaluator access codes raise them.
- Secrets live in `.env` files locally (never committed) and in Secret Manager in the cloud.

## Team

Team Xynapse, AI Builder Cup 2026.
