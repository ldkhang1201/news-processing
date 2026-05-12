import httpx
import respx

from collector.fetcher import fetch_articles
from collector.publishers import Publisher
from collector.settings import Settings


SAMPLE_RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
<title>VnExpress</title>
<link>https://vnexpress.net</link>
<item>
<title>Tin nong hom nay</title>
<link>https://vnexpress.net/article-1</link>
<description>Mot bai bao thu nghiem</description>
<pubDate>Mon, 27 Apr 2026 10:00:00 +0700</pubDate>
<author>An Nguyen</author>
</item>
<item>
<title>Tin thu hai</title>
<link>https://vnexpress.net/article-2</link>
<description>Bai khac</description>
<pubDate>Mon, 27 Apr 2026 11:00:00 +0700</pubDate>
</item>
</channel>
</rss>
"""


@respx.mock
def test_fetch_parses_rss_metadata():
    pub = Publisher(
        id="vnexpress",
        name="VnExpress",
        feeds=("https://vnexpress.net/rss/test.rss",),
        fetch_full_content=False,
    )
    settings = Settings(_env_file=None)
    respx.get("https://vnexpress.net/rss/test.rss").mock(
        return_value=httpx.Response(200, content=SAMPLE_RSS)
    )
    articles = list(fetch_articles(pub, settings))
    assert len(articles) == 2
    assert articles[0].title == "Tin nong hom nay"
    assert articles[0].publisher == "vnexpress"
    assert articles[0].published_at is not None
    assert all(a.content is None for a in articles)
    # ids should be stable and unique
    assert articles[0].id != articles[1].id
    assert len(articles[0].id) == 16


@respx.mock
def test_fetch_returns_empty_on_bad_feed():
    pub = Publisher(
        id="vnexpress",
        name="VnExpress",
        feeds=("https://vnexpress.net/rss/test.rss",),
        fetch_full_content=False,
    )
    settings = Settings(_env_file=None)
    respx.get("https://vnexpress.net/rss/test.rss").mock(
        return_value=httpx.Response(500)
    )
    assert list(fetch_articles(pub, settings)) == []


@respx.mock
def test_fetch_continues_when_one_feed_fails():
    pub = Publisher(
        id="vnexpress",
        name="VnExpress",
        feeds=(
            "https://vnexpress.net/rss/bad.rss",
            "https://vnexpress.net/rss/good.rss",
        ),
        fetch_full_content=False,
    )
    settings = Settings(_env_file=None)
    respx.get("https://vnexpress.net/rss/bad.rss").mock(return_value=httpx.Response(500))
    respx.get("https://vnexpress.net/rss/good.rss").mock(
        return_value=httpx.Response(200, content=SAMPLE_RSS)
    )
    articles = list(fetch_articles(pub, settings))
    assert len(articles) == 2
