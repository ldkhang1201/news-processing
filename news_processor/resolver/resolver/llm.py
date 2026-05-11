from __future__ import annotations

import re

import httpx
import structlog
from pydantic import ValidationError

from resolver.models import Article, LLMEvent, LLMResponse
from resolver.settings import Settings


log = structlog.get_logger()


SYSTEM_PROMPT = """You are a traffic news analyzer for Vietnamese news articles. Extract every distinct traffic-related event mentioned in the article.

An event MUST have an identifiable province (tỉnh/thành phố) to be reported. If the article mentions traffic but gives no province, do NOT include it in the output.

For each event, return these fields:
- event: a short brief description IN VIETNAMESE (e.g. "Tai nạn giao thông liên hoàn trên cao tốc", "Khởi công xây dựng cầu đi bộ").
- province: REQUIRED. The Vietnamese province or centrally-governed city (tỉnh or thành phố trực thuộc trung ương). Examples: "Sơn La", "Hà Nội", "TP Hồ Chí Minh", "Đà Nẵng". Use the natural Vietnamese form without the "Tỉnh"/"Thành phố" prefix when it is already unambiguous.
- commune: OPTIONAL. The ward or commune, including the district if mentioned. Examples: "xã Bắc Yên", "phường Trung Hòa, quận Cầu Giấy", "thị trấn Sa Pa, huyện Sa Pa". Use null if the article gives no sub-province location.
- line: OPTIONAL. The most specific locator on the scene — prefer a road name over anything else. Examples: "Quốc lộ 1A", "đường Nguyễn Trãi", "cao tốc Hà Nội – Hải Phòng". If no road is mentioned, a named landmark or intersection is acceptable: "cầu Chương Dương", "ngã tư Sở". Do NOT include km-markers or house numbers. Use null if nothing more specific than the commune is given.
- time: OPTIONAL. The time the event occurred, in ISO 8601 format (e.g. "2026-04-21T14:30:00"), or null if not explicitly stated. DO NOT use the article's publish date.

Return a JSON object of this shape: {"events": [{"event": ..., "province": ..., "commune": ..., "line": ..., "time": ...}, ...]}
If the article contains no traffic events with an identifiable province, return {"events": []}.
"""


_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")
_MIN_BODY_CHARS = 100


class OllamaError(Exception):
    """Raised when Ollama is unreachable or returns non-2xx after retry."""


def build_user_message(
    article: Article, max_chars: int, prefer_summary_over: int
) -> str | None:
    """Build the user message sent to Ollama, or None if the article has no usable body.

    Prefers `summary` when `content` is large (editor-curated text usually carries the
    location more reliably). Truncates by sentence boundary so Vietnamese diacritics
    aren't cut mid-word.
    """
    content = (article.content or "").strip()
    summary = (article.summary or "").strip()

    if content and len(content) > prefer_summary_over and summary:
        body = summary
    else:
        body = content or summary

    if not body:
        return None

    if len(body) > max_chars:
        body = _sentence_truncate(body, max_chars)

    if len(body) < _MIN_BODY_CHARS:
        return None

    return f"Title: {article.title}\n\n{body}"


def _sentence_truncate(text: str, max_chars: int) -> str:
    parts = [p for p in _SENTENCE_SPLIT.split(text) if p]
    out: list[str] = []
    used = 0
    for p in parts:
        added = len(p) + (1 if out else 0)
        if used + added > max_chars:
            break
        out.append(p)
        used += added
    return " ".join(out) if out else text[:max_chars]


class OllamaClient:
    def __init__(self, settings: Settings) -> None:
        self._url = settings.ollama_host.rstrip("/") + "/api/chat"
        self._model = settings.ollama_model
        self._max_chars = settings.ollama_body_max_chars
        self._prefer_summary_over = settings.ollama_prefer_summary_over
        self._log_raw = settings.ollama_log_raw_response
        self._client = httpx.Client(timeout=settings.ollama_timeout_s)

    def extract_events(self, article: Article) -> list[LLMEvent]:
        user = build_user_message(article, self._max_chars, self._prefer_summary_over)
        if user is None:
            return []

        body = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "format": "json",
            # Disable thinking mode for reasoning models (e.g. qwen3.5).
            # Thinking blows past the timeout on multi-KB Vietnamese articles
            # and the chain-of-thought is unused — we only consume the JSON.
            "think": False,
        }

        last_exc: Exception | None = None
        for attempt in range(2):
            try:
                resp = self._client.post(self._url, json=body)
                resp.raise_for_status()
                content = resp.json().get("message", {}).get("content", "{}")
                if self._log_raw:
                    log.info("llm_raw_response", article_id=article.id, content=content)
                try:
                    parsed = LLMResponse.model_validate_json(content).parse_events()
                except (ValueError, ValidationError) as e:
                    log.warning(
                        "llm_bad_shape",
                        article_id=article.id,
                        error=str(e),
                        sample=content[:200],
                    )
                    return []
                return parsed
            except (httpx.HTTPError, httpx.HTTPStatusError) as e:
                last_exc = e
                if attempt == 0:
                    log.warning(
                        "llm_call_failed_retrying",
                        article_id=article.id,
                        error=str(e),
                    )
        assert last_exc is not None
        raise OllamaError(f"ollama call failed twice for {article.id}: {last_exc}") from last_exc

    def close(self) -> None:
        self._client.close()
