from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, HttpUrl, ValidationError, field_validator, model_validator


class Article(BaseModel):
    """Mirror of the collector's Article schema. Re-declared, not imported."""
    id: str
    publisher: str
    url: HttpUrl
    title: str
    summary: str | None = None
    content: str | None = None
    author: str | None = None
    published_at: datetime | None = None
    collected_at: datetime
    tags: list[str] = []
    language: str = "vi"
    image_url: HttpUrl | None = None


class Address(BaseModel):
    province: str
    commune: str | None = None
    line: str | None = None

    @field_validator("province", mode="before")
    @classmethod
    def _province_required(cls, v: Any) -> str:
        if v is None or not str(v).strip():
            raise ValueError("province must be non-empty")
        return str(v).strip()

    @field_validator("commune", "line", mode="before")
    @classmethod
    def _empty_to_none(cls, v: Any) -> str | None:
        if v is None:
            return None
        s = str(v).strip()
        return s or None


class LLMEvent(BaseModel):
    """One traffic event as emitted by the LLM. Time is naive ISO 8601 (UTC+7 by convention)."""
    event: str
    address: Address
    time: datetime | None = None

    @model_validator(mode="before")
    @classmethod
    def _flatten_address(cls, data: Any) -> Any:
        # LLM emits a flat dict {event, province, commune, line, time};
        # fold the address parts into a nested Address payload.
        if isinstance(data, dict) and "address" not in data:
            data = dict(data)
            data["address"] = {
                "province": data.pop("province", None),
                "commune": data.pop("commune", None),
                "line": data.pop("line", None),
            }
        return data

    @field_validator("event", mode="before")
    @classmethod
    def _strip_event(cls, v: Any) -> str:
        return "" if v is None else str(v).strip()

    @field_validator("time", mode="before")
    @classmethod
    def _parse_time(cls, v: Any) -> datetime | None:
        # Strip tzinfo so all stored times are naive Indochina Time.
        # Returns None on any parse failure (matches demo behavior).
        if v in (None, ""):
            return None
        try:
            ts = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None
        if ts.tzinfo is not None:
            ts = ts.astimezone().replace(tzinfo=None)
        return ts


class LLMResponse(BaseModel):
    """Wrapper that Ollama returns: {\"events\": [...]}."""
    events: list[dict] = Field(default_factory=list)

    def parse_events(self) -> list[LLMEvent]:
        out: list[LLMEvent] = []
        for raw in self.events:
            try:
                out.append(LLMEvent.model_validate(raw))
            except ValidationError:
                # Dropped here: events with empty province, malformed shape, etc.
                continue
        return out


class TrafficEvent(BaseModel):
    """Output schema published to Kafka. lat/long may be None when geocoding fails."""
    event: str
    address: Address
    lat: float | None = None
    long: float | None = None
    time: datetime | None = None
    article_id: str
    article_url: str
