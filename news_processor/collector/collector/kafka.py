from __future__ import annotations

import structlog
from confluent_kafka import KafkaError, Message, Producer

from collector.models import Article
from collector.settings import Settings


log = structlog.get_logger()


def _on_delivery(err: KafkaError | None, msg: Message) -> None:
    if err is not None:
        log.error("kafka_delivery_failed", error=str(err))
    else:
        log.debug(
            "kafka_delivery_ok",
            topic=msg.topic(),
            partition=msg.partition(),
            offset=msg.offset(),
        )


class KafkaPublisher:
    def __init__(self, settings: Settings) -> None:
        self._producer = Producer(
            {
                "bootstrap.servers": settings.kafka_bootstrap_servers,
                "client.id": settings.kafka_client_id,
                "acks": settings.kafka_acks,
                "compression.type": "lz4",
                "linger.ms": 50,
            }
        )
        self._topic = settings.kafka_topic

    def publish(self, article: Article) -> None:
        self._producer.produce(
            topic=self._topic,
            key=article.id.encode(),
            value=article.model_dump_json().encode(),
            headers=[
                ("publisher", article.publisher.encode()),
                ("schema_version", b"1"),
                ("collected_at", article.collected_at.isoformat().encode()),
            ],
            on_delivery=_on_delivery,
        )
        self._producer.poll(0)

    def flush(self, timeout: float = 10.0) -> int:
        return self._producer.flush(timeout)

    def close(self) -> None:
        self._producer.flush(10.0)
