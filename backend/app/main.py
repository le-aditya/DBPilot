"""Application factory, middleware and exception handlers."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import (
    auth,
    connections,
    erd,
    health,
    insights,
    projects,
    queries,
    schema,
    uploads,
)
from app.core.config import get_settings
from app.core.errors import AppError
from app.db.engine import dispose_engine


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    await dispose_engine()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="DBPilot",
        description="AI-powered database explorer and query assistant",
        version=health.VERSION,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=exc.to_payload())

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": "http_error", "message": str(exc.detail)}},
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(
        _: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # Pydantic puts the original exception object in each error's "ctx",
        # which JSONResponse cannot serialise. Take only what a caller can act
        # on: which field, and what is wrong with it.
        fields = [
            {
                "field": ".".join(
                    str(part) for part in error["loc"] if part != "body"
                ),
                "message": error["msg"],
            }
            for error in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "The request body was not valid.",
                    "fields": fields,
                }
            },
        )

    app.include_router(auth.router)
    app.include_router(health.router)
    app.include_router(projects.router)
    app.include_router(connections.router)
    app.include_router(erd.router)
    app.include_router(insights.router)
    app.include_router(insights.project_router)
    app.include_router(queries.router)
    app.include_router(schema.router)
    app.include_router(uploads.router)
    return app


app = create_app()
