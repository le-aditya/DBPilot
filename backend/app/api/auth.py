"""Registration, login, and refresh. PRD section 7."""

from fastapi import APIRouter, status

from app.api.deps import CurrentUser, SessionDep
from app.core.tokens import TokenPair
from app.models import User
from app.schemas.auth import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from app.services.auth import (
    authenticate_user,
    issue_tokens,
    register_user,
    rotate_refresh_token,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _token_response(user: User, pair: TokenPair) -> TokenResponse:
    return TokenResponse(
        access_token=pair.access_token,
        refresh_token=pair.refresh_token,
        user=UserResponse(id=user.id, email=user.email),
    )


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, session: SessionDep) -> TokenResponse:
    user = await register_user(session, body.email, body.password)
    pair = await issue_tokens(session, user)
    return _token_response(user, pair)


@router.post("/login")
async def login(body: LoginRequest, session: SessionDep) -> TokenResponse:
    user = await authenticate_user(session, body.email, body.password)
    pair = await issue_tokens(session, user)
    return _token_response(user, pair)


@router.post("/refresh")
async def refresh(body: RefreshRequest, session: SessionDep) -> TokenResponse:
    user, pair = await rotate_refresh_token(session, body.refresh_token)
    return _token_response(user, pair)


@router.get("/me")
async def me(user: CurrentUser) -> UserResponse:
    return UserResponse(id=user.id, email=user.email)
