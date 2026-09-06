"""The request-scoped session dependency."""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_sessionmaker


async def get_session() -> AsyncIterator[AsyncSession]:
    """Yield a session, committing on success and rolling back on error."""
    async with get_sessionmaker()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
