from __future__ import annotations

from datetime import UTC, datetime
from typing import Callable, Iterable

import feedparser
import httpx
import structlog
import trafilatura
from dateutil import parser as dateparser

from collector.models import Article, canonicalize_url, make_article_id, utcnow
from collector.publishers import Publisher
from collector.settings import Settings

log = structlog.get_logger()


def _struct_to_datetime(struct_time) -> datetime | None:
    if struct_time is None:
        return None
    try:
        return datetime(*struct_time[:6], tzinfo=UTC)
    except (TypeError, ValueError):
        return None


def _parse_published(entry) -> datetime | None:
    for attr in ("published_parsed", "updated_parsed"):
        dt = _struct_to_datetime(getattr(entry, attr, None))
        if dt is not None:
            return dt
    raw = entry.get("published") or entry.get("updated")
    if raw:
        try:
            return dateparser.parse(raw)
        except (ValueError, TypeError):
            return None
    return None


def _entry_to_article(
    publisher: Publisher,
    entry,
    client: httpx.Client,
    fetch_full_content: bool,
    is_seen: Callable[[str], bool] | None,
) -> Article | None:
    raw_url = entry.get("link")
    title = (entry.get("title") or "").strip()
    if not raw_url or not title:
        return None
    canon = canonicalize_url(raw_url)
    article_id = make_article_id(canon)

    # Skip the costly body fetch for entries we've already published —
    # otherwise every poll re-fetches the same ~30 article URLs and trips
    # publisher rate limits (e.g. dantri's Varnish CDN).
    if is_seen is not None and is_seen(article_id):
        return None

    content: str | None = None
    if fetch_full_content:
        try:
            resp = client.get(raw_url, follow_redirects=True)
            resp.raise_for_status()
            content = trafilatura.extract(resp.text, url=raw_url, favor_recall=True)
        except Exception as exc:
            log.warning("article_fetch_failed", url=raw_url, error=str(exc))

    return Article(
        id=article_id,
        publisher=publisher.id,
        url=canon,
        title=title,
        summary=entry.get("summary") or None,
        content=content,
        published_at=_parse_published(entry),
        collected_at=utcnow(),
    )


def fetch_articles(
    publisher: Publisher,
    settings: Settings,
    client: httpx.Client | None = None,
    is_seen: Callable[[str], bool] | None = None,
) -> Iterable[Article]:
    own_client = client is None
    if own_client:
        client = httpx.Client(
            timeout=settings.http_timeout_s,
            headers={"User-Agent": settings.user_agent},
        )
    try:
        for feed_url in publisher.feeds:
            try:
                resp = client.get(feed_url, follow_redirects=True)
                resp.raise_for_status()
                parsed = feedparser.parse(resp.content)
            except Exception as exc:
                log.warning(
                    "feed_fetch_failed",
                    publisher=publisher.id,
                    feed=feed_url,
                    error=str(exc),
                )
                continue
            for entry in parsed.entries:
                try:
                    article = _entry_to_article(
                        publisher,
                        entry,
                        client,
                        publisher.fetch_full_content,
                        is_seen,
                    )
                except Exception as exc:
                    log.warning(
                        "entry_parse_failed", publisher=publisher.id, error=str(exc)
                    )
                    continue
                if article is not None:
                    yield article
    finally:
        if own_client:
            client.close()
