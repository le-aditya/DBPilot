import os
import subprocess
import sys
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.config import Settings, get_settings
from app.db.engine import create_engine
from app.db.session import get_session
from app.main import create_app

BACKEND = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def settings() -> Settings:
    resolved = get_settings()
    if not resolved.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured")
    return resolved


@pytest.fixture(scope="session")
def migrated_database(settings: Settings) -> Settings:
    """Bring the test database to head before any integration test touches it.

    Without this, tests that assert on schema objects depend on the alphabetical
    order pytest happens to collect them in.
    """
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        env={**os.environ, "DATABASE_URL": settings.test_database_url or ""},
    )
    if result.returncode != 0:
        pytest.fail(f"Could not migrate the test database:\n{result.stderr}")
    return settings


@pytest_asyncio.fixture
async def engine(migrated_database: Settings) -> AsyncIterator[AsyncEngine]:
    url = migrated_database.test_database_url
    assert url is not None
    created = create_engine(url)
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


@pytest_asyncio.fixture
async def client(session: AsyncSession) -> AsyncIterator[AsyncClient]:
    """An API client bound to the test session, so requests roll back.

    The session is joined to an outer transaction the `session` fixture rolls
    back, so a handler calling session.commit() still leaves no rows behind.
    """
    app = create_app()

    async def _use_test_session() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_session] = _use_test_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as opened:
        yield opened
    app.dependency_overrides.clear()
