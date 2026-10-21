from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SavedQueryVersion(Base):
    """One dated snapshot of a saved query's SQL.

    Saving over a query replaces its template, which would otherwise destroy the
    only record of what it used to say. Each edit appends a revision instead, so
    the history screen can show what actually changed between two runs.
    """

    __tablename__ = "saved_query_versions"
    __table_args__ = (UniqueConstraint("saved_query_id", "revision"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    saved_query_id: Mapped[int] = mapped_column(
        ForeignKey("dbpilot.saved_queries.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    sql_template: Mapped[str] = mapped_column(Text, nullable=False)
    # [{name, type, label, default}] — parameters can change with the SQL, so a
    # revision stores the binding it expects rather than reading today's list.
    parameters: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
