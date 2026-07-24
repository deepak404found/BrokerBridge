"""Chaos / failure simulator package."""

__all__ = ["list_faults", "set_fault", "clear_all_faults"]


def __getattr__(name: str):
    if name in __all__:
        from app.sim import service as _service

        return getattr(_service, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
