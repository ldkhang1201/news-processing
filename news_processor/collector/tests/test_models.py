from collector.models import Article, canonicalize_url, make_article_id, utcnow


def test_canonical_strips_trailing_slash():
    assert canonicalize_url("https://example.com/path/") == "https://example.com/path"


def test_canonical_strips_fragment():
    assert canonicalize_url("https://example.com/p#section") == "https://example.com/p"


def test_canonical_lowers_host_and_scheme():
    assert canonicalize_url("HTTPS://EXAMPLE.com/p") == "https://example.com/p"


def test_canonical_keeps_query():
    assert canonicalize_url("https://example.com/p?x=1") == "https://example.com/p?x=1"


def test_make_id_stable_across_url_variations():
    a = make_article_id("https://example.com/p")
    b = make_article_id("https://Example.com/p/")
    c = make_article_id("https://example.com/p#frag")
    assert a == b == c
    assert len(a) == 16


def test_make_id_differs_for_different_urls():
    assert make_article_id("https://example.com/a") != make_article_id("https://example.com/b")


def test_article_serializes_with_vietnamese_text():
    article = Article(
        id="abc1234567890def",
        publisher="vnexpress",
        url="https://vnexpress.net/some-article",
        title="Tin nóng hôm nay",
        collected_at=utcnow(),
    )
    payload = article.model_dump_json()
    assert "vnexpress" in payload
    assert "Tin nóng" in payload
    assert article.language == "vi"
