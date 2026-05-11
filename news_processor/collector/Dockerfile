FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY collector ./collector
COPY main.py ./

RUN uv sync --frozen --no-dev

ENV PYTHONUNBUFFERED=1 \
    DEDUP_DB_PATH=/data/dedup.sqlite

VOLUME ["/data"]

# Collector is a one-shot job. Schedule it externally (cron / docker compose
# run / k8s CronJob) — `restart: no` in compose. The default CMD just runs once.
CMD ["uv", "run", "--no-sync", "python", "main.py"]
