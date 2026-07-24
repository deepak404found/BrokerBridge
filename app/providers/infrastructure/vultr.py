"""Real Vultr infrastructure adapter (httpx). Domain never imports this module."""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger("brokerbridge.providers.vultr")

VULTR_API_BASE = "https://api.vultr.com/v2"


class VultrProviderError(Exception):
    def __init__(self, code: str, message: str, *, status: int = 502) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


class VultrProvider:
    """InfrastructureProvider backed by Vultr REST API."""

    def __init__(
        self,
        *,
        api_key: str,
        default_region: str = "ewr",
        base_url: str = VULTR_API_BASE,
        timeout: float = 30.0,
    ) -> None:
        self._api_key = (api_key or "").strip()
        self._default_region = default_region or "ewr"
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self.backend_name = "vultr"

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self._api_key:
            raise VultrProviderError("VULTR_API_KEY_MISSING", "Vultr api_key required", status=422)
        url = f"{self._base_url}{path}"
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.request(
                method,
                url,
                headers=self._headers(),
                json=json,
                params=params,
            )
        if resp.status_code >= 400:
            # Never log the API key; body may still contain soft errors.
            detail = resp.text[:500] if resp.text else resp.reason_phrase
            logger.warning(
                "vultr_http_error status=%s path=%s detail=%s",
                resp.status_code,
                path,
                detail,
            )
            raise VultrProviderError(
                "VULTR_API_ERROR",
                f"Vultr API error HTTP {resp.status_code}",
                status=502 if resp.status_code >= 500 else 422,
            )
        if resp.status_code == 204 or not resp.content:
            return {}
        return resp.json()

    async def probe(self) -> dict[str, Any]:
        if not self._api_key:
            return {"ok": False, "provider": "vultr", "error": "api_key required"}
        try:
            data = await self._request("GET", "/account")
            account = data.get("account") if isinstance(data, dict) else None
            return {
                "ok": True,
                "provider": "vultr",
                "account": {"email": (account or {}).get("email")} if account else None,
            }
        except VultrProviderError as exc:
            return {"ok": False, "provider": "vultr", "error": exc.code, "message": exc.message}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "provider": "vultr", "error": "VULTR_PROBE_FAILED", "message": str(exc)}

    async def create_ip(self, region: str, **kwargs: Any) -> dict[str, Any]:
        body = {"region": region or self._default_region, "type": "v4"}
        data = await self._request("POST", "/reserved-ips", json=body)
        rip = data.get("reserved_ip") or data
        external_id = str(rip.get("id") or rip.get("reserved_ip"))
        return {
            "id": external_id,
            "external_id": external_id,
            "ip_address": rip.get("subnet") or rip.get("ip") or rip.get("address"),
            "region": rip.get("region") or region,
            "status": "allocated",
            "provider": "vultr",
        }

    async def delete_ip(self, external_id: str) -> None:
        await self._request("DELETE", f"/reserved-ips/{external_id}")

    async def attach_ip(self, external_id: str, instance_external_id: str) -> None:
        await self._request(
            "POST",
            f"/reserved-ips/{external_id}/attach",
            json={"instance_id": instance_external_id},
        )

    async def detach_ip(self, external_id: str) -> None:
        await self._request("POST", f"/reserved-ips/{external_id}/detach")

    async def create_instance(self, region: str, **kwargs: Any) -> dict[str, Any]:
        label = kwargs.get("label") or f"brokerbridge-{region}"
        body = {
            "region": region or self._default_region,
            "plan": kwargs.get("plan") or "vc2-1c-1gb",
            "os_id": kwargs.get("os_id") or 2284,
            "label": label,
            "hostname": kwargs.get("hostname") or label.replace(" ", "-")[:60],
        }
        data = await self._request("POST", "/instances", json=body)
        inst = data.get("instance") or data
        external_id = str(inst.get("id"))
        return {
            "id": external_id,
            "external_id": external_id,
            "region": inst.get("region") or region,
            "status": inst.get("status") or "pending",
            "provider": "vultr",
            "label": label,
        }

    async def destroy_instance(self, external_id: str) -> None:
        await self._request("DELETE", f"/instances/{external_id}")

    async def suspend_instance(self, external_id: str) -> None:
        await self._request("POST", f"/instances/{external_id}/halt")

    async def start_instance(self, external_id: str) -> None:
        await self._request("POST", f"/instances/{external_id}/start")

    async def set_auto_renew(self, resource_id: str, enabled: bool) -> None:
        # Vultr auto_backups / pending charges differ by product; store intent via tag when possible.
        # Best-effort: patch instance user_data/tag metadata is not universal — no-op success for missing.
        try:
            await self._request(
                "PATCH",
                f"/instances/{resource_id}",
                json={"tags": [f"auto_renew:{'true' if enabled else 'false'}"]},
            )
        except VultrProviderError:
            # Reserved IPs may not support the same patch — treat as soft success for teardown path.
            logger.info("vultr_set_auto_renew_soft resource=%s enabled=%s", resource_id, enabled)

    async def list_ips(self, region: str | None = None) -> list[dict[str, Any]]:
        data = await self._request("GET", "/reserved-ips")
        rows = data.get("reserved_ips") or []
        out: list[dict[str, Any]] = []
        for rip in rows:
            rgn = rip.get("region")
            if region and rgn != region:
                continue
            out.append(
                {
                    "external_id": str(rip.get("id")),
                    "ip_address": rip.get("subnet") or rip.get("ip"),
                    "region": rgn,
                    "status": rip.get("status") or "allocated",
                    "provider": "vultr",
                }
            )
        return out

    async def get_ip(self, external_id: str) -> dict[str, Any] | None:
        try:
            data = await self._request("GET", f"/reserved-ips/{external_id}")
        except VultrProviderError:
            return None
        rip = data.get("reserved_ip") or data
        return {
            "external_id": str(rip.get("id") or external_id),
            "ip_address": rip.get("subnet") or rip.get("ip"),
            "region": rip.get("region"),
            "status": rip.get("status") or "allocated",
            "provider": "vultr",
        }
