from __future__ import annotations

import sqlite3

from collector.models import Article


_SCHEMA = """
CREATE TABLE IF NOT EXISTS seen (
    id TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    publisher TEXT NOT NULL,
    seen_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_seen_publisher ON seen(publisher);
"""


class SqliteDedup:
    def __init__(self, path: str) -> None:
        self._conn = sqlite3.connect(path, isolation_level=None)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)

    def is_seen(self, article_id: str) -> bool:
        cur = self._conn.execute("SELECT 1 FROM seen WHERE id = ? LIMIT 1", (article_id,))
        return cur.fetchone() is not None

    def mark_seen(self, article: Article) -> None:
        self._conn.execute(
            "INSERT OR IGNORE INTO seen (id, url, publisher, seen_at) VALUES (?, ?, ?, ?)",
            (
                article.id,
                str(article.url),
                article.publisher,
                article.collected_at.isoformat(),
            ),
        )

    def close(self) -> None:
        self._conn.close()
