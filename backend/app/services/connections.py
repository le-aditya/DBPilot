"""External PostgreSQL connections. PRD F2.2, design document section 6.

Credentials are encrypted with Fernet using a key from the environment, never
the repository, and the plaintext password exists only for the length of a
connection attempt.

Before a connection is saved, DBPilot connects as the supplied role and asserts
it cannot write: no superuser, and no INSERT, UPDATE or DELETE privilege on any
table in the target schemas. A role that can write is rejected with an
explanation rather than accepted and policed only by the parser — for an
external database, the user's own role *is* safety layer 4, so it has to be
verified rather than assumed.
"""

from dataclasses import dataclass, field

import psycopg
from cryptography.fernet import Fernet, InvalidToken
from psycopg import sql

from app.core.config import get_settings

CONNECT_TIMEOUT_SECONDS = 8
MAX_REPORTED_TABLES = 5
SSL_MODES = frozenset({"disable", "allow", "prefer", "require", "verify-ca", "verify-full"})


class CredentialError(Exception):
    """The stored ciphertext could not be read with the configured key."""


@dataclass(frozen=True)
class ConnectionSettings:
    host: str
    port: int
    database: str
    username: str
    password: str
    ssl_mode: str = "prefer"

    def dsn(self) -> str:
        return psycopg.conninfo.make_conninfo(
            host=self.host,
            port=self.port,
            dbname=self.database,
            user=self.username,
            password=self.password,
            sslmode=self.ssl_mode,
            connect_timeout=CONNECT_TIMEOUT_SECONDS,
        )


@dataclass(frozen=True)
class TestResult:
    ok: bool
    message: str
    is_read_only: bool = False
    schemas: list[str] = field(default_factory=list)
    table_count: int = 0
    writable_tables: list[str] = field(default_factory=list)


def _fernet() -> Fernet:
    return Fernet(get_settings().encryption_key.encode())


def encrypt_password(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_password(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken as error:
        raise CredentialError(
            "The saved password could not be read. It was encrypted with a "
            "different key, so the connection must be entered again."
        ) from error


# Schemas that are never the user's data, so they are excluded from both the
# privilege check and the table count.
_SYSTEM_SCHEMAS = ("pg_catalog", "information_schema", "pg_toast")

_USER_SCHEMAS = sql.SQL(
    "SELECT nspname FROM pg_namespace "
    "WHERE nspname NOT IN ({}) AND nspname NOT LIKE 'pg_temp%' "
    "  AND nspname NOT LIKE 'pg_toast%' "
    "ORDER BY nspname"
).format(sql.SQL(", ").join(sql.Literal(name) for name in _SYSTEM_SCHEMAS))

_WRITABLE = sql.SQL(
    "SELECT c.relnamespace::regnamespace::text || '.' || c.relname "
    "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
    "WHERE c.relkind IN ('r', 'p') "
    "  AND n.nspname NOT IN ({}) "
    "  AND n.nspname NOT LIKE 'pg_temp%' "
    "  AND (has_table_privilege(c.oid, 'INSERT') "
    "    OR has_table_privilege(c.oid, 'UPDATE') "
    "    OR has_table_privilege(c.oid, 'DELETE') "
    "    OR has_table_privilege(c.oid, 'TRUNCATE')) "
    "LIMIT 50"
).format(sql.SQL(", ").join(sql.Literal(name) for name in _SYSTEM_SCHEMAS))


async def check_connection(settings: ConnectionSettings) -> TestResult:
    """Connect, and report whether this role is genuinely read-only."""
    if settings.ssl_mode not in SSL_MODES:
        return TestResult(ok=False, message=f"{settings.ssl_mode!r} is not an SSL mode.")

    try:
        connection = await psycopg.AsyncConnection.connect(settings.dsn())
    except psycopg.OperationalError as error:
        first = str(error).strip().splitlines()[0] if str(error).strip() else "unreachable"
        return TestResult(ok=False, message=f"Could not connect: {first}")
    except Exception as error:  # noqa: BLE001 — a failed test is a message, not a crash
        return TestResult(ok=False, message=f"Could not connect: {error}")

    try:
        await connection.set_read_only(True)
        superuser = await (await connection.execute(
            sql.SQL("SELECT rolsuper FROM pg_roles WHERE rolname = current_user")
        )).fetchone()
        if superuser and superuser[0]:
            return TestResult(
                ok=False,
                message=(
                    "That role is a superuser, so DBPilot cannot guarantee it will "
                    "not write. Create a role with SELECT-only grants and use that."
                ),
            )

        writable = [row[0] for row in await (await connection.execute(_WRITABLE)).fetchall()]
        if writable:
            shown = ", ".join(writable[:MAX_REPORTED_TABLES])
            extra = len(writable) - MAX_REPORTED_TABLES
            more = f", and {extra} more" if extra > 0 else ""
            return TestResult(
                ok=False,
                writable_tables=writable,
                message=(
                    f"That role can write to {shown}{more}. DBPilot only connects "
                    "with read-only roles. Revoke those grants, or use a different role."
                ),
            )

        schemas = [row[0] for row in await (await connection.execute(_USER_SCHEMAS)).fetchall()]
        count_row = await (await connection.execute(
            sql.SQL(
                "SELECT count(*) FROM pg_class c JOIN pg_namespace n "
                "ON n.oid = c.relnamespace WHERE c.relkind IN ('r','p') "
                "AND n.nspname NOT IN ({})"
            ).format(sql.SQL(", ").join(sql.Literal(n) for n in _SYSTEM_SCHEMAS))
        )).fetchone()

        return TestResult(
            ok=True,
            is_read_only=True,
            message="Connected. This role is read-only.",
            schemas=schemas,
            table_count=int(count_row[0]) if count_row else 0,
        )
    finally:
        await connection.close()
