"""Safety layer 3, proved against a real role on real data."""

import pytest
from psycopg import errors, sql
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import raw
from app.db.readonly import readonly_connection
from app.models import Project
from tests.conftest import CommittedProject

pytestmark = pytest.mark.integration


async def _project(session: AsyncSession, made: CommittedProject) -> Project:
    project = await session.get(Project, made.id)
    assert project is not None
    return project


async def test_the_readonly_connection_can_read_the_project_data(
    session: AsyncSession, committed_project: CommittedProject
) -> None:
    project = await _project(session, committed_project)

    async with readonly_connection(project) as connection:
        rows = await raw.fetch_all(connection, sql.SQL("SELECT count(*) FROM people"))

    assert rows[0][0] == 3


async def test_the_readonly_connection_refuses_an_insert(
    session: AsyncSession, committed_project: CommittedProject
) -> None:
    project = await _project(session, committed_project)

    with pytest.raises((errors.ReadOnlySqlTransaction, errors.InsufficientPrivilege)):
        async with readonly_connection(project) as connection:
            await raw.execute(
                connection, sql.SQL("INSERT INTO people (name) VALUES ('mallory')")
            )


async def test_the_readonly_connection_refuses_a_drop(
    session: AsyncSession, committed_project: CommittedProject
) -> None:
    project = await _project(session, committed_project)

    with pytest.raises((errors.ReadOnlySqlTransaction, errors.InsufficientPrivilege)):
        async with readonly_connection(project) as connection:
            await raw.execute(connection, sql.SQL("DROP TABLE people"))


async def test_one_projects_role_cannot_read_another_projects_schema(
    session: AsyncSession,
    committed_project: CommittedProject,
    other_committed_project: CommittedProject,
) -> None:
    """PRD F1: no cross-user reads at any layer, even fully qualified."""
    project = await _project(session, committed_project)

    with pytest.raises(errors.InsufficientPrivilege):
        async with readonly_connection(project) as connection:
            await raw.fetch_all(
                connection,
                sql.SQL("SELECT * FROM {}.secrets").format(
                    sql.Identifier(other_committed_project.schema_name)
                ),
            )


async def test_one_projects_role_cannot_read_the_metadata_schema(
    session: AsyncSession, committed_project: CommittedProject
) -> None:
    project = await _project(session, committed_project)

    with pytest.raises(errors.InsufficientPrivilege):
        async with readonly_connection(project) as connection:
            await raw.fetch_all(
                connection, sql.SQL("SELECT email FROM dbpilot.users")
            )


async def test_the_role_does_not_leak_out_of_the_context_manager(
    session: AsyncSession, committed_project: CommittedProject
) -> None:
    """SET LOCAL ROLE lasts a whole transaction, so it must have its own."""
    project = await _project(session, committed_project)

    async with readonly_connection(project):
        pass

    who = await raw.fetch_value(
        await raw.connection_of(session), sql.SQL("SELECT current_user")
    )
    assert who == "dbpilot_app"
