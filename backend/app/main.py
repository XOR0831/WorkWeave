"""WorkWeave API: deterministic demo-entry slice. No AI layer is imported or implemented."""

import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.api.routes import router
from app.config import get_settings
from app.errors import ApiError

log = logging.getLogger("workweave")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Local development delivers notifications from this process (DISPATCHER_IN_PROCESS); see ADR-048.
    from app.services import notifications

    notifications.start_worker()
    yield
    notifications.stop_worker()


def create_app() -> FastAPI:
    app = FastAPI(title="WorkWeave API", version="0.1.0", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)

    @app.middleware("http")
    async def request_id(request: Request, call_next):
        request.state.request_id = uuid.uuid4()
        response = await call_next(request)
        response.headers["X-Request-Id"] = str(request.state.request_id)
        # Never cached. A route may add to this (streams also say no-transform so proxies don't buffer them).
        if "no-store" not in response.headers.get("Cache-Control", ""):
            response.headers["Cache-Control"] = "no-store"
        return response

    def error(request: Request, status: int, code: str, message: str, retryable: bool, details: dict | None = None) -> JSONResponse:
        rid = str(getattr(request.state, "request_id", uuid.uuid4()))
        body = {"code": code, "message": message, "retryable": retryable, **(details or {})}
        return JSONResponse({"request_id": rid, "error": body}, status_code=status, headers={"X-Request-Id": rid, "Cache-Control": "no-store"})

    @app.exception_handler(ApiError)
    async def api_error(request: Request, exc: ApiError):
        return error(request, exc.status, exc.code, exc.message, exc.retryable, exc.details)

    @app.exception_handler(RequestValidationError)
    async def invalid(request: Request, exc: RequestValidationError):
        return error(request, 422, "MALFORMED_INPUT", "The request body isn't valid.", False)

    @app.exception_handler(SQLAlchemyError)
    async def db_error(request: Request, exc: SQLAlchemyError):
        log.exception("database error")
        return error(request, 503, "DEPENDENCY_UNAVAILABLE", "The database didn't respond. Nothing was changed; try again.", True)

    @app.exception_handler(Exception)
    async def unexpected(request: Request, exc: Exception):
        # Transactions roll back before this runs, so nothing partial was committed.
        log.exception("unexpected error")
        return error(request, 500, "DEPENDENCY_UNAVAILABLE", "Something went wrong on the server. Nothing was changed; try again.", True)

    app.include_router(router, prefix=get_settings().api_prefix)
    return app


app = create_app()
