from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.openapi import AUTH_ERRORS, success_response
from app.auth.deps import require_roles
from app.config.settings import Settings, get_settings
from app.db.session import get_db
from app.models.user import User
from app.providers.manager import get_provider_manager
from app.schemas.brokers import SessionStatusResponse
from app.sessions.service import SessionService

router = APIRouter(prefix="/api/v1/monitoring", tags=["monitoring"], responses=AUTH_ERRORS)

_SESSION_EXAMPLE = {
    "broker_account_id": "11111111-1111-4111-8111-111111111111",
    "broker_display_name": "Mock Alpha Broker",
    "status": "valid",
    "expires_at": "2026-07-24T11:00:00Z",
    "updated_at": "2026-07-24T10:00:00Z",
    "has_tokens": True,
}


@router.get(
    "/sessions",
    response_model=list[SessionStatusResponse],
    summary="List broker session statuses",
    responses={200: success_response("Sessions", example=[_SESSION_EXAMPLE])},
)
async def list_sessions(
    _: Annotated[User, Depends(require_roles("admin", "ops", "readonly"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> list[SessionStatusResponse]:
    svc = SessionService(db, settings, get_provider_manager())
    rows = await svc.list_all()
    return [
        SessionStatusResponse(
            broker_account_id=sess.broker_account_id,
            broker_display_name=broker.display_name,
            status=sess.status,
            expires_at=sess.expires_at,
            updated_at=sess.updated_at,
            has_tokens=bool(sess.access_token_encrypted),
        )
        for sess, broker in rows
    ]
