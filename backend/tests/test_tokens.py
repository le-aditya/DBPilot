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
