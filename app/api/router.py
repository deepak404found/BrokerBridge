from fastapi import APIRouter

from app.api.routes import admin_providers, auth, brokers, health, infrastructure, monitoring

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(admin_providers.router)
api_router.include_router(brokers.router)
api_router.include_router(infrastructure.router)
api_router.include_router(monitoring.router)
