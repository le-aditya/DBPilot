from typing import Any

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import TimestampedBase


class SavedQuery(TimestampedBase):
    __tablename__ = "saved_queries"
    __table_args__ = (UniqueConstraint("user_id", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    query_id: Mapped[int | None] = mapped_column(
        ForeignKey("dbpilot.queries.id", ondelete="SET NULL")
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("dbpilot.users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    # Design document §11 — SQL with :name placeholders, bound at run time.
    sql_template: Mapped[str] = mapped_column(Text, nullable=False)
    # [{name, type, label, default}]
    parameters: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list
    )
