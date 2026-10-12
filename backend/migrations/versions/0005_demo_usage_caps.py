"""Demo usage caps and evaluator access codes (ADR-029).

Written for review 2026-10-04 (not applied to the local dev database).

The public demo has no login, so anyone with the link can call the tutor, voice and spoken
replies. Budget alerts only notify; these tables let the API refuse work past daily limits instead
of spending the free-trial credits, and give judges (evaluators) a separate, higher allowance:

- demo_access_codes: evaluator codes created by the privileged CLI. Only a SHA-256 of the
  normalized code is stored (codes carry ~80 random bits); codes expire, can be revoked, and are
  never deleted. Each code may create at most max_runs_per_day new demo workspaces per UTC day.
- demo_visitor_sessions.access_code_id: the code a visitor run was opened or upgraded with. The
  API re-checks the code's expiry and revocation on every capped action.
- demo_usage: one counter per (scope type, scope key, kind, UTC day). The API increments it with
  INSERT ... ON CONFLICT DO UPDATE ... WHERE used < limit in the guarded request's transaction, so
  concurrent requests can't overshoot a cap. Counts only: no content or personal data.
- demo_usage_limits: the daily limits per tier (PUBLIC, EVALUATOR) and scope (RUN = one visitor
  run, POOL = everyone in that tier). Seeded below; changed with the CLI (`set-limit`). 0 = off.

Downgrade drops everything this migration added.

Revision ID: 0005
Revises: 0004
"""

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

KINDS = "('DEMO_RUN', 'TUTOR_TURN', 'VOICE_LISTEN', 'VOICE_SPEECH', 'ACCESS_ATTEMPT_FAILED')"

# (tier, scope_type, usage_kind, daily_limit): the reviewed starting values (ADR-029).
SEED = [
    ("PUBLIC", "RUN", "TUTOR_TURN", 120),
    ("PUBLIC", "RUN", "VOICE_LISTEN", 60),
    ("PUBLIC", "RUN", "VOICE_SPEECH", 150),
    ("PUBLIC", "POOL", "DEMO_RUN", 150),
    ("PUBLIC", "POOL", "TUTOR_TURN", 600),
    ("PUBLIC", "POOL", "VOICE_LISTEN", 400),
    ("PUBLIC", "POOL", "VOICE_SPEECH", 600),
    ("PUBLIC", "POOL", "ACCESS_ATTEMPT_FAILED", 500),
    ("EVALUATOR", "RUN", "TUTOR_TURN", 1000),
    ("EVALUATOR", "RUN", "VOICE_LISTEN", 500),
    ("EVALUATOR", "RUN", "VOICE_SPEECH", 1000),
    ("EVALUATOR", "POOL", "DEMO_RUN", 300),
    ("EVALUATOR", "POOL", "TUTOR_TURN", 3000),
    ("EVALUATOR", "POOL", "VOICE_LISTEN", 1500),
    ("EVALUATOR", "POOL", "VOICE_SPEECH", 3000),
]


def upgrade() -> None:
    op.execute(
        f"""
        CREATE TABLE workweave.demo_access_codes (
            access_code_id   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            label            text NOT NULL UNIQUE CHECK (length(btrim(label)) BETWEEN 1 AND 80),
            code_hash        text NOT NULL UNIQUE CHECK (code_hash ~ '^[0-9a-f]{{64}}$'),
            code_hint        text NOT NULL CHECK (code_hint ~ '^[0-9A-Z]{{4}}$'),
            expires_at       timestamptz NOT NULL,
            revoked_at       timestamptz,
            max_runs_per_day integer NOT NULL DEFAULT 50 CHECK (max_runs_per_day > 0),
            created_at       timestamptz NOT NULL DEFAULT now(),
            last_used_at     timestamptz,
            CHECK (expires_at > created_at)
        );

        ALTER TABLE workweave.demo_visitor_sessions
            ADD COLUMN access_code_id uuid REFERENCES workweave.demo_access_codes (access_code_id);

        CREATE TABLE workweave.demo_usage (
            scope_type text NOT NULL CHECK (scope_type IN ('PUBLIC_POOL', 'EVALUATOR_POOL', 'RUN', 'ACCESS_CODE')),
            scope_key  text NOT NULL CHECK (
                (scope_type IN ('PUBLIC_POOL', 'EVALUATOR_POOL') AND scope_key = 'pool')
                OR (scope_type IN ('RUN', 'ACCESS_CODE') AND scope_key ~ '^[0-9a-f]{{8}}-[0-9a-f]{{4}}-[0-9a-f]{{4}}-[0-9a-f]{{4}}-[0-9a-f]{{12}}$')
            ),
            usage_kind text NOT NULL CHECK (usage_kind IN {KINDS}),
            usage_day  date NOT NULL,
            used       integer NOT NULL CHECK (used >= 0),
            updated_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (scope_type, scope_key, usage_kind, usage_day)
        );

        CREATE TABLE workweave.demo_usage_limits (
            tier        text NOT NULL CHECK (tier IN ('PUBLIC', 'EVALUATOR')),
            scope_type  text NOT NULL CHECK (scope_type IN ('RUN', 'POOL')),
            usage_kind  text NOT NULL CHECK (usage_kind IN {KINDS}),
            daily_limit integer NOT NULL CHECK (daily_limit >= 0),
            updated_at  timestamptz NOT NULL DEFAULT now(),
            updated_by  text NOT NULL DEFAULT 'migration 0005',
            PRIMARY KEY (tier, scope_type, usage_kind)
        );
        """
    )
    values = ", ".join(f"('{t}', '{s}', '{k}', {n})" for t, s, k, n in SEED)
    op.execute(f"INSERT INTO workweave.demo_usage_limits (tier, scope_type, usage_kind, daily_limit) VALUES {values};")


def downgrade() -> None:
    op.execute(
        """
        DROP TABLE workweave.demo_usage_limits;
        DROP TABLE workweave.demo_usage;
        ALTER TABLE workweave.demo_visitor_sessions DROP COLUMN access_code_id;
        DROP TABLE workweave.demo_access_codes;
        """
    )
