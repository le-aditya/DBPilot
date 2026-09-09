"""ER diagram, layout and explanation response bodies."""

from pydantic import BaseModel, Field

from app.services.erd import Cardinality


class ErdColumnResponse(BaseModel):
    name: str
    data_type: str
    nullable: bool
    is_primary_key: bool
    is_foreign_key: bool


class ErdNodeResponse(BaseModel):
    name: str
    row_count: int
    is_junction: bool
    columns: list[ErdColumnResponse]
    # Where the user last dragged it, when they have.
    x: float | None = None
    y: float | None = None


class ErdEdgeResponse(BaseModel):
    source: str
    target: str
    source_column: str
    target_column: str
    cardinality: Cardinality
    via: str | None


class ErdResponse(BaseModel):
    nodes: list[ErdNodeResponse]
    edges: list[ErdEdgeResponse]


class Position(BaseModel):
    x: float
    y: float


class LayoutRequest(BaseModel):
    node_positions: dict[str, Position] = Field(default_factory=dict)


class LayoutResponse(BaseModel):
    node_positions: dict[str, Position]


class ClauseResponse(BaseModel):
    clause: str
    text: str
    start: int
    end: int


class ExplanationResponse(BaseModel):
    summary: str
    clauses: list[ClauseResponse]


class ExplainRequest(BaseModel):
    sql: str = Field(min_length=1)
