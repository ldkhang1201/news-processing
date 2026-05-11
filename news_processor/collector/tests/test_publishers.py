from collector.publishers import PUBLISHERS, get_enabled
from collector.settings import Settings


def test_each_publisher_has_id_and_feeds():
    for p in PUBLISHERS:
        assert p.id and p.id.islower()
        assert p.feeds
        for url in p.feeds:
            assert url.startswith("https://")


def test_unique_ids():
    ids = [p.id for p in PUBLISHERS]
    assert len(ids) == len(set(ids))


def test_get_enabled_default_returns_all():
    assert len(get_enabled(Settings(_env_file=None))) == len(PUBLISHERS)


def test_get_enabled_filters():
    s = Settings(_env_file=None, enabled_publishers="vnexpress, tuoitre")
    enabled = get_enabled(s)
    assert {p.id for p in enabled} == {"vnexpress", "tuoitre"}


def test_get_enabled_empty_string_means_all():
    assert len(get_enabled(Settings(_env_file=None, enabled_publishers=""))) == len(PUBLISHERS)
