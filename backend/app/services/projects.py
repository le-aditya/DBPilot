"""Project creation and listing. Ownership is enforced by the caller's filter."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError
from app.models import Project, SourceType
from app.services.provisioning import deprovision


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
    """Delete the project, its data schema, its grants and its read-only role.

    All four go in one transaction. Dropping only the row would leave the schema
    and the role behind, and roles would accumulate in the cluster for the life
    of the installation — the risk carried forward in design document section 16.
    """
    await deprovision(session, project)
    await session.delete(project)
    await session.flush()
