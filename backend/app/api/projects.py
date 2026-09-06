"""Project CRUD. PRD section 7. Every route is scoped to the caller."""

from fastapi import APIRouter, Response, status

from app.api.deps import CurrentUser, OwnedProject, SessionDep
from app.schemas.project import ProjectCreate, ProjectResponse
from app.services.projects import create_project, delete_project, list_projects

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("")
async def index(user: CurrentUser, session: SessionDep) -> list[ProjectResponse]:
    projects = await list_projects(session, user_id=user.id)
    return [ProjectResponse.model_validate(project) for project in projects]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create(
    body: ProjectCreate, user: CurrentUser, session: SessionDep
) -> ProjectResponse:
    project = await create_project(
        session, user_id=user.id, name=body.name, source_type=body.source_type
    )
    return ProjectResponse.model_validate(project)


@router.get("/{project_id}")
async def show(project: OwnedProject) -> ProjectResponse:
    return ProjectResponse.model_validate(project)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def destroy(project: OwnedProject, session: SessionDep) -> Response:
    await delete_project(session, project)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
