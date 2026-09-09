"""Schema-explorer and data-preview response bodies. PRD F3."""

from typing import Any

from pydantic import BaseModel


class SchemaColumn(BaseModel):
    name: str
    data_type: str
    nullable: bool
    default: str | None
    is_primary_key: bool
    references_table: str | None
    references_column: str | None


class SchemaIndex(BaseModel):
    name: str
    definition: str


class SchemaTable(BaseModel):
    name: str
    row_count: int
    columns: list[SchemaColumn]
    indexes: list[SchemaIndex]


class ProjectSchema(BaseModel):
    schema_name: str | None
    tables: list[SchemaTable]


class TablePreview(BaseModel):
    columns: list[str]
    rows: list[list[Any]]
    total: int
    limit: int
    offset: int
