"""What the model must return. These are the contract, not suggestions.

Structured output means the provider validates the shape for us, so the pipeline
never parses prose looking for SQL.
"""

from typing import Literal

from pydantic import BaseModel, Field

Confidence = Literal["high", "medium", "low"]


class GeneratedSQL(BaseModel):
    """PRD F5: the SQL, what was assumed, how sure, and what was missing."""

    sql: str = Field(default="")
    # PRD F5: ambiguity is surfaced as a chip, never buried.
    assumptions: list[str] = Field(default_factory=list)
    confidence: Confidence = "medium"
    # PRD F5: if it cannot answer it must say what is missing, not invent a table.
    missing: str | None = None


class ExplainedClause(BaseModel):
    clause: str
    text: str
    start: int = 0
    end: int = 0


class SQLExplanation(BaseModel):
    summary: str = ""
    clauses: list[ExplainedClause] = Field(default_factory=list)
