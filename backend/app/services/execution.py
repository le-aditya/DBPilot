"""Run gated SQL and record what happened. PRD F7 step 6, F8.

Every execution writes a `queries` row, including blocked and failed ones.
Blocked attempts are the evidence behind the PRD section 12 zero-writes metric,
so they are never silently dropped — a safety claim you cannot audit is not a
safety claim.
"""

import time
from dataclasses import dataclass

from psycopg import errors as pg_errors
from psycopg import sql
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db import raw
from app.db.readonly import readonly_connection
from app.models import Project, Query, QueryStatus
from app.services.safety import Allowed, Blocked, BlockRule, gate

MAX_ERROR_CHARS = 500


@dataclass(frozen=True)
class ExecutionResult:
    status: QueryStatus
    columns: list[str]
    rows: list[list[object]]
    row_count: int
    duration_ms: int
    executed_sql: str | None
    truncated: bool
    error: str | None
    rule: BlockRule | None
    query_id: int


def _jsonable(value: object) -> object:
    """Decimals, dates, UUIDs and intervals are not JSON. Strings of them are."""
    if value is None or isinstance(value, bool | int | float | str):
        return value
    return str(value)


def _readable(error: Exception) -> str:
    """PostgreSQL's message, without the position noise, capped."""
    text = str(error).split("\n")[0].strip()
    return text[:MAX_ERROR_CHARS]


async def execute_sql(
    session: AsyncSession,
    project: Project,
    *,
    user_id: int,
    sql_text: str,
    question: str | None = None,
    generated_sql: str | None = None,
    was_edited: bool = False,
    allow_full_export: bool = False,
) -> ExecutionResult:
    """Gate `sql_text`, run it read-only if it passes, and log the attempt."""
    settings = get_settings()
    decision = gate(
        sql_text,
        allow_full_export=allow_full_export,
        row_limit=settings.default_row_limit,
    )

    record = Query(
        project_id=project.id,
        user_id=user_id,
        question_text=question,
        generated_sql=generated_sql,
        was_edited=was_edited,
        status=QueryStatus.blocked,
    )

    if isinstance(decision, Blocked):
        record.error_message = decision.detail
        session.add(record)
        await session.flush()
        return ExecutionResult(
            status=QueryStatus.blocked,
            columns=[],
            rows=[],
            row_count=0,
            duration_ms=0,
            executed_sql=None,
            truncated=False,
            error=decision.detail,
            rule=decision.rule,
            query_id=record.id,
        )

    assert isinstance(decision, Allowed)
    record.executed_sql = decision.sql

    started = time.perf_counter()
    try:
        async with readonly_connection(project) as connection:
            result = await raw.fetch_all_with_columns(
                connection, sql.SQL(decision.sql)
            )
        columns, rows = result
    except pg_errors.QueryCanceled as error:
        return await _fail(
            session,
            record,
            started,
            f"That query took longer than {settings.statement_timeout_seconds} "
            "seconds and was stopped. Try adding a filter or a smaller LIMIT.",
            original=error,
        )
    except pg_errors.InsufficientPrivilege as error:
        return await _fail(
            session,
            record,
            started,
            "That query touches data this project cannot read.",
            original=error,
        )
    except Exception as error:  # noqa: BLE001 — every failure becomes a logged row
        return await _fail(session, record, started, _readable(error), original=error)

    duration_ms = int((time.perf_counter() - started) * 1000)
    record.status = QueryStatus.success
    record.row_count = len(rows)
    record.duration_ms = duration_ms
    session.add(record)
    await session.flush()

    return ExecutionResult(
        status=QueryStatus.success,
        columns=columns,
        rows=[[_jsonable(cell) for cell in row] for row in rows],
        row_count=len(rows),
        duration_ms=duration_ms,
        executed_sql=decision.sql,
        truncated=decision.limit_injected and len(rows) >= settings.default_row_limit,
        error=None,
        rule=None,
        query_id=record.id,
    )


async def _fail(
    session: AsyncSession,
    record: Query,
    started: float,
    message: str,
    *,
    original: Exception,
) -> ExecutionResult:
    del original  # kept in the signature so callers cannot lose the cause silently
    duration_ms = int((time.perf_counter() - started) * 1000)
    record.status = QueryStatus.error
    record.error_message = message
    record.duration_ms = duration_ms
    session.add(record)
    await session.flush()
    return ExecutionResult(
        status=QueryStatus.error,
        columns=[],
        rows=[],
        row_count=0,
        duration_ms=duration_ms,
        executed_sql=record.executed_sql,
        truncated=False,
        error=message,
        rule=None,
        query_id=record.id,
    )
