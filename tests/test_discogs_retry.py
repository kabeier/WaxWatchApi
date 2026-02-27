from __future__ import annotations

import httpx

from app.providers.base import ProviderError
from app.providers.discogs import DiscogsClient


class _FakeResponse:
    def __init__(self, status_code: int, headers: dict[str, str] | None = None, payload: dict | None = None):
        self.status_code = status_code
        self.headers = headers or {}
        self._payload = payload or {"results": []}

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, responses):
        self._responses = list(responses)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def get(self, *_args, **_kwargs):
        result = self._responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def test_discogs_retries_and_uses_retry_after(monkeypatch):
    sleeps: list[float] = []

    def fake_sleep(seconds: float):
        sleeps.append(seconds)

    responses = [
        _FakeResponse(429, headers={"Retry-After": "0"}),
        _FakeResponse(200, headers={"X-Discogs-Ratelimit-Remaining": "55"}, payload={"results": []}),
    ]

    monkeypatch.setattr("app.providers.discogs.time.sleep", fake_sleep)
    monkeypatch.setattr("app.providers.discogs.httpx.Client", lambda timeout: _FakeClient(responses))
    monkeypatch.setattr("app.providers.discogs.settings.discogs_max_attempts", 2)

    client = DiscogsClient()
    listings = client.search(query={"keywords": ["primus"]}, limit=10)

    assert listings == []
    assert len(sleeps) == 1
    assert client.last_request_meta is not None
    assert client.last_request_meta["attempt"] == 2
    assert client.last_request_meta["attempts_total"] == 2
    assert client.last_request_meta["max_attempts"] == 2


def test_discogs_network_error_has_attempt_metadata(monkeypatch):
    monkeypatch.setattr("app.providers.discogs.time.sleep", lambda _seconds: None)
    monkeypatch.setattr(
        "app.providers.discogs.httpx.Client",
        lambda timeout: _FakeClient([httpx.RequestError("boom"), httpx.RequestError("boom")]),
    )
    monkeypatch.setattr("app.providers.discogs.settings.discogs_max_attempts", 2)

    client = DiscogsClient()

    try:
        client.search(query={"keywords": ["primus"]}, limit=10)
    except ProviderError as exc:
        assert exc.meta is not None
        assert exc.meta["attempt"] == 2
        assert exc.meta["attempts_total"] == 2
        assert exc.meta["max_attempts"] == 2
    else:
        raise AssertionError("Expected ProviderError")
