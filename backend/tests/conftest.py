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
from app.core.security import hash_password
from app.db.engine import create_engine
from app.db.session import get_session
from app.main import create_app
from app.models import Project, SourceType, User

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


@pytest_asyncio.fixture
async def user(session: AsyncSession) -> User:
    """A persisted user, for services that take a model rather than a request."""
    created = User(email="ada@example.com", password_hash=hash_password("secret-123"))
    session.add(created)
    await session.flush()
    return created


@pytest_asyncio.fixture
async def project(session: AsyncSession, user: User) -> Project:
    created = Project(user_id=user.id, name="Sales", source_type=SourceType.upload)
    session.add(created)
    await session.flush()
    return created


async def register(client: AsyncClient, email: str) -> dict[str, str]:
    """Register `email` and return the bearer header for the new session."""
    response = await client.post(
        "/auth/register", json={"email": email, "password": "a-good-password"}
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest_asyncio.fixture
async def auth_headers(client: AsyncClient) -> dict[str, str]:
    return await register(client, "ada@example.com")


@pytest_asyncio.fixture
async def other_headers(client: AsyncClient) -> dict[str, str]:
    return await register(client, "grace@example.com")


@pytest_asyncio.fixture
async def api_project(client: AsyncClient, auth_headers: dict[str, str]) -> dict:
    response = await client.post(
        "/projects", json={"name": "Sales", "source_type": "upload"}, headers=auth_headers
    )
    return response.json()
