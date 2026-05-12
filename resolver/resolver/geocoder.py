"""Nominatim-based geocoder with disk cache and rate limiting.

The LLM emits structured Vietnamese address components `{province, commune, line}`;
this module resolves them to (lat, long) via OpenStreetMap's Nominatim free-text API.

Behavior (ported from demo/geocoder.py, refactored to instance state):
- Free-text query mode: structured params don't map onto Vietnam's admin hierarchy,
  so we concatenate components into `q=` (most-specific first) with `countrycodes=vn`.
- Progressive fallback: full → drop `line` → province only. Levels deduped by query.
- Disk cache. Positive entries never expire; negative entries respect failure_ttl_days.
- Rate limit: at least rate_limit_s between outgoing HTTP calls (thread-safe).
- Never raises out of the public API; logs a warning and returns None on failure.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

import httpx
import structlog

from resolver.models import Address
from resolver.settings import Settings


log = structlog.get_logger()

_WS = re.compile(r"\s+")


class NominatimClient:
    def __init__(self, settings: Settings) -> None:
        self._endpoint = settings.nominatim_endpoint
        self._user_agent = settings.nominatim_user_agent
        self._rate_limit_s = settings.nominatim_rate_limit_s
        self._failure_ttl = timedelta(days=settings.nominatim_failure_ttl_days)
        self._country_code = settings.nominatim_country_code
        self._cache_path = Path(settings.nominatim_cache_file)
        self._client = httpx.Client(timeout=settings.nominatim_timeout_s)
        self._lock = threading.Lock()
        self._last_call_at: float = 0.0
        self._cache: dict[str, dict] = self._load_cache(self._cache_path)

    # ─── public ───

    def geocode(self, addr: Address) -> tuple[float, float] | None:
        """Resolve a structured Vietnamese address to (lat, long), or None. Never raises."""
        key = self._canonical_key(addr)
        with self._lock:
            entry = self._cache.get(key)
            if entry and self._entry_fresh(entry):
                lat, lon = entry.get("lat"), entry.get("long")
                if lat is not None and lon is not None:
                    return float(lat), float(lon)
                return None

            result: tuple[float, float] | None = None
            for level in self._fallback_levels(addr):
                self._rate_limit()
                result = self._query(level)
                if result is not None:
                    break

            self._cache[key] = {
                "lat": result[0] if result else None,
                "long": result[1] if result else None,
                "resolved_at": datetime.now().isoformat(timespec="seconds"),
            }
            try:
                self._save_cache()
            except OSError as e:
                log.warning("geocode_cache_save_failed", error=str(e))
        return result

    def geocode_many(self, addrs: list[Address]) -> list[tuple[float, float] | None]:
        """Resolve in order; per-call dedup so repeated addresses share one resolution."""
        out: list[tuple[float, float] | None] = []
        seen: dict[str, tuple[float, float] | None] = {}
        for addr in addrs:
            key = self._canonical_key(addr)
            if key in seen:
                out.append(seen[key])
                continue
            result = self.geocode(addr)
            seen[key] = result
            out.append(result)
        return out

    def close(self) -> None:
        self._client.close()

    # ─── internals ───

    @staticmethod
    def _normalize(text: str) -> str:
        return _WS.sub(" ", text.strip().lower())

    def _canonical_key(self, addr: Address) -> str:
        return "|".join(
            self._normalize(getattr(addr, f) or "") for f in ("line", "commune", "province")
        )

    @staticmethod
    def _build_q(addr: Address) -> str:
        parts = [addr.line, addr.commune, addr.province]
        return ", ".join(p for p in parts if p)

    def _fallback_levels(self, addr: Address) -> list[Address]:
        levels = [
            addr,
            addr.model_copy(update={"line": None}),
            addr.model_copy(update={"line": None, "commune": None}),
        ]
        seen: set[str] = set()
        out: list[Address] = []
        for a in levels:
            q = self._build_q(a)
            if q and q not in seen:
                seen.add(q)
                out.append(a)
        return out

    def _entry_fresh(self, entry: dict) -> bool:
        if entry.get("lat") is not None and entry.get("long") is not None:
            return True
        resolved_at = entry.get("resolved_at")
        if not resolved_at:
            return False
        try:
            ts = datetime.fromisoformat(resolved_at)
        except ValueError:
            return False
        return datetime.now() - ts < self._failure_ttl

    def _rate_limit(self) -> None:
        # Caller must hold self._lock.
        now = time.monotonic()
        wait = self._rate_limit_s - (now - self._last_call_at)
        if wait > 0:
            time.sleep(wait)
        self._last_call_at = time.monotonic()

    def _query(self, addr: Address) -> tuple[float, float] | None:
        q = self._build_q(addr)
        if not q:
            return None
        params: dict[str, str | int] = {"q": q, "format": "json", "limit": 1}
        if self._country_code:
            params["countrycodes"] = self._country_code
        headers = {"User-Agent": self._user_agent}
        try:
            resp = self._client.get(self._endpoint, params=params, headers=headers)
        except httpx.HTTPError as e:
            log.warning("geocode_request_failed", q=q, error=str(e))
            return None
        if resp.status_code != 200:
            log.warning("geocode_non_200", q=q, status=resp.status_code)
            return None
        try:
            results = resp.json()
        except ValueError as e:
            log.warning("geocode_bad_json", q=q, error=str(e))
            return None
        if not results:
            return None
        top = results[0]
        try:
            return float(top["lat"]), float(top["lon"])
        except (KeyError, TypeError, ValueError) as e:
            log.warning("geocode_bad_result", q=q, error=str(e))
            return None

    @staticmethod
    def _load_cache(path: Path) -> dict:
        if not path.exists():
            return {}
        try:
            with path.open("r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            log.warning("geocode_cache_load_failed", error=str(e))
            return {}

    def _save_cache(self) -> None:
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._cache_path.with_suffix(self._cache_path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(self._cache, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self._cache_path)
