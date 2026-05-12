from __future__ import annotations

from datetime import datetime

import structlog
from confluent_kafka import Consumer, KafkaError, Message, Producer

from resolver.models import Article, TrafficEvent
from resolver.settings import Settings


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


class ArticleConsumer:
    def __init__(self, settings: Settings) -> None:
        self._consumer = Consumer(
            {
                "bootstrap.servers": settings.kafka_bootstrap_servers,
                "group.id": settings.kafka_group_id,
                "client.id": settings.kafka_client_id,
                "enable.auto.commit": False,
                "auto.offset.reset": "earliest",
                "max.poll.interval.ms": settings.kafka_max_poll_interval_ms,
                "session.timeout.ms": settings.kafka_session_timeout_ms,
            }
        )
        self._topics = [settings.kafka_input_topic]
        if settings.kafka_audio_topic:
            self._topics.append(settings.kafka_audio_topic)

    def subscribe(self) -> None:
        self._consumer.subscribe(self._topics)

    def poll(self, timeout: float) -> Message | None:
        msg = self._consumer.poll(timeout)
        if msg is None:
            return None
        if msg.error():
            err = msg.error()
            if err.code() == KafkaError._PARTITION_EOF:
                return None
            log.warning("kafka_poll_error", error=str(err))
            return None
        return msg

    def commit(self, msg: Message) -> None:
        self._consumer.commit(message=msg, asynchronous=False)

    def close(self) -> None:
        self._consumer.close()


def deserialize_article(value: bytes) -> Article:
    return Article.model_validate_json(value)


class EventPublisher:
    def __init__(self, settings: Settings) -> None:
        self._producer = Producer(
            {
                "bootstrap.servers": settings.kafka_bootstrap_servers,
                "client.id": settings.kafka_client_id,
                "acks": settings.kafka_acks,
                "enable.idempotence": True,
                "compression.type": "lz4",
                "linger.ms": 50,
            }
        )
        self._topic = settings.kafka_output_topic

    def publish(self, event: TrafficEvent, idx: int) -> None:
        self._producer.produce(
            topic=self._topic,
            key=f"{event.article_id}:{idx}".encode(),
            value=event.model_dump_json().encode(),
            headers=[
                ("schema_version", b"1"),
                ("produced_at", datetime.now().isoformat().encode()),
            ],
            on_delivery=_on_delivery,
        )
        self._producer.poll(0)

    def flush(self, timeout: float = 30.0) -> int:
        return self._producer.flush(timeout)

    def close(self) -> None:
        self._producer.flush(10.0)
