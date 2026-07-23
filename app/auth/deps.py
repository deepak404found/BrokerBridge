from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import Depends, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import decode_access_token, user_id_from_payload
from app.config.settings import Settings, get_settings
from app.core.errors import AppError
from app.db.session import get_db
from app.models.user import User, UserRole

# auto_error=False so missing/invalid tokens raise AppError (ErrorResponse envelope)
# instead of FastAPI's default HTTPException. Document 401/403 explicitly on protected
# routes (see app.api.openapi.AUTH_ERRORS); security scheme still appears in OpenAPI.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token", auto_error=False)


async def get_current_user(
    token: Annotated[str | None, Depends(oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> User:
    if not token:
        raise AppError("UNAUTHORIZED", "Not authenticated", status_code=status.HTTP_401_UNAUTHORIZED)
    try:
        payload = decode_access_token(token, settings)
        user_id: UUID = user_id_from_payload(payload)
    except Exception as exc:
        raise AppError("UNAUTHORIZED", "Invalid or expired token", status_code=status.HTTP_401_UNAUTHORIZED) from exc

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise AppError("UNAUTHORIZED", "User not found or inactive", status_code=status.HTTP_401_UNAUTHORIZED)
    return user


def require_roles(*roles: str) -> Callable:
    allowed = {UserRole(r) if not isinstance(r, UserRole) else r for r in roles}

    async def _dep(user: Annotated[User, Depends(get_current_user)]) -> User:
        if user.role not in allowed:
            raise AppError("FORBIDDEN", "Insufficient permissions", status_code=status.HTTP_403_FORBIDDEN)
        return user

    return _dep
