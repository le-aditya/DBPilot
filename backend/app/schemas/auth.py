from pydantic import BaseModel, EmailStr, Field

from app.core.security import MAX_PASSWORD_BYTES

# 8 is the usability floor; 72 is bcrypt's hard limit (see app.core.security).
PasswordField = Field(min_length=8, max_length=MAX_PASSWORD_BYTES)


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = PasswordField


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=MAX_PASSWORD_BYTES)


class RefreshRequest(BaseModel):
    refresh_token: str


class UserResponse(BaseModel):
    id: int
    email: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserResponse
