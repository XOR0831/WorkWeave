# Local environment

The `postgres` service is PostgreSQL 16 with pgvector, a health check, a persistent Docker
volume and a port bound only to `127.0.0.1`. The Firestore emulator for the notification
inbox is a second service, and the full stack below adds the API and the site. The [pgvector image documentation](https://github.com/pgvector/pgvector#docker)
lists the selected versioned image tag. Its PostgreSQL major and extension version
are pinned by tag; the tag is not an immutable image digest.

## Full stack (the cloud images, on this machine)

`compose.yaml` also runs the whole app from the same images as the cloud (ADR-052):
- `api`: the API, the graph host with the four LangGraph graphs, and the calendar sign-in service;
- `web`: the static site served like Firebase Hosting, with `/api/**` passed to `api`.

It replaces the four `langgraph dev` servers (5678–5681).

```sh
cd local
docker compose up -d --build --wait     # site http://localhost:3080/demo/   API http://localhost:8080/api/health
docker compose logs -f api              # graph host, calendar service and API logs
docker compose down                     # stops everything; the database volume is kept
```

- **Settings:**
  - `local/.env` supplies the database settings.
  - `ai/.env` supplies the Gemini models and key, the Google OAuth client and the calendar test account. Locally the graphs use the API key; deployed, they use Vertex AI.
- **Database:** the stack uses the same `workweave` database as the reload dev servers. On first start the graph host adds its own `langgraph` schema (conversation checkpoints).
- **Migrations:** run only when you ask for them:
  - `docker compose --profile setup run --rm migrate` gives a fresh database the reviewed baseline, then Alembic, and an existing database Alembic only;
  - add `--activate-reviewed-packs` to publish the demo packs.
- **Calendar:** the sign-in window goes through the API, as in the cloud. Add `http://localhost:3080/api/calendar/auth/google/callback` as a redirect URI on the OAuth client in Google Cloud Console.
- **Ports** (change in `local/.env`): `WEB_PORT` (3080), `API_PORT` (8080), `POSTGRES_PORT` (5432), `FIRESTORE_PORT` (8085).

## Start

From the repository root, with Docker Desktop running:

```sh
cd local
cp .env.example .env
```

Edit `.env` and replace `POSTGRES_PASSWORD`, then:

```sh
docker compose up -d --wait postgres
docker compose ps
```

Do not commit `.env`. If local port 5432 is occupied, change `POSTGRES_PORT` to
5433 in `.env`; use that port in your database client.

## Connect from your machine

| Setting | Default |
| --- | --- |
| Host | `127.0.0.1` |
| Port | `5432` |
| Database | `workweave` |
| Username | `workweave` |
| Password | Your `POSTGRES_PASSWORD` from `.env` |

Use these settings in DBeaver, TablePlus, pgAdmin, or `psql`:

```sh
psql -h 127.0.0.1 -p 5432 -U workweave -d workweave -W
```

Application URL shape: `postgresql://USER:URL_ENCODED_PASSWORD@127.0.0.1:PORT/DB`.
Use a driver-qualified URL when required by the eventual backend. A future service
on this Compose network connects to `postgres:5432`, not `127.0.0.1`.
The bootstrap user is a development administrator, not a production application role.

## Check and stop

```sh
docker compose exec postgres psql -U workweave -d workweave -c "SELECT version();"
docker compose exec postgres psql -U workweave -d workweave -c "SELECT extversion FROM pg_extension WHERE extname = 'vector';"
docker compose logs --tail=50 postgres
docker compose down
```

Adjust `-U` and `-d` if you changed the defaults. `down` preserves the named volume.
Do not use `down -v` unless you deliberately want to permanently delete this stack's
database data. No reset or destructive command has been run as part of creating these files.

Initialization scripts run only when the data volume is empty. Changing credentials
in `.env` does not update an existing database account; use a reviewed SQL password
change instead of deleting the volume. The [business schema and synthetic seed](postgres/README.md)
remain outside the automatic initialization folder. The base schema/seed and additive
Northstar alignment have been applied to the local `workweave` database after user
authorization. Production migrations and private AI checkpoint
schemas remain the responsibility of the separately planned migration owners.

## Creation-time verification

On 2026-09-27, Docker Compose configuration validation passed:

```sh
POSTGRES_PASSWORD=compose-validation-only docker compose -f local/compose.yaml config --quiet
```

Run that command from the repository root. Runtime startup/connectivity were not
verified because the local Docker daemon socket was unavailable. Start Docker
Desktop before running the start commands above.
