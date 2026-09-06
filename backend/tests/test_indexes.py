import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration

EXPECTED = {
    "ix_queries_project_id_created_at",
    "ix_queries_user_id_status",
    "ix_projects_user_id",
}


async def test_prd_indexes_exist_after_migration(session: AsyncSession) -> None:
    result = await session.execute(
        text("select indexname from pg_indexes where schemaname = 'dbpilot'")
    )
    present = {row[0] for row in result}

    assert present >= EXPECTED, f"missing: {EXPECTED - present}"


async def test_users_email_is_unique_indexed(session: AsyncSession) -> None:
    """PRD section 6 names users(email) unique as the login lookup path."""
    result = await session.execute(
        text(
            "select indexdef from pg_indexes "
            "where schemaname = 'dbpilot' and tablename = 'users'"
        )
    )
    definitions = " ".join(row[0] for row in result)

    assert "UNIQUE" in definitions
    assert "email" in definitions
