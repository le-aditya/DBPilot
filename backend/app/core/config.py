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
    # Pinned, not "-latest": the same question against the same schema should
    # not start producing different SQL because a model rolled forward.
    # gemini-2.0-flash was retired. Measured 2026-09-09 against this key:
    # 3.5-flash answered in ~7s, while 3.6-flash and flash-latest were returning
    # 503 "high demand" or hanging past 20s. Revisit if that changes.
    gemini_model: str = "gemini-3.5-flash"

    # Limits — PRD §9
    statement_timeout_seconds: int = 10
    # PRD section 9 budget for the whole AI round trip, retries included --
    # GeminiProvider treats it as a deadline shared across attempts, not as a
    # per-attempt timeout, so retrying cannot quietly multiply the wait.
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
        """Normalise the URL onto psycopg 3, which is the only driver that works.

        Managed hosts (Render, Railway, Heroku) hand out `postgresql://` and
        some still hand out `postgres://`. SQLAlchemy's async engine needs an
        explicit async driver, so an unqualified URL is rewritten rather than
        left to fail at the first connection with an unhelpful error.

        psycopg2 is a different matter: it cannot drive the async engine at all,
        so naming it explicitly is a mistake worth catching loudly at startup.
        """
        if value is None:
            return None
        if "psycopg2" in value:
            raise ValueError(
                "DBPilot requires the psycopg 3 driver: use postgresql+psycopg://"
            )
        for prefix in ("postgresql://", "postgres://"):
            if value.startswith(prefix):
                return "postgresql+psycopg://" + value[len(prefix) :]
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
    return Settings()
