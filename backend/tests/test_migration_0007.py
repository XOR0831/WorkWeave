"""Source-sync migration on disposable scratch databases only."""

import uuid

import pytest
from alembic import command
from sqlalchemy import create_engine, text

from tests import prepare_db


@pytest.fixture()
def scratch():
    name = f"workweave_scratch_{uuid.uuid4().hex[:8]}"
    url = prepare_db.build(name, revision="0006", catalog=False)
    engine = create_engine(url)
    try:
        yield url, engine
    finally:
        engine.dispose()
        prepare_db.drop(name)


def test_upgrade_maps_existing_report_states_and_downgrades(scratch):
    url, engine = scratch
    org, ws, employee, item, assignment = (uuid.uuid4() for _ in range(5))
    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO workweave.organizations (organization_id, name) VALUES (:org, 'Sync test')"),
            {"org": org},
        )
        connection.execute(
            text("INSERT INTO workweave.workspaces (workspace_id, organization_id) VALUES (:ws, :org)"),
            {"ws": ws, "org": org},
        )
        connection.execute(
            text("""INSERT INTO workweave.employees
                    (employee_id, organization_id, workspace_id, first_name, last_name, email)
                    VALUES (:employee, :org, :ws, 'Test', 'Reporter', 'sync@example.test')"""),
            {"employee": employee, "org": org, "ws": ws},
        )
        connection.execute(
            text("""INSERT INTO workweave.work_items
                    (work_item_id, organization_id, workspace_id, work_item_type, title)
                    VALUES (:item, :org, :ws, 'TICKET', 'Test ticket')"""),
            {"item": item, "org": org, "ws": ws},
        )
        connection.execute(
            text("""INSERT INTO workweave.work_item_assignments
                    (assignment_id, organization_id, workspace_id, work_item_id, employee_id,
                     assignment_source, assigned_at)
                    VALUES (:assignment, :org, :ws, :item, :employee, 'MANUAL', now())"""),
            {"assignment": assignment, "org": org, "ws": ws, "item": item, "employee": employee},
        )
        for status in ("PENDING", "VERIFIED", "CONFLICTED"):
            connection.execute(
                text("""INSERT INTO workweave.work_item_reported_updates
                        (organization_id, workspace_id, assignment_id, work_item_id, employee_id,
                         verification_status, verified_at, description)
                        VALUES (:org, :ws, :assignment, :item, :employee, :status, now(), :status)"""),
                {"org": org, "ws": ws, "assignment": assignment, "item": item,
                 "employee": employee, "status": status},
            )

    command.upgrade(prepare_db.alembic_config(url), "0007")
    with engine.connect() as connection:
        rows = connection.execute(
            text("""SELECT description, source_sync_status, source_reconciled_at
                    FROM workweave.work_item_reported_updates ORDER BY description""")
        ).all()
        assert {row.description: row.source_sync_status for row in rows} == {
            "PENDING": "AWAITING_SOURCE", "VERIFIED": "MATCHED", "CONFLICTED": "NEEDS_REVIEW"
        }
        assert all(row.source_reconciled_at is not None for row in rows)

    command.downgrade(prepare_db.alembic_config(url), "0006")
    with engine.connect() as connection:
        assert connection.execute(
            text("SELECT verification_status FROM workweave.work_item_reported_updates WHERE description = 'PENDING'")
        ).scalar_one() == "PENDING"


def test_upgrade_accepts_existing_live_shape(scratch):
    url, engine = scratch
    with engine.begin() as connection:
        connection.execute(
            text("""ALTER TABLE workweave.work_item_reported_updates
                    DROP CONSTRAINT work_item_reported_updates_verification_status_check""")
        )
        connection.execute(text("""ALTER TABLE workweave.work_item_reported_updates
                    RENAME COLUMN verification_status TO source_sync_status"""))
        connection.execute(text("""ALTER TABLE workweave.work_item_reported_updates
                    ALTER COLUMN source_sync_status SET DEFAULT 'AWAITING_SOURCE'"""))
        connection.execute(text("""ALTER TABLE workweave.work_item_reported_updates
                    ADD CONSTRAINT work_item_reported_updates_source_sync_status_check
                    CHECK (source_sync_status IN ('AWAITING_SOURCE', 'MATCHED', 'NEEDS_REVIEW'))"""))
        connection.execute(text("""ALTER TABLE workweave.work_item_reported_updates
                    RENAME COLUMN verified_at TO source_reconciled_at"""))

    command.upgrade(prepare_db.alembic_config(url), "0007")
    with engine.connect() as connection:
        assert connection.execute(
            text("""SELECT column_default FROM information_schema.columns
                    WHERE table_schema = 'workweave' AND table_name = 'work_item_reported_updates'
                      AND column_name = 'source_sync_status'""")
        ).scalar_one() == "'AWAITING_SOURCE'::text"
