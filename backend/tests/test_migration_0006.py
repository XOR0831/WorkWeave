"""Employee report storage and assignment ownership on a disposable database."""

import uuid

import pytest
from alembic import command
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from tests import prepare_db


@pytest.fixture()
def scratch():
    name = f"workweave_scratch_{uuid.uuid4().hex[:8]}"
    url = prepare_db.build(name, revision="0005", catalog=False)
    engine = create_engine(url)
    try:
        command.upgrade(prepare_db.alembic_config(url), "0006")
        yield engine
    finally:
        engine.dispose()
        prepare_db.drop(name)


def test_report_belongs_to_its_assignment_without_closing_source_item(scratch):
    org, ws, employee, other_employee, item, other_item, assignment = (uuid.uuid4() for _ in range(7))
    with scratch.begin() as connection:
        connection.execute(
            text("INSERT INTO workweave.organizations (organization_id, name) VALUES (:org, 'Report test')"),
            {"org": org},
        )
        connection.execute(
            text("INSERT INTO workweave.workspaces (workspace_id, organization_id, kind) VALUES (:ws, :org, 'OPERATIONAL')"),
            {"ws": ws, "org": org},
        )
        for employee_id, suffix in ((employee, "one"), (other_employee, "two")):
            connection.execute(
                text("""INSERT INTO workweave.employees
                        (employee_id, organization_id, workspace_id, first_name, last_name, email)
                        VALUES (:employee, :org, :ws, 'Test', 'Reporter', :email)"""),
                {"employee": employee_id, "org": org, "ws": ws, "email": f"{suffix}@example.test"},
            )
        for item_id in (item, other_item):
            connection.execute(
                text("""INSERT INTO workweave.work_items
                        (work_item_id, organization_id, workspace_id, work_item_type, title)
                        VALUES (:item, :org, :ws, 'TICKET', 'Test ticket')"""),
                {"item": item_id, "org": org, "ws": ws},
            )
        connection.execute(
            text("""INSERT INTO workweave.work_item_assignments
                    (assignment_id, organization_id, workspace_id, work_item_id, employee_id,
                     assignment_source, assigned_at)
                    VALUES (:assignment, :org, :ws, :item, :employee, 'MANUAL', now())"""),
            {"assignment": assignment, "org": org, "ws": ws, "item": item, "employee": employee},
        )
        report_id = connection.execute(
            text("""INSERT INTO workweave.work_item_reported_updates
                    (organization_id, workspace_id, assignment_id, work_item_id, employee_id,
                     reported_status, source_status_at_report, description)
                    VALUES (:org, :ws, :assignment, :item, :employee,
                            'COMPLETED', 'ACTIVE', 'Employee reports completion')
                    RETURNING reported_update_id"""),
            {"org": org, "ws": ws, "assignment": assignment, "item": item, "employee": employee},
        ).scalar_one()

    with scratch.connect() as connection:
        report = connection.execute(
            text("""SELECT verification_status, reported_status, source_status_at_report, revision
                    FROM workweave.work_item_reported_updates WHERE reported_update_id = :id"""),
            {"id": report_id},
        ).one()
        assert report == ("PENDING", "COMPLETED", "ACTIVE", 1)
        assert connection.execute(
            text("SELECT status FROM workweave.work_items WHERE work_item_id = :item"), {"item": item}
        ).scalar_one() == "ACTIVE"

    for wrong_item, wrong_employee in ((other_item, employee), (item, other_employee)):
        with pytest.raises(IntegrityError):
            with scratch.begin() as connection:
                connection.execute(
                    text("""INSERT INTO workweave.work_item_reported_updates
                            (organization_id, workspace_id, assignment_id, work_item_id, employee_id)
                            VALUES (:org, :ws, :assignment, :item, :employee)"""),
                    {"org": org, "ws": ws, "assignment": assignment,
                     "item": wrong_item, "employee": wrong_employee},
                )

    with scratch.begin() as connection:
        connection.execute(
            text("""UPDATE workweave.work_item_reported_updates
                    SET verification_status = 'VERIFIED', verified_at = now()
                    WHERE reported_update_id = :id"""),
            {"id": report_id},
        )
    with scratch.connect() as connection:
        assert connection.execute(
            text("SELECT revision FROM workweave.work_item_reported_updates WHERE reported_update_id = :id"),
            {"id": report_id},
        ).scalar_one() == 2
