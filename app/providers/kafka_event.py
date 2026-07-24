"""Kafka / Redpanda EventProvider adapter (local plaintext + cloud SASL/SSL)."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("brokerbridge.events.kafka")


class KafkaEventProvider:
    """Shared Kafka-compatible producer for redpanda_local / kafka / redpanda_cloud."""

    def __init__(
        self,
        *,
        brokers: str,
        security_protocol: str = "PLAINTEXT",
        sasl_mechanism: str | None = None,
        username: str | None = None,
        password: str | None = None,
        ssl: bool = False,
        topic_prefix: str | None = None,
        topic_map: dict[str, str] | None = None,
        provider_type: str = "kafka",
    ) -> None:
        self.brokers = brokers
        self.security_protocol = (security_protocol or "PLAINTEXT").upper()
        self.sasl_mechanism = sasl_mechanism
        self.username = username
        self.password = password
        self.ssl = bool(ssl)
        self.topic_prefix = topic_prefix
        self.topic_map = topic_map or {}
        self.provider_type = provider_type
        self._producer = None

    def _client_kwargs(self) -> dict[str, Any]:
        import ssl

        protocol = self.security_protocol
        if self.ssl and protocol == "PLAINTEXT":
            protocol = "SSL"
        elif self.ssl and protocol == "SASL_PLAINTEXT":
            protocol = "SASL_SSL"

        kwargs: dict[str, Any] = {
            "bootstrap_servers": self.brokers,
            "security_protocol": protocol,
        }
        if protocol in ("SSL", "SASL_SSL"):
            # aiokafka requires an explicit context for SSL / SASL_SSL
            kwargs["ssl_context"] = ssl.create_default_context()
        if self.sasl_mechanism and self.username is not None:
            kwargs["sasl_mechanism"] = self.sasl_mechanism
            kwargs["sasl_plain_username"] = self.username
            kwargs["sasl_plain_password"] = self.password or ""
        return kwargs

    async def _ensure_producer(self):
        if self._producer is not None:
            return self._producer
        from aiokafka import AIOKafkaProducer

        producer = AIOKafkaProducer(**self._client_kwargs())
        await producer.start()
        self._producer = producer
        return producer

    async def publish(self, topic: str, event: dict[str, Any]) -> None:
        import json

        producer = await self._ensure_producer()
        payload = json.dumps(event).encode("utf-8")
        key = str(event.get("event_id") or "").encode("utf-8") or None
        await producer.send_and_wait(topic, payload, key=key)

    async def probe(self) -> dict[str, Any]:
        """Metadata probe + optional produce to configured topic (scratch)."""
        from aiokafka import AIOKafkaProducer
        from aiokafka.admin import AIOKafkaAdminClient

        admin = None
        try:
            admin = AIOKafkaAdminClient(**self._client_kwargs())
            await admin.start()
            topics = await admin.list_topics()
            ok = True
            detail: dict[str, Any] = {
                "topics_sample": sorted(list(topics))[:20],
                "broker_count": len(topics),
            }
        except Exception as exc:  # noqa: BLE001
            logger.warning("event_probe_metadata_failed: %s", type(exc).__name__)
            return {"ok": False, "error": str(exc), "provider_type": self.provider_type}
        finally:
            if admin is not None:
                try:
                    await admin.close()
                except Exception:  # noqa: BLE001
                    pass

        # Light produce smoke — optional on managed clusters (auto-create often off)
        scratch = f"{(self.topic_prefix or 'brokerbridge').rstrip('.')}.probe"
        known = set(detail.get("topics_sample") or [])
        # Prefer an existing topic under the prefix when scratch is missing
        if scratch not in known and known:
            preferred = (self.topic_prefix or "").rstrip(".")
            if preferred in known:
                scratch = preferred
            else:
                scratch = sorted(known)[0]
        producer = None
        try:
            producer = AIOKafkaProducer(**self._client_kwargs())
            await producer.start()
            await producer.send_and_wait(scratch, b'{"probe":true}')
            detail["probe_topic"] = scratch
        except Exception as exc:  # noqa: BLE001
            # Metadata/auth already proved connectivity; produce is best-effort
            detail["produce_error"] = str(exc)
            detail["probe_topic_attempted"] = scratch
            logger.warning(
                "event_probe_produce_optional_failed: %s",
                type(exc).__name__,
            )
        finally:
            if producer is not None:
                await producer.stop()

        return {"ok": ok, "provider_type": self.provider_type, "brokers": self.brokers, **detail}

    async def aclose(self) -> None:
        if self._producer is not None:
            try:
                await self._producer.stop()
            except Exception:  # noqa: BLE001
                logger.warning("event_producer_stop_failed")
            self._producer = None
