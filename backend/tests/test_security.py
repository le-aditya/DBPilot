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
