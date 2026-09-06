# DBPilot Phase 2 — Identity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A user can register, log in, stay logged in across a refresh, and create, list, and delete projects that no other user can see or touch.

**Architecture:** Password hashing and JWT minting are pure functions in `app/core`, so they test without a database. Refresh tokens are rows, not just signatures — that is what makes rotation and reuse detection possible. Two FastAPI dependencies carry the whole authorisation story: `get_current_user` resolves the bearer token, and `get_owned_project` filters by owner and raises 404 (never 403) so project existence cannot leak.

**Tech Stack:** bcrypt (direct, not passlib), python-jose, SQLAlchemy 2.x async, Alembic, FastAPI dependencies, React + TanStack-free hand-rolled fetch client, React Router.

**Spec:** `docs/superpowers/specs/2026-09-06-dbpilot-design.md`

**Predecessor:** `docs/superpowers/plans/2026-09-06-phase-1-scaffold.md` (tag `phase-1`)

## Global Constraints

- Python runtime is **3.11.9** (`backend/.venv/Scripts/python`). Never the machine default 3.14.
- Run the server with `python run.py`, never `uvicorn app.main:app` — see Phase 1, uvicorn's loop factory bypasses the event loop policy and psycopg 3 then fails.
- Passwords hash with **bcrypt cost ≥ 12**, using the **`bcrypt` package directly**. `passlib` is broken against bcrypt ≥ 4.1 and must not be added.
- Access token TTL **30 minutes**; refresh token TTL **7 days, rotated on every use** (PRD F1).
- A resource the caller does not own returns **404, never 403** (design document §6, layer 1).
- Application metadata stays in PostgreSQL schema **`dbpilot`**.
- Design tokens are exactly PRD §10.2. No component writes a raw hex value.
- Accent budget: at most three lime elements per viewport (PRD §10.2).
- `--text-tertiary` (#5A5A5A) is for disabled and decorative text only, never running copy (PRD §10.8).
- Every commit message ends with the two attribution lines shown in Task 1, Step 6.
- `alembic check` must report no drift at the end of every task that touches a model.

---

## File Structure

**Backend**

| File | Responsibility |
|---|---|
| `backend/app/core/security.py` | `hash_password` / `verify_password`. No I/O, no framework. |
| `backend/app/core/tokens.py` | Mint and decode JWTs. No database. |
| `backend/app/models/refresh_token.py` | The refresh-token row that makes rotation auditable |
| `backend/alembic/versions/0003_refresh_tokens.py` | Its migration |
| `backend/app/schemas/auth.py` | Register/login/refresh request and response bodies |
| `backend/app/schemas/project.py` | Project request and response bodies |
| `backend/app/services/auth.py` | Register, authenticate, rotate. The only module that writes users or tokens. |
| `backend/app/api/deps.py` | `get_current_user`, `get_owned_project` — the authorisation seam |
| `backend/app/api/auth.py` | `/auth/register`, `/auth/login`, `/auth/refresh` |
| `backend/app/api/projects.py` | `/projects` list, create, delete |
| `backend/tests/test_isolation.py` | Proves user B cannot reach user A's data |

**Frontend**

| File | Responsibility |
|---|---|
| `frontend/src/lib/api.ts` | Fetch wrapper: bearer header, one silent refresh on 401 |
| `frontend/src/lib/auth-storage.ts` | Where tokens live, and the reasoning for it |
| `frontend/src/features/auth/AuthContext.tsx` | Session state for the app |
| `frontend/src/components/Button.tsx` | Pill button, PRD §10.5 |
| `frontend/src/components/Field.tsx` | Labelled input with error text |
| `frontend/src/routes/Login.tsx` | Sign-in screen |
| `frontend/src/routes/Register.tsx` | Sign-up screen |
| `frontend/src/routes/Projects.tsx` | Project list, create, delete |
| `frontend/src/routes/ProtectedRoute.tsx` | Redirects anonymous visitors to `/login` |

---

### Task 1: Password hashing

**Files:**
- Create: `backend/app/core/security.py`
- Test: `backend/tests/test_security.py`

**Interfaces:**
- Consumes: `get_settings()` from Phase 1
- Produces:
  - `hash_password(password: str) -> str` — 60-character bcrypt hash, fits `users.password_hash String(60)`
  - `verify_password(password: str, password_hash: str) -> bool` — never raises
  - `MAX_PASSWORD_BYTES: int = 72`

- [ ] **Step 1: Write the failing test**

`backend/tests/test_security.py`:
```python
import pytest

from app.core.security import MAX_PASSWORD_BYTES, hash_password, verify_password


def test_hash_is_not_the_password() -> None:
    hashed = hash_password("correct horse battery staple")

    assert hashed != "correct horse battery staple"
    assert hashed.startswith("$2b$")


def test_hash_fits_the_password_hash_column() -> None:
    """users.password_hash is String(60); bcrypt hashes are exactly 60 chars."""
    assert len(hash_password("a-reasonable-password")) == 60


def test_same_password_hashes_differently_each_time() -> None:
    """A per-hash salt means two users with one password get two hashes."""
    assert hash_password("same-password") != hash_password("same-password")


def test_verify_accepts_the_right_password() -> None:
    hashed = hash_password("correct horse battery staple")

    assert verify_password("correct horse battery staple", hashed) is True


def test_verify_rejects_the_wrong_password() -> None:
    hashed = hash_password("correct horse battery staple")

    assert verify_password("Correct horse battery staple", hashed) is False


def test_verify_returns_false_for_a_malformed_hash() -> None:
    """A corrupted row must not raise into the request handler."""
    assert verify_password("anything", "not-a-bcrypt-hash") is False


def test_cost_factor_meets_the_prd_floor() -> None:
    """PRD F1 requires cost >= 12. The hash records its own cost."""
    cost = int(hash_password("x").split("$")[2])

    assert cost >= 12


def test_password_beyond_bcrypt_limit_is_rejected_loudly() -> None:
    """bcrypt silently ignores bytes past 72; refuse rather than mislead."""
    too_long = "a" * (MAX_PASSWORD_BYTES + 1)

    with pytest.raises(ValueError, match="72 bytes"):
        hash_password(too_long)


def test_limit_is_counted_in_bytes_not_characters() -> None:
    """Emoji are 4 bytes each, so 20 of them exceed the limit."""
    with pytest.raises(ValueError, match="72 bytes"):
        hash_password("🔒" * 20)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /d/Projects/DBQuery/backend && .venv/Scripts/python -m pytest tests/test_security.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.core.security'`

- [ ] **Step 3: Write the implementation**

```python
"""Password hashing. PRD F1: bcrypt, cost at least 12."""

import bcrypt

from app.core.config import get_settings

# bcrypt truncates input past 72 bytes. Silently accepting a longer password
# would mean two different passwords unlock the same account.
MAX_PASSWORD_BYTES = 72


def hash_password(password: str) -> str:
    encoded = password.encode("utf-8")
    if len(encoded) > MAX_PASSWORD_BYTES:
        raise ValueError(
            f"Password must be at most {MAX_PASSWORD_BYTES} bytes; "
            f"this one is {len(encoded)}."
        )
    salt = bcrypt.gensalt(rounds=get_settings().bcrypt_rounds)
    return bcrypt.hashpw(encoded, salt).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """False for a wrong password AND for a malformed stored hash."""
    try:
        return bcrypt.checkpw(
            password.encode("utf-8"), password_hash.encode("utf-8")
        )
    except (ValueError, TypeError):
        return False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /d/Projects/DBQuery/backend && .venv/Scripts/python -m pytest tests/test_security.py -v`
Expected: PASS, 9 tests.

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/security.py backend/tests/test_security.py
git commit -m "feat(auth): add bcrypt password hashing

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Cqgmb8EqhP1PTeqJPA8wHF"
```

---

### Task 2: JWT minting and decoding

**Files:**
- Create: `backend/app/core/tokens.py`
- Test: `backend/tests/test_tokens.py`

**Interfaces:**
- Consumes: `get_settings()`, `UnauthorizedError` from Phase 1
- Produces:
  - `TokenType` — `StrEnum` with members `access`, `refresh`
  - `TokenPair(access_token: str, refresh_token: str, refresh_jti: str, refresh_expires_at: datetime)` — a frozen dataclass
  - `DecodedToken(user_id: int, jti: str, token_type: TokenType, expires_at: datetime)` — a frozen dataclass
  - `create_token_pair(user_id: int) -> TokenPair`
  - `decode_token(token: str, expected: TokenType) -> DecodedToken` — raises `UnauthorizedError`

- [ ] **Step 1: Write the failing test**

`backend/tests/test_tokens.py`:
```python
from datetime import UTC, datetime, timedelta

import pytest
from jose import jwt

from app.core.config import get_settings
from app.core.errors import UnauthorizedError
from app.core.tokens import TokenType, create_token_pair, decode_token


def test_pair_round_trips_the_user_id() -> None:
    pair = create_token_pair(user_id=42)

    assert decode_token(pair.access_token, TokenType.access).user_id == 42
    assert decode_token(pair.refresh_token, TokenType.refresh).user_id == 42


def test_access_and_refresh_are_different_tokens() -> None:
    pair = create_token_pair(user_id=1)

    assert pair.access_token != pair.refresh_token


def test_refresh_jti_matches_the_encoded_token() -> None:
    """The service stores this jti as a row, so it must be the real one."""
    pair = create_token_pair(user_id=7)

    assert decode_token(pair.refresh_token, TokenType.refresh).jti == pair.refresh_jti


def test_an_access_token_is_not_accepted_as_a_refresh_token() -> None:
    """Otherwise a 30-minute token would work for 7 days of refreshing."""
    pair = create_token_pair(user_id=1)

    with pytest.raises(UnauthorizedError):
        decode_token(pair.access_token, TokenType.refresh)


def test_a_refresh_token_is_not_accepted_as_an_access_token() -> None:
    pair = create_token_pair(user_id=1)

    with pytest.raises(UnauthorizedError):
        decode_token(pair.refresh_token, TokenType.access)


def test_ttls_match_the_prd() -> None:
    """PRD F1: access 30 minutes, refresh 7 days."""
    before = datetime.now(UTC)
    pair = create_token_pair(user_id=1)

    access = decode_token(pair.access_token, TokenType.access)
    refresh = decode_token(pair.refresh_token, TokenType.refresh)

    assert timedelta(minutes=29) < access.expires_at - before < timedelta(minutes=31)
    assert timedelta(days=6) < refresh.expires_at - before < timedelta(days=8)


def test_expired_token_is_rejected() -> None:
    settings = get_settings()
    stale = jwt.encode(
        {
            "sub": "1",
            "jti": "abc",
            "type": "access",
            "exp": datetime.now(UTC) - timedelta(minutes=1),
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )

    with pytest.raises(UnauthorizedError):
        decode_token(stale, TokenType.access)


def test_token_signed_with_another_secret_is_rejected() -> None:
    forged = jwt.encode(
        {
            "sub": "1",
            "jti": "abc",
            "type": "access",
            "exp": datetime.now(UTC) + timedelta(minutes=5),
        },
        "not-the-real-secret",
        algorithm="HS256",
    )

    with pytest.raises(UnauthorizedError):
        decode_token(forged, TokenType.access)


def test_garbage_is_rejected_without_leaking_internals() -> None:
    with pytest.raises(UnauthorizedError):
        decode_token("clearly.not.a.jwt", TokenType.access)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /d/Projects/DBQuery/backend && .venv/Scripts/python -m pytest tests/test_tokens.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.core.tokens'`

- [ ] **Step 3: Write the implementation**

```python
"""JWT minting and decoding. PRD F1: 30-minute access, 7-day refresh."""

import enum
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from jose import JWTError, jwt

from app.core.config import get_settings
from app.core.errors import UnauthorizedError


class TokenType(enum.StrEnum):
    access = "access"
    refresh = "refresh"


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    refresh_token: str
    refresh_jti: str
    refresh_expires_at: datetime


@dataclass(frozen=True)
class DecodedToken:
    user_id: int
    jti: str
    token_type: TokenType
    expires_at: datetime


def _encode(user_id: int, token_type: TokenType, ttl: timedelta) -> tuple[str, str, datetime]:
    settings = get_settings()
    issued_at = datetime.now(UTC)
    expires_at = issued_at + ttl
    jti = uuid.uuid4().hex
    token = jwt.encode(
        {
            "sub": str(user_id),
            "jti": jti,
            "type": token_type.value,
            "iat": issued_at,
            "exp": expires_at,
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    return token, jti, expires_at


def create_token_pair(user_id: int) -> TokenPair:
    settings = get_settings()
    access_token, _, _ = _encode(
        user_id,
        TokenType.access,
        timedelta(minutes=settings.access_token_ttl_minutes),
    )
    refresh_token, refresh_jti, refresh_expires_at = _encode(
        user_id,
        TokenType.refresh,
        timedelta(days=settings.refresh_token_ttl_days),
    )
    return TokenPair(
        access_token=access_token,
        refresh_token=refresh_token,
        refresh_jti=refresh_jti,
        refresh_expires_at=refresh_expires_at,
    )


def decode_token(token: str, expected: TokenType) -> DecodedToken:
    """Every rejection is the same error: never say why a token failed."""
    settings = get_settings()
    try:
        claims = jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
    except JWTError as exc:
        raise UnauthorizedError("That session is not valid. Sign in again.") from exc

    if claims.get("type") != expected.value:
        raise UnauthorizedError("That session is not valid. Sign in again.")

    try:
        user_id = int(claims["sub"])
        jti = str(claims["jti"])
        expires_at = datetime.fromtimestamp(claims["exp"], tz=UTC)
    except (KeyError, TypeError, ValueError) as exc:
        raise UnauthorizedError("That session is not valid. Sign in again.") from exc

    return DecodedToken(
        user_id=user_id, jti=jti, token_type=expected, expires_at=expires_at
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /d/Projects/DBQuery/backend && .venv/Scripts/python -m pytest tests/test_tokens.py -v`
Expected: PASS, 9 tests.

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/tokens.py backend/tests/test_tokens.py
git commit -m "feat(auth): add JWT minting and decoding with typed tokens

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Cqgmb8EqhP1PTeqJPA8wHF"
```

---

### Task 3: Refresh token storage

**Files:**
- Create: `backend/app/models/refresh_token.py`, `backend/alembic/versions/0003_refresh_tokens.py`
- Modify: `backend/app/models/__init__.py`
- Test: `backend/tests/test_models.py` (extend)

**Interfaces:**
- Consumes: `Base` / `TimestampedBase` from Phase 1
- Produces: `RefreshToken` model — columns `id`, `user_id`, `jti` (unique), `expires_at`, `revoked_at`, `replaced_by_jti`, `created_at`. Task 4's rotation logic reads and writes these.

Rotation needs rows, not just signatures: a stateless JWT cannot be revoked, so
"rotated on use" (PRD F1) is only enforceable if each refresh token has a row we
can mark spent.

- [ ] **Step 1: Extend the model test**

Append to `backend/tests/test_models.py`, and add `"refresh_tokens"` to the
existing `EXPECTED_TABLES` set:

```python
def test_refresh_tokens_support_rotation_and_reuse_detection() -> None:
    """PRD F1 rotates refresh tokens on use; that needs revocation state."""
    table = Base.metadata.tables["dbpilot.refresh_tokens"]

    assert table.columns["jti"].unique is True
    assert table.columns["revoked_at"].nullable is True
    assert "replaced_by_jti" in table.columns
    assert table.columns["expires_at"].nullable is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /d/Projects/DBQuery/backend && .venv/Scripts/python -m pytest tests/test_models.py -v`
Expected: FAIL — `KeyError: 'dbpilot.refresh_tokens'`

- [ ] **Step 3: Write the model**

`backend/app/models/refresh_token.py`:
```python
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import TimestampedBase


class RefreshToken(TimestampedBase):
    """One row per issued refresh token.

    A JWT on its own cannot be revoked, so rotation is only enforceable with
    server-side state. revoked_at marks a token spent; presenting a spent token
    means it was replayed, and the service revokes the whole family.
    """

    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("dbpilot.users.id", ondelete="CASCADE"), nullable=False
    )
    jti: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replaced_by_jti: Mapped[str | None] = mapped_column(String(32))
```

Add to `backend/app/models/__init__.py`: the import
`from app.models.refresh_token import RefreshToken` and `"RefreshToken"` in
`__all__`, both in alphabetical position.

- [ ] **Step 4: Generate and rename the migration**

Run:
```bash
cd /d/Projects/DBQuery/backend
.venv/Scripts/alembic revision --autogenerate -m "refresh tokens"
```
Rename the generated file to `backend/alembic/versions/0003_refresh_tokens.py`,
set `revision = "0003_refresh_tokens"` and
`down_revision = "0002_performance_indexes"`. The body should contain exactly one
`op.create_table` and one `op.drop_table`. Anything else means drift from an
earlier revision — fix that before continuing.

- [ ] **Step 5: Apply and verify**

Run:
```bash
cd /d/Projects/DBQuery/backend
.venv/Scripts/alembic upgrade head
.venv/Scripts/python -m pytest tests/test_models.py tests/test_migrations.py -v
```
Expected: PASS, 9 tests. `test_migrations_match_the_models` passing proves the
new table and the models agree.

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/refresh_token.py backend/app/models/__init__.py \
        backend/alembic/versions/0003_refresh_tokens.py backend/tests/test_models.py
git commit -m "feat(auth): add refresh token storage for rotation

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Cqgmb8EqhP1PTeqJPA8wHF"
```

---

### Task 4: Auth service

**Files:**
- Create: `backend/app/schemas/__init__.py`, `backend/app/schemas/auth.py`, `backend/app/services/__init__.py`, `backend/app/services/auth.py`
- Modify: `backend/tests/conftest.py`
- Test: `backend/tests/test_auth_service.py`

**Interfaces:**
- Consumes: `hash_password`/`verify_password` (Task 1), `create_token_pair`/`decode_token`/`TokenType` (Task 2), `RefreshToken` (Task 3), `User`, `ConflictError`/`UnauthorizedError`
- Produces:
  - `register_user(session, email: str, password: str) -> User`
  - `authenticate_user(session, email: str, password: str) -> User`
  - `issue_tokens(session, user: User) -> TokenPair`
  - `rotate_refresh_token(session, refresh_token: str) -> tuple[User, TokenPair]`
  - Pydantic models `RegisterRequest`, `LoginRequest`, `RefreshRequest`, `TokenResponse`, `UserResponse`
- Also produces the shared `client` fixture Tasks 5–8 use.

- [ ] **Step 1: Add the shared API client fixture to `conftest.py`**

The app's `get_session` dependency points at the development database. Without
this override, every auth test would write real users into it.

Add these to the existing import block at the top of
`backend/tests/conftest.py`:
```python
from httpx import ASGITransport, AsyncClient

from app.db.session import get_session
from app.main import create_app
```

Then append the fixture at the end of the file:
```python
@pytest_asyncio.fixture
async def client(session: AsyncSession) -> AsyncIterator[AsyncClient]:
    """An API client bound to the test session, so requests roll back.

    The session is joined to an outer transaction the `session` fixture rolls
    back, so a handler calling session.commit() still leaves no rows behind.
    """
    app = create_app()

    async def _use_test_session() -> _AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_session] = _use_test_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as opened:
        yield opened
    app.dependency_overrides.clear()
```

Then delete the now-duplicated local `client` fixture from
`backend/tests/test_health.py` (keep its tests; they pick up the shared one).

- [ ] **Step 2: Write the failing test**

`backend/tests/test_auth_service.py`:
```python
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, UnauthorizedError
from app.models import RefreshToken
from app.services.auth import (
    authenticate_user,
    issue_tokens,
    register_user,
    rotate_refresh_token,
)

pytestmark = pytest.mark.integration


async def test_register_stores_a_hash_not_the_password(session: AsyncSession) -> None:
    user = await register_user(session, "ada@example.com", "a-good-password")

    assert user.password_hash != "a-good-password"
    assert user.password_hash.startswith("$2b$")


async def test_register_normalises_the_email(session: AsyncSession) -> None:
    """Otherwise Ada@example.com and ada@example.com become two accounts."""
    user = await register_user(session, "  Ada@Example.COM ", "a-good-password")

    assert user.email == "ada@example.com"


async def test_register_rejects_a_duplicate_email(session: AsyncSession) -> None:
    await register_user(session, "ada@example.com", "a-good-password")

    with pytest.raises(ConflictError):
        await register_user(session, "ada@example.com", "another-password")


async def test_authenticate_accepts_correct_credentials(
    session: AsyncSession,
) -> None:
    await register_user(session, "ada@example.com", "a-good-password")

    user = await authenticate_user(session, "ada@example.com", "a-good-password")

    assert user.email == "ada@example.com"


async def test_authenticate_rejects_a_wrong_password(session: AsyncSession) -> None:
    await register_user(session, "ada@example.com", "a-good-password")

    with pytest.raises(UnauthorizedError):
        await authenticate_user(session, "ada@example.com", "wrong-password")


async def test_authenticate_rejects_an_unknown_email(session: AsyncSession) -> None:
    with pytest.raises(UnauthorizedError):
        await authenticate_user(session, "nobody@example.com", "any-password")


async def test_authenticate_records_the_login_time(session: AsyncSession) -> None:
    await register_user(session, "ada@example.com", "a-good-password")

    user = await authenticate_user(session, "ada@example.com", "a-good-password")

    assert user.last_login_at is not None


async def test_issuing_tokens_stores_the_refresh_jti(session: AsyncSession) -> None:
    user = await register_user(session, "ada@example.com", "a-good-password")

    pair = await issue_tokens(session, user)

    stored = await session.scalar(
        select(RefreshToken).where(RefreshToken.jti == pair.refresh_jti)
    )
    assert stored is not None
    assert stored.revoked_at is None


async def test_rotation_returns_a_new_pair(session: AsyncSession) -> None:
    user = await register_user(session, "ada@example.com", "a-good-password")
    first = await issue_tokens(session, user)

    rotated_user, second = await rotate_refresh_token(session, first.refresh_token)

    assert rotated_user.id == user.id
    assert second.refresh_token != first.refresh_token


async def test_rotation_spends_the_old_token(session: AsyncSession) -> None:
    """PRD F1: rotated on use. The old token must stop working."""
    user = await register_user(session, "ada@example.com", "a-good-password")
    first = await issue_tokens(session, user)
    await rotate_refresh_token(session, first.refresh_token)

    with pytest.raises(UnauthorizedError):
        await rotate_refresh_token(session, first.refresh_token)


async def test_replaying_a_spent_token_revokes_the_whole_family(
    session: AsyncSession,
) -> None:
    """A replayed token means it leaked. Kill every session for that user."""
    user = await register_user(session, "ada@example.com", "a-good-password")
    first = await issue_tokens(session, user)
    _, second = await rotate_refresh_token(session, first.refresh_token)

    with pytest.raises(UnauthorizedError):
        await rotate_refresh_token(session, first.refresh_token)

    # The token the legitimate client holds is now dead too.
    with pytest.raises(UnauthorizedError):
        await rotate_refresh_token(session, second.refresh_token)


async def test_rotation_rejects_an_access_token(session: AsyncSession) -> None:
    user = await register_user(session, "ada@example.com", "a-good-password")
    pair = await issue_tokens(session, user)

    with pytest.raises(UnauthorizedError):
        await rotate_refresh_token(session, pair.access_token)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd /d/Projects/DBQuery/backend && .venv/Scripts/python -m pytest tests/test_auth_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services'`

- [ ] **Step 4: Write the schemas**

`backend/app/schemas/__init__.py` is an empty file.

`backend/app/schemas/auth.py`:
```python
from pydantic import BaseModel, EmailStr, Field

from app.core.security import MAX_PASSWORD_BYTES

# 8 is the usability floor; 72 is bcrypt's hard limit (see app.core.security).
PasswordField = Field(min_length=8, max_length=MAX_PASSWORD_BYTES)


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = PasswordField


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=MAX_PASSWORD_BYTES)


class RefreshRequest(BaseModel):
    refresh_token: str


class UserResponse(BaseModel):
    id: int
    email: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserResponse
```

`EmailStr` needs the validator package:
```bash
cd /d/Projects/DBQuery/backend
.venv/Scripts/python -m pip install "pydantic[email]"
```
Then add `"pydantic[email]>=2.9",` to the `dependencies` list in
`backend/pyproject.toml`, replacing the existing `"pydantic>=2.9",` entry.

- [ ] **Step 5: Write the service**

`backend/app/services/__init__.py` is an empty file.

`backend/app/services/auth.py`:
```python
"""Registration, authentication, and refresh rotation.

The only module that writes users or refresh tokens.
"""

from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, UnauthorizedError
from app.core.security import hash_password, verify_password
from app.core.tokens import TokenPair, TokenType, create_token_pair, decode_token
from app.models import RefreshToken, User

# One message for every failure mode, so the response never reveals whether an
# account exists.
_BAD_CREDENTIALS = "That email and password combination is not correct."
_BAD_SESSION = "That session has expired. Sign in again."


def normalise_email(email: str) -> str:
    return email.strip().lower()


async def register_user(session: AsyncSession, email: str, password: str) -> User:
    normalised = normalise_email(email)
    existing = await session.scalar(select(User).where(User.email == normalised))
    if existing is not None:
        raise ConflictError("An account with that email already exists.")

    user = User(email=normalised, password_hash=hash_password(password))
    session.add(user)
    await session.flush()
    return user


async def authenticate_user(
    session: AsyncSession, email: str, password: str
) -> User:
    user = await session.scalar(
        select(User).where(User.email == normalise_email(email))
    )
    # Hash-compare even when the user is missing, so a wrong email and a wrong
    # password take about the same time.
    stored_hash = user.password_hash if user else hash_password("timing-equaliser")
    if not verify_password(password, stored_hash) or user is None:
        raise UnauthorizedError(_BAD_CREDENTIALS)

    user.last_login_at = datetime.now(UTC)
    await session.flush()
    return user


async def issue_tokens(session: AsyncSession, user: User) -> TokenPair:
    pair = create_token_pair(user.id)
    session.add(
        RefreshToken(
            user_id=user.id,
            jti=pair.refresh_jti,
            expires_at=pair.refresh_expires_at,
        )
    )
    await session.flush()
    return pair


async def _revoke_all_for_user(session: AsyncSession, user_id: int) -> None:
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )


async def rotate_refresh_token(
    session: AsyncSession, refresh_token: str
) -> tuple[User, TokenPair]:
    decoded = decode_token(refresh_token, TokenType.refresh)

    stored = await session.scalar(
        select(RefreshToken).where(RefreshToken.jti == decoded.jti)
    )
    if stored is None:
        raise UnauthorizedError(_BAD_SESSION)

    if stored.revoked_at is not None:
        # This token was already spent. Someone is replaying a copy, so end
        # every session for this user rather than guess which one is genuine.
        await _revoke_all_for_user(session, stored.user_id)
        await session.flush()
        raise UnauthorizedError(_BAD_SESSION)

    if stored.expires_at <= datetime.now(UTC):
        raise UnauthorizedError(_BAD_SESSION)

    user = await session.get(User, stored.user_id)
    if user is None:
        raise UnauthorizedError(_BAD_SESSION)

    pair = await issue_tokens(session, user)
    stored.revoked_at = datetime.now(UTC)
    stored.replaced_by_jti = pair.refresh_jti
    await session.flush()
    return user, pair
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd /d/Projects/DBQuery/backend && .venv/Scripts/python -m pytest tests/test_auth_service.py -v`
Expected: PASS, 12 tests.

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas/ backend/app/services/ backend/pyproject.toml \
        backend/tests/conftest.py backend/tests/test_auth_service.py backend/tests/test_health.py
git commit -m "feat(auth): add registration, authentication and refresh rotation

Replaying a spent refresh token revokes every session for that user, since a
replay means the token leaked and there is no way to tell the copies apart.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Cqgmb8EqhP1PTeqJPA8wHF"
```

---

### Task 5: Auth endpoints and the current-user dependency

**Files:**
- Create: `backend/app/api/deps.py`, `backend/app/api/auth.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_auth_api.py`

**Interfaces:**
- Consumes: everything from Task 4
- Produces:
  - `CurrentUser` — `Annotated[User, Depends(get_current_user)]`, used by every protected route
  - `SessionDep` — `Annotated[AsyncSession, Depends(get_session)]`
  - `POST /auth/register` → 201 `TokenResponse`
  - `POST /auth/login` → 200 `TokenResponse`
  - `POST /auth/refresh` → 200 `TokenResponse`
  - `GET /auth/me` → 200 `UserResponse`

- [ ] **Step 1: Write the failing test**

`backend/tests/test_auth_api.py`:
```python
import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration

CREDENTIALS = {"email": "ada@example.com", "password": "a-good-password"}


async def test_register_returns_tokens_and_the_user(client: AsyncClient) -> None:
    response = await client.post("/auth/register", json=CREDENTIALS)

    assert response.status_code == 201
    body = response.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["token_type"] == "bearer"
    assert body["user"]["email"] == "ada@example.com"


async def test_register_never_returns_the_password_hash(
    client: AsyncClient,
) -> None:
    response = await client.post("/auth/register", json=CREDENTIALS)

    assert "password" not in response.text
    assert "$2b$" not in response.text


async def test_register_rejects_a_duplicate_email(client: AsyncClient) -> None:
    await client.post("/auth/register", json=CREDENTIALS)

    response = await client.post("/auth/register", json=CREDENTIALS)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


async def test_register_rejects_a_short_password(client: AsyncClient) -> None:
    response = await client.post(
        "/auth/register", json={"email": "ada@example.com", "password": "short"}
    )

    assert response.status_code == 422


async def test_register_rejects_a_malformed_email(client: AsyncClient) -> None:
    response = await client.post(
        "/auth/register", json={"email": "not-an-email", "password": "a-good-password"}
    )

    assert response.status_code == 422


async def test_login_returns_tokens(client: AsyncClient) -> None:
    await client.post("/auth/register", json=CREDENTIALS)

    response = await client.post("/auth/login", json=CREDENTIALS)

    assert response.status_code == 200
    assert response.json()["access_token"]


async def test_login_with_a_wrong_password_is_401(client: AsyncClient) -> None:
    await client.post("/auth/register", json=CREDENTIALS)

    response = await client.post(
        "/auth/login", json={"email": CREDENTIALS["email"], "password": "wrong-password"}
    )

    assert response.status_code == 401


async def test_login_does_not_reveal_whether_an_account_exists(
    client: AsyncClient,
) -> None:
    await client.post("/auth/register", json=CREDENTIALS)

    wrong_password = await client.post(
        "/auth/login", json={"email": CREDENTIALS["email"], "password": "wrong-password"}
    )
    unknown_email = await client.post(
        "/auth/login", json={"email": "nobody@example.com", "password": "wrong-password"}
    )

    assert wrong_password.status_code == unknown_email.status_code
    assert wrong_password.json()["error"]["message"] == (
        unknown_email.json()["error"]["message"]
    )


async def test_refresh_exchanges_the_token(client: AsyncClient) -> None:
    registered = (await client.post("/auth/register", json=CREDENTIALS)).json()

    response = await client.post(
        "/auth/refresh", json={"refresh_token": registered["refresh_token"]}
    )

    assert response.status_code == 200
    assert response.json()["refresh_token"] != registered["refresh_token"]


async def test_a_spent_refresh_token_is_rejected(client: AsyncClient) -> None:
    registered = (await client.post("/auth/register", json=CREDENTIALS)).json()
    await client.post(
        "/auth/refresh", json={"refresh_token": registered["refresh_token"]}
    )

    response = await client.post(
        "/auth/refresh", json={"refresh_token": registered["refresh_token"]}
    )

    assert response.status_code == 401


async def test_me_returns_the_signed_in_user(client: AsyncClient) -> None:
    registered = (await client.post("/auth/register", json=CREDENTIALS)).json()

    response = await client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {registered['access_token']}"},
    )

    assert response.status_code == 200
    assert response.json()["email"] == "ada@example.com"


async def test_me_without_a_token_is_401(client: AsyncClient) -> None:
    response = await client.get("/auth/me")

    assert response.status_code == 401


async def test_me_rejects_a_refresh_token_used_as_a_bearer(
    client: AsyncClient,
) -> None:
    registered = (await client.post("/auth/register", json=CREDENTIALS)).json()

    response = await client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {registered['refresh_token']}"},
    )

    assert response.status_code == 401
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /d/Projects/DBQuery/backend && .venv/Scripts/python -m pytest tests/test_auth_api.py -v`
Expected: FAIL — every request returns 404, because no auth router is mounted.

- [ ] **Step 3: Write the dependencies**

`backend/app/api/deps.py`:
```python
"""The authorisation seam. Every protected route goes through here."""

from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import UnauthorizedError
from app.core.tokens import TokenType, decode_token
from app.db.session import get_session
from app.models import User

SessionDep = Annotated[AsyncSession, Depends(get_session)]

# auto_error=False so a missing header raises our own UnauthorizedError and
# renders the standard error envelope rather than FastAPI's default shape.
_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    session: SessionDep,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(_bearer)
    ] = None,
) -> User:
    if credentials is None:
        raise UnauthorizedError("Sign in to continue.")

    decoded = decode_token(credentials.credentials, TokenType.access)
    user = await session.get(User, decoded.user_id)
    if user is None:
        raise UnauthorizedError("Sign in to continue.")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
```

- [ ] **Step 4: Write the router**

`backend/app/api/auth.py`:
```python
"""Registration, login, and refresh. PRD section 7."""

from fastapi import APIRouter, status

from app.api.deps import CurrentUser, SessionDep
from app.core.tokens import TokenPair
from app.models import User
from app.schemas.auth import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from app.services.auth import (
    authenticate_user,
    issue_tokens,
    register_user,
    rotate_refresh_token,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _token_response(user: User, pair: TokenPair) -> TokenResponse:
    return TokenResponse(
        access_token=pair.access_token,
        refresh_token=pair.refresh_token,
        user=UserResponse(id=user.id, email=user.email),
    )


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, session: SessionDep) -> TokenResponse:
    user = await register_user(session, body.email, body.password)
    pair = await issue_tokens(session, user)
    return _token_response(user, pair)


@router.post("/login")
async def login(body: LoginRequest, session: SessionDep) -> TokenResponse:
    user = await authenticate_user(session, body.email, body.password)
    pair = await issue_tokens(session, user)
    return _token_response(user, pair)


@router.post("/refresh")
async def refresh(body: RefreshRequest, session: SessionDep) -> TokenResponse:
    user, pair = await rotate_refresh_token(session, body.refresh_token)
    return _token_response(user, pair)


@router.get("/me")
async def me(user: CurrentUser) -> UserResponse:
    return UserResponse(id=user.id, email=user.email)
```

- [ ] **Step 5: Mount the router**

In `backend/app/main.py`, change the import
`from app.api import health` to `from app.api import auth, health`, and add
`app.include_router(auth.router)` directly above the existing
`app.include_router(health.router)` line.

- [ ] **Step 6: Run test to verify it passes**

Run: `cd /d/Projects/DBQuery/backend && .venv/Scripts/python -m pytest tests/test_auth_api.py -v`
Expected: PASS, 13 tests.

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/deps.py backend/app/api/auth.py backend/app/main.py \
        backend/tests/test_auth_api.py
git commit -m "feat(api): add auth endpoints and the current-user dependency

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Cqgmb8EqhP1PTeqJPA8wHF"
```

---

### Task 6: Projects CRUD and the ownership dependency

**Files:**
- Create: `backend/app/schemas/project.py`, `backend/app/services/projects.py`, `backend/app/api/projects.py`
- Modify: `backend/app/api/deps.py`, `backend/app/main.py`
- Test: `backend/tests/test_projects_api.py`

**Interfaces:**
- Consumes: `CurrentUser`, `SessionDep` (Task 5), `Project`, `SourceType`
- Produces:
  - `get_owned_project(project_id: int, user: CurrentUser, session: SessionDep) -> Project` — raises `NotFoundError` for someone else's project
  - `OwnedProject` — `Annotated[Project, Depends(get_owned_project)]`
  - `GET /projects` → 200 `list[ProjectResponse]`
  - `POST /projects` → 201 `ProjectResponse`
  - `GET /projects/{id}` → 200 `ProjectResponse`
  - `DELETE /projects/{id}` → 204

- [ ] **Step 1: Write the failing test**

`backend/tests/test_projects_api.py`:
```python
import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration


async def _auth_headers(client: AsyncClient, email: str) -> dict[str, str]:
    response = await client.post(
        "/auth/register", json={"email": email, "password": "a-good-password"}
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def test_creating_a_project_returns_it(client: AsyncClient) -> None:
    headers = await _auth_headers(client, "ada@example.com")

    response = await client.post(
        "/projects", json={"name": "Sales", "source_type": "upload"}, headers=headers
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Sales"
    assert body["source_type"] == "upload"
    assert body["id"]


async def test_listing_returns_only_your_own_projects(client: AsyncClient) -> None:
    ada = await _auth_headers(client, "ada@example.com")
    grace = await _auth_headers(client, "grace@example.com")
    await client.post(
        "/projects", json={"name": "Ada's", "source_type": "upload"}, headers=ada
    )
    await client.post(
        "/projects", json={"name": "Grace's", "source_type": "upload"}, headers=grace
    )

    response = await client.get("/projects", headers=ada)

    names = [project["name"] for project in response.json()]
    assert names == ["Ada's"]


async def test_duplicate_project_name_for_one_user_is_409(
    client: AsyncClient,
) -> None:
    headers = await _auth_headers(client, "ada@example.com")
    await client.post(
        "/projects", json={"name": "Sales", "source_type": "upload"}, headers=headers
    )

    response = await client.post(
        "/projects", json={"name": "Sales", "source_type": "upload"}, headers=headers
    )

    assert response.status_code == 409


async def test_two_users_may_each_have_a_project_of_the_same_name(
    client: AsyncClient,
) -> None:
    ada = await _auth_headers(client, "ada@example.com")
    grace = await _auth_headers(client, "grace@example.com")
    await client.post(
        "/projects", json={"name": "Sales", "source_type": "upload"}, headers=ada
    )

    response = await client.post(
        "/projects", json={"name": "Sales", "source_type": "upload"}, headers=grace
    )

    assert response.status_code == 201


async def test_deleting_your_own_project_succeeds(client: AsyncClient) -> None:
    headers = await _auth_headers(client, "ada@example.com")
    created = await client.post(
        "/projects", json={"name": "Sales", "source_type": "upload"}, headers=headers
    )
    project_id = created.json()["id"]

    response = await client.delete(f"/projects/{project_id}", headers=headers)

    assert response.status_code == 204
    assert (await client.get("/projects", headers=headers)).json() == []


async def test_projects_require_authentication(client: AsyncClient) -> None:
    assert (await client.get("/projects")).status_code == 401
    assert (
        await client.post("/projects", json={"name": "x", "source_type": "upload"})
    ).status_code == 401


async def test_an_unknown_project_is_404(client: AsyncClient) -> None:
    headers = await _auth_headers(client, "ada@example.com")

    response = await client.get("/projects/999999", headers=headers)

    assert response.status_code == 404


async def test_project_name_is_required(client: AsyncClient) -> None:
    headers = await _auth_headers(client, "ada@example.com")

    response = await client.post(
        "/projects", json={"name": "  ", "source_type": "upload"}, headers=headers
    )

    assert response.status_code == 422
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /d/Projects/DBQuery/backend && .venv/Scripts/python -m pytest tests/test_projects_api.py -v`
Expected: FAIL — requests to `/projects` return 404, no router is mounted.

- [ ] **Step 3: Write the schemas**

`backend/app/schemas/project.py`:
```python
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import SourceType


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    source_type: SourceType

    @field_validator("name")
    @classmethod
    def _reject_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("A project needs a name.")
        return stripped


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    source_type: SourceType
    schema_name: str | None
    table_count: int | None
    is_demo: bool
    created_at: datetime
```

- [ ] **Step 4: Write the service**

`backend/app/services/projects.py`:
```python
"""Project creation and listing. Ownership is enforced by the caller's filter."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError
from app.models import Project, SourceType


async def create_project(
    session: AsyncSession, *, user_id: int, name: str, source_type: SourceType
) -> Project:
    existing = await session.scalar(
        select(Project).where(Project.user_id == user_id, Project.name == name)
    )
    if existing is not None:
        raise ConflictError(f"You already have a project called {name!r}.")

    project = Project(user_id=user_id, name=name, source_type=source_type)
    session.add(project)
    await session.flush()
    return project


async def list_projects(session: AsyncSession, *, user_id: int) -> list[Project]:
    result = await session.scalars(
        select(Project).where(Project.user_id == user_id).order_by(Project.created_at)
    )
    return list(result)


async def delete_project(session: AsyncSession, project: Project) -> None:
    """Phase 3 extends this to drop the project schema and its read-only role.

    Today a project is metadata only, so deleting the row is the whole job.
    """
    await session.delete(project)
    await session.flush()
```

- [ ] **Step 5: Add the ownership dependency**

Append to `backend/app/api/deps.py`:
```python
from app.core.errors import NotFoundError  # add to the existing error import
from app.models import Project  # add to the existing model import


async def get_owned_project(
    project_id: int, user: CurrentUser, session: SessionDep
) -> Project:
    """Resolve a project the caller owns.

    Someone else's project is reported as 404, never 403 — a 403 would confirm
    the project exists. Design document §6, layer 1.
    """
    project = await session.scalar(
        select(Project).where(Project.id == project_id, Project.user_id == user.id)
    )
    if project is None:
        raise NotFoundError("That project does not exist.")
    return project


OwnedProject = Annotated[Project, Depends(get_owned_project)]
```

Add `from sqlalchemy import select` to the imports at the top of the file.

- [ ] **Step 6: Write the router**

`backend/app/api/projects.py`:
```python
"""Project CRUD. PRD section 7. Every route is scoped to the caller."""

from fastapi import APIRouter, Response, status

from app.api.deps import CurrentUser, OwnedProject, SessionDep
from app.schemas.project import ProjectCreate, ProjectResponse
from app.services.projects import create_project, delete_project, list_projects

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("")
async def index(user: CurrentUser, session: SessionDep) -> list[ProjectResponse]:
    projects = await list_projects(session, user_id=user.id)
    return [ProjectResponse.model_validate(project) for project in projects]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create(
    body: ProjectCreate, user: CurrentUser, session: SessionDep
) -> ProjectResponse:
    project = await create_project(
        session, user_id=user.id, name=body.name, source_type=body.source_type
    )
    return ProjectResponse.model_validate(project)


@router.get("/{project_id}")
async def show(project: OwnedProject) -> ProjectResponse:
    return ProjectResponse.model_validate(project)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def destroy(project: OwnedProject, session: SessionDep) -> Response:
    await delete_project(session, project)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
```

- [ ] **Step 7: Mount the router**

In `backend/app/main.py`, change the import to
`from app.api import auth, health, projects` and add
`app.include_router(projects.router)` below the auth router line.

- [ ] **Step 8: Run test to verify it passes**

Run: `cd /d/Projects/DBQuery/backend && .venv/Scripts/python -m pytest tests/test_projects_api.py -v`
Expected: PASS, 8 tests.

- [ ] **Step 9: Commit**

```bash
git add backend/app/schemas/project.py backend/app/services/projects.py \
        backend/app/api/projects.py backend/app/api/deps.py backend/app/main.py \
        backend/tests/test_projects_api.py
git commit -m "feat(api): add projects CRUD behind an ownership dependency

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Cqgmb8EqhP1PTeqJPA8wHF"
```

---

### Task 7: Cross-user isolation suite

**Files:**
- Create: `backend/tests/test_isolation.py`

**Interfaces:**
- Consumes: the `client` fixture and every endpoint from Tasks 5–6
- Produces: nothing consumed later. This suite is evidence for PRD F1, "no cross-user reads at any layer."

PRD F1 states it as an absolute. An absolute deserves a test file whose only
job is to try to break it.

- [ ] **Step 1: Write the suite**

`backend/tests/test_isolation.py`:
```python
"""PRD F1: all data is scoped to the owning user, at every layer.

Layer 1 of the four-layer model in design document §6. Layers 2 to 4 arrive
with query execution in Phase 4 and get their own adversarial suite.
"""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration

PASSWORD = "a-good-password"


async def _register(client: AsyncClient, email: str) -> dict[str, str]:
    response = await client.post(
        "/auth/register", json={"email": email, "password": PASSWORD}
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _project_for(client: AsyncClient, headers: dict[str, str], name: str) -> int:
    response = await client.post(
        "/projects", json={"name": name, "source_type": "upload"}, headers=headers
    )
    return int(response.json()["id"])


async def test_another_users_project_reads_as_missing(client: AsyncClient) -> None:
    ada = await _register(client, "ada@example.com")
    grace = await _register(client, "grace@example.com")
    ada_project = await _project_for(client, ada, "Ada's")

    response = await client.get(f"/projects/{ada_project}", headers=grace)

    assert response.status_code == 404, "403 would confirm the project exists"


async def test_another_user_cannot_delete_your_project(client: AsyncClient) -> None:
    ada = await _register(client, "ada@example.com")
    grace = await _register(client, "grace@example.com")
    ada_project = await _project_for(client, ada, "Ada's")

    response = await client.delete(f"/projects/{ada_project}", headers=grace)

    assert response.status_code == 404
    still_there = await client.get(f"/projects/{ada_project}", headers=ada)
    assert still_there.status_code == 200


async def test_a_missing_project_and_a_forbidden_one_are_indistinguishable(
    client: AsyncClient,
) -> None:
    """Identical responses, so probing cannot enumerate other users' ids."""
    ada = await _register(client, "ada@example.com")
    grace = await _register(client, "grace@example.com")
    ada_project = await _project_for(client, ada, "Ada's")

    forbidden = await client.get(f"/projects/{ada_project}", headers=grace)
    missing = await client.get("/projects/99999999", headers=grace)

    assert forbidden.status_code == missing.status_code
    assert forbidden.json() == missing.json()


async def test_a_users_token_does_not_grant_another_users_listing(
    client: AsyncClient,
) -> None:
    ada = await _register(client, "ada@example.com")
    grace = await _register(client, "grace@example.com")
    await _project_for(client, ada, "Ada's")
    await _project_for(client, grace, "Grace's")

    ada_list = (await client.get("/projects", headers=ada)).json()
    grace_list = (await client.get("/projects", headers=grace)).json()

    assert {p["name"] for p in ada_list} == {"Ada's"}
    assert {p["name"] for p in grace_list} == {"Grace's"}


async def test_a_tampered_token_grants_nothing(client: AsyncClient) -> None:
    ada = await _register(client, "ada@example.com")
    tampered = ada["Authorization"][:-1] + ("a" if ada["Authorization"][-1] != "a" else "b")

    response = await client.get("/projects", headers={"Authorization": tampered})

    assert response.status_code == 401


async def test_signing_out_everywhere_stops_the_stolen_token(
    client: AsyncClient,
) -> None:
    """Replay triggers family revocation, so the thief's token dies too."""
    registered = (
        await client.post(
            "/auth/register", json={"email": "ada@example.com", "password": PASSWORD}
        )
    ).json()
    stolen = registered["refresh_token"]

    # The real client rotates once.
    rotated = (
        await client.post("/auth/refresh", json={"refresh_token": stolen})
    ).json()

    # The thief replays the copy they took.
    replay = await client.post("/auth/refresh", json={"refresh_token": stolen})
    assert replay.status_code == 401

    # And the genuine client's newest token is dead too, forcing a real sign-in.
    after = await client.post(
        "/auth/refresh", json={"refresh_token": rotated["refresh_token"]}
    )
    assert after.status_code == 401
```

- [ ] **Step 2: Run the suite**

Run: `cd /d/Projects/DBQuery/backend && .venv/Scripts/python -m pytest tests/test_isolation.py -v`
Expected: PASS, 6 tests.

- [ ] **Step 3: Run the whole backend suite and the linters**

Run:
```bash
cd /d/Projects/DBQuery/backend
.venv/Scripts/python -m pytest -q
.venv/Scripts/ruff check app tests run.py
.venv/Scripts/mypy app
.venv/Scripts/alembic check
```
Expected: all tests pass, ruff clean, mypy clean, `No new upgrade operations detected.`

- [ ] **Step 4: Commit**

```bash
git add backend/tests/test_isolation.py
git commit -m "test(auth): add cross-user isolation suite for PRD F1

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Cqgmb8EqhP1PTeqJPA8wHF"
```

---

### Task 8: Frontend API client and session state

**Files:**
- Create: `frontend/src/lib/auth-storage.ts`, `frontend/src/lib/api.ts`, `frontend/src/features/auth/AuthContext.tsx`, `frontend/.env.development`
- Test: `frontend/src/lib/__tests__/api.test.ts`

**Interfaces:**
- Consumes: the endpoints from Tasks 5–6
- Produces:
  - `apiFetch<T>(path: string, options?: RequestInit): Promise<T>` — attaches the bearer token, retries once after a silent refresh on 401, throws `ApiError`
  - `ApiError` — `{ status: number; code: string; message: string }`
  - `setAccessToken(token: string | null)`, `getAccessToken()`, `setRefreshToken(token: string | null)`, `getRefreshToken()`, `clearTokens()`
  - `AuthProvider`, `useAuth()` → `{ user, status, login, register, signOut }`

- [ ] **Step 1: Write the failing test**

`frontend/src/lib/__tests__/api.test.ts`:
```typescript
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError, apiFetch } from '../api'
import { clearTokens, setAccessToken, setRefreshToken } from '../auth-storage'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('apiFetch', () => {
  beforeEach(() => {
    clearTokens()
    vi.restoreAllMocks()
  })

  afterEach(() => {
    clearTokens()
  })

  it('returns the parsed body on success', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(jsonResponse({ id: 1, name: 'Sales' })),
    )

    await expect(apiFetch('/projects/1')).resolves.toEqual({
      id: 1,
      name: 'Sales',
    })
  })

  it('attaches the access token as a bearer header', async () => {
    setAccessToken('token-abc')
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse([]))
    vi.stubGlobal('fetch', fetchMock)

    await apiFetch('/projects')

    const headers = new Headers(fetchMock.mock.calls[0][1].headers)
    expect(headers.get('Authorization')).toBe('Bearer token-abc')
  })

  it('sends no Authorization header when signed out', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse([]))
    vi.stubGlobal('fetch', fetchMock)

    await apiFetch('/projects')

    const headers = new Headers(fetchMock.mock.calls[0][1].headers)
    expect(headers.get('Authorization')).toBeNull()
  })

  it('refreshes once on 401 and replays the original request', async () => {
    setAccessToken('stale-token')
    setRefreshToken('refresh-abc')
    const fetchMock = vi
      .fn()
      // 1. original request rejected
      .mockResolvedValueOnce(
        jsonResponse({ error: { code: 'unauthorized', message: 'no' } }, 401),
      )
      // 2. refresh succeeds
      .mockResolvedValueOnce(
        jsonResponse({
          access_token: 'fresh-token',
          refresh_token: 'refresh-def',
          token_type: 'bearer',
          user: { id: 1, email: 'ada@example.com' },
        }),
      )
      // 3. replay succeeds
      .mockResolvedValueOnce(jsonResponse([{ id: 1, name: 'Sales' }]))
    vi.stubGlobal('fetch', fetchMock)

    const result = await apiFetch('/projects')

    expect(result).toEqual([{ id: 1, name: 'Sales' }])
    expect(fetchMock).toHaveBeenCalledTimes(3)
    const replayHeaders = new Headers(fetchMock.mock.calls[2][1].headers)
    expect(replayHeaders.get('Authorization')).toBe('Bearer fresh-token')
  })

  it('does not retry more than once', async () => {
    setAccessToken('stale-token')
    setRefreshToken('refresh-abc')
    const unauthorized = () =>
      jsonResponse({ error: { code: 'unauthorized', message: 'no' } }, 401)
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(unauthorized())
      .mockResolvedValueOnce(
        jsonResponse({
          access_token: 'fresh-token',
          refresh_token: 'refresh-def',
          token_type: 'bearer',
          user: { id: 1, email: 'ada@example.com' },
        }),
      )
      .mockResolvedValueOnce(unauthorized())
    vi.stubGlobal('fetch', fetchMock)

    await expect(apiFetch('/projects')).rejects.toBeInstanceOf(ApiError)
    expect(fetchMock).toHaveBeenCalledTimes(3)
  })

  it('clears the session when the refresh itself fails', async () => {
    setAccessToken('stale-token')
    setRefreshToken('dead-refresh')
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValueOnce(
          jsonResponse({ error: { code: 'unauthorized', message: 'no' } }, 401),
        )
        .mockResolvedValueOnce(
          jsonResponse({ error: { code: 'unauthorized', message: 'no' } }, 401),
        ),
    )

    await expect(apiFetch('/projects')).rejects.toBeInstanceOf(ApiError)
    const { getAccessToken } = await import('../auth-storage')
    expect(getAccessToken()).toBeNull()
  })

  it('surfaces the error envelope message', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse(
          { error: { code: 'conflict', message: 'That name is taken.' } },
          409,
        ),
      ),
    )

    await expect(apiFetch('/projects', { method: 'POST' })).rejects.toMatchObject({
      status: 409,
      code: 'conflict',
      message: 'That name is taken.',
    })
  })

  it('returns null for a 204', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 204 })))

    await expect(apiFetch('/projects/1', { method: 'DELETE' })).resolves.toBeNull()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /d/Projects/DBQuery/frontend && npx vitest run`
Expected: FAIL — cannot resolve `../api`.

- [ ] **Step 3: Write the token storage**

`frontend/src/lib/auth-storage.ts`:
```typescript
/**
 * Where tokens live.
 *
 * The access token stays in memory only, so it dies with the tab and never
 * sits in storage an XSS payload could read. The refresh token has to survive
 * a page reload for "stay signed in" to mean anything, so it goes to
 * localStorage — a deliberate trade-off. An httpOnly cookie would be stronger
 * but needs a cookie-based API, which PRD F1 does not describe.
 */

const REFRESH_KEY = 'dbpilot.refresh'

let accessToken: string | null = null

export function getAccessToken(): string | null {
  return accessToken
}

export function setAccessToken(token: string | null): void {
  accessToken = token
}

export function getRefreshToken(): string | null {
  try {
    return localStorage.getItem(REFRESH_KEY)
  } catch {
    return null
  }
}

export function setRefreshToken(token: string | null): void {
  try {
    if (token === null) localStorage.removeItem(REFRESH_KEY)
    else localStorage.setItem(REFRESH_KEY, token)
  } catch {
    // Private browsing can refuse storage. The session still works for this tab.
  }
}

export function clearTokens(): void {
  setAccessToken(null)
  setRefreshToken(null)
}
```

- [ ] **Step 4: Write the API client**

`frontend/.env.development`:
```dotenv
VITE_API_URL=http://127.0.0.1:8000
```

`frontend/src/lib/api.ts`:
```typescript
import {
  clearTokens,
  getAccessToken,
  getRefreshToken,
  setAccessToken,
  setRefreshToken,
} from './auth-storage'

const BASE_URL = import.meta.env.VITE_API_URL ?? 'http://127.0.0.1:8000'

export class ApiError extends Error {
  readonly status: number
  readonly code: string

  constructor(status: number, code: string, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
  }
}

export interface AuthPayload {
  access_token: string
  refresh_token: string
  token_type: string
  user: { id: number; email: string }
}

async function toError(response: Response): Promise<ApiError> {
  let code = 'http_error'
  let message = 'Something went wrong. Try again.'
  try {
    const body = await response.json()
    if (body?.error) {
      code = body.error.code ?? code
      message = body.error.message ?? message
    }
  } catch {
    // A non-JSON body leaves the defaults, which are already readable.
  }
  return new ApiError(response.status, code, message)
}

function request(path: string, options: RequestInit): Promise<Response> {
  const headers = new Headers(options.headers)
  if (!headers.has('Content-Type') && options.body !== undefined) {
    headers.set('Content-Type', 'application/json')
  }
  const token = getAccessToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)

  return fetch(`${BASE_URL}${path}`, { ...options, headers })
}

/** Exchange the refresh token for a new pair. Returns false if it failed. */
export async function refreshSession(): Promise<boolean> {
  const refreshToken = getRefreshToken()
  if (!refreshToken) return false

  const response = await fetch(`${BASE_URL}/auth/refresh`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: refreshToken }),
  })
  if (!response.ok) {
    clearTokens()
    return false
  }

  const payload: AuthPayload = await response.json()
  setAccessToken(payload.access_token)
  setRefreshToken(payload.refresh_token)
  return true
}

export async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  let response = await request(path, options)

  // Exactly one retry. The access token expires every 30 minutes, so a 401 on
  // an otherwise valid session is routine and should not reach the user.
  if (response.status === 401 && (await refreshSession())) {
    response = await request(path, options)
  }

  if (!response.ok) throw await toError(response)
  if (response.status === 204) return null as T
  return (await response.json()) as T
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd /d/Projects/DBQuery/frontend && npx vitest run src/lib`
Expected: PASS, 9 tests.

- [ ] **Step 6: Write the auth context**

`frontend/src/features/auth/AuthContext.tsx`:
```tsx
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'

import {
  apiFetch,
  refreshSession,
  type AuthPayload,
} from '../../lib/api'
import { clearTokens, setAccessToken, setRefreshToken } from '../../lib/auth-storage'

export interface SessionUser {
  id: number
  email: string
}

type Status = 'loading' | 'authenticated' | 'anonymous'

interface AuthValue {
  user: SessionUser | null
  status: Status
  login: (email: string, password: string) => Promise<void>
  register: (email: string, password: string) => Promise<void>
  signOut: () => void
}

const AuthContext = createContext<AuthValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<SessionUser | null>(null)
  const [status, setStatus] = useState<Status>('loading')

  // The access token lives in memory, so a reload starts signed out until the
  // stored refresh token proves otherwise.
  useEffect(() => {
    let cancelled = false
    void (async () => {
      const restored = await refreshSession()
      if (cancelled) return
      if (!restored) {
        setStatus('anonymous')
        return
      }
      try {
        const me = await apiFetch<SessionUser>('/auth/me')
        if (cancelled) return
        setUser(me)
        setStatus('authenticated')
      } catch {
        if (!cancelled) setStatus('anonymous')
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  const adopt = useCallback((payload: AuthPayload) => {
    setAccessToken(payload.access_token)
    setRefreshToken(payload.refresh_token)
    setUser(payload.user)
    setStatus('authenticated')
  }, [])

  const login = useCallback(
    async (email: string, password: string) => {
      adopt(
        await apiFetch<AuthPayload>('/auth/login', {
          method: 'POST',
          body: JSON.stringify({ email, password }),
        }),
      )
    },
    [adopt],
  )

  const register = useCallback(
    async (email: string, password: string) => {
      adopt(
        await apiFetch<AuthPayload>('/auth/register', {
          method: 'POST',
          body: JSON.stringify({ email, password }),
        }),
      )
    },
    [adopt],
  )

  const signOut = useCallback(() => {
    clearTokens()
    setUser(null)
    setStatus('anonymous')
  }, [])

  const value = useMemo(
    () => ({ user, status, login, register, signOut }),
    [user, status, login, register, signOut],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthValue {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth must be used inside AuthProvider')
  return value
}
```

- [ ] **Step 7: Verify the build**

Run: `cd /d/Projects/DBQuery/frontend && npm run build`
Expected: exit 0.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/lib/ frontend/src/features/ frontend/.env.development
git commit -m "feat(frontend): add API client with silent refresh and session state

Access token stays in memory; only the refresh token is persisted, so an XSS
payload cannot lift a working access token out of storage.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Cqgmb8EqhP1PTeqJPA8wHF"
```

---

### Task 9: Form primitives and auth screens

**Files:**
- Create: `frontend/src/components/Button.tsx`, `frontend/src/components/Field.tsx`, `frontend/src/features/auth/AuthForm.tsx`, `frontend/src/routes/Login.tsx`, `frontend/src/routes/Register.tsx`
- Test: `frontend/src/features/auth/__tests__/AuthForm.test.tsx`

**Interfaces:**
- Consumes: `useAuth()` (Task 8), `Eyebrow` / `SplitHeadline` (Phase 1)
- Produces:
  - `<Button variant="primary" | "ghost" type="submit" disabled>` — pill, PRD §10.5
  - `<Field id label type value onChange error autoComplete required>` — labelled input
  - `<AuthForm mode="login" | "register" />` — shared by both screens

- [ ] **Step 1: Write the failing test**

`frontend/src/features/auth/__tests__/AuthForm.test.tsx`:
```tsx
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { AuthForm } from '../AuthForm'

const login = vi.fn()
const register = vi.fn()

vi.mock('../AuthContext', () => ({
  useAuth: () => ({
    user: null,
    status: 'anonymous',
    login,
    register,
    signOut: vi.fn(),
  }),
}))

function renderForm(mode: 'login' | 'register') {
  return render(
    <MemoryRouter>
      <AuthForm mode={mode} />
    </MemoryRouter>,
  )
}

describe('AuthForm', () => {
  beforeEach(() => {
    login.mockReset().mockResolvedValue(undefined)
    register.mockReset().mockResolvedValue(undefined)
  })

  it('labels every input, so the form is usable by keyboard and screen reader', () => {
    renderForm('login')

    expect(screen.getByLabelText(/email/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument()
  })

  it('submits the credentials on login', async () => {
    renderForm('login')
    await userEvent.type(screen.getByLabelText(/email/i), 'ada@example.com')
    await userEvent.type(screen.getByLabelText(/password/i), 'a-good-password')
    await userEvent.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() =>
      expect(login).toHaveBeenCalledWith('ada@example.com', 'a-good-password'),
    )
  })

  it('calls register in register mode', async () => {
    renderForm('register')
    await userEvent.type(screen.getByLabelText(/email/i), 'ada@example.com')
    await userEvent.type(screen.getByLabelText(/password/i), 'a-good-password')
    await userEvent.click(screen.getByRole('button', { name: /create account/i }))

    await waitFor(() =>
      expect(register).toHaveBeenCalledWith('ada@example.com', 'a-good-password'),
    )
  })

  it('rejects a short password before calling the API', async () => {
    renderForm('register')
    await userEvent.type(screen.getByLabelText(/email/i), 'ada@example.com')
    await userEvent.type(screen.getByLabelText(/password/i), 'short')
    await userEvent.click(screen.getByRole('button', { name: /create account/i }))

    expect(await screen.findByText(/at least 8 characters/i)).toBeInTheDocument()
    expect(register).not.toHaveBeenCalled()
  })

  it('shows the server message when sign-in fails', async () => {
    login.mockRejectedValue(
      Object.assign(new Error('That email and password combination is not correct.'), {
        status: 401,
        code: 'unauthorized',
      }),
    )
    renderForm('login')
    await userEvent.type(screen.getByLabelText(/email/i), 'ada@example.com')
    await userEvent.type(screen.getByLabelText(/password/i), 'a-good-password')
    await userEvent.click(screen.getByRole('button', { name: /sign in/i }))

    expect(
      await screen.findByText(/combination is not correct/i),
    ).toBeInTheDocument()
  })

  it('announces errors to assistive technology', async () => {
    renderForm('register')
    await userEvent.type(screen.getByLabelText(/email/i), 'ada@example.com')
    await userEvent.type(screen.getByLabelText(/password/i), 'short')
    await userEvent.click(screen.getByRole('button', { name: /create account/i }))

    expect(await screen.findByRole('alert')).toBeInTheDocument()
  })
})
```

Install the interaction library:
```bash
cd /d/Projects/DBQuery/frontend
npm install -D @testing-library/user-event
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /d/Projects/DBQuery/frontend && npx vitest run src/features`
Expected: FAIL — cannot resolve `../AuthForm`.

- [ ] **Step 3: Write the primitives**

`frontend/src/components/Button.tsx`:
```tsx
import type { ButtonHTMLAttributes, ReactNode } from 'react'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'ghost'
  children: ReactNode
}

/** PRD 10.5: full pills. 10.8: canvas-coloured text on the lime fill. */
export function Button({
  variant = 'primary',
  className = '',
  children,
  ...rest
}: ButtonProps) {
  const base =
    'rounded-full px-6 py-3 text-body font-medium transition-all duration-150 ' +
    'disabled:cursor-not-allowed disabled:opacity-50'
  const look =
    variant === 'primary'
      ? 'bg-accent text-canvas hover:-translate-y-0.5'
      : 'border border-border text-text-secondary hover:border-border-hover hover:text-text-primary'

  return (
    <button className={`${base} ${look} ${className}`} {...rest}>
      {children}
    </button>
  )
}
```

`frontend/src/components/Field.tsx`:
```tsx
import type { InputHTMLAttributes } from 'react'

interface FieldProps extends InputHTMLAttributes<HTMLInputElement> {
  id: string
  label: string
  error?: string
}

/** A labelled input. The label is always rendered, never a placeholder. */
export function Field({ id, label, error, className = '', ...rest }: FieldProps) {
  const errorId = `${id}-error`

  return (
    <div className="flex flex-col gap-2">
      <label htmlFor={id} className="text-small text-text-secondary">
        {label}
      </label>
      <input
        id={id}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? errorId : undefined}
        className={
          'rounded-2xl border border-border bg-surface px-4 py-3 text-body ' +
          'text-text-primary transition-colors duration-150 ' +
          'placeholder:text-text-tertiary hover:border-border-hover ' +
          'focus:border-border-hover focus:outline-2 focus:outline-offset-2 ' +
          `focus:outline-accent ${className}`
        }
        {...rest}
      />
      {error ? (
        <p id={errorId} role="alert" className="text-small text-text-primary">
          {error}
        </p>
      ) : null}
    </div>
  )
}
```

Error text uses `--text-primary`, not lime: PRD §10.8 forbids the accent on
small copy.

- [ ] **Step 4: Write the shared form**

`frontend/src/features/auth/AuthForm.tsx`:
```tsx
import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { Button } from '../../components/Button'
import { Eyebrow } from '../../components/Eyebrow'
import { Field } from '../../components/Field'
import { SplitHeadline } from '../../components/SplitHeadline'
import { useAuth } from './AuthContext'

const MIN_PASSWORD_LENGTH = 8

const COPY = {
  login: {
    eyebrow: 'Sign in',
    lead: 'Welcome back.',
    trail: 'Your projects are where you left them.',
    submit: 'Sign in',
    switchText: 'No account yet?',
    switchLabel: 'Create one',
    switchTo: '/register',
  },
  register: {
    eyebrow: 'Create account',
    lead: 'Ask your database a question.',
    trail: 'It answers in SQL you can actually read.',
    submit: 'Create account',
    switchText: 'Already have an account?',
    switchLabel: 'Sign in',
    switchTo: '/login',
  },
} as const

export function AuthForm({ mode }: { mode: 'login' | 'register' }) {
  const copy = COPY[mode]
  const { login, register } = useAuth()
  const navigate = useNavigate()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [passwordError, setPasswordError] = useState('')
  const [formError, setFormError] = useState('')
  const [busy, setBusy] = useState(false)

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setFormError('')
    setPasswordError('')

    if (mode === 'register' && password.length < MIN_PASSWORD_LENGTH) {
      setPasswordError(`Use at least ${MIN_PASSWORD_LENGTH} characters.`)
      return
    }

    setBusy(true)
    try {
      if (mode === 'login') await login(email, password)
      else await register(email, password)
      navigate('/projects', { replace: true })
    } catch (error) {
      setFormError(
        error instanceof Error
          ? error.message
          : 'Something went wrong. Try again.',
      )
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-[440px] flex-col justify-center px-6 py-24">
      <Eyebrow>{copy.eyebrow}</Eyebrow>

      <div className="mt-8">
        <SplitHeadline as="h2" lead={copy.lead} trail={copy.trail} />
      </div>

      <form onSubmit={handleSubmit} className="mt-12 flex flex-col gap-6" noValidate>
        <Field
          id="email"
          label="Email"
          type="email"
          autoComplete="email"
          required
          value={email}
          onChange={(event) => setEmail(event.target.value)}
        />
        <Field
          id="password"
          label="Password"
          type="password"
          autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
          required
          value={password}
          error={passwordError}
          onChange={(event) => setPassword(event.target.value)}
        />

        {formError ? (
          <p role="alert" className="text-small text-text-primary">
            {formError}
          </p>
        ) : null}

        <Button type="submit" disabled={busy}>
          {busy ? 'Working…' : copy.submit}
        </Button>
      </form>

      <p className="mt-8 text-small text-text-secondary">
        {copy.switchText}{' '}
        <Link
          to={copy.switchTo}
          className="text-text-primary underline underline-offset-4"
        >
          {copy.switchLabel}
        </Link>
      </p>
    </main>
  )
}
```

- [ ] **Step 5: Write the two screens**

`frontend/src/routes/Login.tsx`:
```tsx
import { AuthForm } from '../features/auth/AuthForm'

export function Login() {
  return <AuthForm mode="login" />
}
```

`frontend/src/routes/Register.tsx`:
```tsx
import { AuthForm } from '../features/auth/AuthForm'

export function Register() {
  return <AuthForm mode="register" />
}
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd /d/Projects/DBQuery/frontend && npx vitest run src/features`
Expected: PASS, 6 tests.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/Button.tsx frontend/src/components/Field.tsx \
        frontend/src/features/auth/ frontend/src/routes/Login.tsx \
        frontend/src/routes/Register.tsx frontend/package.json frontend/package-lock.json
git commit -m "feat(frontend): add form primitives and auth screens

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Cqgmb8EqhP1PTeqJPA8wHF"
```

---

### Task 10: Projects screen and protected routing

**Files:**
- Create: `frontend/src/routes/ProtectedRoute.tsx`, `frontend/src/routes/Projects.tsx`
- Modify: `frontend/src/App.tsx`, `frontend/src/main.tsx`
- Test: `frontend/src/routes/__tests__/Projects.test.tsx`

**Interfaces:**
- Consumes: `apiFetch` (Task 8), `useAuth` (Task 8), `Button` / `Field` / `Eyebrow` (Task 9)
- Produces: the `/projects` screen and the `<ProtectedRoute>` wrapper every later phase's screen sits inside.

- [ ] **Step 1: Write the failing test**

`frontend/src/routes/__tests__/Projects.test.tsx`:
```tsx
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { Projects } from '../Projects'

const apiFetch = vi.fn()

vi.mock('../../lib/api', () => ({
  apiFetch: (...args: unknown[]) => apiFetch(...args),
  ApiError: class extends Error {},
}))

vi.mock('../../features/auth/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 1, email: 'ada@example.com' },
    status: 'authenticated',
    login: vi.fn(),
    register: vi.fn(),
    signOut: vi.fn(),
  }),
}))

function renderProjects() {
  return render(
    <MemoryRouter>
      <Projects />
    </MemoryRouter>,
  )
}

describe('Projects', () => {
  beforeEach(() => {
    apiFetch.mockReset()
  })

  it('invites a first project when the list is empty', async () => {
    apiFetch.mockResolvedValue([])
    renderProjects()

    // PRD 10.9: empty states are invitations, not apologies.
    expect(await screen.findByText(/no projects yet/i)).toBeInTheDocument()
  })

  it('lists the projects it loaded', async () => {
    apiFetch.mockResolvedValue([
      {
        id: 1,
        name: 'Sales',
        source_type: 'upload',
        schema_name: null,
        table_count: 3,
        is_demo: false,
        created_at: '2026-09-06T12:00:00Z',
      },
    ])
    renderProjects()

    expect(await screen.findByText('Sales')).toBeInTheDocument()
  })

  it('creates a project and shows it without a reload', async () => {
    apiFetch
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce({
        id: 2,
        name: 'Inventory',
        source_type: 'upload',
        schema_name: null,
        table_count: null,
        is_demo: false,
        created_at: '2026-09-06T12:00:00Z',
      })
    renderProjects()
    await screen.findByText(/no projects yet/i)

    await userEvent.type(screen.getByLabelText(/project name/i), 'Inventory')
    await userEvent.click(screen.getByRole('button', { name: /create project/i }))

    expect(await screen.findByText('Inventory')).toBeInTheDocument()
  })

  it('shows the server message when creation is refused', async () => {
    apiFetch
      .mockResolvedValueOnce([])
      .mockRejectedValueOnce(new Error('You already have a project called \'Sales\'.'))
    renderProjects()
    await screen.findByText(/no projects yet/i)

    await userEvent.type(screen.getByLabelText(/project name/i), 'Sales')
    await userEvent.click(screen.getByRole('button', { name: /create project/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/already have a project/i)
  })

  it('removes a project from the list after deleting it', async () => {
    apiFetch
      .mockResolvedValueOnce([
        {
          id: 1,
          name: 'Sales',
          source_type: 'upload',
          schema_name: null,
          table_count: 0,
          is_demo: false,
          created_at: '2026-09-06T12:00:00Z',
        },
      ])
      .mockResolvedValueOnce(null)
    renderProjects()
    await screen.findByText('Sales')

    await userEvent.click(screen.getByRole('button', { name: /delete sales/i }))

    await waitFor(() => expect(screen.queryByText('Sales')).not.toBeInTheDocument())
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /d/Projects/DBQuery/frontend && npx vitest run src/routes`
Expected: FAIL — cannot resolve `../Projects`.

- [ ] **Step 3: Write the protected route**

`frontend/src/routes/ProtectedRoute.tsx`:
```tsx
import type { ReactNode } from 'react'
import { Navigate } from 'react-router-dom'

import { useAuth } from '../features/auth/AuthContext'

export function ProtectedRoute({ children }: { children: ReactNode }) {
  const { status } = useAuth()

  if (status === 'loading') {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <p className="text-small text-text-secondary">Checking your session…</p>
      </div>
    )
  }
  if (status === 'anonymous') return <Navigate to="/login" replace />
  return <>{children}</>
}
```

- [ ] **Step 4: Write the projects screen**

`frontend/src/routes/Projects.tsx`:
```tsx
import { useCallback, useEffect, useState, type FormEvent } from 'react'

import { Button } from '../components/Button'
import { Eyebrow } from '../components/Eyebrow'
import { Field } from '../components/Field'
import { SplitHeadline } from '../components/SplitHeadline'
import { useAuth } from '../features/auth/AuthContext'
import { apiFetch } from '../lib/api'

interface Project {
  id: number
  name: string
  source_type: 'upload' | 'connection'
  schema_name: string | null
  table_count: number | null
  is_demo: boolean
  created_at: string
}

export function Projects() {
  const { user, signOut } = useAuth()
  const [projects, setProjects] = useState<Project[]>([])
  const [name, setName] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [loaded, setLoaded] = useState(false)

  const load = useCallback(async () => {
    try {
      setProjects(await apiFetch<Project[]>('/projects'))
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not load projects.')
    } finally {
      setLoaded(true)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  async function handleCreate(event: FormEvent) {
    event.preventDefault()
    setError('')
    setBusy(true)
    try {
      const created = await apiFetch<Project>('/projects', {
        method: 'POST',
        body: JSON.stringify({ name, source_type: 'upload' }),
      })
      setProjects((current) => [...current, created])
      setName('')
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not create it.')
    } finally {
      setBusy(false)
    }
  }

  async function handleDelete(project: Project) {
    setError('')
    try {
      await apiFetch<null>(`/projects/${project.id}`, { method: 'DELETE' })
      setProjects((current) => current.filter((one) => one.id !== project.id))
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not delete it.')
    }
  }

  return (
    <main className="mx-auto max-w-[1200px] px-6 py-24">
      <div className="flex flex-wrap items-start justify-between gap-6">
        <div>
          <Eyebrow>Projects</Eyebrow>
          <div className="mt-6">
            <SplitHeadline
              as="h2"
              lead="Your databases."
              trail="Pick one, or start another."
            />
          </div>
        </div>
        <div className="flex items-center gap-4">
          <span className="text-small text-text-secondary">{user?.email}</span>
          <Button variant="ghost" onClick={signOut}>
            Sign out
          </Button>
        </div>
      </div>

      <form
        onSubmit={handleCreate}
        className="mt-16 flex flex-wrap items-end gap-4 rounded-2xl border border-border bg-surface p-6"
      >
        <div className="min-w-[260px] flex-1">
          <Field
            id="project-name"
            label="Project name"
            required
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
        </div>
        <Button type="submit" disabled={busy || name.trim().length === 0}>
          {busy ? 'Creating…' : 'Create project'}
        </Button>
      </form>

      {error ? (
        <p role="alert" className="mt-6 text-small text-text-primary">
          {error}
        </p>
      ) : null}

      <section className="mt-16">
        {loaded && projects.length === 0 ? (
          <p className="text-body text-text-secondary">
            No projects yet. Create your first one above.
          </p>
        ) : (
          <ul className="divide-y divide-border border-y border-border">
            {projects.map((project) => (
              <li
                key={project.id}
                className="flex flex-wrap items-center justify-between gap-4 py-5"
              >
                <div>
                  <p className="text-h3 text-text-primary">{project.name}</p>
                  <p className="mt-1 text-small text-text-secondary">
                    {project.source_type === 'upload' ? 'Uploaded data' : 'Connection'}
                    {project.table_count !== null
                      ? ` · ${project.table_count} tables`
                      : ''}
                  </p>
                </div>
                <Button
                  variant="ghost"
                  aria-label={`Delete ${project.name}`}
                  onClick={() => void handleDelete(project)}
                >
                  Delete
                </Button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  )
}
```

- [ ] **Step 5: Wire the routes**

`frontend/src/App.tsx`:
```tsx
import { Navigate, Route, Routes } from 'react-router-dom'

import { Login } from './routes/Login'
import { Projects } from './routes/Projects'
import { ProtectedRoute } from './routes/ProtectedRoute'
import { Register } from './routes/Register'
import { Tokens } from './routes/Tokens'

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route
        path="/projects"
        element={
          <ProtectedRoute>
            <Projects />
          </ProtectedRoute>
        }
      />
      <Route path="/tokens" element={<Tokens />} />
      <Route path="*" element={<Navigate to="/projects" replace />} />
    </Routes>
  )
}
```

In `frontend/src/main.tsx`, add
`import { AuthProvider } from './features/auth/AuthContext'` and wrap `<App />`
in `<AuthProvider>` inside `<BrowserRouter>`.

- [ ] **Step 6: Run test to verify it passes**

Run: `cd /d/Projects/DBQuery/frontend && npx vitest run`
Expected: PASS, 26 tests across 4 files.

- [ ] **Step 7: Verify the whole stack end to end by hand**

Run, in two terminals:
```bash
cd /d/Projects/DBQuery/backend && .venv/Scripts/python run.py
cd /d/Projects/DBQuery/frontend && npm run dev
```
Then at `http://localhost:5173`: register a new account, confirm it lands on
`/projects`, create a project, reload the page and confirm you are still signed
in (this exercises refresh-on-load), delete the project, sign out, and confirm
`/projects` redirects to `/login`.

- [ ] **Step 8: Run every check**

Run:
```bash
cd /d/Projects/DBQuery/backend
.venv/Scripts/python -m pytest -q
.venv/Scripts/ruff check app tests run.py
.venv/Scripts/mypy app
.venv/Scripts/alembic check
cd ../frontend
npx vitest run
npm run build
```
Expected: every command exits 0.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/routes/ frontend/src/App.tsx frontend/src/main.tsx
git commit -m "feat(frontend): add projects screen and protected routing

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Cqgmb8EqhP1PTeqJPA8wHF"
```

---

## Phase 2 Definition of Done

- [ ] `POST /auth/register` returns 201 with a token pair and the user
- [ ] `POST /auth/login` with a wrong password and with an unknown email return byte-identical error bodies
- [ ] `POST /auth/refresh` issues a new pair and the old refresh token stops working
- [ ] Replaying a spent refresh token revokes every session for that user
- [ ] Password hashes start `$2b$`, are 60 characters, and record cost ≥ 12
- [ ] Another user's project returns 404 with a body identical to a nonexistent one
- [ ] `alembic upgrade head` reaches `0003_refresh_tokens`; `alembic check` reports no drift
- [ ] `pytest`, `ruff check`, `mypy` all pass in `backend/`
- [ ] `vitest run` and `npm run build` pass in `frontend/`
- [ ] A browser can register, reload while staying signed in, create and delete a project, and sign out
- [ ] No `.env` file and no real secret appears in any commit

## Out of scope for Phase 2

- CSV upload, type inference, per-project schemas and read-only roles — Phase 3.
  Project deletion currently deletes only the metadata row; Phase 3 extends
  `delete_project` to drop the schema, revoke grants, and drop the role in one
  transaction, which is the leak risk named in design document §16.
- The safety gate, query execution, Gemini — Phase 4
- ER diagram, explanation, optimisation — Phase 5
- Dashboard, history, saved queries, export, demo project — Phase 6
- Rate limiting (PRD §9: 30 AI queries and 200 executions per hour) belongs with
  the endpoints it protects, in Phase 4
