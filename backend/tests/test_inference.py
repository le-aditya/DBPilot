from datetime import date, datetime
from decimal import Decimal

import pytest

from app.services.inference import ColumnType, coerce, infer_table, iter_rows


def csv_bytes(text: str) -> bytes:
    return text.encode("utf-8")


def test_infers_the_type_ladder_in_order() -> None:
    table = infer_table(
        "sales.csv",
        csv_bytes(
            "Order ID,Amount,Shipped,Order Date,Created At,Notes\n"
            "1,10.50,true,2024-01-15,2024-01-15 09:30:00,hello\n"
            "2,11.25,false,2024-02-20,2024-02-20 11:00:00,world\n"
        ),
    )
    assert [c.type for c in table.columns] == [
        ColumnType.integer,
        ColumnType.numeric,
        ColumnType.boolean,
        ColumnType.date,
        ColumnType.timestamp,
        ColumnType.text,
    ]


def test_names_come_from_the_identifier_rules() -> None:
    table = infer_table("Q3 Sales.csv", csv_bytes("Order ID\n1\n"))
    assert table.name == "q3_sales"
    assert table.columns[0].name == "order_id"
    assert table.columns[0].source_name == "Order ID"


def test_a_zero_one_column_is_an_integer_not_a_boolean() -> None:
    # The ladder checks integer first on purpose: 1/0 is more useful as a number.
    table = infer_table("f.csv", csv_bytes("flag\n1\n0\n"))
    assert table.columns[0].type is ColumnType.integer


def test_one_bad_cell_demotes_the_whole_column_to_text() -> None:
    table = infer_table("f.csv", csv_bytes("n\n1\n2\nnot a number\n"))
    assert table.columns[0].type is ColumnType.text


def test_an_empty_cell_makes_the_column_nullable_without_changing_its_type() -> None:
    table = infer_table("f.csv", csv_bytes("n,other\n1,a\n,b\n3,c\n"))
    assert table.columns[0].type is ColumnType.integer
    assert table.columns[0].nullable is True


def test_a_blank_line_is_skipped_rather_than_read_as_a_row_of_nulls() -> None:
    # csv.reader yields [] for an empty line. Treating that as a row would
    # silently make every column nullable in any file with a trailing blank.
    table = infer_table("f.csv", csv_bytes("n\n1\n\n3\n"))
    assert table.sampled_rows == 2
    assert table.columns[0].nullable is False


def test_a_column_with_no_empty_cells_is_not_nullable() -> None:
    table = infer_table("f.csv", csv_bytes("n\n1\n2\n"))
    assert table.columns[0].nullable is False


def test_an_all_empty_column_is_nullable_text() -> None:
    table = infer_table("f.csv", csv_bytes("a,b\n1,\n2,\n"))
    assert table.columns[1].type is ColumnType.text
    assert table.columns[1].nullable is True


def test_a_utf8_bom_is_not_part_of_the_first_header() -> None:
    table = infer_table("f.csv", b"\xef\xbb\xbfname\nada\n")
    assert table.columns[0].name == "name"


def test_samples_skip_blanks_and_stop_at_three() -> None:
    table = infer_table("f.csv", csv_bytes("n\na\n\nb\nc\nd\n"))
    assert table.columns[0].samples == ("a", "b", "c")


def test_a_file_with_no_data_rows_still_yields_its_columns() -> None:
    table = infer_table("f.csv", csv_bytes("a,b\n"))
    assert [c.name for c in table.columns] == ["a", "b"]
    assert table.sampled_rows == 0


def test_a_file_with_no_header_is_rejected() -> None:
    with pytest.raises(ValueError, match="no columns"):
        infer_table("f.csv", b"")


def test_a_number_too_large_for_bigint_falls_back_to_numeric() -> None:
    table = infer_table("f.csv", csv_bytes("n\n" + "9" * 25 + "\n"))
    assert table.columns[0].type is ColumnType.numeric


@pytest.mark.parametrize(
    ("raw", "column_type", "expected"),
    [
        ("42", ColumnType.integer, 42),
        ("10.50", ColumnType.numeric, Decimal("10.50")),
        ("yes", ColumnType.boolean, True),
        ("f", ColumnType.boolean, False),
        ("2024-01-15", ColumnType.date, date(2024, 1, 15)),
        ("2024-01-15 09:30:00", ColumnType.timestamp, datetime(2024, 1, 15, 9, 30)),
        ("hello", ColumnType.text, "hello"),
        ("", ColumnType.integer, None),
        ("   ", ColumnType.text, None),
    ],
)
def test_coerce(raw: str, column_type: ColumnType, expected: object) -> None:
    assert coerce(raw, column_type) == expected


def test_iter_rows_yields_python_values_not_strings() -> None:
    rows = list(
        iter_rows(csv_bytes("a,b\n1,x\n2,\n"), [ColumnType.integer, ColumnType.text])
    )
    assert rows == [(1, "x"), (2, None)]


def test_iter_rows_pads_a_short_row_rather_than_failing() -> None:
    rows = list(iter_rows(csv_bytes("a,b\n1\n"), [ColumnType.integer, ColumnType.text]))
    assert rows == [(1, None)]


def test_iter_rows_drops_cells_beyond_the_declared_columns() -> None:
    rows = list(iter_rows(csv_bytes("a\n1,extra\n"), [ColumnType.integer]))
    assert rows == [(1,)]


def test_iter_rows_keeps_quoted_commas_and_newlines_intact() -> None:
    rows = list(iter_rows(csv_bytes('a\n"one, two\nthree"\n'), [ColumnType.text]))
    assert rows == [("one, two\nthree",)]
