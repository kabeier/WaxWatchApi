from __future__ import annotations

import httpx

from app.providers.base import ProviderError
from app.providers.ebay import EbayClient


class _FakeResponse:
    def __init__(self, status_code: int, headers: dict[str, str] | None = None, payload: dict | None = None):
        self.status_code = status_code
        self.headers = headers or {}
        self._payload = payload or {}
        self.text = str(self._payload)

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, responses):
        self._responses = list(responses)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def post(self, *_args, **_kwargs):
        result = self._responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    def get(self, *_args, **_kwargs):
        result = self._responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def test_ebay_search_normalizes_payload(monkeypatch):
    monkeypatch.setattr("app.providers.ebay.settings.ebay_client_id", "id")
    monkeypatch.setattr("app.providers.ebay.settings.ebay_client_secret", "secret")
    monkeypatch.setattr("app.providers.ebay.settings.ebay_marketplace_id", "EBAY_US")

    responses = [
        _FakeResponse(200, payload={"access_token": "token"}),
        _FakeResponse(
            200,
            headers={"x-ebay-c-request-id": "r-1"},
            payload={
                "itemSummaries": [
                    {
                        "itemId": "v1|123|0",
                        "title": "Primus LP",
                        "itemWebUrl": "https://www.ebay.com/itm/123",
                        "price": {"value": "49.99", "currency": "USD"},
                        "condition": "Used",
                        "seller": {"username": "seller1"},
                        "itemLocation": {"country": "US"},
                    }
                ]
            },
        ),
    ]

    monkeypatch.setattr("app.providers.ebay.httpx.Client", lambda timeout: _FakeClient(responses))

    listings = EbayClient().search(query={"keywords": ["primus", "vinyl"]}, limit=10)

    assert len(listings) == 1
    listing = listings[0]
    assert listing.provider == "ebay"
    assert listing.external_id == "v1|123|0"
    assert listing.price == 49.99
    assert listing.currency == "USD"


def test_ebay_search_retries_network_error_then_raises(monkeypatch):
    monkeypatch.setattr("app.providers.ebay.settings.ebay_client_id", "id")
    monkeypatch.setattr("app.providers.ebay.settings.ebay_client_secret", "secret")
    monkeypatch.setattr("app.providers.ebay.settings.ebay_max_attempts", 2)
    monkeypatch.setattr("app.providers.ebay.time.sleep", lambda _seconds: None)

    responses = [
        _FakeResponse(200, payload={"access_token": "token"}),
        httpx.RequestError("boom"),
        httpx.RequestError("boom"),
    ]
    monkeypatch.setattr("app.providers.ebay.httpx.Client", lambda timeout: _FakeClient(responses))

    try:
        EbayClient().search(query={"keywords": ["primus"]}, limit=10)
    except ProviderError as exc:
        assert "network error" in str(exc).lower()
        assert exc.meta is not None
        assert exc.meta["attempt"] == 2
        assert exc.meta["attempts_total"] == 2
        assert exc.meta["max_attempts"] == 2
    else:
        raise AssertionError("Expected ProviderError")
