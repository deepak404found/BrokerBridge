from __future__ import annotations

import json
import uuid
import xml.etree.ElementTree as ET
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import Settings
from app.core.errors import AppError
from app.models.broker import BrokerAccount
from app.models.infrastructure import IpAssignment, StaticIp
from app.models.whitelist import WhitelistFinding, WhitelistSnapshot
from app.providers.manager import ProviderManager


def normalize_whitelist(raw_format: str, raw_payload: str) -> dict[str, Any]:
    fmt = raw_format.lower()
    ips: list[str] = []
    if fmt == "json":
        data = json.loads(raw_payload)
        if isinstance(data, dict):
            ips = list(data.get("ips") or data.get("addresses") or [])
        elif isinstance(data, list):
            ips = list(data)
    elif fmt == "xml":
        root = ET.fromstring(raw_payload)
        for node in root.iter():
            tag = node.tag.split("}")[-1].lower()
            if tag in ("ip", "address", "ipv4") and node.text:
                ips.append(node.text.strip())
    else:
        raise AppError("VALIDATION_ERROR", f"Unsupported whitelist format: {raw_format}", status_code=422)
    unique = sorted({ip for ip in ips if ip})
    return {"ips": unique, "count": len(unique)}


class WhitelistService:
    def __init__(
        self,
        db: AsyncSession,
        settings: Settings,
        providers: ProviderManager,
    ) -> None:
        self.db = db
        self.settings = settings
        self.providers = providers

    async def sync(self, broker_id: uuid.UUID, *, format_hint: str | None = None) -> dict[str, Any]:
        result = await self.db.execute(select(BrokerAccount).where(BrokerAccount.id == broker_id))
        broker = result.scalar_one_or_none()
        if broker is None:
            raise AppError("NOT_FOUND", "Broker not found", status_code=404)

        hint = format_hint
        if hint is None and isinstance(broker.capabilities, dict):
            hint = broker.capabilities.get("whitelist_format")

        broker_provider = await self.providers.get_broker_provider(self.db)
        raw = await broker_provider.fetch_whitelist_raw(format_hint=hint)
        raw_format = raw["format"]
        raw_payload = raw["payload"]
        normalized = normalize_whitelist(raw_format, raw_payload)

        snapshot = WhitelistSnapshot(
            broker_account_id=broker_id,
            raw_format=raw_format,
            raw_payload=raw_payload,
            normalized=normalized,
        )
        self.db.add(snapshot)

        # Expected IPs = currently assigned active IPs for this broker
        assigned = await self.db.execute(
            select(StaticIp)
            .join(IpAssignment, IpAssignment.static_ip_id == StaticIp.id)
            .where(
                IpAssignment.broker_account_id == broker_id,
                IpAssignment.status == "active",
            )
        )
        expected = {ip.ip_address for ip in assigned.scalars().all()}
        actual = set(normalized["ips"])

        findings: list[WhitelistFinding] = []
        for ip in sorted(expected - actual):
            findings.append(
                WhitelistFinding(
                    broker_account_id=broker_id,
                    ip_address=ip,
                    finding_type="missing",
                    details={"expected": True, "on_broker_whitelist": False},
                )
            )
        for ip in sorted(actual - expected):
            findings.append(
                WhitelistFinding(
                    broker_account_id=broker_id,
                    ip_address=ip,
                    finding_type="unauthorized" if expected else "ok",
                    details={"expected": False, "on_broker_whitelist": True},
                )
            )
        for ip in sorted(expected & actual):
            findings.append(
                WhitelistFinding(
                    broker_account_id=broker_id,
                    ip_address=ip,
                    finding_type="ok",
                    details={"expected": True, "on_broker_whitelist": True},
                )
            )

        for f in findings:
            self.db.add(f)
        await self.db.commit()
        await self.db.refresh(snapshot)

        return {
            "snapshot": snapshot,
            "findings": findings,
            "normalized": normalized,
        }

    async def latest_findings(self, broker_id: uuid.UUID) -> list[WhitelistFinding]:
        result = await self.db.execute(
            select(WhitelistFinding)
            .where(WhitelistFinding.broker_account_id == broker_id)
            .order_by(WhitelistFinding.detected_at.desc())
            .limit(50)
        )
        return list(result.scalars().all())
