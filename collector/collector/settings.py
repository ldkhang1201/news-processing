from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_topic: str = "articles"
    kafka_client_id: str = "collector"
    kafka_acks: str = "all"

    enabled_publishers: str = ""

    dedup_db_path: str = "./dedup.sqlite"
    user_agent: str = (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
    http_timeout_s: float = 15.0
    log_level: str = "INFO"

    def enabled_publisher_ids(self) -> set[str] | None:
        raw = self.enabled_publishers.strip()
        if not raw:
            return None
        return {s.strip() for s in raw.split(",") if s.strip()}
