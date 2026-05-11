from datetime import UTC, datetime

from collector.dedup import SqliteDedup
from collector.models import Article


def _article(id_: str = "abc1234567890def") -> Article:
    return Article(
        id=id_,
        publisher="vnexpress",
        url="https://vnexpress.net/x",
        title="t",
        collected_at=datetime.now(UTC),
    )


def test_first_unseen_then_seen(tmp_db):
    d = SqliteDedup(tmp_db)
    a = _article()
    assert not d.is_seen(a.id)
    d.mark_seen(a)
    assert d.is_seen(a.id)
    d.close()


def test_survives_reopen(tmp_db):
    d = SqliteDedup(tmp_db)
    d.mark_seen(_article())
    d.close()

    d2 = SqliteDedup(tmp_db)
    assert d2.is_seen("abc1234567890def")
    d2.close()


def test_unrelated_id_not_seen(tmp_db):
    d = SqliteDedup(tmp_db)
    d.mark_seen(_article("aaaa111122223333"))
    assert not d.is_seen("bbbb444455556666")
    d.close()


def test_mark_seen_is_idempotent(tmp_db):
    d = SqliteDedup(tmp_db)
    a = _article()
    d.mark_seen(a)
    d.mark_seen(a)  # must not raise
    assert d.is_seen(a.id)
    d.close()
