"""One error taxonomy for the whole API.

Every error response uses the envelope
``{"error": {"code": ..., "message": ..., "request_id": ...}}`` and carries
the ``X-Request-ID`` header. Routers raise these instead of bare
``HTTPException``.
"""

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from haruspex_server.api.context import get_request_id

logger = structlog.get_logger("haruspex.errors")


class AppError(Exception):
    code = "internal_error"
    status = 500

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class NotFound(AppError):
    code = "not_found"
    status = 404


class Unauthorized(AppError):
    code = "unauthorized"
    status = 401


class Forbidden(AppError):
    code = "forbidden"
    status = 403


class Conflict(AppError):
    code = "conflict"
    status = 409


class InvalidInput(AppError):
    code = "invalid_input"
    status = 422


class RateLimited(AppError):
    code = "rate_limited"
    status = 429

    def __init__(self, message: str, retry_after_s: float):
        super().__init__(message)
        self.retry_after_s = retry_after_s


def error_response(
    *, code: str, message: str, status: int, headers: dict[str, str] | None = None
) -> JSONResponse:
    request_id = get_request_id()
    base_headers = {"X-Request-ID": request_id}
    if headers:
        base_headers.update(headers)
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "request_id": request_id}},
        headers=base_headers,
    )


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> Response:
        headers: dict[str, str] = {}
        if isinstance(exc, RateLimited):
            headers["Retry-After"] = str(max(1, round(exc.retry_after_s)))
        return error_response(
            code=exc.code, message=exc.message, status=exc.status, headers=headers
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError) -> Response:
        first = exc.errors()[0] if exc.errors() else {}
        loc = ".".join(str(part) for part in first.get("loc", ()))
        msg = first.get("msg", "invalid request")
        return error_response(code="invalid_input", message=f"{loc}: {msg}", status=422)

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(request: Request, exc: StarletteHTTPException) -> Response:
        code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "http_error")
        return error_response(
            code=code,
            message=str(exc.detail),
            status=exc.status_code,
            headers=dict(exc.headers) if exc.headers else None,
        )

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception) -> Response:
        logger.exception("unhandled_error", path=request.url.path)
        return error_response(code="internal_error", message="internal server error", status=500)
