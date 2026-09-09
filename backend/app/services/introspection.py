"""Read a project's schema from the catalog, as `dbpilot_app`.

This runs as the application role, not the project's read-only role, and it is
never reachable from user SQL. That separation is deliberate: it is what lets
the Phase 4 safety gate forbid `information_schema` and `pg_catalog` in user
queries without breaking the explorer or the ER diagram (design section 8).

The output is shared with the Phase 5 ERD, which is why foreign keys are
returned even though Phase 3 only draws badges with them.
"""

from dataclasses import dataclass

from psycopg import sql
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import raw


@dataclass(frozen=True)
class ColumnDescription:
    name: str
    data_type: str
    nullable: bool
    default: str | None
    is_primary_key: bool
    references_table: str | None
    references_column: str | None


@dataclass(frozen=True)
class IndexDescription:
    name: str
    definition: str


@dataclass(frozen=True)
class TableDescription:
    name: str
    row_count: int
    columns: tuple[ColumnDescription, ...]
    indexes: tuple[IndexDescription, ...]


_TABLES = sql.SQL(
    "SELECT table_name FROM information_schema.tables "
    "WHERE table_schema = %s AND table_type = 'BASE TABLE' ORDER BY table_name"
)

_COLUMNS = sql.SQL(
    "SELECT table_name, column_name, data_type, is_nullable, column_default "
    "FROM information_schema.columns WHERE table_schema = %s "
    "ORDER BY table_name, ordinal_position"
)

_KEYS = sql.SQL(
    "SELECT tc.constraint_type, kcu.table_name, kcu.column_name, "
    "       ccu.table_name, ccu.column_name "
    "FROM information_schema.table_constraints tc "
    "JOIN information_schema.key_column_usage kcu "
    "  ON tc.constraint_name = kcu.constraint_name "
    " AND tc.table_schema = kcu.table_schema "
    "LEFT JOIN information_schema.constraint_column_usage ccu "
    "  ON tc.constraint_name = ccu.constraint_name "
    " AND tc.table_schema = ccu.table_schema "
    " AND tc.constraint_type = 'FOREIGN KEY' "
    "WHERE tc.table_schema = %s "
    "  AND tc.constraint_type IN ('PRIMARY KEY', 'FOREIGN KEY')"
)

_INDEXES = sql.SQL(
    "SELECT tablename, indexname, indexdef FROM pg_indexes "
    "WHERE schemaname = %s ORDER BY tablename, indexname"
)


async def _row_counts(session: AsyncSession, schema: str, tables: list[str]) -> dict[str, int]:
    """Exact counts in one round trip.

    `reltuples` would be cheaper but reads -1 until the first ANALYZE, and these
    tables are at most 25 MB, so an exact count is affordable and honest.
    """
    if not tables:
        return {}
    connection = await raw.connection_of(session)
    statement = sql.SQL(" UNION ALL ").join(
        sql.SQL("SELECT {} AS t, count(*) AS n FROM {}.{}").format(
            sql.Literal(table), sql.Identifier(schema), sql.Identifier(table)
        )
        for table in tables
    )
    rows = await raw.fetch_all(connection, statement)
    return {str(name): int(count) for name, count in rows}


async def describe_schema(
    session: AsyncSession, schema: str | None
) -> list[TableDescription]:
    """Every table in `schema`, with columns, keys, indexes and row counts."""
    if not schema:
        return []

    connection = await raw.connection_of(session)
    table_rows = await raw.fetch_all(connection, _TABLES, (schema,))
    tables = [str(row[0]) for row in table_rows]
    if not tables:
        return []

    column_rows = await raw.fetch_all(connection, _COLUMNS, (schema,))
    key_rows = await raw.fetch_all(connection, _KEYS, (schema,))
    index_rows = await raw.fetch_all(connection, _INDEXES, (schema,))
    counts = await _row_counts(session, schema, tables)

    primary_keys: set[tuple[str, str]] = set()
    foreign_keys: dict[tuple[str, str], tuple[str, str]] = {}
    for kind, table, column, ref_table, ref_column in key_rows:
        if kind == "PRIMARY KEY":
            primary_keys.add((table, column))
        elif ref_table is not None:
            foreign_keys[(table, column)] = (ref_table, ref_column)

    indexes: dict[str, list[IndexDescription]] = {}
    for table, name, definition in index_rows:
        indexes.setdefault(str(table), []).append(
            IndexDescription(name=str(name), definition=str(definition))
        )

    columns: dict[str, list[ColumnDescription]] = {}
    for table, name, data_type, is_nullable, default in column_rows:
        reference = foreign_keys.get((table, name))
        columns.setdefault(str(table), []).append(
            ColumnDescription(
                name=str(name),
                data_type=str(data_type),
                nullable=is_nullable == "YES",
                default=default,
                is_primary_key=(table, name) in primary_keys,
                references_table=reference[0] if reference else None,
                references_column=reference[1] if reference else None,
            )
        )

    return [
        TableDescription(
            name=table,
            row_count=counts.get(table, 0),
            columns=tuple(columns.get(table, [])),
            indexes=tuple(indexes.get(table, [])),
        )
        for table in tables
    ]
