import ssl
from unittest.mock import AsyncMock, patch

import pytest

from app.events.envelope import build_envelope, resolve_physical_topic
from app.providers.kafka_event import KafkaEventProvider


def test_envelope_shape():
    env = build_envelope("ip.rotated", {"old_ip": "1.1.1.1"}, correlation_id="req-1")
    assert env["event_type"] == "ip.rotated"
    assert env["payload"]["old_ip"] == "1.1.1.1"
    assert env["correlation_id"] == "req-1"
    assert env["event_id"]
    assert env["occurred_at"].endswith("Z")


def test_topic_resolution_prefix_and_map():
    assert resolve_physical_topic("ip") == "brokerbridge.ip"
    assert resolve_physical_topic("orders", topic_prefix="lab") == "lab.orders"
    assert (
        resolve_physical_topic("ip", topic_map={"ip": "custom.ip.topic"}) == "custom.ip.topic"
    )


def test_kafka_client_kwargs_include_ssl_context_for_sasl_ssl():
    provider = KafkaEventProvider(
        brokers="cloud.example:9092",
        security_protocol="SASL_SSL",
        sasl_mechanism="SCRAM-SHA-256",
        username="user",
        password="secret",
        ssl=True,
    )
    kwargs = provider._client_kwargs()
    assert kwargs["security_protocol"] == "SASL_SSL"
    assert isinstance(kwargs["ssl_context"], ssl.SSLContext)
    assert kwargs["sasl_mechanism"] == "SCRAM-SHA-256"
    assert kwargs["sasl_plain_username"] == "user"


def test_kafka_client_kwargs_plaintext_omits_ssl_context():
    provider = KafkaEventProvider(brokers="redpanda:9092", security_protocol="PLAINTEXT")
    kwargs = provider._client_kwargs()
    assert kwargs["security_protocol"] == "PLAINTEXT"
    assert "ssl_context" not in kwargs


@pytest.mark.asyncio
async def test_ensure_topics_creates_missing_only():
    provider = KafkaEventProvider(
        brokers="cloud.example:9092",
        security_protocol="SASL_SSL",
        topic_prefix="brokerbridge.events",
    )
    admin = AsyncMock()
    admin.start = AsyncMock()
    admin.close = AsyncMock()
    admin.list_topics = AsyncMock(
        return_value={"brokerbridge.events.orders", "unrelated.topic"}
    )
    admin.create_topics = AsyncMock()

    with patch("aiokafka.admin.AIOKafkaAdminClient", return_value=admin):
        result = await provider.ensure_topics(
            [
                "brokerbridge.events.orders",
                "brokerbridge.events.ip",
                "brokerbridge.events.config",
            ]
        )

    assert result["ok"] is True
    assert sorted(result["created"]) == [
        "brokerbridge.events.config",
        "brokerbridge.events.ip",
    ]
    assert result["existing"] == ["brokerbridge.events.orders"]
    admin.create_topics.assert_awaited_once()
    new_topics = admin.create_topics.await_args.args[0]
    created_names = {t.name for t in new_topics}
    assert created_names == {"brokerbridge.events.ip", "brokerbridge.events.config"}


@pytest.mark.asyncio
async def test_ensure_topics_skips_create_when_all_exist():
    provider = KafkaEventProvider(brokers="redpanda:9092")
    admin = AsyncMock()
    admin.start = AsyncMock()
    admin.close = AsyncMock()
    admin.list_topics = AsyncMock(return_value={"a", "b"})
    admin.create_topics = AsyncMock()

    with patch("aiokafka.admin.AIOKafkaAdminClient", return_value=admin):
        result = await provider.ensure_topics(["a", "b"])

    assert result["ok"] is True
    assert result["created"] == []
    assert sorted(result["existing"]) == ["a", "b"]
    admin.create_topics.assert_not_awaited()
