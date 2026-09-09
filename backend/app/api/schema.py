"""Schema explorer and data preview. PRD F3.

The preview is the first thing in DBPilot that runs a query against user data,
so it already goes through safety layer 3 — a read-only, role-scoped, rolled-back
transaction — one phase before the gate that Phase 4 adds on top.
"""

from typing import Annotated

from fastapi import APIRouter, Query
from psycopg import sql

from app.api.deps import OwnedProject, SessionDep
from app.core.errors import NotFoundError, UnprocessableError
from app.db import raw
from app.db.readonly import readonly_connection
from app.schemas.schema import (
    ProjectSchema,
    SchemaColumn,
    SchemaIndex,
    SchemaTable,
    TablePreview,
)
from app.services.introspection import TableDescription, describe_schema

router = APIRouter(prefix="/projects/{project_id}", tags=["schema"])

MAX_PREVIEW_ROWS = 100  # PRD F3: "first 100 rows, paginated"


@router.get("/schema")
async def show_schema(project: OwnedProject, session: SessionDep) -> ProjectSchema:
    described = await describe_schema(session, project.schema_name)
    return ProjectSchema(
        schema_name=project.schema_name,
        tables=[
            SchemaTable(
                name=table.name,
                row_count=table.row_count,
                columns=[
                    SchemaColumn(
                        name=column.name,
                        data_type=column.data_type,
                        nullable=column.nullable,
                        default=column.default,
                        is_primary_key=column.is_primary_key,
                        references_table=column.references_table,
                        references_column=column.references_column,
                    )
                    for column in table.columns
                ],
                indexes=[
                    SchemaIndex(name=index.name, definition=index.definition)
                    for index in table.indexes
                ],
            )
            for table in described
        ],
    )


def _find(described: list[TableDescription], table: str) -> TableDescription:
    for candidate in described:
        if candidate.name == table:
            return candidate
    raise NotFoundError(f"This project has no table called {table!r}.")


@router.get("/tables/{table}/preview")
async def preview(
    project: OwnedProject,
    session: SessionDep,
    table: str,
    limit: Annotated[int, Query(ge=1)] = MAX_PREVIEW_ROWS,
    offset: Annotated[int, Query(ge=0)] = 0,
    sort: str | None = None,
    direction: str = "asc",
) -> TablePreview:
    """First rows of one table, paginated and sortable.

    The table and sort column are matched against the introspected schema before
    anything is composed, so the query string chooses from a list this server
    built — it never supplies an identifier of its own.
    """
    described = _find(await describe_schema(session, project.schema_name), table)
    columns = [column.name for column in described.columns]

    if sort is not None and sort not in columns:
        raise UnprocessableError(f"{table!r} has no column called {sort!r} to sort by.")
    if direction.lower() not in {"asc", "desc"}:
        raise UnprocessableError("Sort direction must be 'asc' or 'desc'.")

    schema_id = sql.Identifier(project.schema_name or "")
    table_id = sql.Identifier(table)
    statement = sql.SQL("SELECT {} FROM {}.{}").format(
        sql.SQL(", ").join(sql.Identifier(name) for name in columns),
        schema_id,
        table_id,
    )
    if sort is not None:
        statement = sql.SQL("{} ORDER BY {} {}").format(
            statement,
            sql.Identifier(sort),
            sql.SQL("DESC" if direction.lower() == "desc" else "ASC"),
        )
    statement = sql.SQL("{} LIMIT {} OFFSET {}").format(
        statement,
        sql.Literal(min(limit, MAX_PREVIEW_ROWS)),
        sql.Literal(offset),
    )

    async with readonly_connection(project) as connection:
        rows = await raw.fetch_all(connection, statement)

    return TablePreview(
        columns=columns,
        rows=[[_jsonable(value) for value in row] for row in rows],
        total=described.row_count,
        limit=min(limit, MAX_PREVIEW_ROWS),
        offset=offset,
    )


def _jsonable(value: object) -> object:
    """Decimals, dates and times are not JSON. Strings of them are."""
    if value is None or isinstance(value, bool | int | float | str):
        return value
    return str(value)
