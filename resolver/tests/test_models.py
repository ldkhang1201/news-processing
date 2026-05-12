from datetime import datetime

import pytest
from pydantic import ValidationError

from resolver.models import Address, Article, LLMEvent, LLMResponse, TrafficEvent


def test_article_round_trip():
    article = Article(
        id="abc1234567890def",
        publisher="vnexpress",
        url="https://vnexpress.net/some-article",
        title="Tai nạn liên hoàn trên cao tốc",
        content="Một vụ tai nạn xảy ra...",
        collected_at=datetime(2026, 4, 27, 10, 0, 0),
    )
    payload = article.model_dump_json()
    again = Article.model_validate_json(payload)
    assert again.id == article.id
    assert again.title == article.title
    assert again.language == "vi"


def test_address_requires_non_empty_province():
    with pytest.raises(ValidationError):
        Address(province="")
    with pytest.raises(ValidationError):
        Address(province="   ")


def test_address_strips_empty_optional_to_none():
    addr = Address(province="Hà Nội", commune="  ", line=None)
    assert addr.commune is None
    assert addr.line is None


def test_llm_event_flattens_address():
    ev = LLMEvent.model_validate(
        {
            "event": "Tai nạn",
            "province": "Sơn La",
            "commune": "xã Bắc Yên",
            "line": "Quốc lộ 6",
            "time": "2026-04-21T14:30:00",
        }
    )
    assert ev.address.province == "Sơn La"
    assert ev.address.commune == "xã Bắc Yên"
    assert ev.address.line == "Quốc lộ 6"
    assert ev.time == datetime(2026, 4, 21, 14, 30, 0)


def test_llm_event_drops_when_province_missing():
    with pytest.raises(ValidationError):
        LLMEvent.model_validate({"event": "Tai nạn", "province": None})


def test_llm_event_time_strips_z_suffix():
    ev = LLMEvent.model_validate(
        {"event": "x", "province": "Hà Nội", "time": "2026-04-21T14:30:00Z"}
    )
    assert ev.time is not None
    assert ev.time.tzinfo is None


def test_llm_event_time_returns_none_on_garbage():
    ev = LLMEvent.model_validate(
        {"event": "x", "province": "Hà Nội", "time": "not-a-time"}
    )
    assert ev.time is None


def test_llm_response_parse_events_drops_invalid():
    resp = LLMResponse.model_validate(
        {
            "events": [
                {"event": "ok", "province": "Hà Nội"},
                {"event": "missing province", "province": ""},
                {"event": "valid", "province": "TP Hồ Chí Minh", "line": "Nguyễn Huệ"},
            ]
        }
    )
    parsed = resp.parse_events()
    assert len(parsed) == 2
    assert parsed[0].address.province == "Hà Nội"
    assert parsed[1].address.line == "Nguyễn Huệ"


def test_llm_response_empty():
    assert LLMResponse(events=[]).parse_events() == []


def test_traffic_event_serializes():
    ev = TrafficEvent(
        event="Tai nạn",
        address=Address(province="Hà Nội", line="Nguyễn Trãi"),
        lat=21.0,
        long=105.8,
        time=datetime(2026, 4, 21, 14, 30, 0),
        article_id="abc",
        article_url="https://example.com",
    )
    payload = ev.model_dump_json()
    assert "Tai nạn" in payload
    assert '"lat":21.0' in payload
