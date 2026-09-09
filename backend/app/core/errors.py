"""Application errors. PRD section 9: every failure says what happened."""

from typing import Any


class AppError(Exception):
    """Base for errors that map to a JSON response rather than a 500."""

    status_code = 400
    code = "app_error"

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        code: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail or {}
        if status_code is not None:
            self.status_code = status_code
        if code is not None:
            self.code = code

    def to_payload(self) -> dict[str, Any]:
        return {"error": {"code": self.code, "message": self.message, **self.detail}}


class NotFoundError(AppError):
    """Also raised for resources the caller does not own, so ownership never leaks."""

    status_code = 404
    code = "not_found"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"


class UnauthorizedError(AppError):
    status_code = 401
    code = "unauthorized"


class UnprocessableError(AppError):
    """The request parsed, but what it asked for cannot be done."""

    status_code = 422
    code = "unprocessable"


class PayloadTooLargeError(AppError):
    status_code = 413
    code = "payload_too_large"
