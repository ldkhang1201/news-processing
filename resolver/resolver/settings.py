from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_input_topic: str = "articles"
    kafka_audio_topic: str = ""  # empty disables audio source
    kafka_output_topic: str = "events"
    kafka_output_partitions: int = 3
    kafka_output_replication_factor: int = 1
    kafka_group_id: str = "resolver"
    kafka_client_id: str = "resolver"
    kafka_acks: str = "all"
    kafka_max_poll_interval_ms: int = 900_000
    kafka_session_timeout_ms: int = 45_000

    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b"
    ollama_timeout_s: float = 300.0
    ollama_body_max_chars: int = 8000
    ollama_prefer_summary_over: int = 6000
    ollama_log_raw_response: bool = False

    nominatim_endpoint: str = "https://nominatim.openstreetmap.org/search"
    nominatim_user_agent: str = "vn-traffic-resolver/0.1 (khangl@nvidia.com)"
    nominatim_rate_limit_s: float = 1.1
    nominatim_timeout_s: float = 10.0
    nominatim_failure_ttl_days: int = 7
    nominatim_cache_file: str = "./geocode_cache.json"
    nominatim_country_code: str = "vn"

    log_level: str = "INFO"

    max_articles: int = 0  # 0 = unlimited; >0 stops after N processed articles
