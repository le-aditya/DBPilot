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
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False
