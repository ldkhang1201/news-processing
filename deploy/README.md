# stack — dockerized pipeline

Brings up the four pipeline components (resolver, audio STT server, audio
stream client, collector) on top of the long-running redpanda broker that's
already on the host. Designed to coexist with the running backend +
cloudflared tunnel — neither is touched.

## Layout

```
~/collector/docker-compose.yml      # owns redpanda, NOT modified by this stack
~/stack/docker-compose.yml          # this file
~/resolver/                         # build context
~/audio_processing/                 # build context
~/collector/                        # build context for the dockerized collector
```

The compose file joins the existing `collector_default` network as `external: true`,
so the running redpanda is reachable as `collector-redpanda:9092` from every
service here. We never recreate or stop the broker.

## Bring it up

```sh
cd ~/stack

# Build all four images.
docker compose build

# Start the always-on services (resolver + audio STT + stream client).
docker compose up -d resolver audio-stt audio-client

# Watch logs.
docker compose logs -f resolver audio-client
```

## Run the collector once

The collector is a one-shot job (it polls feeds and exits). Run on demand:

```sh
docker compose --profile oneshot run --rm collector
```

To run hourly, drop this into the host crontab (the running host collector
should be stopped first):

```cron
0 * * * * cd /home/ubuntu/stack && docker compose --profile oneshot run --rm collector >> /var/log/collector.log 2>&1
```

## Verify the audio path end-to-end

```sh
# Topics — `audio_transcripts` should appear once audio-client has run.
docker exec collector-redpanda rpk topic list

# Tail transcripts as they land.
docker exec collector-redpanda rpk topic consume audio_transcripts -o end | jq .

# Tail resolved events.
docker exec collector-redpanda rpk topic consume events -o end | jq .
```

## Existing host processes — what we do and don't touch

| Process | Action |
|---|---|
| `collector-redpanda` (container) | Reuse via `external` network. Untouched. |
| `backend` (uvicorn :8000 on host) | Untouched. Containers don't bind to host :8000. |
| `cloudflared tunnel` (host) | Untouched. |
| `ollama serve` (host loopback) | Untouched. Resolver points to a100 by default. |
| `uv run python main.py` (host collector) | Stop manually before enabling the cron above to avoid duplicate publishing. |

## Configuration overrides

The compose file env vars override anything in the `.env.example` files for
the few values that change inside the container (Kafka bootstrap, audio
topic, STT URL). Other values (Ollama host, Nominatim, etc.) come from each
project's `.env`.
