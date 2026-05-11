from __future__ import annotations

import logging

import httpx
import structlog

from collector.dedup import SqliteDedup
from collector.fetcher import fetch_articles
from collector.kafka import KafkaPublisher
from collector.publishers import Publisher, get_enabled
from collector.settings import Settings

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


def collect(
    publisher: Publisher,
    settings: Settings,
    dedup: SqliteDedup,
    producer: KafkaPublisher,
    http: httpx.Client,
) -> int:
    new_count = 0
    for article in fetch_articles(publisher, settings, client=http, is_seen=dedup.is_seen):
        producer.publish(article)
        dedup.mark_seen(article)
        new_count += 1
        log.info(
            "article_published",
            publisher=publisher.id,
            id=article.id,
            title=article.title[:80],
        )
    log.info("cycle_complete", publisher=publisher.id, new=new_count)
    return new_count


def run() -> None:
    settings = Settings()
    configure_logging(settings.log_level)

    pubs = get_enabled(settings)
    if not pubs:
        log.error("no_publishers_enabled")
        return

    log.info(
        "starting",
        topic=settings.kafka_topic,
        brokers=settings.kafka_bootstrap_servers,
        publishers=[p.id for p in pubs],
    )

    dedup = SqliteDedup(settings.dedup_db_path)
    producer = KafkaPublisher(settings)
    http = httpx.Client(
        timeout=settings.http_timeout_s,
        headers={"User-Agent": settings.user_agent},
    )

    total_new = 0
    try:
        for publisher in pubs:
            try:
                total_new += collect(publisher, settings, dedup, producer, http)
            except Exception:
                log.exception("cycle_failed", publisher=publisher.id)
    finally:
        log.info("run_complete", total_new=total_new)
        producer.flush()
        producer.close()
        dedup.close()
        http.close()
