import ssl

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
