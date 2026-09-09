"""Per-project schema and read-only role. Design document section 6, layer 4.

The role granted here holds privileges on exactly one schema. A query naming
another user's schema therefore fails inside PostgreSQL on privilege, whatever
the parser upstream decided — which is what makes "no cross-user reads at any
layer" (PRD F1) true rather than aspirational.

Every statement runs in the caller's transaction. CREATE SCHEMA, CREATE ROLE,
GRANT and DROP are all transactional in PostgreSQL, so a failure part-way leaves
the cluster exactly as it was.
"""

from psycopg import sql
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import raw
from app.models import Project
from app.services.identifiers import role_name_for, schema_name_for


async def _role_exists(session: AsyncSession, role: str) -> bool:
    connection = await raw.connection_of(session)
    found = await raw.fetch_value(
        connection, sql.SQL("SELECT 1 FROM pg_roles WHERE rolname = %s"), (role,)
    )
    return found is not None


async def grant_read_only(session: AsyncSession, schema: str, role: str) -> None:
    """Give ``role`` read access to everything in ``schema``, now and later.

    Re-run after creating tables: GRANT SELECT ON ALL TABLES only covers the
    tables that existed when it ran. ALTER DEFAULT PRIVILEGES covers tables
    created afterwards by this same role, which is belt and braces for the
    ingestion path re-granting explicitly.
    """
    connection = await raw.connection_of(session)
    schema_id, role_id = sql.Identifier(schema), sql.Identifier(role)
    for statement in (
        sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(schema_id, role_id),
        sql.SQL("GRANT SELECT ON ALL TABLES IN SCHEMA {} TO {}").format(
            schema_id, role_id
        ),
        sql.SQL(
            "ALTER DEFAULT PRIVILEGES IN SCHEMA {} GRANT SELECT ON TABLES TO {}"
        ).format(schema_id, role_id),
    ):
        await raw.execute(connection, statement)


async def provision(session: AsyncSession, project: Project) -> tuple[str, str]:
    """Create the project's schema and read-only role. Idempotent.

    Returns ``(schema_name, role_name)`` and records both on the project, so
    deletion can revoke them precisely rather than reconstructing the names from
    a convention that may have changed (design document section 5).
    """
    schema = project.schema_name or schema_name_for(project.user_id, project.name)
    role = project.readonly_role or role_name_for(project.id)
    connection = await raw.connection_of(session)

    await raw.execute(
        connection,
        sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(schema)),
    )
    if not await _role_exists(session, role):
        await raw.execute(
            connection,
            sql.SQL("CREATE ROLE {} NOLOGIN").format(sql.Identifier(role)),
        )
    await grant_read_only(session, schema, role)
    # The app must be a member of the role to SET ROLE to it at query time.
    await raw.execute(
        connection,
        sql.SQL("GRANT {} TO CURRENT_USER").format(sql.Identifier(role)),
    )

    project.schema_name = schema
    project.readonly_role = role
    await session.flush()
    return schema, role


async def deprovision(session: AsyncSession, project: Project) -> None:
    """Drop the schema, its grants and the role, in one transaction.

    DROP OWNED BY is not optional. ALTER DEFAULT PRIVILEGES leaves catalog rows
    that outlive the schema and would block DROP ROLE, so without it every
    deleted project would leak a role into the cluster forever — the risk
    carried forward in design document section 16.
    """
    connection = await raw.connection_of(session)

    if project.schema_name:
        await raw.execute(
            connection,
            sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(
                sql.Identifier(project.schema_name)
            ),
        )
    if project.readonly_role and await _role_exists(session, project.readonly_role):
        role_id = sql.Identifier(project.readonly_role)
        await raw.execute(connection, sql.SQL("DROP OWNED BY {}").format(role_id))
        await raw.execute(connection, sql.SQL("DROP ROLE IF EXISTS {}").format(role_id))

    project.schema_name = None
    project.readonly_role = None
    project.table_count = None
