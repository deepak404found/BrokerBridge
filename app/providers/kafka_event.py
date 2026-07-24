"""Kafka / Redpanda EventProvider adapter (local plaintext + cloud SASL/SSL)."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

logger = logging.getLogger("brokerbridge.events.kafka")

EventHandler = Callable[[str, dict[str, Any]], Awaitable[None]]


class KafkaEventProvider:
    """Shared Kafka-compatible producer/consumer for redpanda_local / kafka / redpanda_cloud."""

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
        consumer_group: str | None = None,
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
        self.consumer_group = consumer_group or "brokerbridge-lab"
        self._producer = None
        self._consumer = None
        self._handler: EventHandler | None = None
        self._topics: list[str] = []
        self._stop = asyncio.Event()
        self._closed = False

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
        producer = await self._ensure_producer()
        payload = json.dumps(event).encode("utf-8")
        key = str(event.get("event_id") or "").encode("utf-8") or None
        await producer.send_and_wait(topic, payload, key=key)

    async def subscribe(
        self,
        topics: Sequence[str],
        handler: EventHandler,
        *,
        consumer_group: str | None = None,
    ) -> None:
        if self._closed:
            raise RuntimeError("KafkaEventProvider is closed")
        self._handler = handler
        self._topics = list(topics)
        if consumer_group:
            self.consumer_group = consumer_group
        self._stop.clear()

    async def run_consumer(self) -> None:
        """Blocking consume loop until aclose / stop."""
        if not self._topics or self._handler is None:
            await self._stop.wait()
            return

        from aiokafka import AIOKafkaConsumer

        consumer = AIOKafkaConsumer(
            *self._topics,
            group_id=self.consumer_group,
            enable_auto_commit=True,
            auto_offset_reset="earliest",
            **self._client_kwargs(),
        )
        self._consumer = consumer
        await consumer.start()
        logger.info(
            "kafka_consumer_started group=%s topics=%s",
            self.consumer_group,
            self._topics,
        )
        try:
            while not self._stop.is_set() and not self._closed:
                try:
                    batch = await consumer.getmany(timeout_ms=1000, max_records=50)
                except asyncio.CancelledError:
                    raise
                except Exception:  # noqa: BLE001
                    logger.exception("kafka_consumer_poll_failed")
                    await asyncio.sleep(1.0)
                    continue
                for _tp, messages in batch.items():
                    for msg in messages:
                        if self._handler is None:
                            continue
                        try:
                            raw = msg.value.decode("utf-8") if msg.value else "{}"
                            event = json.loads(raw)
                            if not isinstance(event, dict):
                                event = {"payload": event}
                            await self._handler(msg.topic, event)
                        except Exception:  # noqa: BLE001
                            logger.exception(
                                "kafka_handler_failed topic=%s offset=%s",
                                msg.topic,
                                msg.offset,
                            )
        finally:
            try:
                await consumer.stop()
            except Exception:  # noqa: BLE001
                logger.warning("kafka_consumer_stop_failed")
            self._consumer = None
            logger.info("kafka_consumer_stopped")

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
                "consumer_group": self.consumer_group,
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

        scratch = f"{(self.topic_prefix or 'brokerbridge').rstrip('.')}.probe"
        known = set(detail.get("topics_sample") or [])
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
        self._closed = True
        self._stop.set()
        if self._consumer is not None:
            try:
                await self._consumer.stop()
            except Exception:  # noqa: BLE001
                logger.warning("event_consumer_stop_failed")
            self._consumer = None
        if self._producer is not None:
            try:
                await self._producer.stop()
            except Exception:  # noqa: BLE001
                logger.warning("event_producer_stop_failed")
            self._producer = None
