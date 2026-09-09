"""CSV sampling and the type ladder. Pure — no database, no filesystem.

Keeping this free of I/O is what makes the type rules exhaustively testable, and
it is why the review screen can show a proposal without anything being created.
"""

import csv
import enum
import io
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import PurePosixPath

from app.services.identifiers import normalise, unique_names

SAMPLE_ROWS = 1000
SAMPLE_VALUES = 3  # what the review screen shows per column

_TRUE = frozenset({"true", "t", "yes", "y", "1"})
_FALSE = frozenset({"false", "f", "no", "n", "0"})

_BIGINT_MIN = -(2**63)
_BIGINT_MAX = 2**63 - 1


class ColumnType(enum.StrEnum):
    integer = "integer"
    numeric = "numeric"
    boolean = "boolean"
    date = "date"
    timestamp = "timestamp"
    text = "text"


# Design document section 7: first match wins, checked in this order. `integer`
# precedes `boolean` on purpose, so a column of 1s and 0s stays a number.
LADDER = (
    ColumnType.integer,
    ColumnType.numeric,
    ColumnType.boolean,
    ColumnType.date,
    ColumnType.timestamp,
)


@dataclass(frozen=True)
class InferredColumn:
    name: str
    source_name: str
    type: ColumnType
    nullable: bool
    samples: tuple[str, ...]


@dataclass(frozen=True)
class InferredTable:
    name: str
    source_filename: str
    columns: tuple[InferredColumn, ...]
    sampled_rows: int


def _decode(data: bytes) -> str:
    """Decode a CSV that may carry a BOM and may not be UTF-8 at all.

    latin-1 cannot fail, so a spreadsheet exported on a Windows machine gives a
    slightly wrong character rather than a failed import.
    """
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("latin-1")


def _reader(data: bytes) -> csv.reader:
    return csv.reader(io.StringIO(_decode(data), newline=""))


def _is_blank(value: str) -> bool:
    return not value.strip()


def _as_integer(value: str) -> int | None:
    try:
        parsed = int(value.strip())
    except ValueError:
        return None
    return parsed if _BIGINT_MIN <= parsed <= _BIGINT_MAX else None


def _as_numeric(value: str) -> Decimal | None:
    try:
        parsed = Decimal(value.strip())
    except (InvalidOperation, ValueError):
        return None
    # NaN and Infinity parse as Decimal but are not what a spreadsheet meant.
    return parsed if parsed.is_finite() else None


def _as_boolean(value: str) -> bool | None:
    lowered = value.strip().lower()
    if lowered in _TRUE:
        return True
    if lowered in _FALSE:
        return False
    return None


def _as_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return None


def _as_timestamp(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.strip())
    except ValueError:
        return None


_PARSERS = {
    ColumnType.integer: _as_integer,
    ColumnType.numeric: _as_numeric,
    ColumnType.boolean: _as_boolean,
    ColumnType.date: _as_date,
    ColumnType.timestamp: _as_timestamp,
}


def coerce(value: str, column_type: ColumnType) -> object | None:
    """Parse one cell into the Python value psycopg will send to PostgreSQL.

    A blank cell is absent, whatever the column type. Anything the type cannot
    parse also comes back as None; callers only reach that path for a type the
    user overrode by hand, and a NULL is friendlier than a failed import.
    """
    if _is_blank(value):
        return None
    if column_type is ColumnType.text:
        return value
    return _PARSERS[column_type](value)


def _infer_type(values: Sequence[str]) -> ColumnType:
    """The first ladder rung every non-blank sampled value satisfies."""
    present = [value for value in values if not _is_blank(value)]
    if not present:
        return ColumnType.text
    for candidate in LADDER:
        parser = _PARSERS[candidate]
        if all(parser(value) is not None for value in present):
            return candidate
    return ColumnType.text


def infer_table(filename: str, data: bytes) -> InferredTable:
    """Read the header and up to SAMPLE_ROWS data rows, and propose a schema."""
    rows = _reader(data)
    try:
        header = next(rows)
    except StopIteration:
        raise ValueError(f"{filename} has no columns.") from None
    if not header:
        raise ValueError(f"{filename} has no columns.")

    width = len(header)
    columns: list[list[str]] = [[] for _ in range(width)]
    sampled = 0
    for row in rows:
        if not row:
            continue
        for index in range(width):
            columns[index].append(row[index] if index < len(row) else "")
        sampled += 1
        if sampled >= SAMPLE_ROWS:
            break

    names = unique_names(header)
    return InferredTable(
        name=normalise(PurePosixPath(filename).stem),
        source_filename=filename,
        sampled_rows=sampled,
        columns=tuple(
            InferredColumn(
                name=name,
                source_name=source,
                type=_infer_type(values),
                nullable=any(_is_blank(value) for value in values) or not values,
                samples=tuple(
                    value for value in values if not _is_blank(value)
                )[:SAMPLE_VALUES],
            )
            for name, source, values in zip(names, header, columns, strict=True)
        ),
    )


def iter_rows(
    data: bytes, types: Sequence[ColumnType]
) -> Iterator[tuple[object | None, ...]]:
    """Yield every data row coerced to Python values, header skipped.

    Ragged rows are padded and truncated rather than raising: one malformed line
    in the middle of a 100k-row export should not lose the other 99,999.
    """
    rows = _reader(data)
    next(rows, None)  # header
    width = len(types)
    for row in rows:
        if not row:
            continue
        yield tuple(
            coerce(row[index] if index < len(row) else "", types[index])
            for index in range(width)
        )
