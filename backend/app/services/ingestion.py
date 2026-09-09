"""Commit a reviewed schema: create tables, COPY the rows, record the upload.

Everything runs in the caller's transaction, so a failure part-way leaves no
half-built schema behind (design document section 7). Every identifier is
composed through psycopg.sql.Identifier — CSV headers reach PostgreSQL as
*names*, never as SQL text — and every cell value goes through psycopg's COPY
adapter, so no cell content can break out of its column.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from psycopg import sql
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import UnprocessableError
from app.db import raw
from app.models import Project, Upload
from app.services.inference import ColumnType, iter_rows
from app.services.provisioning import grant_read_only, provision

SURROGATE_KEY = "id"


_PG_TYPE = {
    ColumnType.integer: "BIGINT",
    ColumnType.numeric: "NUMERIC",
    ColumnType.boolean: "BOOLEAN",
    ColumnType.date: "DATE",
    ColumnType.timestamp: "TIMESTAMP",
    ColumnType.text: "TEXT",
}


@dataclass(frozen=True)
class ColumnSpec:
    name: str
    source_name: str
    type: ColumnType
    nullable: bool = True


@dataclass(frozen=True)
class ForeignKeySpec:
    column: str
    references_table: str
    references_column: str


@dataclass(frozen=True)
class TableSpec:
    name: str
    source_filename: str
    columns: tuple[ColumnSpec, ...]
    primary_key: str | None = None
    foreign_keys: tuple[ForeignKeySpec, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class CommittedTable:
    name: str
    row_count: int


def surrogate_name(columns: Sequence[ColumnSpec]) -> str:
    """A name for the generated key that no uploaded column already uses.

    A CSV that already has its own `id` column is common, and silently colliding
    with it would fail the CREATE TABLE. Falling back to a prefixed name keeps
    the user's column intact and still gives the table a key.
    """
    taken = {column.name for column in columns}
    if SURROGATE_KEY not in taken:
        return SURROGATE_KEY
    candidate = f"dbpilot_{SURROGATE_KEY}"
    suffix = 2
    while candidate in taken:
        candidate = f"dbpilot_{SURROGATE_KEY}_{suffix}"
        suffix += 1
    return candidate


def _validate(specs: Sequence[TableSpec], files: Mapping[str, bytes]) -> None:
    """Refuse the whole batch before touching the database if anything is wrong."""
    if not specs:
        raise UnprocessableError("Choose at least one table to import.")

    names = [spec.name for spec in specs]
    duplicates = {name for name in names if names.count(name) > 1}
    if duplicates:
        raise UnprocessableError(
            f"Two tables would be called {sorted(duplicates)[0]!r}. Rename one."
        )

    by_name = {spec.name: spec for spec in specs}
    for spec in specs:
        if not spec.columns:
            raise UnprocessableError(f"{spec.name!r} has no columns.")
        if spec.source_filename not in files:
            raise UnprocessableError(
                f"{spec.name!r} refers to {spec.source_filename!r}, "
                "which was not one of the uploaded files."
            )

        columns = {column.name: column for column in spec.columns}
        if spec.primary_key is not None:
            key = columns.get(spec.primary_key)
            if key is None:
                raise UnprocessableError(
                    f"{spec.name!r} has no column called {spec.primary_key!r} "
                    "to use as its primary key."
                )
            if key.nullable:
                raise UnprocessableError(
                    f"{spec.primary_key!r} has empty values, so it cannot be a "
                    "primary key. Pick another column or add an id column."
                )

        for foreign_key in spec.foreign_keys:
            if foreign_key.column not in columns:
                raise UnprocessableError(
                    f"{spec.name!r} has no column called {foreign_key.column!r}."
                )
            target = by_name.get(foreign_key.references_table)
            if target is None:
                raise UnprocessableError(
                    f"{foreign_key.references_table!r} is not one of the tables "
                    "being imported, so no foreign key can point at it."
                )
            target_columns = {column.name for column in target.columns} | {
                surrogate_name(target.columns)
            }
            if foreign_key.references_column not in target_columns:
                raise UnprocessableError(
                    f"{foreign_key.references_table!r} has no column called "
                    f"{foreign_key.references_column!r}."
                )


def _create_table(schema: str, spec: TableSpec) -> sql.Composed:
    definitions: list[sql.Composable] = []
    if spec.primary_key is None:
        # PRD F2.1: the user may nominate a key, or take a generated surrogate.
        definitions.append(
            sql.SQL("{} BIGSERIAL PRIMARY KEY").format(
                sql.Identifier(surrogate_name(spec.columns))
            )
        )
    for column in spec.columns:
        parts = [sql.Identifier(column.name), sql.SQL(_PG_TYPE[column.type])]
        if column.name == spec.primary_key:
            parts.append(sql.SQL("PRIMARY KEY"))
        elif not column.nullable:
            parts.append(sql.SQL("NOT NULL"))
        definitions.append(sql.SQL(" ").join(parts))

    return sql.SQL("CREATE TABLE {}.{} ({})").format(
        sql.Identifier(schema),
        sql.Identifier(spec.name),
        sql.SQL(", ").join(definitions),
    )


async def _copy_rows(
    session: AsyncSession, schema: str, spec: TableSpec, data: bytes
) -> int:
    connection = await raw.connection_of(session)
    driver = await raw.driver_of(connection)
    statement = sql.SQL("COPY {}.{} ({}) FROM STDIN").format(
        sql.Identifier(schema),
        sql.Identifier(spec.name),
        sql.SQL(", ").join(sql.Identifier(column.name) for column in spec.columns),
    )
    types = [column.type for column in spec.columns]

    written = 0
    async with driver.cursor() as cursor, cursor.copy(statement) as copy:
        for row in iter_rows(data, types):
            await copy.write_row(row)
            written += 1
    return written


async def commit_upload(
    session: AsyncSession,
    project: Project,
    specs: Sequence[TableSpec],
    files: Mapping[str, bytes],
) -> list[CommittedTable]:
    """Create every table, load every row, and record what happened."""
    _validate(specs, files)
    schema, role = await provision(session, project)
    connection = await raw.connection_of(session)

    committed: list[CommittedTable] = []
    for spec in specs:
        await raw.execute(
            connection,
            sql.SQL("DROP TABLE IF EXISTS {}.{} CASCADE").format(
                sql.Identifier(schema), sql.Identifier(spec.name)
            ),
        )
        await raw.execute(connection, _create_table(schema, spec))
        rows = await _copy_rows(session, schema, spec, files[spec.source_filename])
        committed.append(CommittedTable(name=spec.name, row_count=rows))

    # Foreign keys go on after every table exists, so declaration order in the
    # review screen does not constrain what the user can point at.
    for spec in specs:
        for foreign_key in spec.foreign_keys:
            await raw.execute(
                connection,
                sql.SQL(
                    "ALTER TABLE {}.{} ADD FOREIGN KEY ({}) REFERENCES {}.{} ({})"
                ).format(
                    sql.Identifier(schema),
                    sql.Identifier(spec.name),
                    sql.Identifier(foreign_key.column),
                    sql.Identifier(schema),
                    sql.Identifier(foreign_key.references_table),
                    sql.Identifier(foreign_key.references_column),
                ),
            )

    for spec in specs:
        await raw.execute(
            connection,
            sql.SQL("ANALYZE {}.{}").format(
                sql.Identifier(schema), sql.Identifier(spec.name)
            ),
        )

    # GRANT SELECT ON ALL TABLES only covered the tables that existed when
    # provision() ran, so the new ones need it again.
    await grant_read_only(session, schema, role)

    for spec, result in zip(specs, committed, strict=True):
        session.add(
            Upload(
                project_id=project.id,
                original_filename=spec.source_filename,
                table_name=spec.name,
                row_count=result.row_count,
                byte_size=len(files[spec.source_filename]),
            )
        )

    project.table_count = await raw.fetch_value(
        connection,
        sql.SQL(
            "SELECT count(*) FROM information_schema.tables WHERE table_schema = %s"
        ),
        (schema,),
    )
    await session.flush()
    return committed
