import pytest
from psycopg import errors, sql
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import raw
from app.models import Project, SourceType, User
from app.services.provisioning import deprovision, provision

pytestmark = pytest.mark.integration


async def _schema_exists(session: AsyncSession, name: str) -> bool:
    connection = await raw.connection_of(session)
    found = await raw.fetch_value(
        connection,
        sql.SQL("SELECT 1 FROM information_schema.schemata WHERE schema_name = %s"),
        (name,),
    )
    return found is not None


async def _role_exists(session: AsyncSession, name: str) -> bool:
    connection = await raw.connection_of(session)
    found = await raw.fetch_value(
        connection, sql.SQL("SELECT 1 FROM pg_roles WHERE rolname = %s"), (name,)
    )
    return found is not None


async def test_provision_creates_the_schema_and_role(
    session: AsyncSession, user: User, project: Project
) -> None:
    schema, role = await provision(session, project)

    assert schema == f"user_{user.id}_sales"
    assert role == f"ro_p{project.id}"
    assert await _schema_exists(session, schema)
    assert await _role_exists(session, role)


async def test_provision_is_idempotent(
    session: AsyncSession, project: Project
) -> None:
    first = await provision(session, project)

    assert await provision(session, project) == first


async def test_provision_records_both_names_on_the_project(
    session: AsyncSession, project: Project
) -> None:
    schema, role = await provision(session, project)

    assert project.schema_name == schema
    assert project.readonly_role == role


async def test_the_role_may_read_its_own_schema(
    session: AsyncSession, project: Project
) -> None:
    schema, role = await provision(session, project)
    connection = await raw.connection_of(session)
    await raw.execute(
        connection,
        sql.SQL("CREATE TABLE {}.t (a int)").format(sql.Identifier(schema)),
    )
    await raw.execute(
        connection,
        sql.SQL("INSERT INTO {}.t VALUES (1)").format(sql.Identifier(schema)),
    )
    await raw.execute(
        connection,
        sql.SQL("GRANT SELECT ON {}.t TO {}").format(
            sql.Identifier(schema), sql.Identifier(role)
        ),
    )

    await raw.execute(connection, sql.SQL("SET LOCAL ROLE {}").format(sql.Identifier(role)))
    count = await raw.fetch_value(
        connection, sql.SQL("SELECT count(*) FROM {}.t").format(sql.Identifier(schema))
    )
    await raw.execute(connection, sql.SQL("RESET ROLE"))

    assert count == 1


async def test_the_role_cannot_read_the_application_metadata_schema(
    session: AsyncSession, project: Project
) -> None:
    """A project role must never see other users' accounts."""
    _, role = await provision(session, project)
    connection = await raw.connection_of(session)

    await raw.execute(connection, sql.SQL("SET LOCAL ROLE {}").format(sql.Identifier(role)))
    with pytest.raises(errors.InsufficientPrivilege):
        await raw.fetch_value(connection, sql.SQL("SELECT count(*) FROM dbpilot.users"))


async def test_deprovision_removes_the_schema_and_the_role(
    session: AsyncSession, project: Project
) -> None:
    schema, role = await provision(session, project)

    await deprovision(session, project)

    assert not await _schema_exists(session, schema)
    assert not await _role_exists(session, role)
    assert project.schema_name is None
    assert project.readonly_role is None


async def test_deprovision_on_a_project_that_was_never_provisioned_is_a_no_op(
    session: AsyncSession, project: Project
) -> None:
    await deprovision(session, project)

    assert project.schema_name is None


async def test_a_project_name_that_looks_like_sql_cannot_inject(
    session: AsyncSession, user: User
) -> None:
    """Schema names are composed as identifiers, never formatted as text."""
    hostile = Project(
        user_id=user.id,
        name='x"; DROP SCHEMA dbpilot CASCADE; --',
        source_type=SourceType.upload,
    )
    session.add(hostile)
    await session.flush()

    schema, _ = await provision(session, hostile)

    assert await _schema_exists(session, schema)
    # The metadata schema is untouched, which is the whole point.
    assert await _schema_exists(session, "dbpilot")
