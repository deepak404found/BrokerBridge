from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import jwt

from app.config.settings import Settings


def create_access_token(*, subject: str, role: str, settings: Settings, extra: dict[str, Any] | None = None) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": subject,
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expire_minutes),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str, settings: Settings) -> dict[str, Any]:
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])


def user_id_from_payload(payload: dict[str, Any]) -> UUID:
    return UUID(str(payload["sub"]))
