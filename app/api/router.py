from fastapi import APIRouter

from app.api.routes import (
    admin_config,
    admin_providers,
    auth,
    brokers,
    health,
    infrastructure,
    monitoring,
    orders,
    ws_events,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(admin_providers.router)
api_router.include_router(admin_config.router)
api_router.include_router(brokers.router)
api_router.include_router(infrastructure.router)
api_router.include_router(monitoring.router)
api_router.include_router(orders.router)
api_router.include_router(ws_events.router)
