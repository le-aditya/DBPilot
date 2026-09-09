"""External connections, tested against real PostgreSQL roles.

The read-only check is the only thing standing between DBPilot and a user's
production database, so it is proved against a role that really can write and a
role that really cannot, rather than against a mock.
"""

import pytest
from httpx import AsyncClient
from psycopg import sql
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db import raw
from app.services.connections import (
    ConnectionSettings,
    CredentialError,
    check_connection,
    decrypt_password,
    encrypt_password,
)
from tests.conftest import CommittedProject

pytestmark = pytest.mark.integration

READER = "dbpilot_conn_reader"
WRITER = "dbpilot_conn_writer"
PASSWORD = "probe-password-123"


@pytest.fixture
async def probe_roles(session: AsyncSession, migrated_database: Settings):
    """A genuinely read-only role and a genuinely writable one, then cleaned up."""
    connection = await raw.connection_of(session)
    driver = await raw.driver_of(connection)
    await driver.set_autocommit(True)
    try:
        for role, writable in ((READER, False), (WRITER, True)):
            await raw.execute(
                connection,
                sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(role)),
            )
            await raw.execute(
                connection,
                sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
                    sql.Identifier(role), sql.Literal(PASSWORD)
                ),
            )
            await raw.execute(
                connection,
                sql.SQL("GRANT USAGE ON SCHEMA dbpilot TO {}").format(
                    sql.Identifier(role)
                ),
            )
            grant = "ALL" if writable else "SELECT"
            await raw.execute(
                connection,
                sql.SQL("GRANT {} ON ALL TABLES IN SCHEMA dbpilot TO {}").format(
                    sql.SQL(grant), sql.Identifier(role)
                ),
            )
            # Membership is what makes DROP OWNED BY legal in teardown. Real
            # project roles get the same grant from provisioning, for the same
            # reason -- without it a role cannot be cleaned up at all.
            await raw.execute(
                connection,
                sql.SQL("GRANT {} TO CURRENT_USER").format(sql.Identifier(role)),
            )
        yield
    finally:
        for role in (READER, WRITER):
            await raw.execute(
                connection,
                sql.SQL("DROP OWNED BY {}").format(sql.Identifier(role)),
            )
            await raw.execute(
                connection,
                sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(role)),
            )
        await driver.set_autocommit(False)


def settings_for(user: str, database: str) -> ConnectionSettings:
    return ConnectionSettings(
        host="localhost",
        port=5432,
        database=database,
        username=user,
        password=PASSWORD,
    )


# --- credentials -------------------------------------------------------------


def test_a_password_round_trips_through_encryption() -> None:
    assert decrypt_password(encrypt_password("hunter2")) == "hunter2"


def test_the_ciphertext_does_not_contain_the_password() -> None:
    assert "hunter2" not in encrypt_password("hunter2")


def test_the_same_password_encrypts_differently_each_time() -> None:
    """Fernet includes a nonce, so equal passwords are not equal ciphertexts."""
    assert encrypt_password("hunter2") != encrypt_password("hunter2")


def test_ciphertext_from_another_key_is_refused_with_an_explanation() -> None:
    from cryptography.fernet import Fernet

    foreign = Fernet(Fernet.generate_key()).encrypt(b"hunter2").decode()

    with pytest.raises(CredentialError, match="entered again"):
        decrypt_password(foreign)


# --- the read-only check -----------------------------------------------------


async def test_a_read_only_role_is_accepted(
    probe_roles: None, migrated_database: Settings
) -> None:
    database = migrated_database.test_database_url.rsplit("/", 1)[-1]  # type: ignore[union-attr]

    result = await check_connection(settings_for(READER, database))

    assert result.ok is True
    assert result.is_read_only is True
    assert "dbpilot" in result.schemas


async def test_a_writable_role_is_refused_and_told_why(
    probe_roles: None, migrated_database: Settings
) -> None:
    """The check that protects a user's production database."""
    database = migrated_database.test_database_url.rsplit("/", 1)[-1]  # type: ignore[union-attr]

    result = await check_connection(settings_for(WRITER, database))

    assert result.ok is False
    assert "can write to" in result.message
    assert result.writable_tables


async def test_a_wrong_password_reports_the_failure_rather_than_raising(
    probe_roles: None, migrated_database: Settings
) -> None:
    database = migrated_database.test_database_url.rsplit("/", 1)[-1]  # type: ignore[union-attr]
    wrong = ConnectionSettings(
        host="localhost", port=5432, database=database, username=READER, password="nope"
    )

    result = await check_connection(wrong)

    assert result.ok is False
    assert "Could not connect" in result.message


async def test_an_unreachable_host_reports_the_failure(
    migrated_database: Settings,
) -> None:
    result = await check_connection(
        ConnectionSettings(
            host="localhost", port=59999, database="x", username="y", password="z"
        )
    )

    assert result.ok is False
    assert "Could not connect" in result.message


async def test_an_invalid_ssl_mode_is_refused_before_connecting() -> None:
    result = await check_connection(
        ConnectionSettings(
            host="localhost",
            port=5432,
            database="x",
            username="y",
            password="z",
            ssl_mode="banana",
        )
    )

    assert result.ok is False
    assert "SSL mode" in result.message


# --- the endpoints -----------------------------------------------------------


async def test_saving_a_writable_connection_is_refused(
    live_client: AsyncClient,
    committed_project: CommittedProject,
    probe_roles: None,
    migrated_database: Settings,
) -> None:
    database = migrated_database.test_database_url.rsplit("/", 1)[-1]  # type: ignore[union-attr]

    response = await live_client.post(
        f"/projects/{committed_project.id}/connection",
        headers=committed_project.headers,
        json={
            "host": "localhost",
            "port": 5432,
            "database_name": database,
            "username": WRITER,
            "password": PASSWORD,
        },
    )

    assert response.status_code == 422
    assert "read-only" in response.json()["error"]["message"]


async def test_saving_a_read_only_connection_never_returns_the_password(
    live_client: AsyncClient,
    committed_project: CommittedProject,
    probe_roles: None,
    migrated_database: Settings,
) -> None:
    database = migrated_database.test_database_url.rsplit("/", 1)[-1]  # type: ignore[union-attr]

    response = await live_client.post(
        f"/projects/{committed_project.id}/connection",
        headers=committed_project.headers,
        json={
            "host": "localhost",
            "port": 5432,
            "database_name": database,
            "username": READER,
            "password": PASSWORD,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["username"] == READER
    assert PASSWORD not in response.text
    assert "password" not in body


async def test_testing_a_connection_saves_nothing(
    live_client: AsyncClient,
    committed_project: CommittedProject,
    probe_roles: None,
    migrated_database: Settings,
) -> None:
    database = migrated_database.test_database_url.rsplit("/", 1)[-1]  # type: ignore[union-attr]

    await live_client.post(
        f"/projects/{committed_project.id}/connection/test",
        headers=committed_project.headers,
        json={
            "host": "localhost",
            "port": 5432,
            "database_name": database,
            "username": READER,
            "password": PASSWORD,
        },
    )

    stored = await live_client.get(
        f"/projects/{committed_project.id}/connection",
        headers=committed_project.headers,
    )
    assert stored.status_code == 404


async def test_another_users_connection_is_a_404(
    live_client: AsyncClient,
    committed_project: CommittedProject,
    other_committed_project: CommittedProject,
) -> None:
    response = await live_client.post(
        f"/projects/{committed_project.id}/connection/test",
        headers=other_committed_project.headers,
        json={
            "host": "localhost",
            "port": 5432,
            "database_name": "x",
            "username": "y",
            "password": "z",
        },
    )

    assert response.status_code == 404
