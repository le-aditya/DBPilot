"""Connecting an existing PostgreSQL database. PRD F2.2."""

from datetime import UTC, datetime

from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import OwnedProject, SessionDep
from app.core.errors import NotFoundError, UnprocessableError
from app.models import Connection, SourceType
from app.schemas.connection import (
    ConnectionRequest,
    ConnectionResponse,
    ConnectionTestResponse,
)
from app.services.connections import (
    ConnectionSettings,
    check_connection,
    encrypt_password,
)

router = APIRouter(prefix="/projects/{project_id}", tags=["connections"])


def _settings_from(body: ConnectionRequest) -> ConnectionSettings:
    return ConnectionSettings(
        host=body.host,
        port=body.port,
        database=body.database_name,
        username=body.username,
        password=body.password.get_secret_value(),
        ssl_mode=body.ssl_mode,
    )


@router.post("/connection/test")
async def test(body: ConnectionRequest, project: OwnedProject) -> ConnectionTestResponse:
    """Try the credentials and report what was found. Saves nothing."""
    del project
    result = await check_connection(_settings_from(body))
    return ConnectionTestResponse(
        ok=result.ok,
        message=result.message,
        is_read_only=result.is_read_only,
        schemas=result.schemas,
        table_count=result.table_count,
    )


@router.post("/connection")
async def save(
    body: ConnectionRequest, project: OwnedProject, session: SessionDep
) -> ConnectionResponse:
    """Save the connection, but only after proving the role cannot write.

    PRD F2.2 requires the connection to be tested before save. Refusing a
    writable role here is what makes safety layer 4 real for an external
    database, where DBPilot does not own the grants.
    """
    result = await check_connection(_settings_from(body))
    if not result.ok:
        raise UnprocessableError(result.message)

    existing = await session.scalar(
        select(Connection).where(Connection.project_id == project.id)
    )
    if existing is not None:
        await session.delete(existing)
        await session.flush()

    connection = Connection(
        project_id=project.id,
        host=body.host,
        port=body.port,
        database_name=body.database_name,
        username=body.username,
        password_encrypted=encrypt_password(body.password.get_secret_value()),
        ssl_mode=body.ssl_mode,
        last_tested_at=datetime.now(UTC),
    )
    session.add(connection)

    project.source_type = SourceType.connection
    project.table_count = result.table_count
    await session.commit()

    return ConnectionResponse.model_validate(connection)


@router.get("/connection")
async def show(project: OwnedProject, session: SessionDep) -> ConnectionResponse:
    connection = await session.scalar(
        select(Connection).where(Connection.project_id == project.id)
    )
    if connection is None:
        raise NotFoundError("This project has no connection.")
    return ConnectionResponse.model_validate(connection)
