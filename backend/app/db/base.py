"""Declarative base. Every model inherits the dbpilot schema from here."""

from datetime import datetime

from sqlalchemy import DateTime, MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s",
    "pk": "pk_%(table_name)s",
}

METADATA_SCHEMA = "dbpilot"


class Base(DeclarativeBase):
    metadata = MetaData(schema=METADATA_SCHEMA, naming_convention=NAMING_CONVENTION)


class TimestampedBase(Base):
    """Adds the created_at column that most DBPilot tables carry."""

    __abstract__ = True

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
