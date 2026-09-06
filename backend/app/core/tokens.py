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


def _encode(
    user_id: int, token_type: TokenType, ttl: timedelta
) -> tuple[str, str, datetime]:
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
