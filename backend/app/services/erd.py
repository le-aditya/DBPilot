"""Turn an introspected schema into an ER diagram. PRD F4, design section 8.

Pure: it takes the same TableDescription list the schema explorer renders and
returns nodes and edges. No database, no drawing — the layout and the pixels are
the frontend's job, which is what lets cardinality detection be tested exactly.

Cardinality follows the keys, not the data:

- A foreign key whose referencing columns are unique is 1:1, because the
  database will not permit a second row pointing at the same parent.
- Otherwise it is 1:N.
- A table whose columns are covered entirely by exactly two foreign keys, plus
  an optional surrogate key, is a junction table: it exists to join its two
  parents, so the diagram draws one N:M edge between them instead of two 1:N
  edges through a box that means nothing to the reader.
"""

import enum
from collections.abc import Sequence
from dataclasses import dataclass

from app.services.introspection import ColumnDescription, TableDescription


class Cardinality(enum.StrEnum):
    one_to_one = "1:1"
    one_to_many = "1:N"
    many_to_many = "N:M"


@dataclass(frozen=True)
class ErdColumn:
    name: str
    data_type: str
    nullable: bool
    is_primary_key: bool
    is_foreign_key: bool


@dataclass(frozen=True)
class ErdNode:
    name: str
    row_count: int
    columns: tuple[ErdColumn, ...]
    # A junction table is still returned, so the explorer and the diagram agree
    # about what exists; the diagram just draws it differently.
    is_junction: bool


@dataclass(frozen=True)
class ErdEdge:
    source: str
    target: str
    source_column: str
    target_column: str
    cardinality: Cardinality
    # Set when this edge replaces two edges through a junction table, so the UI
    # can explain where an N:M line came from.
    via: str | None = None


@dataclass(frozen=True)
class Erd:
    nodes: tuple[ErdNode, ...]
    edges: tuple[ErdEdge, ...]


def _unique_columns(table: TableDescription) -> set[frozenset[str]]:
    """Column sets the database guarantees are unique, from PK and unique indexes."""
    unique: set[frozenset[str]] = set()
    keys = {column.name for column in table.columns if column.is_primary_key}
    if keys:
        unique.add(frozenset(keys))
    for index in table.indexes:
        definition = index.definition.upper()
        if "UNIQUE INDEX" not in definition:
            continue
        inside = index.definition[index.definition.find("(") + 1 : index.definition.rfind(")")]
        names = {part.strip().strip('"').split(" ")[0] for part in inside.split(",")}
        if names:
            unique.add(frozenset(names))
    return unique


def _foreign_keys(table: TableDescription) -> list[ColumnDescription]:
    return [column for column in table.columns if column.references_table]


def _is_junction(table: TableDescription) -> bool:
    """Does this table exist only to join two others?"""
    keys = _foreign_keys(table)
    if len(keys) != 2:
        return False
    if keys[0].references_table == keys[1].references_table:
        return False  # a self-join table is a real entity, not a crossing
    covered = {column.name for column in keys}
    surrogate = {
        column.name
        for column in table.columns
        if column.is_primary_key and column.name not in covered
    }
    remaining = {column.name for column in table.columns} - covered - surrogate
    return not remaining


def _cardinality(table: TableDescription, column: ColumnDescription) -> Cardinality:
    if frozenset({column.name}) in _unique_columns(table):
        return Cardinality.one_to_one
    return Cardinality.one_to_many


def build_erd(tables: Sequence[TableDescription]) -> Erd:
    """Nodes and edges for `tables`, with junction tables collapsed to N:M."""
    junctions = {table.name for table in tables if _is_junction(table)}

    nodes = tuple(
        ErdNode(
            name=table.name,
            row_count=table.row_count,
            is_junction=table.name in junctions,
            columns=tuple(
                ErdColumn(
                    name=column.name,
                    data_type=column.data_type,
                    nullable=column.nullable,
                    is_primary_key=column.is_primary_key,
                    is_foreign_key=column.references_table is not None,
                )
                for column in table.columns
            ),
        )
        for table in tables
    )

    edges: list[ErdEdge] = []
    known = {table.name for table in tables}
    for table in tables:
        if table.name in junctions:
            left, right = _foreign_keys(table)
            if left.references_table in known and right.references_table in known:
                edges.append(
                    ErdEdge(
                        source=str(left.references_table),
                        target=str(right.references_table),
                        source_column=str(left.references_column),
                        target_column=str(right.references_column),
                        cardinality=Cardinality.many_to_many,
                        via=table.name,
                    )
                )
            continue

        for column in _foreign_keys(table):
            if column.references_table not in known:
                continue
            edges.append(
                ErdEdge(
                    source=table.name,
                    target=str(column.references_table),
                    source_column=column.name,
                    target_column=str(column.references_column),
                    cardinality=_cardinality(table, column),
                )
            )

    return Erd(nodes=nodes, edges=tuple(edges))
