# WorkWeave API (demo-entry slice)

FastAPI + PostgreSQL backend for the first database-backed slice: public synthetic catalog →
isolated server-side visitor workspace → pack personas → persona selection → persona home.
No AI layer, document parsing, embeddings, `/app/` login or other module APIs are implemented.

## Routes (`/api` prefix)

| Route | Contract |
| --- | --- |
| `GET /scenarios` | READY synthetic packs only (blueprint/07) |
| `POST /demo-sessions` | `{scenario_id, intent: RESUME \| FRESH, pack_version?}` → isolated workspace + session cookie |
| `GET /demo-sessions/current` | Current session or `null` |
| `POST /demo-sessions/current/persona` | `{employee_id}` from this workspace's pack roster |
| `GET /personas` | This workspace's pack personas |
| `GET /demo-sessions/runs` | **Proposed** (not in 07): this visitor's resumable runs, for catalog/Resume UI |
| `DELETE /demo-sessions/current` | **Proposed**: stop using the current run in this browser |
| `GET /onboarding` | Current persona's assigned curriculum, ordered path, saved progress and resume position (no criteria, attempts or conversations) |
| `GET /onboarding/progress` | Team progress by subtopic; needs an explicit `learning:supervise` grant scoped to the team |
| `GET /curricula` (PROPOSED) | Read-only catalog of this workspace's curricula with stored counts; needs an explicit, currently valid, workspace-scoped `curriculum:read` grant |
| `GET /curricula/{id}` (PROPOSED) | Read-only detail: active topics/subtopics, stored objectives, `curriculum_sources` with parsed headings and recorded section links; same grant; other workspaces' IDs are 404 |
| `POST /onboarding/sessions` | Create or resume the learner's session at the deterministic position (tutor shell) |
| `GET /onboarding/sessions/{id}` | The owner's committed session state; never checkpoint data |
| `POST /onboarding/sessions/{id}/turns` | `{client_turn_id, expected_revision, text, input_kind}`; returns `CAPABILITY_UNAVAILABLE` until a tutor engine is connected, storing nothing |
| `POST /onboarding/sessions/{id}/pause` | `{client_turn_id, expected_revision}`; idempotent (command receipt) and audited; never changes progress |
| `GET /health` | Liveness |

Sessions are opaque random tokens in `HttpOnly`, `SameSite=Lax` cookies on path `/api`
(`ww_session` for the run in use, `ww_run_<company>` per company); PostgreSQL stores only SHA-256
hashes. There is no signing secret. Commands require the `X-WorkWeave-Client: web` header.

## Run locally

Prerequisites: Docker Desktop, the local PostgreSQL stack (`../local`, with `POSTGRES_PASSWORD`
in `../local/.env`), [uv](https://docs.astral.sh/uv/), Node 24.

```sh
cd local && docker compose up -d --wait postgres

cd ../backend
uv sync
uv run alembic upgrade head                      # 0001 (additive) and 0002 (see below)
uv run python -m app.cli sync-catalog ../seed/packs/northstar-manufacturing \
  ../seed/packs/acme-infrastructure ../seed/packs/harbor-support
uv run python -m app.cli activate northstar acme harbor --confirm-reviewed
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000

# second terminal: either the dev server (hot reload) or the static HTTP build
cd ../frontend
npm run dev                                       # http://localhost:3000/demo/, proxies /api to :8000
npm run build:http && npm run serve:http          # http://localhost:4319/demo/ (static export + proxy)
```

Or start both halves in one terminal (API with `--reload`, `next dev` in API mode):

```sh
cd frontend && npm run dev:stack
```

`npm run dev:preview` runs the labelled fixture preview with no backend.

All steps are repeatable: the migration is versioned, `sync-catalog` replaces only catalog
presentation and persona metadata, and activation re-verifies the pack. Nothing resets data.
`uv run python -m app.cli status` lists catalog state; `deactivate <company>` hides a pack.

The UI preview (`npm run build && npm run serve`, port 4318) still uses labelled browser fixtures.

## Onboarding slice notes

- Each new visitor run also copies competencies, curricula, all topics (including document-bound topics from SOP ingestion), subtopics, objectives, prerequisites, assignments and progress. Northstar's learners are assigned Machine Fundamentals 1.1, built from SOP-001 v3.4's ingested topics (product-owner decision 2026-10-04; 1.0 is archived). Linked source documents are copied too (all versions, their source records and the `knowledge_mappings` links), and `GET /onboarding` lists only the approved, current version, for example SOP-001 v3.4 for Northstar.
- A subtopic whose objectives are all optional (`required = false`, e.g. the v3.4 Reference aids) is shown as optional: it can be studied and completes when its own objective passes, but curriculum completion counts required subtopics only.
- Runs created before this slice have no copied curriculum: use **Start fresh demo** to get one.
- For curricula linked through `curriculum_sources`, each run also copies the approved, current, unrevoked version's `knowledge_sections`, the typed `curriculum_source_sections` of copied subtopics, and every chunk with its embedding (copied in SQL; all IDs remapped). A run fails closed if such a version has a chunk without an embedding. Onboarding reads prefer the typed links and fall back to legacy `knowledge_mappings` only when a path has none, never a union. `teaching_chunks` returns current-guidance chunks only.
- Tests for this use `tests/ingestion_db.py`: a read-only `pg_dump` of the local dev database restored into disposable `workweave_scratch_*` databases, because the ingestion output isn't reproducible from repo scripts.
- Team progress needs `learning:supervise`. Apply `../local/postgres/11_onboarding_supervision_grants.sql`, then run `activate <packs> --confirm-reviewed` (the pack's identity hash includes grants; `sync-catalog` is only for catalog.json changes).

## Curricula read slice notes

- Read-only: both routes run in a `READ ONLY` transaction. Authoring (create, upload, parse, map, review, publish) has no backend route; the frontend renders no control for it in API mode.
- **Authorization (approved 2026-10-03, option 2):** both routes require a currently valid `curriculum:read` grant whose `resource_scope` is explicitly the whole workspace: `"scope": "WORKSPACE"` and no `team_id`, `department_id` or `employee_id` key. **Workspace scope means:** the holder may read every curriculum in this one workspace (whichever teams its learners belong to) and nothing in any other workspace. A grant without the marker, with a narrowing key, expired or not yet valid authorizes nothing; no other action (including team-scoped `knowledge:review`) authorizes these reads. The pack coordinators (Northstar and Acme: Morgan Lee; Harbor: Ravi Patel) receive it from `local/postgres/13_curriculum_read_grants.sql`. Persona display grants show `curriculum.read` only for such a grant, and the API-mode Coordinator nav follows it.
- Only stored data is returned. Gaps against the preview's authoring model: no processing stage, section kind, excerpt, filename or review receipts are stored, and an unlinked section can't be told apart as reference-only or unresolved. `sources` is always empty; `linked_sources` carries the stored rows. Headings of a revoked source are withheld; section and chunk content are never returned.
- There is still no stored curriculum-to-team relationship; that is why curriculum reads use a workspace-scoped grant instead of a team-scoped one.

## Tutor shell and the AI boundary

`app/integrations/tutor.py` defines a **proposed** `TutorEngine` port (`open_session`, `process_turn`, `pause`) using the integration contract's typed statuses. The only implementation is `NotConnectedTutor`, which returns `unavailable`: there is no mock tutor and no scripted reply. The AI engineer's onboarding graph plugs in behind this port once the first contract version is agreed and pinned (blueprint/14). Sessions record a server-generated, workspace-scoped thread ID (`ww-<session id>`) and `graph_version = not-connected`.

### Tutor turns (application side)

`POST /onboarding/sessions/{id}/turns` (`app/services/tutor_turns.py`) runs in three phases so no transaction is open during the engine call: a short claim (owner, `client_turn_id` receipt, `expected_revision`, ACTIVE status; a `RECEIVED` row without learner text), the engine call, then one transaction that re-checks the revision, validates the output against fresh state and writes the turn, events, attempt, evidence and progress together or not at all.

- **Contract `proposed-1` (not signed off by the AI engineer):** strict Pydantic `TurnOutput` (unknown fields rejected): `reply` (kind, text, strategy, citations), optional `event`, `new_check` (a comprehension question), `assessment` (criterion-level, for the pending question) and `metadata`. Metadata such as model confidence is stored but never consulted.
- **Citations:** each must name a document version that is among the session's permitted sources (the overview's typed-or-legacy path), approved, `CURRENT`, the document's current pointer and unrevoked, plus a section and/or chunk of that exact version in the same workspace. Re-checked at commit time and again when the transcript is read (a later revocation withholds the excerpt). Teaching and example replies need at least one.
- **Evidence (`mvp-objective-evidence-1`):** PASSED only for a `CORRECT` attempt on the pending question whose criterion results cover exactly the objective's reviewed `required_checks`, all met, without hints (unless the objective's `hint_policy.hinted_attempts_count` is true). Contradictory results are rejected outright. A subtopic completes only when every required objective has PASSED evidence for its current criteria version; the next item stays `NOT_STARTED`.
- **Pending question:** stored as a `COMPREHENSION_QUESTION` learning event (the schema has no `learning_sessions.pending_question` column); open until PASSED evidence or a newer question replaces it, and revalidated against the current criteria version.
- **Idempotency and failures:** a committed duplicate replays the committed state without a second engine call; the same ID with another message is 422; a failed or invalid result marks the claim `FAILED` (no text kept) and returns 503 so the client can retry with the same ID; a revision change during the call is 409.
- **Engines:** only `NotConnectedTutor` runs in development and release. `install_test_tutor()` works only with `WORKWEAVE_ENV=test` (set by `tests/conftest.py`); the deterministic engine lives in `tests/tutor_fakes.py`.

## The AI engineer's tutor engine (ADR-030)

With `TUTOR_ENGINE=langgraph` and `LANGGRAPH_URL` set (locally `langgraph dev` in `ai/ai_adaptive_onboarding`, `http://127.0.0.1:5678`), onboarding conversations run on her graph. **Start conversation** opens it (her opening question). Each message resumes it, and **Continue** after a completed item opens the next one (`POST /api/onboarding/sessions/{id}/continue`). Her graph saves every turn, event, evidence and progress row itself (contract `engine-1`). The backend only authorizes, applies the demo caps, drives the graph and reads the saved rows back, so it writes no learning data. See `app/services/engine_turns.py`; tests use a fake LangGraph API (`tests/test_engine_turns.py`).

**Live progress:** `POST /api/onboarding/sessions/{id}/turns/stream` takes the same body as `/turns` and answers as server-sent events. It sends `progress` {label} as the graph's steps finish (fixed plain-language labels mapped from her step names in `engine_turns.progress_label`, never model output), then `done` {request_id, data} or `error` {request_id, error}. Checks that fail before the tutor starts return the usual JSON error. Streamed responses are `Cache-Control: no-store, no-transform`, so proxies (the Next.js dev proxy, Firebase Hosting) don't compress them and hold the events back.

## Work Companion (ADR-031)

`GET /api/work-state`, `GET /api/assignments`, `GET /api/work-events`: the persona's work, from its own `work:read` grants. Fresh demos copy the pack's work scenario with times moved to "today". `POST /api/work-sessions` opens the conversation (one per employee at a time) and `POST /api/work-sessions/{id}/voice/listen` gives voice input. See `app/services/companion.py` and `tests/test_companion.py`. Without the AI engine, messages return `CAPABILITY_UNAVAILABLE` and nothing is stored.

**The AI engineer's Companion engine (ADR-034):** set `COMPANION_ENGINE=langgraph` and `LANGGRAPH_COMPANION_URL` (locally `langgraph dev` in `ai/ai_work_companion`, `http://127.0.0.1:5679`; later graphs take the next ports: Shift Handover 5680, Exit KT 5681; assistant `LANGGRAPH_COMPANION_ASSISTANT`, default `ai_work_companion`). Opening the session runs her opening brief; `POST /api/work-sessions/{id}/messages` resumes her graph with the message (`client_turn_id`, `expected_revision`, `text`, `input_kind`). The backend saves the exchange in `work_session_messages` (migration 0009), picks the canvas from the steps that ran (allowlisted `ui_action`), keeps the approved chunks guidance used as citations (`GET /api/work-sessions/{id}/guidance/{message_id}`), and gives reports her graph saved the ADR-033 bookkeeping. Her calendar and scheduling steps run in her graph once her calendar service (`CALENDAR_SERVICE_URL`, default `http://127.0.0.1:8001`) is signed in to Google. If it isn't, the reply offers **Connect Google Calendar** (`GET /api/calendar/status` reports the connection). `COMPANION_CALENDAR=false` stops them and gives a fixed reply. Automatic assignment (ADR-035): when the Companion opens, the team's open unassigned tickets go to members on the shift in progress by the `competency-v1` rule (`app/services/assignment.py`, `AUTO_ASSIGN_WORK`). The shift lead overrides with `POST /api/work-items/{id}/assignee` (candidates: `GET .../assignment-candidates`), and `GET /api/work-items/{id}/assignment` explains why (assignee or lead only). A shift lead can ask to hand their own tickets to teammates on the same shift: her graph suggests, the backend rechecks and creates a delegation proposal (`work_commands.propose_from_engine`), and nothing is assigned until the lead confirms. Turns count against the demo's `TUTOR_TURN` cap. Replies are read aloud like the tutor's: `GET /api/work-sessions/{id}/voice/speech/{message_id}` (WAV) and `.../stream` (PCM), only for the session's own employee and only the companion's saved replies, with the same audio cache and `VOICE_SPEECH` cap. See `app/services/companion_turns.py`, `app/integrations/companion_engine.py` and `tests/test_companion_turns.py`.

Reports and the ticket system (ADR-033): `POST /api/work-items/{id}/reports` (what the employee says; never changes the ticket), `GET /api/ticket-system` and `POST /api/ticket-system/items/{id}/status` (the simulated ticket tool: the real status). Reports are matched against it in `app/services/work_sync.py`. Commands (ADR-032): `GET|PATCH /api/delegation-proposals[/{id}]`, `POST .../confirm|reject`, `GET|POST /api/memory-drafts`, `POST /api/memory-drafts/{id}/review`, `DELETE /api/memory-drafts/{id}?idempotency_key=`. Each takes an `idempotency_key` (and `expected_revision` where it guards a change). See `app/services/work_commands.py` and `tests/test_companion_commands.py`.

## Voice transport (onboarding)

Built for the AI engineer as transport only (owner exception 2026-10-04; `app/integrations/voice.py`, `app/services/voice.py`): no tutor logic and no analysis of how the learner sounds.

- **Listening:** `POST /api/onboarding/sessions/{id}/voice/listen` with `{"mode": "TAP" | "HANDS_FREE"}` mints a single-use Gemini ephemeral token locked to the transcription-only Live model (text output, input transcription on; automatic voice activity detection off for tap-to-talk, on for hands-free) and returns the setup message the browser must send. The browser streams 16 kHz PCM straight to Gemini; the API key never leaves the backend and no audio reaches or is stored by it. Only the session owner, with an ACTIVE session, gets a grant.
- **Speaking (streamed):** `GET /api/onboarding/sessions/{id}/voice/speech/{turn_id}:out/stream` streams raw 16-bit mono PCM (rate in `X-Sample-Rate`) as Gemini generates it (`streamGenerateContent`), and the browser plays it chunk by chunk with Web Audio (`lib/voice/stream-player.ts`). First sound arrives about 1.5 s after the request instead of after the whole reply (~28 s for 86 words, measured 2026-10-04). Errors before the first audio return the usual JSON error; a failure later just ends the audio early.
- **Speaking (whole file):** `GET /api/onboarding/sessions/{id}/voice/speech/{turn_id}:out` returns WAV of that committed tutor reply, read verbatim by Gemini text-to-speech. Learner messages, other sessions and arbitrary text are refused. On Cloud Run speech goes through **Vertex AI** (`aiplatform.googleapis.com`, location `global`, paid by the project's credits), authenticated as the service account with a token from the metadata server, so no key is used. Locally it uses the Gemini API key. `VOICE_TTS_BACKEND` = `auto` (default: Vertex when `GOOGLE_GENAI_USE_VERTEXAI=true` and `GOOGLE_CLOUD_PROJECT` are set), `vertex` or `gemini_api`. Listening always uses the key; the paid `GEMINI_EVALUATOR_API_KEY` is used for evaluator runs.
- **Keyboard:** Space mirrors the mic button whenever focus isn't in a text field, on a control or in a dialog: it interrupts a reply being read, starts tap-to-talk, or stops it so the transcript can be reviewed (held keys and modifier combinations are ignored).
- **Interrupting a reply:** while a reply is read aloud, the mic button becomes "Interrupt (Space)": it stops playback and listens (tap-to-talk starts listening; hands-free simply resumes, still on). An optional "Interrupt by voice" setting (hands-free, off by default; best with headphones) keeps listening during playback and stops the reply only when the transcript has two consecutive words that aren't in the reply being read (echo filter), after a 0.5 s grace period; speech heard during playback without a barge-in is discarded. The next turn carries `interrupted_previous_reply: true`, stored with the learner's input and passed to the engine as `TutorContext.previous_reply_interrupted`.
- **Capabilities:** `GET /api/capabilities` reports `voice_adapter` (and `conversation_engine`) as `AVAILABLE` or `UNAVAILABLE`.
- **Configuration** (`src/local/.env`, never committed): `GEMINI_API_KEY`; optional `VOICE_LISTEN_MODEL` (default `gemini-3.5-transcribe-live`), `VOICE_TTS_MODEL` (`gemini-3.8-flash-lite-tts`), `VOICE_TTS_VOICE` (`Kore`), `VOICE_LANGUAGE_CODES` (JSON list, default `["en-US"]`), `VOICE_TRANSCRIPT_MODE` (`VERBATIM` or `SMART`). Restart the API after changing them.
- Tests use a mocked HTTP transport and a fake provider (`install_test_voice`, test environment only); no real Gemini call is made by the test suite.

## Demo spending caps and evaluator access (ADR-029)

The public demo has no login, so `app/services/usage.py` counts actions that spend Gemini or workspace
capacity per UTC day in `workweave.demo_usage` (migration 0005): new workspaces, tutor turns, voice
listening grants and spoken replies, per visitor run and per tier pool. A full bucket answers
`429 LIMIT_REACHED` with `limit: {kind, scope, resets_at}` before any external call and counts
nothing. The session view carries `demo_limits` so the UI can show limits up front.

Evaluator runs (opened with a valid access code, `app/services/access.py`) use their own, higher
limits and pool, and the optional paid voice-listening key (`GEMINI_EVALUATOR_API_KEY`).

```sh
uv run python -m app.cli create-access-code --label "Judge - Panel A" --expires 2026-11-15   # shown once
uv run python -m app.cli list-access-codes
uv run python -m app.cli revoke-access-code "Judge - Panel A"
uv run python -m app.cli show-limits
uv run python -m app.cli set-limit EVALUATOR POOL TUTOR_TURN 5000     # 0 turns a cap off
uv run python -m app.cli reset-usage --confirm [--kind TUTOR_TURN]     # clear today's counters now
```

Caps reset by themselves every day at 00:00 UTC (8:00 AM Manila): usage is counted per UTC day.
`reset-usage` starts today's allowance over for everyone, e.g. after testing, so it needs `--confirm`.
The cleanup job also removes counters older than `--keep-usage-days` (default 7); they hold counts only.

The test suite turns every cap off at start; `tests/test_usage_caps.py` and
`tests/test_access_codes.py` set the limits they need.

## Migrations

| Revision | Change | Local `workweave` |
| --- | --- | --- |
| `0001` | Catalog presentation, `scenario_personas`, `demo_visitor_sessions`, `employees.baseline_employee_id` (additive) | Applied 2026-10-03 |
| `0002` | Drop the empty legacy `demo_sessions`/`demo_persona_grants` (aborts if they have rows); visitor sessions may only attach to `DEMO` workspaces (three-column FK) | Applied 2026-10-03 (after a passing read-only preflight) |
| `0003` | Reviewed retention exception: append-only rows may be deleted only by the demo cleanup, only in an expired/revoked `DEMO` visitor workspace (never a pack original or `OPERATIONAL`); adds the content-free `demo_workspace_purges` log | Applied 2026-10-03; first `--confirm` run purged 1 revoked run (42 rows) |
| `0004` | Durable visitor-run proof: `demo_visitor_runs` (written at materialization; backfilled only from existing sessions) and `visitor_run_purge_allowed()`. PostgreSQL rejects purge deletes of append-only rows, sessions, workspaces and proof rows without valid proof; active unexpired sessions are never deletable; proof rows are immutable | Applied 2026-10-03; backfilled 11 proof rows (`BACKFILL_FROM_SESSION`), one per workspace with sessions |

Run the read-only preflight in the next section before applying `0002` anywhere. Never run its downgrade on a database you care about.

## Preflight for 0002 (read-only)

```sh
cd local
docker compose exec -T postgres psql -U workweave -d workweave -f - < ../backend/scripts/preflight_0002.sql
```

Every row must show `ok = t`. The script runs in a `READ ONLY` transaction and ends with `ROLLBACK`.

## Demo visitor cleanup

Fresh starts and expired sessions leave their copied runs in the database until this job purges them.

```sh
uv run python -m app.workers.cleanup                         # dry run (read-only): what would be purged
uv run python -m app.workers.cleanup --confirm               # purge, one run per transaction
uv run python -m app.workers.cleanup --grace-minutes 120 --limit 20
```

With migration 0004 the evidence is a `demo_visitor_runs` proof row, and runs with proof but no remaining session are listed as `needs review` (`PROOF_WITHOUT_SESSION`), never purged by age; before 0004 the worker uses session rows as evidence. Eligible only with positive evidence of a visitor run: a `DEMO` workspace in a visitor organization (`company_key` NULL), not a pack original, with at least one `demo_visitor_sessions` row; none of its sessions ACTIVE and unexpired, and no session activity for `--grace-minutes` (default 60). `DEMO` workspaces with no session row are never purged automatically: both modes list them as `needs review`. Each purge runs in its own transaction: it locks the workspace (which also blocks new sessions), then every session of the run, and only then re-checks eligibility, so a run resumed meanwhile is skipped. It then deletes every scoped row (including its audit rows and command receipts, under migration 0003's exception), removes the visitor organization and logs counts in `demo_workspace_purges`. `--confirm` needs migration 0003.

**Hosting:** the same container image runs this as a Cloud Run Job, invoked by Cloud Scheduler under its own least-privilege cleanup identity (blueprint/15 `operations/`). It is never an HTTP endpoint. The Terraform for the job and schedule is not written yet.

## Tests

```sh
uv run pytest                                     # API + PostgreSQL (rebuilds workweave_test only)
cd ../frontend && npm run build:http && npm run e2e:http   # browser against API on :8100
```

Tests drop and recreate only the `workweave_test` database in the local container.

## Shift Handover (ADR-038)

`POST /api/handovers/active` opens the handover from the team's shift in progress (the lead's first open creates the draft). The lead: `PATCH /api/handovers/{id}/sections/{section_id}`, `POST /api/handover-suggestions/{id}/accept|ignore`, `POST /api/handovers/{id}/template-versions`, `POST /api/handovers/{id}/publish`. The receiving shift: `POST /api/handover-publications/{id}/receipt`. The originating shift's lead: `POST /api/handover-acknowledgements/{cycle_id}/acknowledge|dispute`. Resolving a linked ticket in the ticket system completes its handover items (`handover.on_ticket_change`). See `app/services/handover.py` and `tests/test_handover.py`.

## Exit KT (ADR-039)

`GET /api/exit-kt/case` returns the persona's case filtered by role. Commands live under `/api/exit-kt/` (knowledge items, findings, artifacts and their submit/decision/promote, transfers, package assemble/submit/decision/receipt, checklist, complete). Discovery, interviews, drafting and package questions answer `CAPABILITY_UNAVAILABLE`. See `app/services/exit_kt.py` and `tests/test_exit_kt.py`.

## Shift Handover graph (ADR-043)

Run it from the AI folder: `cd ai/ai_shift_handover && ../.ai_builder_env/bin/langgraph dev --port 5680` (her `.env` supplies Gemini and the database). The backend reaches it at `LANGGRAPH_HANDOVER_URL` (default `http://127.0.0.1:5680`); `HANDOVER_ENGINE=none` turns it off. Routes: `POST /api/handovers/{id}/gap-check`, `/section-drafts`, `/copilot`. Graph tests: `WORKWEAVE_TEST_DATABASE_URL=… ../.ai_builder_env/bin/python -m pytest tests` (Gemini mocked).

## Voice for Shift Handover and Exit KT (ADR-045)

The same transport as the Companion. `POST /api/handover/voice/listen` and `GET /api/handover/voice/speech/{message_id}/stream` are for shift leads, and only for their own copilot's AI answers. `POST /api/exit-kt/voice/listen` and `GET /api/exit-kt/voice/speech/{message_id}/stream` are for people on the case, and only for their own copilot answers or their own interview questions. They have the same caps and cache as the other voice routes. See `app/services/voice.py` and `tests/test_voice_handover_kt.py`.

## Exit KT graph (ADR-044)

Run it from the AI folder: `cd ai/ai_exit_knowledge_transfer && ../.ai_builder_env/bin/langgraph dev --port 5681`. The backend reaches it at `LANGGRAPH_EXIT_KT_URL` (default `http://127.0.0.1:5681`); `EXIT_KT_ENGINE=none` turns it off. Routes: `POST /api/exit-kt/discovery`, `/recommendations`, `/plan/{id}/accept|decline`, `/copilot`, `/knowledge-items/{id}/interview`, `/interviews/{id}/messages|draft`, `/package/questions`, `/cases`, `/successor`. Graph tests: `WORKWEAVE_TEST_DATABASE_URL=… ../.ai_builder_env/bin/python -m pytest tests` (Gemini mocked).

## In the cloud container (ADR-052)

The image (`backend/Dockerfile`, built from the repository root) runs `backend/start.sh`: the [graph host](../graph_host/README.md) with the four graphs on `127.0.0.1:8123`, the AI engineer's calendar sign-in service on `127.0.0.1:8001` (only when the Google OAuth client is configured), then the API. If any of them stops, the container exits and Cloud Run replaces it.

- **Calendar sign-in through the API.** In the cloud the calendar service is reachable only from inside the container. `CALENDAR_CONNECT_URL=/api/calendar/auth/google` makes the Companion's **Connect Google Calendar** window open `GET /api/calendar/auth/google`, which needs a persona with work access and redirects only to `accounts.google.com`. Google returns to `GET /api/calendar/auth/google/callback`, which passes just the OAuth parameters to the service and shows only the outcome: no account address and no error details. Only the configured test account can connect.
- **Ingestion.** `INGESTION_PASS_GEMINI_ENV=true` (set in the image) gives the AI engineer's ingestion the Gemini settings from the deployment, because her `.env` isn't in the image.
- **Inbox.** A release build always uses real Firestore, never the emulator default.
