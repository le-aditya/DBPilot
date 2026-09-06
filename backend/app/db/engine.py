"""Async engine construction. One engine per process, disposed on shutdown."""

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings
from app.core.platform import configure_event_loop_policy

# Must run before any loop is created. Every async database consumer — the app,
# the tests, and alembic — reaches PostgreSQL through this module, so doing it
# here covers all three without each having to remember.
configure_event_loop_policy()

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def create_engine(url: str) -> AsyncEngine:
    """Build an engine. Separate from get_engine so tests can point elsewhere."""
    return create_async_engine(
        url,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
        echo=False,
    )


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = create_engine(get_settings().database_url)
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(
            bind=get_engine(), expire_on_commit=False, autoflush=False
        )
    return _sessionmaker


async def dispose_engine() -> None:
    """Release pooled connections. Called from the app lifespan shutdown."""
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None
