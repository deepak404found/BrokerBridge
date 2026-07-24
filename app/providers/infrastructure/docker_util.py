"""Docker Engine availability helpers (provider layer only)."""

from __future__ import annotations

from typing import Any

DOCKER_SOCKET_HINT = (
    "Docker socket not mounted or Docker Engine unavailable; "
    "use mock_backend=database, or ensure /var/run/docker.sock is mounted "
    "(Local Lab: docker compose up)"
)


def docker_engine_available(docker_host: str | None = None) -> tuple[bool, str | None]:
    """Return (ok, error_message). Does not raise."""
    try:
        import docker
    except ImportError:
        return False, "docker package required (poetry install --extras infra-docker)"
    try:
        if docker_host:
            client = docker.DockerClient(base_url=docker_host)
        else:
            client = docker.from_env()
        client.ping()
        return True, None
    except Exception as exc:  # noqa: BLE001
        return False, f"{DOCKER_SOCKET_HINT} ({exc})"


def docker_probe_failure(docker_host: str | None = None) -> dict[str, Any]:
    """Probe-shaped failure payload for Admin validate."""
    ok, err = docker_engine_available(docker_host)
    if ok:
        return {"ok": True, "provider": "mock", "backend": "docker"}
    return {
        "ok": False,
        "provider": "mock",
        "backend": "docker",
        "error": "DOCKER_UNAVAILABLE",
        "message": err or DOCKER_SOCKET_HINT,
        "hint": DOCKER_SOCKET_HINT,
    }
