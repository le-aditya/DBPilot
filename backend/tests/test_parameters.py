"""Saved-query parameters. Pure, so the binding rules are tested exactly."""

from datetime import date
from decimal import Decimal

import pytest

from app.services.parameters import (
    Parameter,
    ParameterType,
    bind,
    extract_parameters,
    for_parsing,
)
from app.services.safety import Allowed, gate


def test_placeholders_are_found_in_order() -> None:
    found = extract_parameters(
        "SELECT * FROM orders WHERE city = :city AND amount > :floor"
    )

    assert [p.name for p in found] == ["city", "floor"]


def test_a_repeated_placeholder_is_one_parameter() -> None:
    found = extract_parameters("SELECT :a, :b, :a")

    assert [p.name for p in found] == ["a", "b"]


def test_a_cast_is_not_a_placeholder() -> None:
    """PostgreSQL's ::type would otherwise look like a parameter called `type`."""
    assert extract_parameters("SELECT amount::numeric FROM orders") == []


def test_a_colon_inside_a_string_literal_is_not_a_placeholder() -> None:
    found = extract_parameters("SELECT * FROM t WHERE at = '12:30' AND city = :city")

    assert [p.name for p in found] == ["city"]


def test_parameters_default_to_text_with_a_readable_label() -> None:
    found = extract_parameters("SELECT :order_date")

    assert found[0].type is ParameterType.text
    assert found[0].label == "order date"


def test_a_template_with_no_placeholders_has_no_parameters() -> None:
    assert extract_parameters("SELECT 1") == []


# --- the gate still applies ---------------------------------------------------


def test_a_parameterised_template_parses_for_the_gate() -> None:
    template = "SELECT * FROM orders WHERE amount > :floor LIMIT :rows"
    parameters = [
        Parameter("floor", ParameterType.numeric),
        Parameter("rows", ParameterType.integer),
    ]

    assert isinstance(gate(for_parsing(template, parameters)), Allowed)


def test_a_parameterised_write_is_still_blocked() -> None:
    """Placeholders must not become a way past layer 2."""
    template = "DELETE FROM orders WHERE id = :id"
    parameters = [Parameter("id", ParameterType.integer)]

    assert not isinstance(gate(for_parsing(template, parameters)), Allowed)


def test_sentinels_match_the_declared_type() -> None:
    parsed = for_parsing(
        "SELECT :when, :count, :flag",
        [
            Parameter("when", ParameterType.date),
            Parameter("count", ParameterType.integer),
            Parameter("flag", ParameterType.boolean),
        ],
    )

    assert "DATE '2000-01-01'" in parsed
    assert "TRUE" in parsed
    assert ":" not in parsed.replace("DATE '2000-01-01'", "")


# --- binding ------------------------------------------------------------------


def test_binding_produces_positional_placeholders_and_values() -> None:
    sql, values = bind(
        "SELECT * FROM orders WHERE city = :city AND amount > :floor",
        [Parameter("city"), Parameter("floor", ParameterType.numeric)],
        {"city": "London", "floor": "50"},
    )

    assert sql == "SELECT * FROM orders WHERE city = %s AND amount > %s"
    assert values == ["London", Decimal("50")]


def test_a_repeated_placeholder_binds_once_per_occurrence() -> None:
    sql, values = bind("SELECT :a, :b, :a", [Parameter("a"), Parameter("b")],
                       {"a": "x", "b": "y"})

    assert sql == "SELECT %s, %s, %s"
    assert values == ["x", "y", "x"]


def test_values_are_coerced_to_the_declared_type() -> None:
    _, values = bind(
        "SELECT :n, :d, :b",
        [
            Parameter("n", ParameterType.integer),
            Parameter("d", ParameterType.date),
            Parameter("b", ParameterType.boolean),
        ],
        {"n": "42", "d": "2024-01-15", "b": "yes"},
    )

    assert values == [42, date(2024, 1, 15), True]


def test_a_default_is_used_when_no_value_is_supplied() -> None:
    _, values = bind(
        "SELECT :city",
        [Parameter("city", default="London")],
        {},
    )

    assert values == ["London"]


def test_a_supplied_value_beats_the_default() -> None:
    _, values = bind("SELECT :city", [Parameter("city", default="London")], {"city": "NYC"})

    assert values == ["NYC"]


def test_a_missing_value_with_no_default_is_refused() -> None:
    with pytest.raises(ValueError, match="city"):
        bind("SELECT :city", [Parameter("city")], {})


def test_an_empty_value_becomes_null_rather_than_an_empty_string() -> None:
    _, values = bind("SELECT :city", [Parameter("city")], {"city": ""})

    assert values == [None]


def test_a_value_containing_sql_stays_a_value() -> None:
    """The whole point: a parameter supplies a value, never structure."""
    sql, values = bind(
        "SELECT * FROM t WHERE name = :name",
        [Parameter("name")],
        {"name": "'); DROP TABLE users; --"},
    )

    assert sql == "SELECT * FROM t WHERE name = %s"
    assert values == ["'); DROP TABLE users; --"]
