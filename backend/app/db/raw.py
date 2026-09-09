"""Reach psycopg from a SQLAlchemy connection.

Two jobs need the driver directly: composing DDL from user-derived identifiers
(``psycopg.sql.Identifier`` is the only safe way — identifiers cannot be bound
as parameters) and ``COPY``. Everything else in the app should use SQLAlchemy.

Keeping the escape hatch in one module means there is exactly one place to audit
when asking "can any user input reach SQL as text?". The answer must stay no.
"""

from typing import Any, cast

import psycopg
from psycopg import sql
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession


async def driver_of(connection: AsyncConnection) -> psycopg.AsyncConnection:
    raw = await connection.get_raw_connection()
    return cast(psycopg.AsyncConnection, raw.driver_connection)


async def connection_of(session: AsyncSession) -> AsyncConnection:
    return await session.connection()


async def execute(
    connection: AsyncConnection,
    statement: sql.Composable,
    params: tuple[Any, ...] | None = None,
) -> None:
    driver = await driver_of(connection)
    await driver.execute(statement, params)


async def fetch_all(
    connection: AsyncConnection,
    statement: sql.Composable,
    params: tuple[Any, ...] | None = None,
) -> list[tuple[Any, ...]]:
    driver = await driver_of(connection)
    cursor = await driver.execute(statement, params)
    return await cursor.fetchall()


async def fetch_value(
    connection: AsyncConnection,
    statement: sql.Composable,
    params: tuple[Any, ...] | None = None,
) -> Any:
    rows = await fetch_all(connection, statement, params)
    return rows[0][0] if rows else None
