"""Request and response bodies for the two-step CSV import."""

from pydantic import BaseModel, Field

from app.services.inference import ColumnType
from app.services.ingestion import ColumnSpec, ForeignKeySpec, TableSpec


class ColumnProposal(BaseModel):
    name: str
    source_name: str
    type: ColumnType
    nullable: bool
    samples: list[str]


class ColumnTypeChange(BaseModel):
    """A column whose inferred type no longer matches what is stored."""

    column: str
    was: str
    now: ColumnType


class TableDiff(BaseModel):
    """What re-uploading this file would change about an existing table.

    `existing` is false for a table this project has never had, in which case
    everything else is empty because there is nothing to compare against.
    """

    existing: bool
    previous_row_count: int | None = None
    previous_columns: list[str] = Field(default_factory=list)
    added_columns: list[str] = Field(default_factory=list)
    removed_columns: list[str] = Field(default_factory=list)
    type_changes: list[ColumnTypeChange] = Field(default_factory=list)
    unchanged: bool = True


class TableProposal(BaseModel):
    name: str
    source_filename: str
    sampled_rows: int
    columns: list[ColumnProposal]
    diff: TableDiff | None = None


class UploadAnalysis(BaseModel):
    """What the review screen renders. Nothing has been created at this point."""

    tables: list[TableProposal]


class ColumnSpecIn(BaseModel):
    name: str = Field(min_length=1, max_length=63)
    source_name: str
    type: ColumnType
    nullable: bool = True

    def to_spec(self) -> ColumnSpec:
        return ColumnSpec(
            name=self.name,
            source_name=self.source_name,
            type=self.type,
            nullable=self.nullable,
        )


class ForeignKeySpecIn(BaseModel):
    column: str
    references_table: str
    references_column: str

    def to_spec(self) -> ForeignKeySpec:
        return ForeignKeySpec(
            column=self.column,
            references_table=self.references_table,
            references_column=self.references_column,
        )


class TableSpecIn(BaseModel):
    name: str = Field(min_length=1, max_length=63)
    source_filename: str
    columns: list[ColumnSpecIn]
    primary_key: str | None = None
    foreign_keys: list[ForeignKeySpecIn] = Field(default_factory=list)

    def to_spec(self) -> TableSpec:
        return TableSpec(
            name=self.name,
            source_filename=self.source_filename,
            columns=tuple(column.to_spec() for column in self.columns),
            primary_key=self.primary_key,
            foreign_keys=tuple(key.to_spec() for key in self.foreign_keys),
        )


class UploadCommit(BaseModel):
    tables: list[TableSpecIn]


class CommittedTableResponse(BaseModel):
    name: str
    row_count: int


class UploadResult(BaseModel):
    schema_name: str
    table_count: int
    tables: list[CommittedTableResponse]
