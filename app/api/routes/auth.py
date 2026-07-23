from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.openapi import INVALID_CREDENTIALS, TOKEN_SUCCESS
from app.auth.jwt import create_access_token
from app.auth.passwords import verify_password
from app.config.settings import Settings, get_settings
from app.core.errors import AppError
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import TokenResponse

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post(
    "/token",
    response_model=TokenResponse,
    summary="Obtain JWT access token",
    description="OAuth2 password grant. Use email as username.",
    responses={**TOKEN_SUCCESS, **INVALID_CREDENTIALS},
)
async def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TokenResponse:
    # OAuth2 form uses "username" field; we treat it as email
    result = await db.execute(select(User).where(User.email == form.username))
    user = result.scalar_one_or_none()
    if user is None or not user.password_hash or not verify_password(form.password, user.password_hash):
        raise AppError("UNAUTHORIZED", "Invalid credentials", status_code=401)
    if not user.is_active:
        raise AppError("UNAUTHORIZED", "User inactive", status_code=401)
    token = create_access_token(subject=str(user.id), role=user.role.value, settings=settings)
    return TokenResponse(access_token=token, role=user.role.value, email=user.email)
