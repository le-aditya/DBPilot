"""The authorisation seam. Every protected route goes through here."""

from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import UnauthorizedError
from app.core.tokens import TokenType, decode_token
from app.db.session import get_session
from app.models import User

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
