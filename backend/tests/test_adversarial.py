"""The adversarial suite. PRD section 12 lists zero writes as a success metric,
so this file is explicit about what it proves.

Every case here is a real attempt to make DBPilot write, read another user's
data, reach the filesystem, or escape the project schema. A failure in this file
is a security defect, not a test bug.

These run against the pure gate, which is layer 2 of four. Layer 4 (the role)
is proved separately in test_readonly.py, so a hole here still meets a locked
door — but the point of defence in depth is that neither layer is allowed to be
the only one working.
"""

import pytest

from app.services.safety import Allowed, Blocked, BlockRule, gate


def block(sql: str) -> Blocked:
    result = gate(sql)
    assert isinstance(result, Blocked), f"NOT BLOCKED: {sql!r} -> {result}"
    return result


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO users VALUES (1, 'mallory')",
        "UPDATE users SET email = 'x'",
        "DELETE FROM users",
        "DROP TABLE users",
        "DROP SCHEMA dbpilot CASCADE",
        "ALTER TABLE users ADD COLUMN x int",
        "CREATE TABLE evil (a int)",
        "CREATE INDEX ON users (email)",
        "TRUNCATE users",
        "GRANT SELECT ON users TO mallory",
        "REVOKE SELECT ON users FROM app",
        "MERGE INTO users USING t ON true WHEN MATCHED THEN DELETE",
        "COPY users TO '/tmp/stolen.csv'",
        "COPY users FROM '/tmp/planted.csv'",
        "CALL some_procedure()",
        "DO $$ BEGIN PERFORM 1; END $$",
        "VACUUM users",
        "SET ROLE postgres",
        "RESET ROLE",
        "CREATE ROLE mallory SUPERUSER",
        "ALTER ROLE dbpilot_app SUPERUSER",
        "CREATE FUNCTION f() RETURNS int AS 'SELECT 1' LANGUAGE sql",
        "REFRESH MATERIALIZED VIEW mv",
        "LOCK TABLE users",
    ],
)
def test_every_kind_of_write_is_blocked(sql: str) -> None:
    block(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 1; DROP TABLE users",
        "SELECT 1;DROP TABLE users",
        "SELECT 1 ; ; DROP TABLE users",
        "SELECT 1;\n-- innocent\nDELETE FROM users",
    ],
)
def test_statement_chaining_is_blocked(sql: str) -> None:
    assert block(sql).rule is BlockRule.multiple_statements


@pytest.mark.parametrize(
    "sql",
    [
        "WITH x AS (DELETE FROM users RETURNING *) SELECT * FROM x",
        "WITH x AS (INSERT INTO users VALUES (1) RETURNING *) SELECT * FROM x",
        "WITH x AS (UPDATE users SET email='x' RETURNING *) SELECT * FROM x",
        "WITH a AS (SELECT 1), b AS (DELETE FROM users RETURNING *) SELECT * FROM a, b",
    ],
)
def test_a_write_hidden_in_a_cte_is_blocked(sql: str) -> None:
    """PostgreSQL really runs these, and they parse with a SELECT at the root."""
    assert block(sql).rule is BlockRule.writes_data


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM users -- ; DROP TABLE users",
        "SELECT /* DROP TABLE users */ 1",
        "SELECT * FROM users /* multi\nline */ WHERE id = 1",
    ],
)
def test_a_write_smuggled_into_a_comment_is_inert(sql: str) -> None:
    """Comments are not executed, so these are allowed — and stay harmless."""
    assert isinstance(gate(sql), Allowed)


@pytest.mark.parametrize(
    "sql",
    [
        "sElEcT 1; dRoP TaBlE users",
        "SELECT\n\t1\n;\nDROP\nTABLE\nusers",
        "   SELECT 1   ;   DROP TABLE users   ",
    ],
)
def test_casing_and_whitespace_do_not_evade_the_gate(sql: str) -> None:
    """The gate reads the parse tree, so cosmetics change nothing."""
    block(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM pg_catalog.pg_roles",
        "SELECT * FROM information_schema.tables",
        "SELECT * FROM information_schema.columns WHERE table_schema = 'user_1_x'",
        "SELECT * FROM pg_class",
        "SELECT * FROM pg_shadow",
        "SELECT * FROM PG_CATALOG.PG_USER",
        "SELECT (SELECT count(*) FROM pg_roles) AS n",
        "WITH c AS (SELECT * FROM pg_catalog.pg_authid) SELECT * FROM c",
    ],
)
def test_catalog_reads_are_blocked(sql: str) -> None:
    assert block(sql).rule is BlockRule.catalog_access


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT pg_read_file('/etc/passwd')",
        "SELECT pg_read_binary_file('/etc/passwd')",
        "SELECT pg_ls_dir('/')",
        "SELECT lo_import('/etc/passwd')",
        "SELECT lo_export(1, '/tmp/out')",
        "SELECT dblink('host=evil', 'SELECT 1')",
        "SELECT pg_sleep(600)",
        "SELECT pg_terminate_backend(1)",
        "SELECT * FROM t WHERE x = pg_read_file('/etc/passwd')",
    ],
)
def test_file_and_admin_functions_are_blocked(sql: str) -> None:
    assert block(sql).rule is BlockRule.forbidden_function


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * INTO stolen FROM users",
        "SELECT * FROM users FOR UPDATE",
        "SELECT * FROM users FOR SHARE",
    ],
)
def test_select_shaped_writes_and_locks_are_blocked(sql: str) -> None:
    block(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "this is not sql at all",
        "SELECT FROM WHERE",
        "'; DROP TABLE users; --",
        "",
        "   ",
    ],
)
def test_nonsense_is_refused_rather_than_guessed_at(sql: str) -> None:
    block(sql)


def test_a_blocked_statement_names_the_rule_that_stopped_it() -> None:
    """PRD section 9: a blocked query must say which rule blocked it."""
    result = block("DELETE FROM users")

    assert result.rule is BlockRule.writes_data
    assert "SELECT" in result.detail


def test_injection_planted_in_a_string_literal_is_just_a_string() -> None:
    """A CSV cell containing SQL is data. It must not become structure."""
    result = gate("SELECT * FROM t WHERE note = '''); DROP TABLE users; --'")

    assert isinstance(result, Allowed)
    assert "DROP TABLE users" in result.sql  # still inside the literal
