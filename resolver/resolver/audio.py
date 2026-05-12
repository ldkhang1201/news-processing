from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from resolver.models import Article


class AudioTranscript(BaseModel):
    """Mirror of the audio_processing topic schema. Re-declared, not imported,
    matching the same convention used for Article from collector.
    """
    source: str
    stream_id: int | None = None
    text: str
    event_hint: str = "unknown"
    captured_at: datetime
    audio_duration_s: float | None = None
    stt_time_s: float | None = None
    schema_version: int = 1


def deserialize_audio_transcript(value: bytes) -> AudioTranscript:
    return AudioTranscript.model_validate_json(value)


def transcript_to_article(t: AudioTranscript) -> Article:
    """Wrap a transcript as a synthetic Article so the LLM/geocode pipeline
    treats it like any other input.

    URL is synthetic — `audio.local` makes it obvious to UIs that this didn't
    come from a real publisher's article page. The resolver dedupes by id, not
    URL, so a non-resolvable URL is fine for processing.
    """
    ts = int(t.captured_at.timestamp())
    stream_part = "x" if t.stream_id is None else str(t.stream_id)
    article_id = f"audio-{stream_part}-{ts}"
    title = t.text[:80] + ("…" if len(t.text) > 80 else "") or "audio transcript"
    tags = ["audio", t.source]
    if t.event_hint and t.event_hint != "unknown":
        tags.append(t.event_hint)
    return Article(
        id=article_id,
        publisher=t.source,
        url=f"https://audio.local/{t.source}/{ts}",
        title=title,
        content=t.text,
        collected_at=t.captured_at,
        tags=tags,
        language="vi",
    )
