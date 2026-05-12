from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel, HttpUrl


def canonicalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    netloc = parts.netloc.lower()
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), netloc, path, parts.query, ""))


def make_article_id(url: str) -> str:
    return hashlib.sha256(canonicalize_url(url).encode()).hexdigest()[:16]


def utcnow() -> datetime:
    return datetime.now(UTC)


class Article(BaseModel):
    id: str
    publisher: str
    url: HttpUrl
    title: str
    summary: str | None = None
    content: str | None = None
    published_at: datetime | None = None
    collected_at: datetime
    language: Literal["vi"] = "vi"
