import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.passwords import hash_password
from app.config.settings import Settings
from app.core.crypto import encrypt_secret
from app.models.broker import BrokerAccount
from app.models.config_item import ConfigurationItem
from app.models.provider_config import (
    ProviderConfig,
    ProviderKind,
    ProviderScope,
    ProviderStatus,
)
from app.models.user import Client, User, UserRole


async def seed_defaults(session: AsyncSession, settings: Settings) -> None:
    result = await session.execute(select(User).where(User.email == settings.seed_admin_email))
    if result.scalar_one_or_none() is None:
        session.add(
            User(
                email=settings.seed_admin_email,
                role=UserRole.admin,
                password_hash=hash_password(settings.seed_admin_password),
                is_active=True,
            )
        )

    for kind, ptype in (
        (ProviderKind.infrastructure, settings.infra_provider),
        (ProviderKind.broker_default, settings.broker_provider),
    ):
        existing = await session.execute(
            select(ProviderConfig).where(
                ProviderConfig.kind == kind,
                ProviderConfig.status == ProviderStatus.active,
            )
        )
        if existing.scalars().first() is None:
            session.add(
                ProviderConfig(
                    kind=kind,
                    provider_type=ptype or "mock",
                    scope_type=ProviderScope.global_,
                    status=ProviderStatus.active,
                    version=1,
                    config_non_secret={},
                )
            )

    demo_client = await session.execute(select(Client).where(Client.name == "Demo Lab Client"))
    client = demo_client.scalar_one_or_none()
    if client is None:
        client = Client(name="Demo Lab Client", status="active")
        session.add(client)
        await session.flush()

    cooldown = await session.execute(
        select(ConfigurationItem).where(ConfigurationItem.key == "ip.reuse.cooldown_hours")
    )
    if cooldown.scalar_one_or_none() is None:
        session.add(
            ConfigurationItem(
                key="ip.reuse.cooldown_hours",
                value={"hours": settings.ip_reuse_cooldown_hours},
                version=1,
            )
        )

    w3_defaults: dict[str, dict] = {
        "routing.weights": {
            "w_lat": 0.25,
            "w_succ": 0.30,
            "w_conn": 0.15,
            "w_to": 0.20,
            "w_ip": 0.10,
        },
        "routing.health_thresholds": {"healthy_min": 80, "degraded_min": 50},
        "routing.require_assigned_ip": {"enabled": True},
        "routing.policy": {"policy": "WEIGHTED_SCORE"},
        "rate_limit.exceed_policy": {"policy": "REROUTE"},
        "orders.execution_mode": {"mode": "inline"},
    }
    for key, value in w3_defaults.items():
        existing = await session.execute(
            select(ConfigurationItem).where(ConfigurationItem.key == key)
        )
        if existing.scalar_one_or_none() is None:
            session.add(ConfigurationItem(key=key, value=value, version=1))

    brokers = await session.execute(
        select(BrokerAccount).where(BrokerAccount.client_id == client.id)
    )
    if not brokers.scalars().first():
        creds = encrypt_secret(
            json.dumps({"api_key": "mock-demo-key", "api_secret": "mock-demo-secret"}),
            settings,
        )
        session.add(
            BrokerAccount(
                client_id=client.id,
                provider_type="mock",
                display_name="Mock Alpha Broker",
                priority=10,
                enabled=True,
                allowed_regions=["ewr", "ord"],
                capabilities={
                    "asset_classes": ["equities"],
                    "order_types": ["MARKET", "LIMIT"],
                    "supports_whitelist": True,
                },
                credentials_encrypted=creds,
                rate_limit_rps=50,
            )
        )
        session.add(
            BrokerAccount(
                client_id=client.id,
                provider_type="mock",
                display_name="Mock Beta Broker",
                priority=20,
                enabled=True,
                allowed_regions=["ewr"],
                capabilities={
                    "asset_classes": ["equities", "fx"],
                    "order_types": ["MARKET"],
                    "supports_whitelist": True,
                    "whitelist_format": "xml",
                },
                credentials_encrypted=creds,
                rate_limit_rps=25,
            )
        )

    await session.commit()
