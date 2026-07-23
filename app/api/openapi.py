"""Shared OpenAPI response declarations using the W0 ErrorResponse envelope."""

from typing import Any

from app.schemas.errors import ErrorResponse

REQUEST_ID_EXAMPLE = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"

# ---------------------------------------------------------------------------
# Error envelope examples (status-specific)
# ---------------------------------------------------------------------------

EXAMPLE_401_UNAUTHORIZED: dict[str, Any] = {
    "error_code": "UNAUTHORIZED",
    "message": "Not authenticated",
    "request_id": REQUEST_ID_EXAMPLE,
    "details": {},
}

EXAMPLE_401_INVALID_CREDENTIALS: dict[str, Any] = {
    "error_code": "UNAUTHORIZED",
    "message": "Invalid credentials",
    "request_id": REQUEST_ID_EXAMPLE,
    "details": {},
}

EXAMPLE_403_FORBIDDEN: dict[str, Any] = {
    "error_code": "FORBIDDEN",
    "message": "Insufficient permissions",
    "request_id": REQUEST_ID_EXAMPLE,
    "details": {},
}

EXAMPLE_404_NOT_FOUND: dict[str, Any] = {
    "error_code": "NOT_FOUND",
    "message": "No active provider config",
    "request_id": REQUEST_ID_EXAMPLE,
    "details": {},
}

EXAMPLE_422_VALIDATION: dict[str, Any] = {
    "error_code": "VALIDATION_ERROR",
    "message": "Request validation failed",
    "request_id": REQUEST_ID_EXAMPLE,
    "details": {
        "errors": [
            {
                "type": "missing",
                "loc": ["body", "provider_type"],
                "msg": "Field required",
                "input": {},
            }
        ]
    },
}

EXAMPLE_422_PROVIDER_VALIDATION: dict[str, Any] = {
    "error_code": "PROVIDER_VALIDATION_FAILED",
    "message": "Provider probe failed",
    "request_id": REQUEST_ID_EXAMPLE,
    "details": {"ok": False, "reason": "mock probe refused"},
}

EXAMPLE_500_INTERNAL: dict[str, Any] = {
    "error_code": "INTERNAL_ERROR",
    "message": "An unexpected error occurred",
    "request_id": REQUEST_ID_EXAMPLE,
    "details": {},
}

# ---------------------------------------------------------------------------
# Success payload examples
# ---------------------------------------------------------------------------

EXAMPLE_TOKEN_RESPONSE: dict[str, Any] = {
    "access_token": (
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
        "eyJzdWIiOiIwMDAwMDAwMC0wMDAwLTQwMDAtODAwMC0wMDAwMDAwMDAwMDEiLCJyb2xlIjoiYWRtaW4ifQ."
        "signature"
    ),
    "token_type": "bearer",
    "role": "admin",
    "email": "admin@brokerbridge.local",
}

EXAMPLE_PROVIDER_INFRA: dict[str, Any] = {
    "kind": "infrastructure",
    "provider_type": "mock",
    "version": 1,
    "status": "active",
    "config": {"region": "ewr", "api_key": "***"},
    "validated": True,
    "activated_at": "2026-07-23T12:00:00Z",
}

EXAMPLE_PROVIDER_BROKER: dict[str, Any] = {
    "kind": "broker_default",
    "provider_type": "mock",
    "version": 1,
    "status": "active",
    "config": {"environment": "paper", "api_key": "***"},
    "validated": True,
    "activated_at": "2026-07-23T12:00:00Z",
}

EXAMPLE_PROVIDER_LIST: list[dict[str, Any]] = [
    EXAMPLE_PROVIDER_INFRA,
    EXAMPLE_PROVIDER_BROKER,
]

EXAMPLE_PROVIDER_ACTIVATE_REQUEST: dict[str, Any] = {
    "provider_type": "mock",
    "scope": "global",
    "client_id": None,
    "validate_first": True,
    "activate": True,
    "config": {"region": "ewr", "api_key": "vultr-secret-key"},
}

EXAMPLE_LIVE: dict[str, Any] = {"status": "ok"}

EXAMPLE_READY_OK: dict[str, Any] = {
    "status": "ok",
    "checks": {
        "postgres": {"status": "ok", "latency_ms": 2.4, "detail": None},
        "redis": {"status": "ok", "latency_ms": 0.8, "detail": None},
        "redpanda": {"status": "ok", "latency_ms": 1.1, "detail": None},
    },
}

EXAMPLE_READY_NOT_READY: dict[str, Any] = {
    "status": "not_ready",
    "checks": {
        "postgres": {"status": "ok", "latency_ms": 2.4, "detail": None},
        "redis": {
            "status": "fail",
            "latency_ms": None,
            "detail": "Connection refused",
        },
        "redpanda": {"status": "ok", "latency_ms": 1.1, "detail": None},
    },
}


def json_example(
    example: Any,
    *,
    name: str = "default",
    summary: str = "Example",
) -> dict[str, Any]:
    """OpenAPI media-type content with singular + named examples.

    Swagger UI Example Value follows media-type ``example`` / ``examples.*.value``.
    Schema-only ``json_schema_extra`` / field ``examples`` often still render as
    type placeholders (``\"string\"``, ``additionalProp1``).
    """
    return {
        "application/json": {
            "example": example,
            "examples": {
                name: {
                    "summary": summary,
                    "value": example,
                }
            },
        }
    }


def error_response(
    description: str,
    *,
    example: dict[str, Any],
    summary: str = "Error envelope",
) -> dict[str, Any]:
    return {
        "model": ErrorResponse,
        "description": description,
        "content": json_example(example, name="error", summary=summary),
    }


def success_response(
    description: str,
    *,
    example: Any,
    model: Any | None = None,
    summary: str = "Success",
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "description": description,
        "content": json_example(example, name="success", summary=summary),
    }
    if model is not None:
        body["model"] = model
    return body


# Auth / RBAC — apply on protected routers or individual routes
UNAUTHORIZED: dict[int, dict[str, Any]] = {
    401: error_response(
        "Unauthorized — missing or invalid bearer token",
        example=EXAMPLE_401_UNAUTHORIZED,
    ),
}
FORBIDDEN: dict[int, dict[str, Any]] = {
    403: error_response(
        "Forbidden — insufficient role",
        example=EXAMPLE_403_FORBIDDEN,
    ),
}
AUTH_ERRORS: dict[int, dict[str, Any]] = {**UNAUTHORIZED, **FORBIDDEN}

# Common AppError statuses
NOT_FOUND: dict[int, dict[str, Any]] = {
    404: error_response(
        "Resource not found",
        example=EXAMPLE_404_NOT_FOUND,
    ),
}
UNPROCESSABLE: dict[int, dict[str, Any]] = {
    422: error_response(
        "Validation or business-rule failure",
        example=EXAMPLE_422_PROVIDER_VALIDATION,
    ),
}

# App-level defaults (main.py)
APP_VALIDATION_ERROR: dict[str, Any] = error_response(
    "Validation error",
    example=EXAMPLE_422_VALIDATION,
)
APP_INTERNAL_ERROR: dict[str, Any] = error_response(
    "Internal server error",
    example=EXAMPLE_500_INTERNAL,
)

# Login (OAuth2 password grant)
INVALID_CREDENTIALS: dict[int, dict[str, Any]] = {
    401: error_response(
        "Unauthorized — invalid credentials or inactive user",
        example=EXAMPLE_401_INVALID_CREDENTIALS,
    ),
}

# Success response helpers for routes
TOKEN_SUCCESS: dict[int, dict[str, Any]] = {
    200: success_response("JWT issued", example=EXAMPLE_TOKEN_RESPONSE),
}
PROVIDER_LIST_SUCCESS: dict[int, dict[str, Any]] = {
    200: success_response(
        "Active provider configs",
        example=EXAMPLE_PROVIDER_LIST,
    ),
}
PROVIDER_GET_SUCCESS: dict[int, dict[str, Any]] = {
    200: success_response(
        "Active provider config for kind",
        example=EXAMPLE_PROVIDER_INFRA,
    ),
}
PROVIDER_PUT_SUCCESS: dict[int, dict[str, Any]] = {
    200: success_response(
        "Provider config activated or staged",
        example=EXAMPLE_PROVIDER_INFRA,
    ),
}
LIVE_SUCCESS: dict[int, dict[str, Any]] = {
    200: success_response("Process is alive", example=EXAMPLE_LIVE),
}


def _ready_responses() -> dict[int, dict[str, Any]]:
    # Lazy import avoids circular imports with schemas.health at module load.
    from app.schemas.health import ReadyResponse

    return {
        200: success_response(
            "All critical dependencies ready",
            example=EXAMPLE_READY_OK,
            model=ReadyResponse,
        ),
        503: success_response(
            "One or more critical dependencies not ready",
            example=EXAMPLE_READY_NOT_READY,
            model=ReadyResponse,
        ),
    }


READY_RESPONSES: dict[int, dict[str, Any]] = _ready_responses()
