from contextlib import asynccontextmanager
from pathlib import Path
import asyncio

from fastapi import FastAPI
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router
from app.config.settings import get_settings
from app.core.exception_handlers import register_exception_handlers
from app.core.logging import setup_logging
from app.core.middleware import RequestIdMiddleware
from app.db.base import Base
from app.db.seed import seed_defaults
from app.db.session import configure_engine, get_session_factory
from app.api.openapi import APP_INTERNAL_ERROR, APP_VALIDATION_ERROR
import app.models  # noqa: F401 — register models


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_engine(settings.database_url)
    factory = get_session_factory()
    from app.db.session import engine

    assert engine is not None
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with factory() as session:
        await seed_defaults(session, settings)
        # Resolve infra once so docker→database fallback logs are visible at boot.
        try:
            from app.providers.manager import get_provider_manager

            mgr = get_provider_manager()
            desc = await mgr.describe_infrastructure(session)
            if desc.get("degraded"):
                import logging

                logging.getLogger("brokerbridge.providers").warning(
                    "infra_degraded_at_startup configured=%s effective=%s message=%s",
                    desc.get("configured_backend"),
                    desc.get("effective_backend"),
                    desc.get("degrade_message"),
                )
        except Exception:  # noqa: BLE001
            pass

    from app.events.consumer import event_consumer_loop

    stop = asyncio.Event()
    ready = asyncio.Event()
    fanin_task = asyncio.create_task(
        event_consumer_loop(group_suffix="-api", stop_event=stop, ready_event=ready),
        name="event-fanin-api",
    )
    try:
        await asyncio.wait_for(ready.wait(), timeout=15.0)
    except TimeoutError:
        pass
    app.state.event_fanin_stop = stop
    app.state.event_fanin_task = fanin_task
    try:
        yield
    finally:
        stop.set()
        fanin_task.cancel()
        try:
            await fanin_task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(settings.log_level)
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description=(
            "Broker Network Gateway & Static IP Orchestrator.\n\n"
            "**Docs:** [Swagger UI](/docs) · [ReDoc](/redoc) · [OpenAPI JSON](/openapi.json)\n\n"
            "**Ops:** [Admin UI](/admin)"
        ),
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url="/redoc" if settings.docs_enabled else None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
        swagger_ui_parameters={"persistAuthorization": True},
        lifespan=lifespan,
        responses={
            422: APP_VALIDATION_ERROR,
            500: APP_INTERNAL_ERROR,
        },
    )
    app.add_middleware(RequestIdMiddleware)
    register_exception_handlers(app)
    app.include_router(api_router)
    admin_dir = Path(__file__).parent / "static" / "admin"
    favicon_path = admin_dir / "favicon.png"

    @app.get("/favicon.ico", include_in_schema=False)
    async def favicon() -> FileResponse | RedirectResponse:
        if favicon_path.is_file():
            return FileResponse(favicon_path, media_type="image/png")
        return RedirectResponse(url="/admin")

    if settings.admin_ui_enabled and admin_dir.exists():
        app.mount("/admin", StaticFiles(directory=admin_dir, html=True), name="admin")

    @app.get("/")
    async def root() -> RedirectResponse:
        return RedirectResponse(url="/admin" if settings.admin_ui_enabled else "/docs")

    return app


app = create_app()
