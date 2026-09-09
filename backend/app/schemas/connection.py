"""External connection request and response bodies. PRD F2.2."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, SecretStr


class ConnectionRequest(BaseModel):
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(default=5432, ge=1, le=65535)
    database_name: str = Field(min_length=1, max_length=63)
    username: str = Field(min_length=1, max_length=63)
    # SecretStr so the password cannot be logged by accident: repr() redacts it.
    password: SecretStr
    ssl_mode: str = "prefer"


class ConnectionTestResponse(BaseModel):
    ok: bool
    message: str
    is_read_only: bool
    schemas: list[str]
    table_count: int


class ConnectionResponse(BaseModel):
    """Never carries the password, encrypted or otherwise."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    host: str
    port: int
    database_name: str
    username: str
    ssl_mode: str
    last_tested_at: datetime | None
    created_at: datetime
