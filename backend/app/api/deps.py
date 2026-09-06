"""The authorisation seam. Every protected route goes through here."""

from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError, UnauthorizedError
from app.core.tokens import TokenType, decode_token
from app.db.session import get_session
from app.models import Project, User

SessionDep = Annotated[AsyncSession, Depends(get_session)]

# auto_error=False so a missing header raises our own UnauthorizedError and
# renders the standard error envelope rather than FastAPI's default shape.
_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    session: SessionDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)] = None,
) -> User:
    if credentials is None:
        raise UnauthorizedError("Sign in to continue.")

    decoded = decode_token(credentials.credentials, TokenType.access)
    user = await session.get(User, decoded.user_id)
    if user is None:
        raise UnauthorizedError("Sign in to continue.")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_owned_project(
    project_id: int, user: CurrentUser, session: SessionDep
) -> Project:
    """Resolve a project the caller owns.

    Someone else's project is reported as 404, never 403 — a 403 would confirm
    the project exists. Design document §6, layer 1.
    """
    project = await session.scalar(
        select(Project).where(Project.id == project_id, Project.user_id == user.id)
    )
    if project is None:
        raise NotFoundError("That project does not exist.")
    return project


OwnedProject = Annotated[Project, Depends(get_owned_project)]
