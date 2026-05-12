# collector

One-shot job that polls RSS feeds from major Vietnamese news publishers,
extracts full article content, and publishes one JSON message per article to a
Kafka topic (default: `articles`) for downstream digestion. Run it on a cron
or systemd timer at whatever cadence matches your freshness target (hourly is
a good default).

## Publishers

VnExpress · Tuổi Trẻ · Thanh Niên · Dân trí · VietnamNet · Znews

Filter at runtime via `ENABLED_PUBLISHERS=vnexpress,tuoitre`.

## Quickstart

```sh
uv sync
cp .env.example .env

docker compose up -d
docker compose exec redpanda rpk topic create articles -p 3 -r 1

uv run python main.py
```

`main.py` polls all enabled publishers once and exits. To run it hourly:

```cron
0 * * * * cd /path/to/collector && uv run python main.py >> /var/log/collector.log 2>&1
```

Consume what got published in another shell:

```sh
docker compose exec redpanda rpk topic consume articles -o start -n 5 | jq .
```

## Configuration

All knobs are env vars (see `.env.example`). Highlights:

| Var | Default | Notes |
|---|---|---|
| `KAFKA_BOOTSTRAP_SERVERS` | `localhost:9092` | |
| `KAFKA_TOPIC` | `articles` | |
| `ENABLED_PUBLISHERS` | (all) | Comma-separated allowlist |
| `DEDUP_DB_PATH` | `./dedup.sqlite` | SQLite seen-set, survives restart |

## Kafka message shape

- **Topic**: `articles`
- **Key**: `article.id` (sha256 of canonical URL, 16 hex chars) — stable for downstream dedup / log compaction.
- **Value**: JSON `Article` (see `collector/models.py`) — id, publisher, url, title, summary, content, published_at, collected_at, language.
- **Headers**: `publisher`, `schema_version=1`, `collected_at`.

## Tests

```sh
uv run pytest
```
