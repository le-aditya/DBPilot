"""Dashboard, history, saved queries and exports. PRD F8, F9, F10."""

from typing import Annotated

from fastapi import APIRouter, Response, status
from fastapi import Query as QueryParam
from fastapi.responses import StreamingResponse

from app.api.deps import CurrentUser, OwnedProject, SessionDep
from app.core.errors import UnprocessableError
from app.models import QueryStatus
from app.schemas.insights import (
    DashboardResponse,
    HistoryResponse,
    QuerySummaryResponse,
    RunSavedRequest,
    SavedQueryResponse,
    SaveQueryRequest,
)
from app.schemas.query import ExecuteResponse
from app.services.analytics import QuerySummary, build_dashboard, list_history
from app.services.execution import execute_sql
from app.services.export import rows_to_csv, rows_to_json, schema_to_markdown
from app.services.introspection import describe_schema
from app.services.parameters import bind, for_parsing
from app.services.saved import (
    as_parameters,
    delete_saved,
    get_saved,
    list_saved,
    save_query,
)

router = APIRouter(tags=["insights"])
project_router = APIRouter(prefix="/projects/{project_id}", tags=["insights"])

MAX_HISTORY_PAGE = 100
MAX_EXPORT_ROWS = 50_000


def _summary(one: QuerySummary) -> QuerySummaryResponse:
    return QuerySummaryResponse(
        id=one.id,
        question_text=one.question_text,
        executed_sql=one.executed_sql,
        status=one.status,
        row_count=one.row_count,
        duration_ms=one.duration_ms,
        was_edited=one.was_edited,
        error_message=one.error_message,
        created_at=one.created_at,
    )


@project_router.get("/dashboard")
async def dashboard(project: OwnedProject, session: SessionDep) -> DashboardResponse:
    built = await build_dashboard(session, project)
    return DashboardResponse(
        table_count=built.table_count,
        total_rows=built.total_rows,
        storage_bytes=built.storage_bytes,
        queries_run=built.queries_run,
        queries_this_week=built.queries_this_week,
        blocked_count=built.blocked_count,
        average_duration_ms=built.average_duration_ms,
        slowest=[_summary(one) for one in built.slowest],
        recent=[_summary(one) for one in built.recent],
    )


@project_router.get("/history")
async def history(
    project: OwnedProject,
    session: SessionDep,
    limit: Annotated[int, QueryParam(ge=1, le=MAX_HISTORY_PAGE)] = 50,
    offset: Annotated[int, QueryParam(ge=0)] = 0,
    status_filter: QueryStatus | None = None,
) -> HistoryResponse:
    """Every attempt, newest first — blocked ones included (PRD F8)."""
    rows, total = await list_history(
        session, project.id, limit=limit, offset=offset, status=status_filter
    )
    return HistoryResponse(
        queries=[_summary(one) for one in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@project_router.get("/export")
async def export(
    project: OwnedProject,
    user: CurrentUser,
    session: SessionDep,
    format: str = "csv",
    sql: str | None = None,
) -> Response:
    """Results as CSV or JSON, or the schema as Markdown.

    A results export runs through execute_sql like everything else, so the gate
    and the read-only role apply to an export exactly as they do to a query.
    """
    if format == "markdown":
        tables = await describe_schema(session, project.schema_name)
        return Response(
            content=schema_to_markdown(project.name, tables),
            media_type="text/markdown; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="{project.name}-schema.md"'
            },
        )

    if format not in {"csv", "json"}:
        raise UnprocessableError("Choose csv, json or markdown.")
    if not sql:
        raise UnprocessableError("An export needs the SQL to run.")

    result = await execute_sql(
        session,
        project,
        user_id=user.id,
        sql_text=sql,
        allow_full_export=True,
    )
    await session.commit()

    if result.status is not QueryStatus.success:
        raise UnprocessableError(result.error or "That query could not run.")
    if result.row_count > MAX_EXPORT_ROWS:
        raise UnprocessableError(
            f"That is {result.row_count} rows. Add a LIMIT of "
            f"{MAX_EXPORT_ROWS} or fewer to export it."
        )

    if format == "json":
        return Response(
            content=rows_to_json(result.columns, result.rows),
            media_type="application/json",
            headers={"Content-Disposition": 'attachment; filename="results.json"'},
        )

    return StreamingResponse(
        rows_to_csv(result.columns, result.rows),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="results.csv"'},
    )


@router.get("/saved-queries")
async def index(user: CurrentUser, session: SessionDep) -> list[SavedQueryResponse]:
    return [
        SavedQueryResponse.model_validate(one)
        for one in await list_saved(session, user_id=user.id)
    ]


@router.post("/saved-queries", status_code=status.HTTP_201_CREATED)
async def create(
    body: SaveQueryRequest, user: CurrentUser, session: SessionDep
) -> SavedQueryResponse:
    saved = await save_query(
        session,
        user_id=user.id,
        name=body.name,
        sql_template=body.sql_template,
        query_id=body.query_id,
    )
    await session.commit()
    return SavedQueryResponse.model_validate(saved)


@router.delete("/saved-queries/{saved_id}", status_code=status.HTTP_204_NO_CONTENT)
async def destroy(saved_id: int, user: CurrentUser, session: SessionDep) -> Response:
    saved = await get_saved(session, user_id=user.id, saved_id=saved_id)
    await delete_saved(session, saved)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@project_router.post("/saved-queries/{saved_id}/run")
async def run_saved(
    body: RunSavedRequest,
    saved_id: int,
    project: OwnedProject,
    user: CurrentUser,
    session: SessionDep,
) -> ExecuteResponse:
    """Bind the supplied values and run the template.

    Values are bound by psycopg, never interpolated, so a parameter can supply a
    value but never SQL structure. The gate runs on a sentinel copy of the
    template first — see execute_sql's `gate_sql`.
    """
    saved = await get_saved(session, user_id=user.id, saved_id=saved_id)
    parameters = as_parameters(saved.parameters)

    try:
        statement, values = bind(saved.sql_template, parameters, body.values)
    except ValueError as error:
        raise UnprocessableError(str(error)) from error

    result = await execute_sql(
        session,
        project,
        user_id=user.id,
        sql_text=statement,
        question=f"Saved query: {saved.name}",
        parameters=values,
        gate_sql=for_parsing(saved.sql_template, parameters),
    )
    await session.commit()

    return ExecuteResponse(
        query_id=result.query_id,
        status=result.status,
        columns=result.columns,
        rows=result.rows,
        row_count=result.row_count,
        duration_ms=result.duration_ms,
        executed_sql=result.executed_sql,
        truncated=result.truncated,
        error=result.error,
        rule=result.rule.value if result.rule else None,
    )
