import pytest

from app.services.identifiers import (
    MAX_IDENTIFIER_BYTES,
    normalise,
    role_name_for,
    schema_name_for,
    unique_names,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Order ID", "order_id"),
        ("  Total (USD)  ", "total_usd"),
        ("2024 revenue", "col_2024_revenue"),  # cannot start with a digit
        ("", "column"),  # a blank header still needs a name
        ("Customer-Name", "customer_name"),
        ("select", "select_col"),  # reserved word
        ("ÉLÈVE", "eleve"),  # accents fold to ASCII
        ("a" * 100, "a" * MAX_IDENTIFIER_BYTES),
    ],
)
def test_normalise(raw: str, expected: str) -> None:
    assert normalise(raw) == expected


def test_unique_names_disambiguates_collisions() -> None:
    assert unique_names(["Name", "name", "NAME"]) == ["name", "name_2", "name_3"]


def test_schema_name_is_scoped_to_the_user() -> None:
    assert schema_name_for(7, "Q3 Sales!") == "user_7_q3_sales"


def test_schema_name_stays_within_the_identifier_limit() -> None:
    assert len(schema_name_for(7, "x" * 200)) <= MAX_IDENTIFIER_BYTES


def test_role_name_is_derived_from_the_project_id() -> None:
    assert role_name_for(42) == "ro_p42"
