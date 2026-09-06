"""Liveness and readiness. Readiness means PostgreSQL actually answered."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session

router = APIRouter(tags=["health"])

VERSION = "0.1.0"


@router.get("/health")
async def health(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, object]:
    try:
        await session.execute(text("select 1"))
        database_ok = True
    except SQLAlchemyError:
        database_ok = False

    return {
        "status": "ok" if database_ok else "degraded",
        "database": database_ok,
        "version": VERSION,
    }
