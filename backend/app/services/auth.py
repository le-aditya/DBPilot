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


async def authenticate_user(session: AsyncSession, email: str, password: str) -> User:
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
