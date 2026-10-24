"""Alembic environment. The URL and schema come from Settings, never alembic.ini."""

import asyncio
from logging.config import fileConfig

from sqlalchemy.engine import Connection
from sqlalchemy import text
from alembic import context
from app.core.config import get_settings
from app.db.base import METADATA_SCHEMA, Base
from app.db.engine import create_engine
from app.models import *  # noqa: F401,F403  (registers every mapper)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _url() -> str:
    return get_settings().database_url


def _configure(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_schemas=True,
        version_table_schema=METADATA_SCHEMA,
        compare_type=True,
        compare_server_default=True,
    )


def run_migrations_offline() -> None:
    context.configure(
        url=_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        include_schemas=True,
        version_table_schema=METADATA_SCHEMA,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_run(connection: Connection) -> None:
    _configure(connection)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_engine(_url())
    async with engine.connect() as connection:
        await connection.execute(
            text(f'CREATE SCHEMA IF NOT EXISTS "{METADATA_SCHEMA}"')
        )
        await connection.commit()

        await connection.run_sync(_do_run)
        await connection.commit()

    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
