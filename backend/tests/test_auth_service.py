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


async def test_authenticate_accepts_correct_credentials(session: AsyncSession) -> None:
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
