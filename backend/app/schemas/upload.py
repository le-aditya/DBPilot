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


class TableProposal(BaseModel):
    name: str
    source_filename: str
    sampled_rows: int
    columns: list[ColumnProposal]


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
