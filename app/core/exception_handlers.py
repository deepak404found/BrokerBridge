import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.errors import AppError
from app.core.middleware import REQUEST_ID_HEADER, get_request_id
from app.schemas.errors import ErrorResponse

logger = logging.getLogger("brokerbridge.errors")


def _envelope(
    *,
    error_code: str,
    message: str,
    request_id: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return ErrorResponse(
        error_code=error_code,
        message=message,
        request_id=request_id,
        details=details or {},
    ).model_dump()


def _error_response(
    *,
    status_code: int,
    error_code: str,
    message: str,
    request_id: str,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=_envelope(
            error_code=error_code,
            message=message,
            request_id=request_id,
            details=details,
        ),
        headers={REQUEST_ID_HEADER: request_id},
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        return _error_response(
            status_code=exc.status_code,
            error_code=exc.error_code,
            message=exc.message,
            request_id=get_request_id(request),
            details=exc.details,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        return _error_response(
            status_code=422,
            error_code="VALIDATION_ERROR",
            message="Request validation failed",
            request_id=get_request_id(request),
            details={"errors": jsonable_encoder(exc.errors())},
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        request: Request,
        exc: StarletteHTTPException,
    ) -> JSONResponse:
        detail = exc.detail
        request_id = get_request_id(request)
        if isinstance(detail, dict) and "error_code" in detail:
            return JSONResponse(
                status_code=exc.status_code,
                content=detail,
                headers={REQUEST_ID_HEADER: request_id},
            )

        message = detail if isinstance(detail, str) else str(detail)
        return _error_response(
            status_code=exc.status_code,
            error_code=f"HTTP_{exc.status_code}",
            message=message,
            request_id=request_id,
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        request_id = get_request_id(request)
        logger.exception("unhandled_error request_id=%s", request_id)
        return _error_response(
            status_code=500,
            error_code="INTERNAL_ERROR",
            message="An unexpected error occurred",
            request_id=request_id,
        )
