"""Safety layer 3: a transaction that cannot write and always rolls back.

Design document section 6. Four constraints hold at once — the connection runs
as the project's read-only role, the transaction is read-only, statements time
out, and the whole thing rolls back whatever happened. A SELECT has nothing to
commit, so the rollback costs nothing and makes an accidental write impossible
even if every layer above this one failed.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from psycopg import sql
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.config import get_settings
from app.db import raw
from app.db.engine import get_engine
from app.models import Project


@asynccontextmanager
async def readonly_connection(project: Project) -> AsyncIterator[AsyncConnection]:
    """Borrow a connection scoped to one project's read-only role.

    Deliberately NOT the request's metadata session. `SET LOCAL ROLE` lasts for
    the whole transaction, so sharing the session would leave the rest of the
    request running as the read-only role — including the ownership checks.
    """
    settings = get_settings()
    async with get_engine().connect() as connection:
        transaction = await connection.begin()
        try:
            if project.readonly_role:
                await raw.execute(
                    connection,
                    sql.SQL("SET LOCAL ROLE {}").format(
                        sql.Identifier(project.readonly_role)
                    ),
                )
            # SET TRANSACTION READ ONLY, not `default_transaction_read_only`:
            # the latter only supplies a default for later transactions and does
            # nothing to the one already open. Verified against PostgreSQL 18.6.
            await raw.execute(connection, sql.SQL("SET TRANSACTION READ ONLY"))
            await raw.execute(
                connection,
                sql.SQL("SET LOCAL statement_timeout = {}").format(
                    sql.Literal(f"{settings.statement_timeout_seconds}s")
                ),
            )
            if project.schema_name:
                await raw.execute(
                    connection,
                    sql.SQL("SET LOCAL search_path = {}").format(
                        sql.Identifier(project.schema_name)
                    ),
                )
            yield connection
        finally:
            await transaction.rollback()
