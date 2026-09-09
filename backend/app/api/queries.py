"""Query execution. PRD section 7.

Nothing here decides what is safe: it calls the gate and reports what the gate
said. Keeping the decision in one pure function is what makes it testable and
what stops a second, subtly different rule set growing in the API layer.
"""

from fastapi import APIRouter
from psycopg import sql

from app.ai.pipeline import SchemaTooLarge, generate_sql
from app.ai.prompts import SAMPLE_ROWS as PROMPT_SAMPLE_ROWS
from app.ai.provider import ProviderUnavailable
from app.api.deps import CurrentUser, OwnedProject, SessionDep
from app.api.deps_ai import get_provider
from app.core.errors import ServiceUnavailableError, UnprocessableError
from app.db import raw
from app.db.readonly import readonly_connection
from app.models import Project
from app.schemas.query import (
    ExecuteRequest,
    ExecuteResponse,
    QuestionRequest,
    QuestionResponse,
)
from app.services.execution import execute_sql
from app.services.introspection import TableDescription, describe_schema

router = APIRouter(prefix="/projects/{project_id}", tags=["queries"])


@router.post("/execute")
async def execute(
    body: ExecuteRequest,
    project: OwnedProject,
    user: CurrentUser,
    session: SessionDep,
) -> ExecuteResponse:
    """Run SQL against the project, read-only, and record the attempt.

    A blocked statement is a 200 carrying status="blocked", not an HTTP error:
    it is a normal, expected outcome the workspace renders inline next to the
    SQL, and PRD F8 requires it in history either way.
    """
    if project.schema_name is None:
        raise UnprocessableError(
            "This project has no data yet. Upload a CSV before running a query."
        )

    result = await execute_sql(
        session,
        project,
        user_id=user.id,
        sql_text=body.sql,
        question=body.question,
        generated_sql=body.generated_sql,
        was_edited=body.was_edited,
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


async def _sample_rows(
    project: Project, tables: list[TableDescription]
) -> dict[str, list[list[object]]]:
    """A few rows per table, read through the same read-only path as everything else."""
    samples: dict[str, list[list[object]]] = {}
    if not tables:
        return samples
    async with readonly_connection(project) as connection:
        for table in tables:
            statement = sql.SQL("SELECT * FROM {} LIMIT {}").format(
                sql.Identifier(table.name), sql.Literal(PROMPT_SAMPLE_ROWS)
            )
            try:
                rows = await raw.fetch_all(connection, statement)
            except Exception:  # noqa: BLE001 — samples are a nicety, never a blocker
                continue
            samples[table.name] = [list(row) for row in rows]
    return samples


@router.post("/query")
async def ask(
    body: QuestionRequest,
    project: OwnedProject,
    user: CurrentUser,
    session: SessionDep,
) -> QuestionResponse:
    """Turn a question into SQL, then run it through the same gate as everything else.

    The generated SQL goes through execute_sql, not a private path. That is the
    point of building the gate first: there is no route from the model to the
    database that skips it.
    """
    if project.schema_name is None:
        raise UnprocessableError(
            "This project has no data yet. Upload a CSV before asking a question."
        )

    try:
        provider = get_provider()
        tables = await describe_schema(session, project.schema_name)
        samples = await _sample_rows(project, tables)
        generation = await generate_sql(
            provider, question=body.question, tables=tables, samples=samples
        )
    except ProviderUnavailable as error:
        # PRD section 13: degrade to a usable editor, never take the page down.
        # The fallback is named here rather than left to the client, so the user
        # is told what still works at the moment the thing they tried failed.
        raise ServiceUnavailableError(
            f"{error} You can still write and run SQL yourself in the editor."
        ) from error
    except SchemaTooLarge as error:
        raise UnprocessableError(str(error)) from error

    answer = generation.result
    if not answer.sql.strip():
        return QuestionResponse(
            sql="",
            assumptions=answer.assumptions,
            confidence=answer.confidence,
            missing=answer.missing or "The model could not answer that from this schema.",
            cached=generation.cached,
            execution=None,
        )

    result = await execute_sql(
        session,
        project,
        user_id=user.id,
        sql_text=answer.sql,
        question=body.question,
        generated_sql=answer.sql,
        was_edited=False,
    )
    await session.commit()

    return QuestionResponse(
        sql=answer.sql,
        assumptions=answer.assumptions,
        confidence=answer.confidence,
        missing=answer.missing,
        cached=generation.cached,
        execution=ExecuteResponse(
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
        ),
    )
