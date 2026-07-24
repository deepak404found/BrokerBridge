"""Provider-layer errors (no FastAPI / domain coupling)."""

from __future__ import annotations


class RedisUnavailableError(RuntimeError):
    """Redis could not be reached or timed out."""

    def __init__(self, message: str = "Redis unavailable", *, detail: str | None = None) -> None:
        super().__init__(message)
        self.detail = detail or message
