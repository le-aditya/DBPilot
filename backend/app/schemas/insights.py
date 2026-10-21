"""Dashboard, history and saved-query bodies."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import QueryStatus


class QuerySummaryResponse(BaseModel):
    id: int
    question_text: str | None
    executed_sql: str | None
    status: QueryStatus
    row_count: int | None
    duration_ms: int | None
    was_edited: bool
    error_message: str | None
    created_at: datetime


class DashboardResponse(BaseModel):
    table_count: int
    total_rows: int
    storage_bytes: int
    queries_run: int
    queries_this_week: int
    blocked_count: int
    average_duration_ms: int | None
    slowest: list[QuerySummaryResponse]
    recent: list[QuerySummaryResponse]


class HistoryResponse(BaseModel):
    queries: list[QuerySummaryResponse]
    total: int
    limit: int
    offset: int


class SaveQueryRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    sql_template: str = Field(min_length=1)
    query_id: int | None = None

    @field_validator("name")
    @classmethod
    def _reject_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("A saved query needs a name.")
        return stripped


class SavedQueryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    sql_template: str
    parameters: list[dict[str, Any]]
    query_id: int | None
    created_at: datetime


class UpdateSavedQueryRequest(BaseModel):
    """Both fields are optional: a rename and a SQL edit are separate actions."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    sql_template: str | None = Field(default=None, min_length=1)

    @field_validator("name")
    @classmethod
    def _reject_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("A saved query needs a name.")
        return stripped


class SavedQueryVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    revision: int
    sql_template: str
    parameters: list[dict[str, Any]]
    created_at: datetime


class RunSavedRequest(BaseModel):
    values: dict[str, Any] = Field(default_factory=dict)
