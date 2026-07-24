"""Shared test helpers."""


def as_items(payload):
    """Unwrap paginated `{items, total}` envelopes; pass through plain lists."""
    if isinstance(payload, dict) and "items" in payload:
        return payload["items"]
    return payload
