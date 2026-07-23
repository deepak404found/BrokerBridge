from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router
from app.config.settings import get_settings
from app.core.exception_handlers import register_exception_handlers
from app.core.logging import setup_logging
from app.core.middleware import RequestIdMiddleware
from app.schemas.errors import ErrorResponse


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(settings.log_level)
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url="/redoc" if settings.docs_enabled else None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
        responses={
            422: {"model": ErrorResponse, "description": "Validation error"},
            500: {"model": ErrorResponse, "description": "Internal server error"},
        },
    )
    app.add_middleware(RequestIdMiddleware)
    register_exception_handlers(app)
    app.include_router(api_router)
    if settings.admin_ui_enabled:
        admin_dir = Path(__file__).parent / "static" / "admin"
        if admin_dir.exists():
            app.mount("/admin", StaticFiles(directory=admin_dir, html=True), name="admin")

    @app.get("/")
    async def root() -> RedirectResponse:
        return RedirectResponse(url="/admin" if settings.admin_ui_enabled else "/docs")

    return app


app = create_app()
