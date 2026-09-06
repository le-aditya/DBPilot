from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.config import Settings, get_settings
from app.db.engine import create_engine


@pytest.fixture(scope="session")
def settings() -> Settings:
    resolved = get_settings()
    if not resolved.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured")
    return resolved


@pytest_asyncio.fixture
async def engine(settings: Settings) -> AsyncIterator[AsyncEngine]:
    assert settings.test_database_url is not None
    created = create_engine(settings.test_database_url)
    try:
        yield created
    finally:
        await created.dispose()


@pytest_asyncio.fixture
async def session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """A session whose work is always rolled back, so tests never leak rows."""
    async with engine.connect() as connection:
        transaction = await connection.begin()
        async with AsyncSession(bind=connection, expire_on_commit=False) as opened:
            yield opened
        await transaction.rollback()
