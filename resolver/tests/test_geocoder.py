import json
from datetime import datetime, timedelta

import httpx
import pytest
import respx

from resolver.geocoder import NominatimClient
from resolver.models import Address
from resolver.settings import Settings


@pytest.fixture
def settings(tmp_path):
    return Settings(
        _env_file=None,
        nominatim_cache_file=str(tmp_path / "cache.json"),
        nominatim_rate_limit_s=0.0,
    )


def _result(lat: float, lon: float) -> list[dict]:
    return [{"lat": str(lat), "lon": str(lon)}]


# ─── pure helpers ───


def test_build_q_most_specific_first(settings):
    addr = Address(province="Hà Nội", commune="phường Trung Hòa", line="Nguyễn Trãi")
    assert NominatimClient._build_q(addr) == "Nguyễn Trãi, phường Trung Hòa, Hà Nội"


def test_canonical_key_normalizes_whitespace(settings):
    client = NominatimClient(settings)
    a = Address(province="Hà Nội", commune="  phường  Trung Hòa  ", line="Nguyễn Trãi")
    b = Address(province="Hà Nội", commune="phường Trung Hòa", line="nguyễn trãi")
    assert client._canonical_key(a) == client._canonical_key(b)


def test_fallback_levels_dedups_when_no_line(settings):
    client = NominatimClient(settings)
    addr = Address(province="Hà Nội", commune="phường Trung Hòa", line=None)
    levels = client._fallback_levels(addr)
    qs = [client._build_q(level) for level in levels]
    # full level == "drop line" level when line is already None → deduped
    assert qs == ["phường Trung Hòa, Hà Nội", "Hà Nội"]


# ─── geocode + cache ───


@respx.mock
def test_geocode_returns_coords_on_success(settings):
    respx.get("https://nominatim.openstreetmap.org/search").mock(
        return_value=httpx.Response(200, json=_result(21.0, 105.8))
    )
    client = NominatimClient(settings)
    result = client.geocode(Address(province="Hà Nội"))
    assert result == (21.0, 105.8)


@respx.mock
def test_geocode_caches_positive_result(settings):
    route = respx.get("https://nominatim.openstreetmap.org/search").mock(
        return_value=httpx.Response(200, json=_result(21.0, 105.8))
    )
    client = NominatimClient(settings)
    client.geocode(Address(province="Hà Nội"))
    client.geocode(Address(province="Hà Nội"))
    assert route.call_count == 1


@respx.mock
def test_geocode_caches_negative_result_within_ttl(settings):
    route = respx.get("https://nominatim.openstreetmap.org/search").mock(
        return_value=httpx.Response(200, json=[])
    )
    client = NominatimClient(settings)
    assert client.geocode(Address(province="Đảo Hư Cấu")) is None
    assert client.geocode(Address(province="Đảo Hư Cấu")) is None
    # Three fallback levels collapse to one query when commune/line absent.
    assert route.call_count == 1


@respx.mock
def test_geocode_rechecks_after_negative_ttl_expires(settings, tmp_path):
    cache_path = tmp_path / "cache.json"
    expired = (datetime.now() - timedelta(days=settings.nominatim_failure_ttl_days + 1)).isoformat()
    addr = Address(province="X")
    client = NominatimClient(settings)
    key = client._canonical_key(addr)
    cache_path.write_text(json.dumps({key: {"lat": None, "long": None, "resolved_at": expired}}))
    # rebuild client to pick up the cache file
    client = NominatimClient(settings)

    route = respx.get("https://nominatim.openstreetmap.org/search").mock(
        return_value=httpx.Response(200, json=_result(10.0, 20.0))
    )
    result = client.geocode(addr)
    assert result == (10.0, 20.0)
    assert route.call_count == 1


@respx.mock
def test_geocode_falls_back_when_full_query_empty(settings):
    """First (full) query empty; second (drop line) returns a hit."""
    full_q = "Nguyễn Trãi, phường Trung Hòa, Hà Nội"
    fallback_q = "phường Trung Hòa, Hà Nội"
    full_route = respx.get(
        "https://nominatim.openstreetmap.org/search", params={"q": full_q}
    ).mock(return_value=httpx.Response(200, json=[]))
    fallback_route = respx.get(
        "https://nominatim.openstreetmap.org/search", params={"q": fallback_q}
    ).mock(return_value=httpx.Response(200, json=_result(21.02, 105.81)))

    client = NominatimClient(settings)
    result = client.geocode(
        Address(province="Hà Nội", commune="phường Trung Hòa", line="Nguyễn Trãi")
    )
    assert result == (21.02, 105.81)
    assert full_route.call_count == 1
    assert fallback_route.call_count == 1


@respx.mock
def test_geocode_handles_http_error_gracefully(settings):
    respx.get("https://nominatim.openstreetmap.org/search").mock(
        return_value=httpx.Response(500)
    )
    client = NominatimClient(settings)
    assert client.geocode(Address(province="Hà Nội")) is None


# ─── geocode_many ───


@respx.mock
def test_geocode_many_dedups_repeated_addresses(settings):
    route = respx.get("https://nominatim.openstreetmap.org/search").mock(
        return_value=httpx.Response(200, json=_result(21.0, 105.8))
    )
    client = NominatimClient(settings)
    addrs = [
        Address(province="Hà Nội"),
        Address(province="Hà Nội"),
        Address(province="Hà Nội"),
    ]
    results = client.geocode_many(addrs)
    assert results == [(21.0, 105.8)] * 3
    assert route.call_count == 1


# ─── rate limiting ───


@respx.mock
def test_rate_limit_sleeps_between_calls(monkeypatch, tmp_path):
    sleeps: list[float] = []
    now_ref = [0.0]

    def fake_monotonic() -> float:
        return now_ref[0]

    def fake_sleep(s: float) -> None:
        sleeps.append(s)
        now_ref[0] += s

    monkeypatch.setattr("resolver.geocoder.time.monotonic", fake_monotonic)
    monkeypatch.setattr("resolver.geocoder.time.sleep", fake_sleep)

    settings = Settings(
        _env_file=None,
        nominatim_cache_file=str(tmp_path / "cache.json"),
        nominatim_rate_limit_s=1.5,
    )
    respx.get("https://nominatim.openstreetmap.org/search").mock(
        return_value=httpx.Response(200, json=_result(21.0, 105.8))
    )
    client = NominatimClient(settings)
    client.geocode(Address(province="A"))
    client.geocode(Address(province="B"))

    # First call has nothing to wait for. Second call should wait the full interval
    # because no real time elapsed between them.
    assert any(abs(s - 1.5) < 1e-6 for s in sleeps)
