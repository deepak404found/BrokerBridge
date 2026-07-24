"""Shared errors for mock infrastructure backends."""


class MockInfrastructureError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        status: int = 503,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
