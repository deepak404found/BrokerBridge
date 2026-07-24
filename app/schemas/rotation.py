"""Re-export rotation schemas from events module for OpenAPI clarity."""

from app.schemas.events import RotateIpRequest, RotateIpResponse

__all__ = ["RotateIpRequest", "RotateIpResponse"]
