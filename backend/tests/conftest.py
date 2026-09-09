import os
import subprocess
import sys
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.config import Settings, get_settings
from app.core.security import hash_password
from app.core.tokens import create_token_pair
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


@pytest_asyncio.fixture(autouse=True)
async def global_engine(migrated_database: Settings) -> AsyncIterator[None]:
    """Point app.db.engine's process-wide engine at the test database.

    Anything that borrows its own connection rather than taking the request
    session — safety layer 3, notably — goes through get_engine(), which is
    built from DATABASE_URL. Without this it would quietly read the development
    database while the fixtures wrote to the test one.
    """
    from app.db import engine as engine_module

    url = migrated_database.test_database_url
    assert url is not None
    engine_module._engine = create_engine(url)
    engine_module._sessionmaker = None
    try:
        yield
    finally:
        await engine_module.dispose_engine()


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
async def live_client(global_engine: None) -> AsyncIterator[AsyncClient]:
    """A client whose sessions are short-lived and really commit.

    The rolled-back `client` cannot be used against a committed schema: its
    transaction stays open for the whole test, holding ACCESS SHARE locks that
    block the DROP SCHEMA in fixture teardown. Requests here behave the way they
    do in production — one session per request, released at the end of it — so
    tests that read genuinely committed data use this instead.
    """
    from app.db.engine import get_sessionmaker

    app = create_app()

    async def _real_session() -> AsyncIterator[AsyncSession]:
        async with get_sessionmaker()() as opened:
            yield opened

    app.dependency_overrides[get_session] = _real_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as opened:
        yield opened
    app.dependency_overrides.clear()


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


@dataclass
class CommittedProject:
    """A project whose schema really exists, visible to other connections.

    The `session` fixture rolls everything back, which is invisible to the
    separate connection safety layer 3 borrows. Anything exercising the
    read-only role therefore needs data that is genuinely committed, and
    genuinely cleaned up afterwards.
    """

    id: int
    user_id: int
    schema_name: str
    readonly_role: str
    headers: dict[str, str]


async def _purge(opened: AsyncSession, email: str) -> None:
    """Remove any leftover user of this email, and everything it owned."""
    from sqlalchemy import select

    from app.services.projects import delete_project

    stale = await opened.scalar(select(User).where(User.email == email))
    if stale is None:
        return
    projects = await opened.scalars(select(Project).where(Project.user_id == stale.id))
    for project in projects:
        await delete_project(opened, project)
    await opened.delete(stale)
    await opened.commit()


async def _make_committed_project(
    url: str, email: str, name: str, files: dict[str, bytes]
) -> tuple[CommittedProject, AsyncEngine]:
    from app.services.inference import infer_table
    from app.services.ingestion import ColumnSpec, TableSpec, commit_upload

    engine = create_engine(url)
    async with AsyncSession(bind=engine, expire_on_commit=False) as opened:
        # A run killed mid-test never reaches its teardown. Clearing the previous
        # occupant keeps one crashed run from failing every later one.
        await _purge(opened, email)
        user = User(email=email, password_hash=hash_password("secret-123"))
        opened.add(user)
        await opened.flush()
        project = Project(user_id=user.id, name=name, source_type=SourceType.upload)
        opened.add(project)
        await opened.flush()

        specs = []
        for filename, data in files.items():
            inferred = infer_table(filename, data)
            specs.append(
                TableSpec(
                    name=inferred.name,
                    source_filename=filename,
                    columns=tuple(
                        ColumnSpec(c.name, c.source_name, c.type, c.nullable)
                        for c in inferred.columns
                    ),
                )
            )
        await commit_upload(opened, project, specs, files)
        await opened.commit()

        return (
            CommittedProject(
                id=project.id,
                user_id=user.id,
                schema_name=project.schema_name or "",
                readonly_role=project.readonly_role or "",
                headers={
                    "Authorization": f"Bearer {create_token_pair(user.id).access_token}"
                },
            ),
            engine,
        )


async def _destroy_committed_project(engine: AsyncEngine, made: CommittedProject) -> None:
    from app.services.projects import delete_project

    async with AsyncSession(bind=engine, expire_on_commit=False) as opened:
        project = await opened.get(Project, made.id)
        if project is not None:
            await delete_project(opened, project)
        user = await opened.get(User, made.user_id)
        if user is not None:
            await opened.delete(user)
        await opened.commit()
    await engine.dispose()


PREVIEW_CSV = b"id,name,amount,shipped\n1,Ada,10.50,true\n2,Grace,20.25,false\n3,Alan,5.00,true\n"


@pytest_asyncio.fixture
async def committed_project(
    migrated_database: Settings,
) -> AsyncIterator[CommittedProject]:
    url = migrated_database.test_database_url
    assert url is not None
    made, engine = await _make_committed_project(
        url, "preview@example.com", "Preview", {"people.csv": PREVIEW_CSV}
    )
    try:
        yield made
    finally:
        await _destroy_committed_project(engine, made)


@pytest_asyncio.fixture
async def other_committed_project(
    migrated_database: Settings,
) -> AsyncIterator[CommittedProject]:
    url = migrated_database.test_database_url
    assert url is not None
    made, engine = await _make_committed_project(
        url, "neighbour@example.com", "Neighbour", {"secrets.csv": b"code\nhunter2\n"}
    )
    try:
        yield made
    finally:
        await _destroy_committed_project(engine, made)
