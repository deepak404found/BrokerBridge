"""WebSocket feed for Admin Event Bus (outbox auto-refresh)."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.auth.jwt import decode_access_token, user_id_from_payload
from app.config.settings import get_settings
from app.db.session import get_session_factory
from app.events.outbox import list_outbox
from app.models.user import User, UserRole
from app.schemas.events import OutboxEventResponse

logger = logging.getLogger("brokerbridge.ws.events")

router = APIRouter(prefix="/api/v1/ws", tags=["websocket"])

_ALLOWED_ROLES = {UserRole.admin, UserRole.ops, UserRole.readonly}
_POLL_SECONDS = 1.5


def _fingerprint(events: list[dict[str, Any]]) -> str:
    raw = json.dumps(
        [(e.get("id"), e.get("status"), e.get("sent_at"), e.get("error")) for e in events],
        default=str,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def _serialize(rows: list[Any]) -> list[dict[str, Any]]:
    return [OutboxEventResponse.model_validate(r).model_dump(mode="json") for r in rows]


async def _authenticate_ws(token: str | None) -> User | None:
    if not token:
        return None
    settings = get_settings()
    try:
        payload = decode_access_token(token, settings)
        user_id: UUID = user_id_from_payload(payload)
    except Exception:  # noqa: BLE001
        return None
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user is None or not user.is_active or user.role not in _ALLOWED_ROLES:
            return None
        return user


@router.websocket("/events")
async def outbox_events_ws(
    websocket: WebSocket,
    token: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> None:
    """Push outbox snapshots when rows change. Auth via JWT query param `token`."""
    user = await _authenticate_ws(token)
    if user is None:
        await websocket.close(code=4401)
        return

    await websocket.accept()
    factory = get_session_factory()
    last_fp: str | None = None
    try:
        while True:
            async with factory() as session:
                rows = await list_outbox(session, limit=limit)
            events = _serialize(rows)
            fp = _fingerprint(events)
            if fp != last_fp:
                msg_type = "snapshot" if last_fp is None else "update"
                await websocket.send_json(
                    {"type": msg_type, "fingerprint": fp, "events": events}
                )
                last_fp = fp
            await asyncio.sleep(_POLL_SECONDS)
    except WebSocketDisconnect:
        logger.debug("events_ws_disconnected user=%s", user.id)
    except Exception:  # noqa: BLE001
        logger.exception("events_ws_failed")
        try:
            await websocket.close(code=1011)
        except Exception:  # noqa: BLE001
            pass
