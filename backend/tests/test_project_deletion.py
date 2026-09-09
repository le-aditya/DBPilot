"""Deleting a project must not leak a schema or a role.

Design document section 16 names this as the risk the per-project role model
introduces: without an explicit teardown, every deleted project leaves a role
in the cluster forever.
"""

import pytest
from psycopg import sql
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import raw
from app.models import Project, SourceType, User
from app.services.ingestion import commit_upload
from app.services.projects import delete_project
from tests.test_ingestion import CUSTOMERS, spec_from

pytestmark = pytest.mark.integration


async def _count(session: AsyncSession, statement: sql.Composable, name: str) -> int:
    value = await raw.fetch_value(await raw.connection_of(session), statement, (name,))
    return int(value or 0)


async def _schema_count(session: AsyncSession, name: str) -> int:
    return await _count(
        session,
        sql.SQL(
            "SELECT count(*) FROM information_schema.schemata WHERE schema_name = %s"
        ),
        name,
    )


async def _role_count(session: AsyncSession, name: str) -> int:
    return await _count(
        session, sql.SQL("SELECT count(*) FROM pg_roles WHERE rolname = %s"), name
    )


async def _with_data(session: AsyncSession, project: Project) -> tuple[str, str]:
    await commit_upload(
        session, project, [spec_from("customers.csv", CUSTOMERS)],
        {"customers.csv": CUSTOMERS},
    )
    assert project.schema_name and project.readonly_role
    return project.schema_name, project.readonly_role


async def test_deleting_a_project_drops_its_schema(
    session: AsyncSession, project: Project
) -> None:
    schema, _ = await _with_data(session, project)

    await delete_project(session, project)

    assert await _schema_count(session, schema) == 0


async def test_deleting_a_project_drops_its_readonly_role(
    session: AsyncSession, project: Project
) -> None:
    _, role = await _with_data(session, project)

    await delete_project(session, project)

    assert await _role_count(session, role) == 0


async def test_deleting_one_project_leaves_another_alone(
    session: AsyncSession, user: User, project: Project
) -> None:
    kept = Project(user_id=user.id, name="Kept", source_type=SourceType.upload)
    session.add(kept)
    await session.flush()
    kept_schema, kept_role = await _with_data(session, kept)
    await _with_data(session, project)

    await delete_project(session, project)

    assert await _schema_count(session, kept_schema) == 1
    assert await _role_count(session, kept_role) == 1


async def test_deleting_a_never_provisioned_project_still_works(
    session: AsyncSession, project: Project
) -> None:
    await delete_project(session, project)

    assert project.schema_name is None
