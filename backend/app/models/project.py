import enum
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import TimestampedBase

if TYPE_CHECKING:
    from app.models.user import User


class SourceType(str, enum.Enum):
    upload = "upload"
    connection = "connection"


class Project(TimestampedBase):
    __tablename__ = "projects"
    __table_args__ = (UniqueConstraint("user_id", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("dbpilot.users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    source_type: Mapped[SourceType] = mapped_column(
        Enum(SourceType, name="source_type", schema="dbpilot"), nullable=False
    )
    schema_name: Mapped[str | None] = mapped_column(String(63))
    # Design document §5 — recorded, not derived, so deletion can revoke it precisely.
    readonly_role: Mapped[str | None] = mapped_column(String(63))
    is_demo: Mapped[bool] = mapped_column(nullable=False, default=False)
    # Design document §5 — deliberate denormalisation for the dashboard read path.
    table_count: Mapped[int | None] = mapped_column()

    owner: Mapped["User"] = relationship(back_populates="projects")
