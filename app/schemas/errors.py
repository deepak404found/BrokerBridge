from typing import Any

from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    """TDD §13.8 error envelope for failed API requests."""

    error_code: str = Field(description="Machine-readable error code")
    message: str = Field(description="Human-readable error summary")
    request_id: str = Field(description="Correlation id from X-Request-ID")
    details: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional structured context (validation errors, etc.)",
    )
