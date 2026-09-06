"""Project creation and listing. Ownership is enforced by the caller's filter."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError
from app.models import Project, SourceType


async def create_project(
    session: AsyncSession, *, user_id: int, name: str, source_type: SourceType
) -> Project:
    existing = await session.scalar(
        select(Project).where(Project.user_id == user_id, Project.name == name)
    )
    if existing is not None:
        raise ConflictError(f"You already have a project called {name!r}.")

    project = Project(user_id=user_id, name=name, source_type=source_type)
    session.add(project)
    await session.flush()
    return project


async def list_projects(session: AsyncSession, *, user_id: int) -> list[Project]:
    result = await session.scalars(
        select(Project).where(Project.user_id == user_id).order_by(Project.created_at)
    )
    return list(result)


async def delete_project(session: AsyncSession, project: Project) -> None:
    """Phase 3 extends this to drop the project schema and its read-only role.

    Today a project is metadata only, so deleting the row is the whole job.
    """
    await session.delete(project)
    await session.flush()
