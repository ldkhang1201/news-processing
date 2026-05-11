from datetime import UTC, datetime

from resolver.audio import (
    AudioTranscript,
    deserialize_audio_transcript,
    transcript_to_article,
)


def _transcript(**overrides) -> AudioTranscript:
    base = dict(
        source="VOH Channel 1",
        stream_id=0,
        text="tình trạng kẹt xe trên cầu Sài Gòn lúc sáng nay",
        event_hint="traffic_jam",
        captured_at=datetime(2026, 5, 10, 7, 42, 11, tzinfo=UTC),
        audio_duration_s=20.0,
        stt_time_s=1.84,
    )
    base.update(overrides)
    return AudioTranscript(**base)


def test_deserialize_round_trip():
    raw = _transcript().model_dump_json().encode()
    parsed = deserialize_audio_transcript(raw)
    assert parsed.source == "VOH Channel 1"
    assert parsed.event_hint == "traffic_jam"
    assert parsed.stream_id == 0


def test_transcript_to_article_basic_shape():
    t = _transcript()
    a = transcript_to_article(t)
    assert a.publisher == "VOH Channel 1"
    assert a.content == t.text
    assert a.language == "vi"
    assert a.url.host == "audio.local"
    assert "audio" in a.tags
    assert "VOH Channel 1" in a.tags
    assert "traffic_jam" in a.tags


def test_transcript_to_article_id_is_stable():
    t1 = _transcript()
    t2 = _transcript()
    assert transcript_to_article(t1).id == transcript_to_article(t2).id


def test_transcript_to_article_id_changes_with_capture_time():
    t1 = _transcript(captured_at=datetime(2026, 5, 10, 7, 42, 11, tzinfo=UTC))
    t2 = _transcript(captured_at=datetime(2026, 5, 10, 7, 42, 31, tzinfo=UTC))
    assert transcript_to_article(t1).id != transcript_to_article(t2).id


def test_transcript_to_article_truncates_long_title():
    long_text = "x" * 200
    a = transcript_to_article(_transcript(text=long_text))
    assert len(a.title) == 81  # 80 chars + ellipsis
    assert a.title.endswith("…")


def test_transcript_to_article_omits_unknown_event_hint_from_tags():
    a = transcript_to_article(_transcript(event_hint="unknown"))
    assert "unknown" not in a.tags


def test_transcript_to_article_handles_missing_stream_id():
    a = transcript_to_article(_transcript(stream_id=None))
    assert a.id.startswith("audio-x-")
