# DBPilot Phase 1 — Scaffold Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up a running DBPilot skeleton — a FastAPI backend whose `/health` endpoint proves a live PostgreSQL connection, the complete application data model under Alembic migrations, and a Vite frontend rendering the PRD design tokens — with CI green.

**Architecture:** A monorepo with `backend/` (FastAPI + SQLAlchemy 2.x async + psycopg3) and `frontend/` (React + Vite + Tailwind v4). Application metadata lives in a dedicated `dbpilot` PostgreSQL schema, kept separate from the per-project `user_<id>_<project>` schemas that later phases create. Migrations are split so the performance indexes land in their own revision and can be benchmarked before and after.

**Tech Stack:** Python 3.11.9, FastAPI, SQLAlchemy 2.x (async), psycopg 3, Alembic, Pydantic v2 + pydantic-settings, pytest + pytest-asyncio, PostgreSQL 18.6, React 19 + TypeScript + Vite, Tailwind CSS v4, Vitest.

**Spec:** `docs/superpowers/specs/2026-09-06-dbpilot-design.md`

## Global Constraints

- Python runtime is **3.11.9** exactly (`py -3.11`). The machine default 3.14 must not be used.
- PostgreSQL driver is **psycopg 3** (`postgresql+psycopg://`), never psycopg2.
- Application metadata lives in PostgreSQL schema **`dbpilot`**. Never `public`.
- Passwords hash with **bcrypt cost ≥ 12** (Phase 2 consumes this; the dependency is pinned here).
- Use the **`bcrypt` package directly**, never `passlib` — passlib's bcrypt backend is broken against bcrypt ≥ 4.1.
- No secret value is ever committed. `.env` is gitignored; `.env.example` carries placeholder values only.
- Design tokens are exactly PRD §10.2. No component may write a raw hex value.
- Every module past ~300 lines is a signal to split.
- Every commit message ends with the two attribution lines shown in Task 1, Step 6.

---

## File Structure

**Backend**

| File | Responsibility |
|---|---|
| `backend/pyproject.toml` | Dependencies, pytest/ruff/mypy config |
| `backend/app/core/config.py` | `Settings` loaded from env; single source of configuration |
| `backend/app/core/errors.py` | `AppError` hierarchy and the JSON error envelope |
| `backend/app/db/base.py` | `Base` declarative class carrying the `dbpilot` schema and naming convention |
| `backend/app/db/engine.py` | Async engine and sessionmaker construction |
| `backend/app/db/session.py` | `get_session` FastAPI dependency |
| `backend/app/models/*.py` | One module per aggregate, per spec §4 |
| `backend/app/api/health.py` | `/health` router |
| `backend/app/main.py` | App factory, middleware, exception handlers |
| `backend/alembic/env.py` | Async migration environment wired to `Settings` |
| `backend/alembic/versions/0001_initial.py` | Tables, constraints, enums |
| `backend/alembic/versions/0002_performance_indexes.py` | PRD §6 indexes, isolated for benchmarking |
| `backend/tests/conftest.py` | Test settings, engine, and transactional session fixtures |

**Frontend**

| File | Responsibility |
|---|---|
| `frontend/src/styles/tokens.css` | PRD §10.2 tokens as the Tailwind v4 `@theme` |
| `frontend/src/components/Eyebrow.tsx` | Section eyebrow per PRD §10.3 (lime dot + tracked caps) |
| `frontend/src/components/SplitHeadline.tsx` | The PRD §10.3 signature white/gray headline |
| `frontend/src/routes/Tokens.tsx` | Visual proof sheet for the token system |
| `frontend/src/App.tsx` | Router shell |

**Repo root**

| File | Responsibility |
|---|---|
| `scripts/bootstrap.sql` | Idempotent cluster setup (databases, app role) |
| `.github/workflows/ci.yml` | Lint, type-check, backend tests, frontend build |

---

### Task 1: Repository skeleton and database bootstrap

**Files:**
- Create: `.gitignore`, `README.md`, `scripts/bootstrap.sql`

**Interfaces:**
- Consumes: nothing
- Produces: databases `dbpilot` and `dbpilot_test`, login role `dbpilot_app` with `CREATEROLE`, schema `dbpilot` in both databases. Every later task connects as `dbpilot_app`.

- [ ] **Step 1: Initialise the repository**

```bash
cd /d/Projects/DBQuery
git init -b main
```

- [ ] **Step 2: Write `.gitignore`**

```gitignore
# Python
__pycache__/
*.py[cod]
.venv/
.pytest_cache/
.mypy_cache/
.ruff_cache/
.coverage
htmlcov/

# Node
node_modules/
dist/
.vite/

# Secrets and local config
.env
.env.local
*.pem

# OS / editor
.DS_Store
Thumbs.db
.idea/
.vscode/
```

- [ ] **Step 3: Write `scripts/bootstrap.sql`**

Idempotent so it can be re-run after a reset. Replace `change_me_now` with the real password before running.

```sql
-- DBPilot cluster bootstrap. Run as the postgres superuser:
--   psql -U postgres -h localhost -f scripts/bootstrap.sql

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dbpilot_app') THEN
    CREATE ROLE dbpilot_app WITH LOGIN PASSWORD 'change_me_now' CREATEROLE CREATEDB;
  END IF;
END
$$;

SELECT 'CREATE DATABASE dbpilot OWNER dbpilot_app'
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'dbpilot')\gexec

SELECT 'CREATE DATABASE dbpilot_test OWNER dbpilot_app'
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'dbpilot_test')\gexec

\c dbpilot
CREATE SCHEMA IF NOT EXISTS dbpilot AUTHORIZATION dbpilot_app;
REVOKE ALL ON SCHEMA public FROM PUBLIC;

\c dbpilot_test
CREATE SCHEMA IF NOT EXISTS dbpilot AUTHORIZATION dbpilot_app;
REVOKE ALL ON SCHEMA public FROM PUBLIC;
```

- [ ] **Step 4: Run the bootstrap and verify both databases answer**

Run:
```bash
psql -U postgres -h localhost -f scripts/bootstrap.sql
psql "postgresql://dbpilot_app:<password>@localhost:5432/dbpilot" -c "select current_user, current_database();"
psql "postgresql://dbpilot_app:<password>@localhost:5432/dbpilot_test" -c "select nspname from pg_namespace where nspname='dbpilot';"
```
Expected: first prints `dbpilot_app | dbpilot`; second prints one row `dbpilot`.

- [ ] **Step 5: Write `README.md`**

```markdown
# DBPilot

AI-powered database explorer and query assistant. Connect or upload a database,
see it as an ER diagram, and query it in plain English — the generated SQL is
always shown, always explained, and never allowed to write.

## Status

Phase 1 — scaffold. See `docs/superpowers/plans/` for the build plan.

## Requirements

- Python 3.11
- Node 20+
- PostgreSQL 15 or newer

## Setup

```bash
psql -U postgres -h localhost -f scripts/bootstrap.sql

cd backend
py -3.11 -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"
cp .env.example .env    # then fill in the real values
.venv/Scripts/alembic upgrade head
.venv/Scripts/uvicorn app.main:app --reload

cd ../frontend
npm install
npm run dev
```

## Layout

- `backend/` — FastAPI application, migrations, tests
- `frontend/` — React + Vite client
- `docs/` — design document, plans, normalisation write-up, benchmarks
- `scripts/` — cluster bootstrap and demo seeding
```

- [ ] **Step 6: Commit**

```bash
git add .gitignore README.md scripts/bootstrap.sql docs/
git commit -m "chore: initialise repository with database bootstrap

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Cqgmb8EqhP1PTeqJPA8wHF"
```

---

### Task 2: Backend package and test harness

**Files:**
- Create: `backend/pyproject.toml`, `backend/app/__init__.py`, `backend/tests/__init__.py`, `backend/tests/test_smoke.py`

**Interfaces:**
- Consumes: Task 1's repository
- Produces: an importable `app` package, a working `pytest` command, and the `.venv` every later task uses at `backend/.venv/Scripts/python`.

- [ ] **Step 1: Write `backend/pyproject.toml`**

```toml
[project]
name = "dbpilot"
version = "0.1.0"
description = "AI-powered database explorer and query assistant"
requires-python = ">=3.11,<3.12"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.32",
    "sqlalchemy[asyncio]>=2.0.36",
    "psycopg[binary,pool]>=3.2",
    "alembic>=1.14",
    "pydantic>=2.9",
    "pydantic-settings>=2.6",
    "python-jose[cryptography]>=3.3",
    "bcrypt>=4.2",
    "cryptography>=43.0",
    "sqlglot>=25.0",
    "python-multipart>=0.0.12",
    "google-genai>=0.3",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.3",
    "pytest-asyncio>=0.24",
    "pytest-cov>=6.0",
    "httpx>=0.27",
    "ruff>=0.8",
    "mypy>=1.13",
]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
include = ["app*"]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "function"
markers = [
    "integration: requires a live PostgreSQL connection",
]

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM"]

[tool.mypy]
python_version = "3.11"
plugins = ["pydantic.mypy"]
warn_unused_ignores = true
disallow_untyped_defs = true
```

- [ ] **Step 2: Create the package markers and a smoke test**

`backend/app/__init__.py` and `backend/tests/__init__.py` are both empty files.

`backend/tests/test_smoke.py`:
```python
def test_app_package_imports() -> None:
    import app

    assert app is not None
```

- [ ] **Step 3: Create the virtualenv and install**

Run:
```bash
cd /d/Projects/DBQuery/backend
py -3.11 -m venv .venv
.venv/Scripts/python -m pip install --upgrade pip
.venv/Scripts/python -m pip install -e ".[dev]"
```
Expected: install completes; `.venv/Scripts/python -c "import fastapi, sqlalchemy, psycopg, sqlglot; print('ok')"` prints `ok`.

- [ ] **Step 4: Run the smoke test**

Run: `cd /d/Projects/DBQuery/backend && .venv/Scripts/python -m pytest tests/test_smoke.py -v`
Expected: PASS, 1 test.

- [ ] **Step 5: Commit**

```bash
git add backend/pyproject.toml backend/app/__init__.py backend/tests/
git commit -m "chore(backend): add package layout, dependencies and test harness

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Cqgmb8EqhP1PTeqJPA8wHF"
```

---

### Task 3: Configuration module

**Files:**
- Create: `backend/app/core/__init__.py`, `backend/app/core/config.py`, `backend/.env.example`
- Test: `backend/tests/test_config.py`

**Interfaces:**
- Consumes: Task 2's package
- Produces:
  - `Settings` — pydantic-settings model with fields `database_url: str`, `test_database_url: str | None`, `metadata_schema: str`, `jwt_secret: str`, `jwt_algorithm: str`, `access_token_ttl_minutes: int`, `refresh_token_ttl_days: int`, `bcrypt_rounds: int`, `encryption_key: str`, `gemini_api_key: str | None`, `gemini_model: str`, `statement_timeout_seconds: int`, `ai_timeout_seconds: int`, `max_upload_bytes: int`, `default_row_limit: int`, `cors_origins: list[str]`
  - `get_settings() -> Settings` — cached accessor used by every module

- [ ] **Step 1: Write the failing test**

`backend/tests/test_config.py`:
Settings are populated from environment variables, so the tests drive them the
same way. `_env_file=None` stops the developer's real `.env` from leaking into
the assertions.

```python
import pytest

from app.core.config import Settings

REQUIRED = {
    "DATABASE_URL": "postgresql+psycopg://u:p@localhost:5432/dbpilot",
    "JWT_SECRET": "test-secret",
    "DBPILOT_ENCRYPTION_KEY": "test-fernet-key",
}


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    for key, value in REQUIRED.items():
        monkeypatch.setenv(key, value)
    return monkeypatch


def test_settings_read_required_values_from_env(env: pytest.MonkeyPatch) -> None:
    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.database_url == "postgresql+psycopg://u:p@localhost:5432/dbpilot"
    assert settings.jwt_secret == "test-secret"
    assert settings.encryption_key == "test-fernet-key"


def test_settings_apply_prd_defaults(env: pytest.MonkeyPatch) -> None:
    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.metadata_schema == "dbpilot"
    assert settings.access_token_ttl_minutes == 30
    assert settings.refresh_token_ttl_days == 7
    assert settings.bcrypt_rounds >= 12
    assert settings.statement_timeout_seconds == 10
    assert settings.ai_timeout_seconds == 30
    assert settings.max_upload_bytes == 25 * 1024 * 1024
    assert settings.default_row_limit == 1000


def test_settings_reject_psycopg2_driver(env: pytest.MonkeyPatch) -> None:
    env.setenv("DATABASE_URL", "postgresql+psycopg2://u:p@localhost:5432/d")

    with pytest.raises(ValueError, match="psycopg"):
        Settings(_env_file=None)  # type: ignore[call-arg]


def test_settings_reject_a_weak_bcrypt_cost(env: pytest.MonkeyPatch) -> None:
    env.setenv("BCRYPT_ROUNDS", "8")

    with pytest.raises(ValueError, match="at least 12"):
        Settings(_env_file=None)  # type: ignore[call-arg]


def test_settings_require_a_secret(env: pytest.MonkeyPatch) -> None:
    env.delenv("JWT_SECRET")

    with pytest.raises(ValueError):
        Settings(_env_file=None)  # type: ignore[call-arg]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /d/Projects/DBQuery/backend && .venv/Scripts/python -m pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.core'`

- [ ] **Step 3: Write the implementation**

`backend/app/core/__init__.py` is an empty file.

`backend/app/core/config.py`:
```python
"""Application configuration, loaded once from the environment."""

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Every tunable value in DBPilot. Nothing reads os.environ directly."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    database_url: str
    test_database_url: str | None = None
    metadata_schema: str = "dbpilot"

    # Auth — PRD F1
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 30
    refresh_token_ttl_days: int = 7
    bcrypt_rounds: int = 12

    # Credential encryption — PRD F2.2.
    # The field name maps to DBPILOT_ENCRYPTION_KEY case-insensitively, so no
    # alias is needed; `encryption_key` below is the name the rest of the app uses.
    dbpilot_encryption_key: str

    # AI — PRD F5
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.0-flash"

    # Limits — PRD §9
    statement_timeout_seconds: int = 10
    ai_timeout_seconds: int = 30
    max_upload_bytes: int = 25 * 1024 * 1024
    default_row_limit: int = 1000

    cors_origins: list[str] = ["http://localhost:5173"]

    @property
    def encryption_key(self) -> str:
        return self.dbpilot_encryption_key

    @field_validator("database_url", "test_database_url")
    @classmethod
    def _require_psycopg3(cls, value: str | None) -> str | None:
        """psycopg2 cannot drive the async engine; catch the mistake at startup."""
        if value is not None and "psycopg2" in value:
            raise ValueError(
                "DBPilot requires the psycopg 3 driver: use postgresql+psycopg://"
            )
        return value

    @field_validator("bcrypt_rounds")
    @classmethod
    def _enforce_cost_floor(cls, value: int) -> int:
        if value < 12:
            raise ValueError("PRD F1 requires a bcrypt cost of at least 12")
        return value


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance. Call this, never Settings() directly."""
    return Settings()  # type: ignore[call-arg]
```

- [ ] **Step 4: Write `backend/.env.example`**

Placeholders only — this file is committed.

```dotenv
# Copy to .env and fill in. .env is gitignored and must never be committed.
DATABASE_URL=postgresql+psycopg://dbpilot_app:CHANGE_ME@localhost:5432/dbpilot
TEST_DATABASE_URL=postgresql+psycopg://dbpilot_app:CHANGE_ME@localhost:5432/dbpilot_test

# openssl rand -hex 32
JWT_SECRET=CHANGE_ME

# python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
DBPILOT_ENCRYPTION_KEY=CHANGE_ME

GEMINI_API_KEY=CHANGE_ME
GEMINI_MODEL=gemini-2.0-flash
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd /d/Projects/DBQuery/backend && .venv/Scripts/python -m pytest tests/test_config.py -v`
Expected: PASS, 6 tests.

- [ ] **Step 6: Create the real `.env`**

Run:
```bash
cd /d/Projects/DBQuery/backend
cp .env.example .env
.venv/Scripts/python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```
Then edit `.env`: set both URLs to the real `dbpilot_app` password, paste the generated Fernet key into `DBPILOT_ENCRYPTION_KEY`, set `JWT_SECRET` to a fresh random hex string, and paste the user's Gemini key.

Verify: `.venv/Scripts/python -c "from app.core.config import get_settings; print(get_settings().metadata_schema)"` prints `dbpilot`.

- [ ] **Step 7: Commit**

`.env` must NOT appear in the commit — confirm with `git status` first.

```bash
git add backend/app/core/ backend/.env.example backend/tests/test_config.py
git commit -m "feat(config): add settings module with PRD limits and driver guard

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Cqgmb8EqhP1PTeqJPA8wHF"
```

---

### Task 4: Async database engine and session

**Files:**
- Create: `backend/app/db/__init__.py`, `backend/app/db/engine.py`, `backend/app/db/session.py`
- Test: `backend/tests/conftest.py`, `backend/tests/test_engine.py`

**Interfaces:**
- Consumes: `get_settings()` from Task 3
- Produces:
  - `create_engine(url: str) -> AsyncEngine`
  - `get_engine() -> AsyncEngine` — process-wide cached engine
  - `get_sessionmaker() -> async_sessionmaker[AsyncSession]`
  - `get_session() -> AsyncIterator[AsyncSession]` — the FastAPI dependency every router uses
  - `dispose_engine() -> None` — called on app shutdown
  - Fixtures `settings`, `engine`, `session` in `conftest.py`

- [ ] **Step 1: Write the failing test**

`backend/tests/conftest.py`:
```python
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
```

`backend/tests/test_engine.py`:
```python
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration


async def test_session_reaches_postgres(session: AsyncSession) -> None:
    result = await session.execute(text("select 1"))

    assert result.scalar_one() == 1


async def test_session_connects_as_the_app_role(session: AsyncSession) -> None:
    result = await session.execute(text("select current_user"))

    assert result.scalar_one() == "dbpilot_app"


async def test_metadata_schema_exists(session: AsyncSession) -> None:
    result = await session.execute(
        text("select nspname from pg_namespace where nspname = 'dbpilot'")
    )

    assert result.scalar_one_or_none() == "dbpilot"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /d/Projects/DBQuery/backend && .venv/Scripts/python -m pytest tests/test_engine.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.db'`

- [ ] **Step 3: Write the implementation**

`backend/app/db/__init__.py` is an empty file.

`backend/app/db/engine.py`:
```python
"""Async engine construction. One engine per process, disposed on shutdown."""

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings

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
```

`backend/app/db/session.py`:
```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /d/Projects/DBQuery/backend && .venv/Scripts/python -m pytest tests/test_engine.py -v`
Expected: PASS, 3 tests. A failure here means `.env` has the wrong password — fix `.env`, not the code.

- [ ] **Step 5: Commit**

```bash
git add backend/app/db/ backend/tests/conftest.py backend/tests/test_engine.py
git commit -m "feat(db): add async engine, sessionmaker and session dependency

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Cqgmb8EqhP1PTeqJPA8wHF"
```

---

### Task 5: Application data model

**Files:**
- Create: `backend/app/db/base.py`, `backend/app/models/__init__.py`, `backend/app/models/user.py`, `backend/app/models/project.py`, `backend/app/models/connection.py`, `backend/app/models/upload.py`, `backend/app/models/query.py`, `backend/app/models/explanation.py`, `backend/app/models/saved_query.py`, `backend/app/models/diagram_layout.py`
- Test: `backend/tests/test_models.py`

**Interfaces:**
- Consumes: nothing from earlier tasks (pure declarative model definitions)
- Produces: `Base` with `Base.metadata` scoped to schema `dbpilot`, and model classes `User`, `Project`, `Connection`, `Upload`, `Query`, `Explanation`, `SavedQuery`, `DiagramLayout`, plus enums `SourceType` (`upload`, `connection`) and `QueryStatus` (`success`, `error`, `blocked`). Task 6 autogenerates migrations from `Base.metadata`.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_models.py`:
```python
from app.db.base import Base
from app.models import (  # noqa: F401  (import registers the mappers)
    Connection,
    DiagramLayout,
    Explanation,
    Project,
    Query,
    SavedQuery,
    Upload,
    User,
)

EXPECTED_TABLES = {
    "users",
    "projects",
    "connections",
    "uploads",
    "queries",
    "explanations",
    "saved_queries",
    "diagram_layouts",
}


def test_every_prd_table_is_mapped() -> None:
    assert set(Base.metadata.tables) == {f"dbpilot.{name}" for name in EXPECTED_TABLES}


def test_all_tables_live_in_the_dbpilot_schema() -> None:
    for table in Base.metadata.tables.values():
        assert table.schema == "dbpilot", f"{table.name} escaped the dbpilot schema"


def test_projects_are_unique_per_user_and_name() -> None:
    table = Base.metadata.tables["dbpilot.projects"]
    unique_column_sets = {
        tuple(sorted(c.name for c in constraint.columns))
        for constraint in table.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }

    assert ("name", "user_id") in unique_column_sets


def test_saved_queries_carry_a_template_and_parameters() -> None:
    """Design doc §11 — parameterised saved queries are v1 scope."""
    table = Base.metadata.tables["dbpilot.saved_queries"]

    assert "sql_template" in table.columns
    assert "parameters" in table.columns
    assert table.columns["sql_template"].nullable is False


def test_projects_track_their_readonly_role() -> None:
    """Design doc §16 — role cleanup on delete must not guess the role name."""
    table = Base.metadata.tables["dbpilot.projects"]

    assert "readonly_role" in table.columns
    assert "is_demo" in table.columns


def test_queries_records_the_denormalised_dashboard_columns() -> None:
    """Design doc §5 — stored rather than recomputed, a documented trade-off."""
    table = Base.metadata.tables["dbpilot.queries"]

    assert "row_count" in table.columns
    assert "duration_ms" in table.columns
    assert table.columns["status"].nullable is False
```

Note the models declare **no** indexes at this point. Task 7 adds them, so that
`0001` and `0002` are separable and the dashboard can be benchmarked against
each — design document §5.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /d/Projects/DBQuery/backend && .venv/Scripts/python -m pytest tests/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.db.base'`

- [ ] **Step 3: Write `backend/app/db/base.py`**

```python
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
```

- [ ] **Step 4: Write the model modules**

`backend/app/models/user.py`:
```python
from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import TimestampedBase


class User(TimestampedBase):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(60), nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    projects: Mapped[list["Project"]] = relationship(  # noqa: F821
        back_populates="owner", cascade="all, delete-orphan"
    )
```

`backend/app/models/project.py`:
```python
import enum

from sqlalchemy import Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import TimestampedBase


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
    # Design doc §5 — recorded, not derived, so deletion can revoke it precisely.
    readonly_role: Mapped[str | None] = mapped_column(String(63))
    is_demo: Mapped[bool] = mapped_column(nullable=False, default=False)
    # Design doc §5 — deliberate denormalisation for the dashboard read path.
    table_count: Mapped[int | None] = mapped_column()

    owner: Mapped["User"] = relationship(back_populates="projects")  # noqa: F821
```

`backend/app/models/connection.py`:
```python
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import TimestampedBase


class Connection(TimestampedBase):
    __tablename__ = "connections"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("dbpilot.projects.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    port: Mapped[int] = mapped_column(nullable=False, default=5432)
    database_name: Mapped[str] = mapped_column(String(63), nullable=False)
    username: Mapped[str] = mapped_column(String(63), nullable=False)
    # Fernet ciphertext. Never a plaintext password. Design doc §6.
    password_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    ssl_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="prefer")
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
```

`backend/app/models/upload.py`:
```python
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Upload(Base):
    __tablename__ = "uploads"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("dbpilot.projects.id", ondelete="CASCADE"), nullable=False
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    table_name: Mapped[str] = mapped_column(String(63), nullable=False)
    row_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
```

`backend/app/models/query.py`:
```python
import enum

from sqlalchemy import Enum, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import TimestampedBase


class QueryStatus(str, enum.Enum):
    success = "success"
    error = "error"
    blocked = "blocked"


class Query(TimestampedBase):
    __tablename__ = "queries"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("dbpilot.projects.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("dbpilot.users.id", ondelete="CASCADE"), nullable=False
    )
    question_text: Mapped[str | None] = mapped_column(Text)
    generated_sql: Mapped[str | None] = mapped_column(Text)
    executed_sql: Mapped[str | None] = mapped_column(Text)
    was_edited: Mapped[bool] = mapped_column(nullable=False, default=False)
    # Design doc §5 — stored, not recomputed, for the dashboard.
    row_count: Mapped[int | None] = mapped_column()
    duration_ms: Mapped[int | None] = mapped_column()
    status: Mapped[QueryStatus] = mapped_column(
        Enum(QueryStatus, name="query_status", schema="dbpilot"), nullable=False
    )
    error_message: Mapped[str | None] = mapped_column(Text)
```

`backend/app/models/explanation.py`:
```python
from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import TimestampedBase


class Explanation(TimestampedBase):
    __tablename__ = "explanations"

    id: Mapped[int] = mapped_column(primary_key=True)
    query_id: Mapped[int] = mapped_column(
        ForeignKey("dbpilot.queries.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    summary: Mapped[str | None] = mapped_column(Text)
    clause_breakdown: Mapped[list[dict]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    optimization_notes: Mapped[list[dict]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    model_version: Mapped[str | None] = mapped_column(String(64))
```

`backend/app/models/saved_query.py`:
```python
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
    # Design doc §11 — SQL with :name placeholders, bound at run time.
    sql_template: Mapped[str] = mapped_column(Text, nullable=False)
    # [{name, type, label, default}]
    parameters: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list)
```

`backend/app/models/diagram_layout.py`:
```python
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DiagramLayout(Base):
    __tablename__ = "diagram_layouts"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("dbpilot.projects.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    # {table_name: {x: float, y: float}}
    node_positions: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
```

`backend/app/models/__init__.py`:
```python
"""Importing this package registers every mapper with Base.metadata."""

from app.models.connection import Connection
from app.models.diagram_layout import DiagramLayout
from app.models.explanation import Explanation
from app.models.project import Project, SourceType
from app.models.query import Query, QueryStatus
from app.models.saved_query import SavedQuery
from app.models.upload import Upload
from app.models.user import User

__all__ = [
    "Connection",
    "DiagramLayout",
    "Explanation",
    "Project",
    "Query",
    "QueryStatus",
    "SavedQuery",
    "SourceType",
    "Upload",
    "User",
]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd /d/Projects/DBQuery/backend && .venv/Scripts/python -m pytest tests/test_models.py -v`
Expected: PASS, 6 tests.

- [ ] **Step 6: Commit**

```bash
git add backend/app/db/base.py backend/app/models/ backend/tests/test_models.py
git commit -m "feat(models): add the PRD section 6 data model in the dbpilot schema

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Cqgmb8EqhP1PTeqJPA8wHF"
```

---

### Task 6: Alembic and the initial migration

**Files:**
- Create: `backend/alembic.ini`, `backend/alembic/env.py`, `backend/alembic/script.py.mako`, `backend/alembic/versions/0001_initial.py`
- Test: `backend/tests/test_migrations.py`

**Interfaces:**
- Consumes: `Base.metadata` from Task 5, `get_settings()` from Task 3
- Produces: revision `0001_initial` creating schema `dbpilot`, both enum types, and all eight tables. Task 7 chains from `down_revision = "0001_initial"`.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_migrations.py`:
```python
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
pytestmark = pytest.mark.integration


def _alembic(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        env=_test_env(),
    )


def _test_env() -> dict[str, str]:
    import os

    from app.core.config import get_settings

    settings = get_settings()
    assert settings.test_database_url is not None
    return {**os.environ, "DATABASE_URL": settings.test_database_url}


def test_upgrade_head_then_downgrade_base_round_trips() -> None:
    up = _alembic("upgrade", "head")
    assert up.returncode == 0, up.stderr

    down = _alembic("downgrade", "base")
    assert down.returncode == 0, down.stderr

    again = _alembic("upgrade", "head")
    assert again.returncode == 0, again.stderr


def test_migrations_match_the_models() -> None:
    """An empty autogenerate diff proves 0001 and the models agree."""
    _alembic("upgrade", "head")
    check = _alembic("check")

    assert check.returncode == 0, (
        "Models and migrations have drifted:\n" + check.stdout + check.stderr
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /d/Projects/DBQuery/backend && .venv/Scripts/python -m pytest tests/test_migrations.py -v`
Expected: FAIL — alembic reports no `alembic.ini` found.

- [ ] **Step 3: Scaffold Alembic with the async template**

Run:
```bash
cd /d/Projects/DBQuery/backend
.venv/Scripts/alembic init -t async alembic
```
This writes `alembic.ini`, `alembic/env.py`, `alembic/script.py.mako`, and `alembic/versions/`.

- [ ] **Step 4: Point `alembic.ini` at nothing and use a readable revision format**

Edit `backend/alembic.ini` — set `sqlalchemy.url` to empty (the URL comes from `Settings`, so it is never written to a committed file) and add the filename template:

```ini
sqlalchemy.url =
file_template = %%(rev)s_%%(slug)s
```

- [ ] **Step 5: Replace `backend/alembic/env.py`**

```python
"""Alembic environment. The URL and schema come from Settings, never alembic.ini."""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.engine import Connection

from app.core.config import get_settings
from app.db.base import METADATA_SCHEMA, Base
from app.db.engine import create_engine
from app.models import *  # noqa: F401,F403  (registers every mapper)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _url() -> str:
    return get_settings().database_url


def _configure(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_schemas=True,
        version_table_schema=METADATA_SCHEMA,
        compare_type=True,
        compare_server_default=True,
    )


def run_migrations_offline() -> None:
    context.configure(
        url=_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        include_schemas=True,
        version_table_schema=METADATA_SCHEMA,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_run(connection: Connection) -> None:
    _configure(connection)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_engine(_url())
    async with engine.connect() as connection:
        await connection.run_sync(_do_run)
        await connection.commit()
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
```

- [ ] **Step 6: Generate the initial revision**

Run:
```bash
cd /d/Projects/DBQuery/backend
.venv/Scripts/alembic revision --autogenerate -m "initial"
```
Then rename the generated file to `backend/alembic/versions/0001_initial.py` and set `revision = "0001_initial"` and `down_revision = None` inside it.

- [ ] **Step 7: Add schema and enum handling to `0001_initial`**

Autogenerate does not create the schema itself, and it leaves enum creation implicit. Edit the revision so `upgrade()` opens with the schema and `downgrade()` closes by removing the enums:

```python
def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS dbpilot")
    # ... autogenerated op.create_table(...) calls follow, unchanged ...


def downgrade() -> None:
    # ... autogenerated op.drop_table(...) calls first, unchanged ...
    sa.Enum(name="query_status", schema="dbpilot").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="source_type", schema="dbpilot").drop(op.get_bind(), checkfirst=True)
```

- [ ] **Step 8: Run test to verify it passes**

Run: `cd /d/Projects/DBQuery/backend && .venv/Scripts/python -m pytest tests/test_migrations.py -v`
Expected: PASS, 2 tests. If `alembic check` reports a diff, the models and the revision disagree — fix the revision to match the models.

- [ ] **Step 9: Apply to the development database**

Run:
```bash
cd /d/Projects/DBQuery/backend
.venv/Scripts/alembic upgrade head
psql "postgresql://dbpilot_app:<password>@localhost:5432/dbpilot" -c "\dt dbpilot.*"
```
Expected: nine rows — the eight model tables plus `alembic_version`.

- [ ] **Step 10: Commit**

```bash
git add backend/alembic.ini backend/alembic/ backend/tests/test_migrations.py
git commit -m "feat(db): add alembic with the initial schema migration

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Cqgmb8EqhP1PTeqJPA8wHF"
```

---

### Task 7: Performance index migration

**Files:**
- Create: `backend/alembic/versions/0002_performance_indexes.py`
- Test: `backend/tests/test_indexes.py`

**Interfaces:**
- Consumes: revision `0001_initial` from Task 6
- Produces: `Index` declarations on the `Query` and `Project` models, and revision `0002_performance_indexes` creating the three composite/single-column indexes from PRD §6 (the fourth, `users(email)`, is already unique-indexed by Task 5). Phase 6's benchmark measures the dashboard query at `0001` and at `0002`.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_indexes.py`:
```python
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration

EXPECTED = {
    "ix_queries_project_id_created_at",
    "ix_queries_user_id_status",
    "ix_projects_user_id",
}


async def test_prd_indexes_exist_after_migration(session: AsyncSession) -> None:
    result = await session.execute(
        text("select indexname from pg_indexes where schemaname = 'dbpilot'")
    )
    present = {row[0] for row in result}

    assert EXPECTED <= present, f"missing: {EXPECTED - present}"


async def test_users_email_is_unique_indexed(session: AsyncSession) -> None:
    """PRD section 6 names users(email) unique as the login lookup path."""
    result = await session.execute(
        text(
            "select indexdef from pg_indexes "
            "where schemaname = 'dbpilot' and tablename = 'users'"
        )
    )
    definitions = " ".join(row[0] for row in result)

    assert "UNIQUE" in definitions
    assert "email" in definitions
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /d/Projects/DBQuery/backend && .venv/Scripts/python -m pytest tests/test_indexes.py -v`
Expected: FAIL on `test_prd_indexes_exist_after_migration` — the three indexes are missing.

- [ ] **Step 3: Declare the indexes on the models**

The indexes must exist on the models, not only in the migration — otherwise
`alembic check` (Task 6) sees the database holding indexes the models do not
declare and reports drift. Declaring them here, one revision after `0001`, is
what keeps both revisions separable *and* the drift check honest.

Add to `backend/app/models/query.py` — the import line becomes
`from sqlalchemy import Enum, ForeignKey, Index, Text, text` and the class gains
`__table_args__` immediately after `__tablename__`:

```python
class Query(TimestampedBase):
    __tablename__ = "queries"
    __table_args__ = (
        # PRD §6 — powers history and the dashboard, the hottest read path.
        Index(
            "ix_queries_project_id_created_at",
            "project_id",
            text("created_at DESC"),
        ),
        # PRD §6 — filtered activity views.
        Index("ix_queries_user_id_status", "user_id", "status"),
    )
```

Add to `backend/app/models/project.py` — the import line becomes
`from sqlalchemy import Enum, ForeignKey, Index, String, UniqueConstraint` and
the existing `__table_args__` gains a second entry:

```python
    __table_args__ = (
        UniqueConstraint("user_id", "name"),
        # PRD §6 — every request scopes by owner.
        Index("ix_projects_user_id", "user_id"),
    )
```

`users(email)` needs no entry: the `unique=True` in Task 5 already creates a
unique index, which is why the test asserts it but nothing creates it here.

- [ ] **Step 4: Autogenerate the revision**

Run:
```bash
cd /d/Projects/DBQuery/backend
.venv/Scripts/alembic revision --autogenerate -m "performance indexes"
```
Rename the generated file to
`backend/alembic/versions/0002_performance_indexes.py`, set
`revision = "0002_performance_indexes"` and `down_revision = "0001_initial"`,
and replace the docstring with:

```python
"""Performance indexes from PRD section 6.

Deliberately split from 0001 so the dashboard read path can be benchmarked
before and after — see the design document section 5.

Revision ID: 0002_performance_indexes
Revises: 0001_initial
"""
```

The body should contain exactly three `op.create_index` calls in `upgrade()` and
three matching `op.drop_index` calls in `downgrade()`. If autogenerate produced
anything else, the models and `0001` have drifted — fix that before continuing.

- [ ] **Step 5: Apply and run the tests**

Run:
```bash
cd /d/Projects/DBQuery/backend
.venv/Scripts/alembic upgrade head
.venv/Scripts/python -m pytest tests/test_indexes.py tests/test_migrations.py tests/test_models.py -v
```
Expected: PASS, 10 tests. `test_migrations_match_the_models` passing here is the
proof that models, `0001`, and `0002` all agree.

- [ ] **Step 6: Verify the revisions are genuinely separable**

This is what the Phase 6 benchmark depends on.

Run:
```bash
cd /d/Projects/DBQuery/backend
.venv/Scripts/alembic downgrade 0001_initial
psql "postgresql://dbpilot_app:<password>@localhost:5432/dbpilot" \
  -c "select count(*) from pg_indexes where schemaname='dbpilot' and indexname like 'ix_%';"
.venv/Scripts/alembic upgrade head
```
Expected: the count is `0` at `0001_initial`, and `alembic upgrade head` restores
the indexes without error.

- [ ] **Step 7: Commit**

```bash
git add backend/app/models/query.py backend/app/models/project.py \
        backend/alembic/versions/0002_performance_indexes.py backend/tests/test_indexes.py
git commit -m "feat(db): add PRD performance indexes as a separate revision

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Cqgmb8EqhP1PTeqJPA8wHF"
```

---

### Task 8: FastAPI application and health endpoint

**Files:**
- Create: `backend/app/core/errors.py`, `backend/app/api/__init__.py`, `backend/app/api/health.py`, `backend/app/main.py`
- Test: `backend/tests/test_health.py`

**Interfaces:**
- Consumes: `get_session` (Task 4), `dispose_engine` (Task 4), `get_settings` (Task 3)
- Produces:
  - `AppError(message: str, *, status_code: int = 400, code: str = "app_error")` and subclasses `NotFoundError`, `ConflictError`, `UnauthorizedError` — every later phase raises these
  - `create_app() -> FastAPI` — the factory CI and uvicorn both use
  - `app` — the module-level instance for `uvicorn app.main:app`
  - `GET /health` returning `{"status": "ok"|"degraded", "database": bool, "version": str}`

- [ ] **Step 1: Write the failing test**

`backend/tests/test_health.py`:
```python
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import create_app

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as opened:
        yield opened


async def test_health_reports_ok_when_the_database_answers(
    client: AsyncClient,
) -> None:
    response = await client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] is True
    assert body["version"]


async def test_unknown_route_returns_the_error_envelope(client: AsyncClient) -> None:
    response = await client.get("/no-such-route")

    assert response.status_code == 404
    assert "error" in response.json()


async def test_app_error_renders_message_and_code() -> None:
    from app.core.errors import NotFoundError

    error = NotFoundError("Project not found")

    assert error.status_code == 404
    assert error.code == "not_found"
    assert error.message == "Project not found"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /d/Projects/DBQuery/backend && .venv/Scripts/python -m pytest tests/test_health.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.main'`

- [ ] **Step 3: Write `backend/app/core/errors.py`**

```python
"""Application errors. PRD section 9: every failure says what happened."""


class AppError(Exception):
    """Base for errors that map to a JSON response rather than a 500."""

    status_code = 400
    code = "app_error"

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        code: str | None = None,
        detail: dict | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail or {}
        if status_code is not None:
            self.status_code = status_code
        if code is not None:
            self.code = code

    def to_payload(self) -> dict:
        return {"error": {"code": self.code, "message": self.message, **self.detail}}


class NotFoundError(AppError):
    """Also raised for resources the caller does not own, so ownership never leaks."""

    status_code = 404
    code = "not_found"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"


class UnauthorizedError(AppError):
    status_code = 401
    code = "unauthorized"
```

- [ ] **Step 4: Write `backend/app/api/health.py`**

`backend/app/api/__init__.py` is an empty file.

```python
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
```

- [ ] **Step 5: Write `backend/app/main.py`**

```python
"""Application factory, middleware and exception handlers."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import health
from app.core.config import get_settings
from app.core.errors import AppError
from app.db.engine import dispose_engine


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    await dispose_engine()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="DBPilot",
        description="AI-powered database explorer and query assistant",
        version=health.VERSION,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=exc.to_payload())

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": "http_error", "message": str(exc.detail)}},
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(
        _: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "The request body was not valid.",
                    "fields": exc.errors(),
                }
            },
        )

    app.include_router(health.router)
    return app


app = create_app()
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd /d/Projects/DBQuery/backend && .venv/Scripts/python -m pytest tests/test_health.py -v`
Expected: PASS, 3 tests.

- [ ] **Step 7: Verify the server actually starts**

Run:
```bash
cd /d/Projects/DBQuery/backend
.venv/Scripts/uvicorn app.main:app --port 8000 &
sleep 3
curl -s http://localhost:8000/health
```
Expected: `{"status":"ok","database":true,"version":"0.1.0"}`. Stop the server afterwards.

- [ ] **Step 8: Run the whole backend suite and the linters**

Run:
```bash
cd /d/Projects/DBQuery/backend
.venv/Scripts/python -m pytest -v
.venv/Scripts/ruff check app tests
.venv/Scripts/mypy app
```
Expected: all tests pass, ruff clean, mypy clean.

- [ ] **Step 9: Commit**

```bash
git add backend/app/main.py backend/app/api/ backend/app/core/errors.py backend/tests/test_health.py
git commit -m "feat(api): add app factory, error envelope and health endpoint

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Cqgmb8EqhP1PTeqJPA8wHF"
```

---

### Task 9: Frontend scaffold with the PRD design tokens

**Files:**
- Create: `frontend/` via Vite, then `frontend/src/styles/tokens.css`, `frontend/src/components/Eyebrow.tsx`, `frontend/src/components/SplitHeadline.tsx`, `frontend/src/routes/Tokens.tsx`, `frontend/src/App.tsx`, `frontend/vite.config.ts`
- Test: `frontend/src/components/__tests__/design-system.test.tsx`

**Interfaces:**
- Consumes: nothing from the backend
- Produces: `<Eyebrow>{children}</Eyebrow>` and `<SplitHeadline lead="..." trail="..." as="h1" />`, both consumed by every screen in Phases 2–6.

- [ ] **Step 1: Scaffold the Vite app**

Run:
```bash
cd /d/Projects/DBQuery
npm create vite@latest frontend -- --template react-ts
cd frontend
npm install
npm install -D tailwindcss @tailwindcss/vite vitest @vitest/coverage-v8 jsdom \
  @testing-library/react @testing-library/jest-dom
npm install react-router-dom
```

- [ ] **Step 2: Write `frontend/vite.config.ts`**

```typescript
/// <reference types="vitest" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { port: 5173 },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test-setup.ts'],
  },
})
```

`frontend/src/test-setup.ts`:
```typescript
import '@testing-library/jest-dom'
```

- [ ] **Step 3: Write the failing test**

`frontend/src/components/__tests__/design-system.test.tsx`:
```tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { Eyebrow } from '../Eyebrow'
import { SplitHeadline } from '../SplitHeadline'

describe('Eyebrow', () => {
  it('renders its label in uppercase tracking', () => {
    render(<Eyebrow>Schema explorer</Eyebrow>)

    expect(screen.getByText('Schema explorer')).toBeInTheDocument()
  })

  it('carries the lime dot the PRD requires before the label', () => {
    const { container } = render(<Eyebrow>Dashboard</Eyebrow>)

    expect(container.querySelector('[data-accent-dot]')).not.toBeNull()
  })
})

describe('SplitHeadline', () => {
  it('renders the lead clause in primary text and the trail in secondary', () => {
    render(
      <SplitHeadline
        lead="Ask your database a question."
        trail="It answers in SQL you can actually read."
      />,
    )

    expect(screen.getByText('Ask your database a question.')).toHaveClass(
      'text-text-primary',
    )
    expect(
      screen.getByText('It answers in SQL you can actually read.'),
    ).toHaveClass('text-text-secondary')
  })

  it('renders as the requested heading level', () => {
    render(<SplitHeadline as="h2" lead="Lead" trail="Trail" />)

    expect(screen.getByRole('heading', { level: 2 })).toBeInTheDocument()
  })
})
```

- [ ] **Step 4: Run test to verify it fails**

Run: `cd /d/Projects/DBQuery/frontend && npx vitest run`
Expected: FAIL — cannot resolve `../Eyebrow`.

- [ ] **Step 5: Write `frontend/src/styles/tokens.css`**

The PRD §10.2 palette, declared once. Tailwind v4 turns each `--color-*` into a utility, so `text-text-secondary` and `bg-canvas` exist without a config file.

```css
@import 'tailwindcss';

@theme {
  /* PRD 10.2 — the only palette. No component writes a raw hex. */
  --color-canvas: #0a0a0a;
  --color-surface: #141414;
  --color-border: #232323;
  --color-border-hover: #313131;

  --color-text-primary: #ffffff;
  --color-text-secondary: #8a8a8a;
  --color-text-tertiary: #5a5a5a;

  --color-accent: #d4ff3f;
  --color-glow-violet: #4c3bcf;

  --font-sans: 'Inter', ui-sans-serif, system-ui, sans-serif;
  --font-mono: 'JetBrains Mono', ui-monospace, monospace;

  /* PRD 10.3 type scale */
  --text-display: 4rem;
  --text-display--line-height: 0.98;
  --text-display--letter-spacing: -0.02em;
  --text-h2: 2.5rem;
  --text-h2--line-height: 1.05;
  --text-h2--letter-spacing: -0.02em;
  --text-h3: 1.5rem;
  --text-h3--line-height: 1.2;
  --text-body: 1rem;
  --text-body--line-height: 1.6;
  --text-small: 0.875rem;
  --text-small--line-height: 1.5;
  --text-eyebrow: 0.6875rem;
  --text-eyebrow--line-height: 1.2;
  --text-eyebrow--letter-spacing: 0.12em;
}

html {
  color-scheme: dark;
}

body {
  background-color: var(--color-canvas);
  color: var(--color-text-primary);
  font-family: var(--font-sans);
  margin: 0;
}

/* PRD 10.6 — motion is restrained, and optional. */
@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    animation-duration: 0.01ms !important;
    transition-duration: 0.01ms !important;
  }
}
```

- [ ] **Step 6: Write the two components**

`frontend/src/components/Eyebrow.tsx`:
```tsx
import type { ReactNode } from 'react'

interface EyebrowProps {
  children: ReactNode
}

/** PRD 10.3 — a small lime dot, then wide-tracked uppercase in secondary text. */
export function Eyebrow({ children }: EyebrowProps) {
  return (
    <p className="flex items-center gap-2 text-eyebrow uppercase text-text-secondary">
      <span
        data-accent-dot
        aria-hidden="true"
        className="inline-block size-1.5 rounded-full bg-accent"
      />
      {children}
    </p>
  )
}
```

`frontend/src/components/SplitHeadline.tsx`:
```tsx
interface SplitHeadlineProps {
  lead: string
  trail: string
  as?: 'h1' | 'h2' | 'h3'
  className?: string
}

/**
 * PRD 10.3 signature move: one headline split between white and gray, so the
 * gray clause reads as the subordinate thought. Used instead of bold or colour.
 */
export function SplitHeadline({
  lead,
  trail,
  as: Tag = 'h1',
  className = '',
}: SplitHeadlineProps) {
  const size = Tag === 'h1' ? 'text-display' : Tag === 'h2' ? 'text-h2' : 'text-h3'

  return (
    <Tag className={`${size} font-sans ${className}`}>
      <span className="text-text-primary">{lead}</span>{' '}
      <span className="text-text-secondary">{trail}</span>
    </Tag>
  )
}
```

- [ ] **Step 7: Run test to verify it passes**

Run: `cd /d/Projects/DBQuery/frontend && npx vitest run`
Expected: PASS, 4 tests.

- [ ] **Step 8: Write the token proof sheet and wire the app**

`frontend/src/routes/Tokens.tsx` — a page that renders every token so a design regression is visible at a glance:

```tsx
import { Eyebrow } from '../components/Eyebrow'
import { SplitHeadline } from '../components/SplitHeadline'

const SURFACES = [
  { name: '--canvas', className: 'bg-canvas' },
  { name: '--surface', className: 'bg-surface' },
  { name: '--border', className: 'bg-border' },
  { name: '--border-hover', className: 'bg-border-hover' },
  { name: '--accent', className: 'bg-accent' },
  { name: '--glow-violet', className: 'bg-glow-violet' },
]

export function Tokens() {
  return (
    <main className="mx-auto max-w-[1200px] px-6 py-32">
      <Eyebrow>Design system</Eyebrow>

      <div className="mt-8">
        <SplitHeadline
          lead="Ask your database a question."
          trail="It answers in SQL you can actually read."
        />
      </div>

      <section className="mt-32">
        <Eyebrow>Surfaces</Eyebrow>
        <div className="mt-8 grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
          {SURFACES.map((surface) => (
            <div key={surface.name}>
              <div
                className={`${surface.className} h-24 rounded-2xl border border-border`}
              />
              <p className="mt-3 font-mono text-small text-text-tertiary">
                {surface.name}
              </p>
            </div>
          ))}
        </div>
      </section>

      <section className="mt-32">
        <Eyebrow>Type scale</Eyebrow>
        <div className="mt-8 space-y-6">
          <p className="text-h2 text-text-primary">Heading two, 40px</p>
          <p className="text-h3 text-text-primary">Heading three, 24px</p>
          <p className="max-w-[60ch] text-body text-text-secondary">
            Body copy at 16px and 1.6 leading. Secondary text is the floor for
            running copy — it passes 5.3:1 against the canvas, so it stays
            readable while the white above it carries the emphasis.
          </p>
          <p className="text-small text-text-tertiary">
            Tertiary, 14px — disabled and decorative only, never running copy.
          </p>
        </div>
      </section>

      <section className="mt-32">
        <Eyebrow>Accent budget</Eyebrow>
        <div className="mt-8 flex items-center gap-4">
          <button
            type="button"
            className="rounded-full bg-accent px-6 py-3 text-body font-medium text-canvas transition-transform duration-150 hover:-translate-y-0.5"
          >
            Try DBPilot
          </button>
          <span className="flex items-center gap-2 rounded-full border border-border px-4 py-2 text-small text-text-secondary">
            <span className="inline-block size-1.5 rounded-full bg-accent" />
            Read-only
          </span>
        </div>
      </section>
    </main>
  )
}
```

`frontend/src/App.tsx`:
```tsx
import { Navigate, Route, Routes } from 'react-router-dom'

import { Tokens } from './routes/Tokens'

export default function App() {
  return (
    <Routes>
      <Route path="/tokens" element={<Tokens />} />
      <Route path="*" element={<Navigate to="/tokens" replace />} />
    </Routes>
  )
}
```

`frontend/src/main.tsx`:
```tsx
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'

import App from './App.tsx'
import './styles/tokens.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
)
```

Delete the Vite starter leftovers: `frontend/src/App.css`, `frontend/src/index.css`, `frontend/src/assets/react.svg`.

- [ ] **Step 9: Verify the build and the page**

Run:
```bash
cd /d/Projects/DBQuery/frontend
npx tsc --noEmit
npm run build
npm run dev
```
Expected: type-check clean, build succeeds, and `http://localhost:5173/tokens` renders the swatches on a near-black canvas with exactly one lime button. Stop the dev server afterwards.

- [ ] **Step 10: Commit**

```bash
git add frontend/
git commit -m "feat(frontend): scaffold vite app with the PRD design tokens

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Cqgmb8EqhP1PTeqJPA8wHF"
```

---

### Task 10: Continuous integration

**Files:**
- Create: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: every command verified by hand in Tasks 2–9
- Produces: a workflow that must stay green for the rest of the build

- [ ] **Step 1: Write the workflow**

The PostgreSQL service container replaces the local cluster, so the same suite runs unchanged.

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  backend:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:18
        env:
          POSTGRES_USER: dbpilot_app
          POSTGRES_PASSWORD: dbpilot_ci
          POSTGRES_DB: dbpilot_test
        ports: ['5432:5432']
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    env:
      DATABASE_URL: postgresql+psycopg://dbpilot_app:dbpilot_ci@localhost:5432/dbpilot_test
      TEST_DATABASE_URL: postgresql+psycopg://dbpilot_app:dbpilot_ci@localhost:5432/dbpilot_test
      JWT_SECRET: ci-secret-not-used-in-production
      DBPILOT_ENCRYPTION_KEY: 4Nf1kQ0mS2vX8yZ7bC3dE6gH9jK2lM5nP8qR1sT4uV0=

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install
        working-directory: backend
        run: |
          python -m pip install --upgrade pip
          pip install -e ".[dev]"

      - name: Create the metadata schema
        run: |
          PGPASSWORD=dbpilot_ci psql -h localhost -U dbpilot_app -d dbpilot_test \
            -c "CREATE SCHEMA IF NOT EXISTS dbpilot AUTHORIZATION dbpilot_app;"

      - name: Lint
        working-directory: backend
        run: ruff check app tests

      - name: Type-check
        working-directory: backend
        run: mypy app

      - name: Migrate
        working-directory: backend
        run: alembic upgrade head

      - name: Test
        working-directory: backend
        run: pytest -v

  frontend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: npm
          cache-dependency-path: frontend/package-lock.json

      - name: Install
        working-directory: frontend
        run: npm ci

      - name: Type-check
        working-directory: frontend
        run: npx tsc --noEmit

      - name: Test
        working-directory: frontend
        run: npx vitest run

      - name: Build
        working-directory: frontend
        run: npm run build
```

The `DBPILOT_ENCRYPTION_KEY` above is a throwaway CI value, never used against real data.

- [ ] **Step 2: Verify locally that the same commands pass**

Run:
```bash
cd /d/Projects/DBQuery/backend
.venv/Scripts/ruff check app tests && .venv/Scripts/mypy app && .venv/Scripts/python -m pytest -v
cd ../frontend
npx tsc --noEmit && npx vitest run && npm run build
```
Expected: every command exits 0.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: add backend and frontend workflows

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Cqgmb8EqhP1PTeqJPA8wHF"
```

---

## Phase 1 Definition of Done

- [ ] `psql` reaches `dbpilot` and `dbpilot_test` as `dbpilot_app`
- [ ] `alembic upgrade head` creates eight tables plus `alembic_version` in schema `dbpilot`
- [ ] `alembic downgrade base` then `upgrade head` round-trips cleanly
- [ ] `alembic check` reports no drift between models and migrations
- [ ] `GET /health` returns `{"status":"ok","database":true,"version":"0.1.0"}`
- [ ] `pytest`, `ruff check`, and `mypy` all pass in `backend/`
- [ ] `vitest run`, `tsc --noEmit`, and `npm run build` all pass in `frontend/`
- [ ] `/tokens` renders the PRD §10.2 palette with exactly one lime call to action
- [ ] No `.env` file appears in `git status` or any commit

## Out of scope for Phase 1

Deferred deliberately, each to its named phase:

- Registration, login, JWT issuance, the `refresh_tokens` table and migration `0003` — Phase 2
- CSV upload, type inference, per-project schemas and read-only roles — Phase 3
- The safety gate, query execution, Gemini integration — Phase 4
- ER diagram, explanation, optimisation — Phase 5
- Dashboard, history, saved queries, export, demo project, benchmarks — Phase 6
