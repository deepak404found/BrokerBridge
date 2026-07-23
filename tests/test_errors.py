import pytest
from fastapi import APIRouter
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel

from app.core.errors import AppError


class _EchoIn(BaseModel):
    name: str


def _app_with_error_routes(base_app):
    router = APIRouter()

    @router.get("/__test__/boom")
    async def boom() -> None:
        raise AppError(
            "NO_ROUTE",
            "No eligible broker for capability OPTIONS",
            status_code=409,
            details={"capability": "OPTIONS"},
        )

    @router.get("/__test__/crash")
    async def crash() -> None:
        raise RuntimeError("secret-should-not-leak")

    @router.post("/__test__/echo")
    async def echo(payload: _EchoIn) -> dict[str, str]:
        return {"name": payload.name}

    base_app.include_router(router)
    return base_app


@pytest.fixture
async def error_client(configured_app):
    app = _app_with_error_routes(configured_app)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_app_error_envelope(error_client):
    r = await error_client.get("/__test__/boom", headers={"X-Request-ID": "err-1"})
    assert r.status_code == 409
    body = r.json()
    assert body == {
        "error_code": "NO_ROUTE",
        "message": "No eligible broker for capability OPTIONS",
        "request_id": "err-1",
        "details": {"capability": "OPTIONS"},
    }
    assert r.headers["X-Request-ID"] == "err-1"


@pytest.mark.asyncio
async def test_validation_error_envelope(error_client):
    r = await error_client.post("/__test__/echo", json={"name": 123})
    assert r.status_code == 422
    body = r.json()
    assert body["error_code"] == "VALIDATION_ERROR"
    assert body["message"] == "Request validation failed"
    assert "request_id" in body
    assert "errors" in body["details"]


@pytest.mark.asyncio
async def test_unhandled_error_envelope_hides_internals(configured_app):
    # Exception handlers for bare Exception run via ServerErrorMiddleware, which
    # re-raises after sending the response so servers/tests can observe it.
    app = _app_with_error_routes(configured_app)
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/__test__/crash")
    assert r.status_code == 500
    body = r.json()
    assert body["error_code"] == "INTERNAL_ERROR"
    assert body["message"] == "An unexpected error occurred"
    assert "secret" not in body["message"].lower()
    assert body["details"] == {}
    assert "X-Request-ID" in r.headers


@pytest.mark.asyncio
async def test_http_404_envelope(error_client):
    r = await error_client.get("/__test__/missing")
    assert r.status_code == 404
    body = r.json()
    assert body["error_code"] == "HTTP_404"
    assert "request_id" in body
