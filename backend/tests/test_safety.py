"""The gate's other half: real analytical SQL must get through.

A gate that blocks everything passes every adversarial test and ships a useless
product, so these cases carry as much weight as test_adversarial.py.
"""

import pytest

from app.services.safety import Allowed, Blocked, BlockRule, gate


def allow(sql: str, **kwargs: object) -> Allowed:
    result = gate(sql, **kwargs)  # type: ignore[arg-type]
    assert isinstance(result, Allowed), f"WRONGLY BLOCKED: {sql!r} -> {result}"
    return result


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM customers",
        "SELECT name, amount FROM orders WHERE amount > 100",
        "SELECT c.name, sum(o.amount) FROM customers c "
        "JOIN orders o ON o.customer_id = c.id GROUP BY c.name",
        "SELECT count(*) FROM orders HAVING count(*) > 2",
        "WITH recent AS (SELECT * FROM orders WHERE ordered_on > '2024-01-01') "
        "SELECT count(*) FROM recent",
        "SELECT * FROM a UNION SELECT * FROM b",
        "SELECT * FROM a INTERSECT SELECT * FROM b",
        "SELECT * FROM a EXCEPT SELECT * FROM b",
        "SELECT name, rank() OVER (ORDER BY amount DESC) FROM orders",
        "SELECT * FROM orders WHERE customer_id IN (SELECT id FROM customers)",
        "SELECT date_trunc('month', ordered_on), sum(amount) FROM orders GROUP BY 1",
        "SELECT coalesce(nickname, name) FROM customers ORDER BY 1",
        "SELECT * FROM customers LEFT JOIN orders ON true",
        "SELECT * FROM generate_series(1, 10)",
    ],
)
def test_ordinary_analytical_sql_is_allowed(sql: str) -> None:
    allow(sql)


def test_a_missing_limit_is_injected() -> None:
    result = allow("SELECT * FROM customers")

    assert result.limit_injected is True
    assert result.sql.endswith("LIMIT 1000")


def test_an_existing_limit_is_left_alone() -> None:
    result = allow("SELECT * FROM customers LIMIT 5")

    assert result.limit_injected is False
    assert "LIMIT 5" in result.sql
    assert "1000" not in result.sql


def test_a_full_export_keeps_every_row() -> None:
    result = allow("SELECT * FROM customers", allow_full_export=True)

    assert result.limit_injected is False
    assert "LIMIT" not in result.sql


def test_the_row_limit_is_configurable() -> None:
    result = allow("SELECT * FROM customers", row_limit=25)

    assert result.sql.endswith("LIMIT 25")


def test_a_union_gets_one_limit_for_the_whole_result() -> None:
    result = allow("SELECT * FROM a UNION SELECT * FROM b")

    assert result.sql.count("LIMIT") == 1


def test_the_returned_sql_is_what_runs_not_what_was_submitted() -> None:
    """The caller must execute result.sql — the limit lives only in there."""
    submitted = "select * from customers"

    result = allow(submitted)

    assert result.sql != submitted
    assert "LIMIT 1000" in result.sql


def test_a_table_named_like_a_catalog_table_elsewhere_is_still_blocked() -> None:
    """Conservative on purpose: a user table called pg_stats is not worth the risk."""
    assert isinstance(gate("SELECT * FROM pg_stats"), Blocked)


def test_a_column_called_pg_something_is_fine() -> None:
    """The rule is about tables and functions, not every identifier."""
    allow("SELECT pg_size FROM my_table")


def test_blocking_never_raises_whatever_the_input() -> None:
    """Every path returns a GateResult; nothing reaches the caller as a 500."""
    for hostile in ["\x00", "SELECT '" + "a" * 5000, "((((((", "🙂", "--", "/*"]:
        assert isinstance(gate(hostile), Allowed | Blocked)


def test_every_block_rule_carries_an_actionable_message() -> None:
    """PRD section 9: errors state the cause and the fix."""
    cases = {
        BlockRule.writes_data: "DELETE FROM t",
        BlockRule.multiple_statements: "SELECT 1; SELECT 2",
        BlockRule.catalog_access: "SELECT * FROM pg_catalog.pg_roles",
        BlockRule.forbidden_function: "SELECT pg_read_file('/x')",
        BlockRule.locks_rows: "SELECT * FROM t FOR UPDATE",
        # An unterminated literal: the tokenizer cannot even produce a tree.
        BlockRule.unparseable: "SELECT 'oops",
    }
    for rule, sql in cases.items():
        result = gate(sql)
        assert isinstance(result, Blocked)
        assert result.rule is rule, f"{sql!r} gave {result.rule}, expected {rule}"
        assert len(result.detail) > 20, f"{rule} has no useful message"
