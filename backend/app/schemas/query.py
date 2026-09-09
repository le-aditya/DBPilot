"""Execute and query-generation request and response bodies."""

from typing import Any

from pydantic import BaseModel, Field

from app.models import QueryStatus


class ExecuteRequest(BaseModel):
    sql: str = Field(min_length=1)
    question: str | None = None
    generated_sql: str | None = None
    was_edited: bool = False


class ExecuteResponse(BaseModel):
    query_id: int
    status: QueryStatus
    columns: list[str]
    rows: list[list[Any]]
    row_count: int
    duration_ms: int
    executed_sql: str | None
    truncated: bool
    error: str | None
    rule: str | None


class QuestionRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)


class QuestionResponse(BaseModel):
    """PRD F5: the SQL is always shown, and the reasoning is never buried."""

    sql: str
    assumptions: list[str]
    confidence: str
    missing: str | None
    cached: bool
    # None when the model declined to answer, so nothing was run.
    execution: ExecuteResponse | None
