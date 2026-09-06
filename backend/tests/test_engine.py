import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration


async def test_session_reaches_postgres(session: AsyncSession) -> None:
    result = await session.execute(text("select 1"))

    assert result.scalar_one() == 1


async def test_session_connects_as_the_app_role(session: AsyncSession) -> None:
    result = await session.execute(text("select current_user"))

    assert result.scalar_one() == "dbpilot_app"


async def test_metadata_schema_exists(session: AsyncSession) -> None:
    result = await session.execute(
        text("select nspname from pg_namespace where nspname = 'dbpilot'")
    )

    assert result.scalar_one_or_none() == "dbpilot"
