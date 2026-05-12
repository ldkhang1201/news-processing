FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY resolver ./resolver
COPY main.py ./

# Install the project itself (cheap, src-only).
RUN uv sync --frozen --no-dev

ENV PYTHONUNBUFFERED=1 \
    NOMINATIM_CACHE_FILE=/data/geocode_cache.json

VOLUME ["/data"]

CMD ["uv", "run", "--no-sync", "python", "main.py"]
