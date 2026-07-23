from typing import Any

from pydantic import BaseModel, ConfigDict, Field


_ERROR_EXAMPLE = {
    "error_code": "UNAUTHORIZED",
    "message": "Not authenticated",
    "request_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "details": {},
}


class ErrorResponse(BaseModel):
    """TDD §13.8 error envelope for failed API requests."""

    model_config = ConfigDict(
        json_schema_extra={
            # Singular ``example`` is what many UIs sample from for $ref schemas.
            "example": _ERROR_EXAMPLE,
            "examples": [_ERROR_EXAMPLE],
        }
    )

    error_code: str = Field(
        description="Machine-readable error code",
        examples=["UNAUTHORIZED"],
    )
    message: str = Field(
        description="Human-readable error summary",
        examples=["Not authenticated"],
    )
    request_id: str = Field(
        description="Correlation id from X-Request-ID",
        examples=["a1b2c3d4-e5f6-7890-abcd-ef1234567890"],
    )
    details: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional structured context (validation errors, etc.)",
        examples=[{}],
    )
