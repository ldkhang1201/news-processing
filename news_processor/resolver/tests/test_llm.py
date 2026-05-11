import json
from datetime import datetime

import httpx
import pytest
import respx

from resolver.llm import OllamaClient, OllamaError, build_user_message
from resolver.models import Article
from resolver.settings import Settings


def _article(content: str | None = None, summary: str | None = None, title: str = "T") -> Article:
    return Article(
        id="abc1234567890def",
        publisher="vnexpress",
        url="https://vnexpress.net/x",
        title=title,
        content=content,
        summary=summary,
        collected_at=datetime(2026, 4, 27, 10, 0, 0),
    )


def _ollama_response(events: list[dict]) -> dict:
    return {"message": {"role": "assistant", "content": json.dumps({"events": events}, ensure_ascii=False)}}


# ─── build_user_message ───


def test_build_user_message_empty_returns_none():
    assert build_user_message(_article(), max_chars=8000, prefer_summary_over=6000) is None


def test_build_user_message_short_content_returns_none():
    assert build_user_message(_article(content="too short"), max_chars=8000, prefer_summary_over=6000) is None


def test_build_user_message_uses_content_when_small():
    body = "Một bài báo dài đủ để vượt qua ngưỡng tối thiểu của trình thu thập. " * 5
    msg = build_user_message(_article(content=body, summary="bỏ qua"), max_chars=8000, prefer_summary_over=6000)
    assert msg is not None
    assert "Title: T" in msg
    assert "Một bài báo dài" in msg
    assert "bỏ qua" not in msg


def test_build_user_message_prefers_summary_when_content_huge():
    huge = "x" * 7000
    summary = "Tóm tắt do biên tập viên viết, mô tả vắn tắt sự kiện giao thông tại Hà Nội xảy ra hôm nay với thông tin đầy đủ."
    msg = build_user_message(
        _article(content=huge, summary=summary), max_chars=8000, prefer_summary_over=6000
    )
    assert msg is not None
    assert "Tóm tắt" in msg
    assert "x" * 100 not in msg


def test_build_user_message_truncates_by_sentence_boundary():
    sentences = [f"Câu thứ {i} mô tả một sự kiện giao thông tại địa phương." for i in range(50)]
    body = " ".join(sentences)
    msg = build_user_message(_article(content=body), max_chars=300, prefer_summary_over=99999)
    assert msg is not None
    body_part = msg.split("\n\n", 1)[1]
    assert len(body_part) <= 300
    # truncation should land on whole sentences (end with period)
    assert body_part.rstrip().endswith(".")


# ─── OllamaClient.extract_events ───


@respx.mock
def test_extract_happy_path():
    respx.post("http://localhost:11434/api/chat").mock(
        return_value=httpx.Response(
            200,
            json=_ollama_response(
                [
                    {"event": "Tai nạn", "province": "Hà Nội", "line": "Nguyễn Trãi", "time": "2026-04-21T14:30:00"},
                    {"event": "Khởi công", "province": "TP Hồ Chí Minh"},
                ]
            ),
        )
    )
    client = OllamaClient(Settings(_env_file=None))
    article = _article(content="x" * 200)
    events = client.extract_events(article)
    assert len(events) == 2
    assert events[0].address.line == "Nguyễn Trãi"


@respx.mock
def test_extract_empty_events():
    respx.post("http://localhost:11434/api/chat").mock(
        return_value=httpx.Response(200, json=_ollama_response([]))
    )
    client = OllamaClient(Settings(_env_file=None))
    assert client.extract_events(_article(content="x" * 200)) == []


@respx.mock
def test_extract_drops_event_missing_province():
    respx.post("http://localhost:11434/api/chat").mock(
        return_value=httpx.Response(
            200,
            json=_ollama_response(
                [
                    {"event": "no province", "province": ""},
                    {"event": "good", "province": "Hà Nội"},
                ]
            ),
        )
    )
    client = OllamaClient(Settings(_env_file=None))
    events = client.extract_events(_article(content="x" * 200))
    assert len(events) == 1
    assert events[0].address.province == "Hà Nội"


@respx.mock
def test_extract_returns_empty_on_malformed_content():
    respx.post("http://localhost:11434/api/chat").mock(
        return_value=httpx.Response(
            200, json={"message": {"role": "assistant", "content": "not json"}}
        )
    )
    client = OllamaClient(Settings(_env_file=None))
    assert client.extract_events(_article(content="x" * 200)) == []


@respx.mock
def test_extract_retries_on_500_then_succeeds():
    route = respx.post("http://localhost:11434/api/chat").mock(
        side_effect=[
            httpx.Response(500),
            httpx.Response(200, json=_ollama_response([{"event": "ok", "province": "Hà Nội"}])),
        ]
    )
    client = OllamaClient(Settings(_env_file=None))
    events = client.extract_events(_article(content="x" * 200))
    assert len(events) == 1
    assert route.call_count == 2


@respx.mock
def test_extract_raises_after_two_failures():
    respx.post("http://localhost:11434/api/chat").mock(return_value=httpx.Response(500))
    client = OllamaClient(Settings(_env_file=None))
    with pytest.raises(OllamaError):
        client.extract_events(_article(content="x" * 200))


def test_extract_skips_when_body_empty():
    # No HTTP mock needed because no call should be made.
    client = OllamaClient(Settings(_env_file=None))
    assert client.extract_events(_article()) == []
