"""Dashboard and history reads. PRD F8, F9, design section 12.

Both lean on the `(project_id, created_at DESC)` index from migration 0002, and
both take `row_count` and `duration_ms` from the stored columns rather than
recomputing them — the denormalisation PRD section 6 asks for, paid for on write
so the dashboard is one pass over one index.
"""

from dataclasses import dataclass, field
from datetime import datetime

from psycopg import sql
from sqlalchemy import Select, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import raw
from app.db.readonly import readonly_connection
from app.models import Project, Query, QueryStatus

SLOWEST_LIMIT = 5
ACTIVITY_LIMIT = 10


@dataclass(frozen=True)
class QuerySummary:
    id: int
    question_text: str | None
    executed_sql: str | None
    status: QueryStatus
    row_count: int | None
    duration_ms: int | None
    was_edited: bool
    error_message: str | None
    created_at: datetime


@dataclass(frozen=True)
class Dashboard:
    table_count: int
    total_rows: int
    storage_bytes: int
    queries_run: int
    queries_this_week: int
    blocked_count: int
    average_duration_ms: int | None
    slowest: list[QuerySummary] = field(default_factory=list)
    recent: list[QuerySummary] = field(default_factory=list)


def _summary(row: Query) -> QuerySummary:
    return QuerySummary(
        id=row.id,
        question_text=row.question_text,
        executed_sql=row.executed_sql,
        status=row.status,
        row_count=row.row_count,
        duration_ms=row.duration_ms,
        was_edited=row.was_edited,
        error_message=row.error_message,
        created_at=row.created_at,
    )


def _for_project(project_id: int) -> Select[tuple[Query]]:
    return select(Query).where(Query.project_id == project_id)


async def list_history(
    session: AsyncSession,
    project_id: int,
    *,
    limit: int = 50,
    offset: int = 0,
    status: QueryStatus | None = None,
) -> tuple[list[QuerySummary], int]:
    """Newest first. Blocked attempts are included — they are the safety record."""
    statement = _for_project(project_id)
    counter = select(func.count()).select_from(Query).where(Query.project_id == project_id)
    if status is not None:
        statement = statement.where(Query.status == status)
        counter = counter.where(Query.status == status)

    rows = await session.scalars(
        statement.order_by(Query.created_at.desc(), Query.id.desc())
        .limit(limit)
        .offset(offset)
    )
    total = await session.scalar(counter) or 0
    return [_summary(row) for row in rows], total


async def _data_size(project: Project) -> tuple[int, int]:
    """Total rows and on-disk bytes for the project's own schema.

    Read through the read-only connection like every other look at user data, so
    there is one path to it rather than a privileged shortcut for statistics.
    """
    if not project.schema_name:
        return 0, 0
    statement = sql.SQL(
        "SELECT coalesce(sum(c.reltuples)::bigint, 0), "
        "       coalesce(sum(pg_total_relation_size(c.oid)), 0) "
        "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = {} AND c.relkind = 'r'"
    ).format(sql.Literal(project.schema_name))
    try:
        async with readonly_connection(project) as connection:
            rows = await raw.fetch_all(connection, statement)
    except Exception:  # noqa: BLE001 — statistics must never break the dashboard
        return 0, 0
    if not rows:
        return 0, 0
    rows_estimate, size = rows[0]
    return max(int(rows_estimate or 0), 0), int(size or 0)


async def build_dashboard(session: AsyncSession, project: Project) -> Dashboard:
    counts = (
        await session.execute(
            select(Query.status, func.count(), func.avg(Query.duration_ms))
            .where(Query.project_id == project.id)
            .group_by(Query.status)
        )
    ).all()

    by_status = {status: (count, average) for status, count, average in counts}
    total = sum(count for count, _ in by_status.values())
    successes = by_status.get(QueryStatus.success, (0, None))
    average = int(successes[1]) if successes[1] is not None else None

    week = await session.scalar(
        select(func.count())
        .select_from(Query)
        .where(
            Query.project_id == project.id,
            Query.created_at >= func.now() - text("interval '7 days'"),
        )
    )

    slowest = await session.scalars(
        _for_project(project.id)
        .where(Query.status == QueryStatus.success, Query.duration_ms.is_not(None))
        .order_by(Query.duration_ms.desc())
        .limit(SLOWEST_LIMIT)
    )
    recent = await session.scalars(
        _for_project(project.id)
        .order_by(Query.created_at.desc(), Query.id.desc())
        .limit(ACTIVITY_LIMIT)
    )

    total_rows, storage_bytes = await _data_size(project)

    return Dashboard(
        table_count=project.table_count or 0,
        total_rows=total_rows,
        storage_bytes=storage_bytes,
        queries_run=total,
        queries_this_week=int(week or 0),
        blocked_count=by_status.get(QueryStatus.blocked, (0, None))[0],
        average_duration_ms=average,
        slowest=[_summary(row) for row in slowest],
        recent=[_summary(row) for row in recent],
    )
