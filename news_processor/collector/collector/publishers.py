from __future__ import annotations

from dataclasses import dataclass

from collector.settings import Settings


@dataclass(frozen=True)
class Publisher:
    id: str
    name: str
    feeds: tuple[str, ...]
    timezone: str = "Asia/Ho_Chi_Minh"
    fetch_full_content: bool = True


PUBLISHERS: tuple[Publisher, ...] = (
    Publisher(
        id="vnexpress",
        name="VnExpress",
        feeds=(
            "https://vnexpress.net/rss/tin-moi-nhat.rss",
            "https://vnexpress.net/rss/the-gioi.rss",
            "https://vnexpress.net/rss/kinh-doanh.rss",
        ),
    ),
    Publisher(
        id="tuoitre",
        name="Tuổi Trẻ",
        feeds=(
            "https://tuoitre.vn/rss/tin-moi-nhat.rss",
            "https://tuoitre.vn/rss/the-gioi.rss",
        ),
    ),
    Publisher(
        id="thanhnien",
        name="Thanh Niên",
        feeds=(
            "https://thanhnien.vn/rss/home.rss",
            "https://thanhnien.vn/rss/thoi-su.rss",
        ),
    ),
    Publisher(
        id="dantri",
        name="Dân trí",
        feeds=(
            "https://dantri.com.vn/rss/home.rss",
            "https://dantri.com.vn/rss/the-gioi.rss",
        ),
    ),
    Publisher(
        id="vietnamnet",
        name="VietnamNet",
        feeds=(
            "https://vietnamnet.vn/thoi-su.rss",
            "https://vietnamnet.vn/the-gioi.rss",
        ),
    ),
    Publisher(
        id="znews",
        name="Znews",
        feeds=(
            "https://znews.vn/rss/thoi-su.rss",
            "https://znews.vn/rss/the-gioi.rss",
        ),
    ),
)


def get_enabled(settings: Settings) -> list[Publisher]:
    allow = settings.enabled_publisher_ids()
    if allow is None:
        return list(PUBLISHERS)
    return [p for p in PUBLISHERS if p.id in allow]
