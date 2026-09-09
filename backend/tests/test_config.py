import pytest

from app.core.config import Settings

REQUIRED = {
    "DATABASE_URL": "postgresql+psycopg://u:p@localhost:5432/dbpilot",
    "JWT_SECRET": "test-secret",
    "DBPILOT_ENCRYPTION_KEY": "test-fernet-key",
}


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    """Drive Settings the way production does — through the environment."""
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


def test_a_managed_host_url_is_normalised_onto_psycopg3(
    env: pytest.MonkeyPatch,
) -> None:
    """Render and Railway hand out postgresql://, which the async engine rejects."""
    env.setenv("DATABASE_URL", "postgresql://u:p@host:5432/d")

    assert Settings(_env_file=None).database_url == "postgresql+psycopg://u:p@host:5432/d"  # type: ignore[call-arg]


def test_the_older_postgres_scheme_is_normalised_too(env: pytest.MonkeyPatch) -> None:
    env.setenv("DATABASE_URL", "postgres://u:p@host:5432/d")

    assert Settings(_env_file=None).database_url == "postgresql+psycopg://u:p@host:5432/d"  # type: ignore[call-arg]


def test_an_already_qualified_url_is_left_alone(env: pytest.MonkeyPatch) -> None:
    env.setenv("DATABASE_URL", "postgresql+psycopg://u:p@host:5432/d")

    assert Settings(_env_file=None).database_url == "postgresql+psycopg://u:p@host:5432/d"  # type: ignore[call-arg]
