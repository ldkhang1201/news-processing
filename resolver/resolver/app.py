from __future__ import annotations

import logging
import signal
import statistics
import threading
import time

import structlog
from confluent_kafka.admin import AdminClient, NewTopic

from resolver.audio import deserialize_audio_transcript, transcript_to_article
from resolver.geocoder import NominatimClient
from resolver.kafka import ArticleConsumer, EventPublisher, deserialize_article
from resolver.llm import OllamaClient, OllamaError
from resolver.models import Article, TrafficEvent
from resolver.settings import Settings


log = structlog.get_logger()


def configure_logging(level: str) -> None:
    numeric = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(level=numeric, format="%(message)s")
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(numeric),
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
    )


def install_signal_handlers() -> threading.Event:
    shutdown = threading.Event()

    def _handler(signum, _frame):
        log.info("shutdown_signal", signal=signum)
        shutdown.set()

    signal.signal(signal.SIGTERM, _handler)
    signal.signal(signal.SIGINT, _handler)
    return shutdown


def ensure_topics(settings: Settings) -> None:
    """Verify the input topic exists; create the output topic if missing.

    The input topic is collector-owned: if it's missing the upstream is broken,
    and we fail fast rather than auto-creating it. The audio topic, if
    configured, is owned by the audio_processing producer — we warn but don't
    fail, since that service may start later. The output topic is ours, so we
    create it on first run with configured partitions/replication.
    """
    admin = AdminClient({"bootstrap.servers": settings.kafka_bootstrap_servers})
    metadata = admin.list_topics(timeout=10)

    if settings.kafka_input_topic not in metadata.topics:
        log.error("input_topic_missing", topic=settings.kafka_input_topic)
        raise RuntimeError(f"input topic {settings.kafka_input_topic!r} not found on broker")

    if settings.kafka_audio_topic and settings.kafka_audio_topic not in metadata.topics:
        # The audio topic is owned by the audio_processing producer. Don't
        # create it here; just warn and let it appear when that service starts.
        log.warning("audio_topic_missing", topic=settings.kafka_audio_topic)

    if settings.kafka_output_topic not in metadata.topics:
        new = NewTopic(
            settings.kafka_output_topic,
            num_partitions=settings.kafka_output_partitions,
            replication_factor=settings.kafka_output_replication_factor,
        )
        futures = admin.create_topics([new])
        futures[settings.kafka_output_topic].result()
        log.info(
            "output_topic_created",
            topic=settings.kafka_output_topic,
            partitions=settings.kafka_output_partitions,
            replication_factor=settings.kafka_output_replication_factor,
        )


def resolve(
    article: Article,
    ollama: OllamaClient,
    geocoder: NominatimClient,
    publisher: EventPublisher,
) -> int:
    """Resolve one article: extract events, geocode each, publish. Returns event count."""
    if article.language != "vi":
        log.info("article_skipped_non_vi", article_id=article.id, lang=article.language)
        return 0
    if not (article.content or article.summary):
        log.info("article_skipped_empty_body", article_id=article.id)
        return 0

    events = ollama.extract_events(article)
    n_geocoded = 0
    for idx, ev in enumerate(events):
        coords = geocoder.geocode(ev.address)
        traffic_event = TrafficEvent(
            event=ev.event,
            address=ev.address,
            lat=coords[0] if coords else None,
            long=coords[1] if coords else None,
            time=ev.time,
            article_id=article.id,
            article_url=str(article.url),
        )
        publisher.publish(traffic_event, idx)
        if coords is not None:
            n_geocoded += 1

    log.info(
        "article_resolved",
        article_id=article.id,
        n_events=len(events),
        n_geocoded=n_geocoded,
    )
    return len(events)


def run() -> None:
    settings = Settings()
    configure_logging(settings.log_level)
    log.info(
        "starting",
        input_topic=settings.kafka_input_topic,
        audio_topic=settings.kafka_audio_topic or None,
        output_topic=settings.kafka_output_topic,
        brokers=settings.kafka_bootstrap_servers,
        ollama_model=settings.ollama_model,
    )

    ensure_topics(settings)

    consumer = ArticleConsumer(settings)
    consumer.subscribe()
    publisher = EventPublisher(settings)
    ollama = OllamaClient(settings)
    geocoder = NominatimClient(settings)
    shutdown = install_signal_handlers()

    latencies_ms: list[float] = []
    total_events = 0
    run_started = time.monotonic()

    try:
        while not shutdown.is_set():
            if settings.max_articles and len(latencies_ms) >= settings.max_articles:
                log.info("max_articles_reached", count=len(latencies_ms))
                break

            msg = consumer.poll(1.0)
            if msg is None:
                continue

            try:
                if msg.topic() == settings.kafka_audio_topic:
                    transcript = deserialize_audio_transcript(msg.value())
                    article = transcript_to_article(transcript)
                else:
                    article = deserialize_article(msg.value())
            except Exception:
                log.exception(
                    "article_deserialize_failed",
                    topic=msg.topic(),
                    offset=msg.offset(),
                )
                consumer.commit(msg)  # poison-pill: skip and advance
                continue

            t0 = time.monotonic()
            try:
                n_events = resolve(article, ollama, geocoder, publisher)
            except OllamaError:
                log.exception("ollama_failed", article_id=article.id)
                continue  # don't commit; redeliver on next poll cycle
            except Exception:
                log.exception("resolve_failed", article_id=article.id)
                continue

            outstanding = publisher.flush(30.0)
            if outstanding > 0:
                log.error(
                    "flush_outstanding",
                    article_id=article.id,
                    outstanding=outstanding,
                )
                continue  # don't commit; redeliver

            elapsed_ms = (time.monotonic() - t0) * 1000.0
            latencies_ms.append(elapsed_ms)
            total_events += n_events
            consumer.commit(msg)
    finally:
        wall_s = time.monotonic() - run_started
        _log_run_summary(latencies_ms, total_events, wall_s)
        log.info("shutting_down")
        publisher.close()
        consumer.close()
        ollama.close()
        geocoder.close()
        log.info("shutdown_complete")


def _log_run_summary(latencies_ms: list[float], total_events: int, wall_s: float) -> None:
    n = len(latencies_ms)
    if n == 0:
        log.info("run_summary", articles=0, wall_s=round(wall_s, 2))
        return
    sorted_ms = sorted(latencies_ms)
    p50 = sorted_ms[n // 2]
    p95 = sorted_ms[min(n - 1, max(0, int(round(0.95 * n)) - 1))]
    log.info(
        "run_summary",
        articles=n,
        events=total_events,
        wall_s=round(wall_s, 2),
        articles_per_s=round(n / wall_s, 3) if wall_s > 0 else None,
        latency_avg_ms=round(statistics.fmean(latencies_ms), 1),
        latency_p50_ms=round(p50, 1),
        latency_p95_ms=round(p95, 1),
        latency_min_ms=round(sorted_ms[0], 1),
        latency_max_ms=round(sorted_ms[-1], 1),
    )
