import enum

from sqlalchemy import Enum, ForeignKey, Index, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import TimestampedBase


class QueryStatus(str, enum.Enum):
    success = "success"
    error = "error"
    blocked = "blocked"


class Query(TimestampedBase):
    __tablename__ = "queries"
    __table_args__ = (
        # PRD §6 — powers history and the dashboard, the hottest read path.
        Index(
            "ix_queries_project_id_created_at",
            "project_id",
            text("created_at DESC"),
        ),
        # PRD §6 — filtered activity views.
        Index("ix_queries_user_id_status", "user_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("dbpilot.projects.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("dbpilot.users.id", ondelete="CASCADE"), nullable=False
    )
    question_text: Mapped[str | None] = mapped_column(Text)
    generated_sql: Mapped[str | None] = mapped_column(Text)
    executed_sql: Mapped[str | None] = mapped_column(Text)
    was_edited: Mapped[bool] = mapped_column(nullable=False, default=False)
    # Design document §5 — stored, not recomputed, for the dashboard.
    row_count: Mapped[int | None] = mapped_column()
    duration_ms: Mapped[int | None] = mapped_column()
    status: Mapped[QueryStatus] = mapped_column(
        Enum(QueryStatus, name="query_status", schema="dbpilot"), nullable=False
    )
    error_message: Mapped[str | None] = mapped_column(Text)
