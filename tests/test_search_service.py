from __future__ import annotations

import uuid

from app.db import models
from app.providers.base import ProviderError, ProviderListing
from app.schemas.search import SearchQuery
from app.services import search as search_service


class _FakeListingRow:
    def __init__(self, *, provider: str, external_id: str, row_id):
        self.provider = models.Provider(provider)
        self.external_id = external_id
        self.id = row_id


class _FakeQueryChain:
    def __init__(self, rows):
        self._rows = rows

    def filter(self, *_args, **_kwargs):
        return self

    def all(self):
        return self._rows


class _FakeDB:
    def __init__(self, rows=None):
        self.rows = rows or []

    def query(self, _model):
        return _FakeQueryChain(self.rows)


def test_default_providers_filters_out_non_enum_values(monkeypatch):
    monkeypatch.setattr(search_service, "mock_provider_enabled", lambda: True)
    monkeypatch.setattr(search_service, "list_available_providers", lambda: ["discogs", "mock", "bad"])

    providers = search_service._default_providers()

    assert "discogs" in providers
    assert "mock" in providers
    assert "bad" not in providers


def test_default_providers_excludes_mock_in_production_environment(monkeypatch):
    monkeypatch.setattr(search_service, "mock_provider_enabled", lambda: False)
    monkeypatch.setattr(search_service, "list_available_providers", lambda: ["discogs", "mock"])

    providers = search_service._default_providers()

    assert providers == ["discogs"]


def test_default_providers_includes_mock_only_when_enabled_in_test_environment(monkeypatch):
    monkeypatch.setattr(search_service, "list_available_providers", lambda: ["discogs", "mock"])

    monkeypatch.setattr(search_service, "mock_provider_enabled", lambda: False)
    providers_when_disabled = search_service._default_providers()
    assert providers_when_disabled == ["discogs"]

    monkeypatch.setattr(search_service, "mock_provider_enabled", lambda: True)
    providers_when_enabled = search_service._default_providers()
    assert providers_when_enabled == ["discogs", "mock"]


def test_resolve_providers_uses_query_values_when_present():
    query = SearchQuery(keywords=["primus"], providers=["discogs"], page=1, page_size=10)

    assert search_service._resolve_providers(query) == ["discogs"]


def test_passes_filters_respects_price_bounds():
    query = SearchQuery(
        keywords=["primus"],
        min_price=10,
        max_price=50,
        page=1,
        page_size=10,
    )

    below_min = ProviderListing(
        provider="discogs",
        external_id="below",
        url="https://example.com/below",
        title="Below",
        price=9,
    )
    above_max = ProviderListing(
        provider="discogs",
        external_id="above",
        url="https://example.com/above",
        title="Above",
        price=51,
    )

    assert search_service._passes_filters(below_min, query) is False
    assert search_service._passes_filters(above_max, query) is False


def test_condition_meets_minimum_handles_unknown_values():
    assert search_service._condition_meets_minimum("vg+", "vg") is True
    assert search_service._condition_meets_minimum("poor", "nm") is False
    assert search_service._condition_meets_minimum(None, "nm") is False
    assert search_service._condition_meets_minimum("vg", "unknown-min") is True
    assert search_service._condition_meets_minimum("unknown-condition", "vg") is False


def test_run_search_records_provider_errors_and_filters_results(monkeypatch):
    class _DiscogsProvider:
        default_endpoint = "/discogs/search"

        def __init__(self):
            self.last_duration_ms = 12
            self.last_request_meta = {"page": 1}

        def search(self, *, query, limit):
            assert query["keywords"] == ["primus"]
            assert limit == 2
            return [
                ProviderListing(
                    provider="discogs",
                    external_id="one",
                    url="https://example.com/one",
                    title="One",
                    price=10,
                    condition="vg+",
                ),
                ProviderListing(
                    provider="discogs",
                    external_id="two",
                    url="https://example.com/two",
                    title="Two",
                    price=500,
                    condition="m",
                ),
            ]

    class _MockProvider:
        default_endpoint = "/mock/search"

        def __init__(self):
            self.last_duration_ms = 7

        def search(self, *, query, limit):
            raise ProviderError(
                "mock timeout",
                status_code=504,
                endpoint="/mock/search",
                method="POST",
                duration_ms=99,
                meta={"timeout": True},
            )

    logs = []

    def _provider_factory(name):
        if name == "discogs":
            return _DiscogsProvider
        if name == "mock":
            return _MockProvider
        raise AssertionError(f"unexpected provider {name}")

    monkeypatch.setattr(search_service, "get_provider_class", _provider_factory)
    monkeypatch.setattr(search_service, "log_provider_request", lambda *args, **kwargs: logs.append(kwargs))

    query = SearchQuery(
        keywords=["primus"],
        providers=["discogs", "mock"],
        min_price=5,
        max_price=100,
        min_condition="vg",
        page=1,
        page_size=2,
    )

    result = search_service.run_search(_FakeDB(), user_id=uuid.uuid4(), query=query)

    assert [item.external_id for item in result.items] == ["one"]
    assert result.provider_errors == {"mock": "mock timeout"}
    assert result.providers_searched == ["discogs", "mock"]
    assert len(logs) == 2
    assert logs[0]["status_code"] == 200
    assert logs[1]["status_code"] == 504
    assert logs[1]["method"] == "POST"


def test_run_search_populates_listing_id_from_persisted_listing(monkeypatch):
    existing_id = uuid.uuid4()

    class _DiscogsProvider:
        default_endpoint = "/discogs/search"

        def search(self, *, query, limit):
            return [
                ProviderListing(
                    provider="discogs",
                    external_id="existing-1",
                    url="https://example.com/existing-1",
                    title="Existing",
                    price=12,
                    condition="vg+",
                )
            ]

    db = _FakeDB(rows=[_FakeListingRow(provider="discogs", external_id="existing-1", row_id=existing_id)])

    monkeypatch.setattr(search_service, "get_provider_class", lambda _name: _DiscogsProvider)
    monkeypatch.setattr(search_service, "log_provider_request", lambda *_args, **_kwargs: None)

    query = SearchQuery(keywords=["existing"], providers=["discogs"], page=1, page_size=20)
    result = search_service.run_search(db, user_id=uuid.uuid4(), query=query)

    assert result.items[0].listing_id == existing_id


def test_save_search_alert_uses_default_provider_list(monkeypatch):
    captured = {}

    monkeypatch.setattr(search_service, "_resolve_providers", lambda _query: ["discogs", "mock"])

    def _fake_create_rule(db, *, user_id, name, query, poll_interval_seconds):
        captured.update(
            {
                "db": db,
                "user_id": user_id,
                "name": name,
                "query": query,
                "poll_interval_seconds": poll_interval_seconds,
            }
        )
        return "created"

    monkeypatch.setattr(search_service, "create_watch_rule", _fake_create_rule)

    result = search_service.save_search_alert(
        object(),
        user_id=uuid.uuid4(),
        name="my alert",
        query=SearchQuery(keywords=["primus"], page=1, page_size=10),
        poll_interval_seconds=600,
    )

    assert result == "created"
    assert captured["query"]["sources"] == ["discogs", "mock"]
    assert captured["query"]["keywords"] == ["primus"]


def test_run_search_supports_multiple_provider_request_logs(monkeypatch):
    class _EbayProvider:
        default_endpoint = "/buy/browse/v1/item_summary/search"

        def __init__(self, *, request_logger=None):
            self._request_logger = request_logger

        def search(self, *, query, limit):
            if self._request_logger:
                self._request_logger(
                    search_service.ProviderRequestLog(
                        endpoint="/identity/v1/oauth2/token",
                        method="POST",
                        status_code=200,
                        duration_ms=8,
                        meta={"request_id": "auth-req"},
                    )
                )
                self._request_logger(
                    search_service.ProviderRequestLog(
                        endpoint="/buy/browse/v1/item_summary/search",
                        method="GET",
                        status_code=200,
                        duration_ms=12,
                        meta={"request_id": "data-req"},
                    )
                )
            return [
                ProviderListing(
                    provider="ebay",
                    external_id="abc123",
                    url="https://example.com/abc123",
                    title="Primus LP",
                    price=99,
                )
            ]

    logs = []
    monkeypatch.setattr(search_service, "get_provider_class", lambda _name: _EbayProvider)
    monkeypatch.setattr(search_service, "log_provider_request", lambda *args, **kwargs: logs.append(kwargs))

    query = SearchQuery(keywords=["primus"], providers=["ebay"], page=1, page_size=10)
    result = search_service.run_search(_FakeDB(), user_id=uuid.uuid4(), query=query)

    assert len(result.items) == 1
    assert len(logs) == 2
    assert [log["endpoint"] for log in logs] == [
        "/identity/v1/oauth2/token",
        "/buy/browse/v1/item_summary/search",
    ]
    assert [log["method"] for log in logs] == ["POST", "GET"]
