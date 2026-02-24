from __future__ import annotations

from app.db import models
from app.providers.base import ProviderError, ProviderListing
from app.services.rule_runner import run_rule_once


class _OkProvider:
    name = "ebay"
    default_endpoint = "/buy/browse/v1/item_summary/search"

    def __init__(self):
        self.last_duration_ms = 14
        self.last_request_meta = {"request_id": "ok-1"}

    def search(self, *, query, limit=20):
        return [
            ProviderListing(
                provider="ebay",
                external_id="i-1",
                url="https://www.ebay.com/itm/1",
                title="Primus Vinyl",
                price=55.0,
                currency="USD",
            )
        ]


class _FailProvider:
    name = "ebay"
    default_endpoint = "/buy/browse/v1/item_summary/search"

    def search(self, *, query, limit=20):
        raise ProviderError(
            "bad request",
            status_code=429,
            endpoint=self.default_endpoint,
            method="GET",
            duration_ms=11,
            meta={"retry_after_seconds": 1},
        )


class _CrashProvider:
    name = "ebay"
    default_endpoint = "/buy/browse/v1/item_summary/search"

    def search(self, *, query, limit=20):
        raise RuntimeError("unexpected parser issue")


def _make_rule(db_session, user_id):
    rule = models.WatchSearchRule(
        user_id=user_id,
        name="ebay rule",
        query={"keywords": ["primus"], "sources": ["ebay"], "max_price": 70},
        is_active=True,
        poll_interval_seconds=600,
    )
    db_session.add(rule)
    db_session.flush()
    return rule


def test_run_rule_once_logs_provider_request_success(db_session, user, monkeypatch):
    rule = _make_rule(db_session, user.id)
    monkeypatch.setattr("app.services.rule_runner.get_provider_class", lambda _source: _OkProvider)

    summary = run_rule_once(db_session, user_id=user.id, rule_id=rule.id, limit=5)

    req = db_session.query(models.ProviderRequest).order_by(models.ProviderRequest.created_at.desc()).first()
    assert req is not None
    assert req.provider == models.Provider.ebay
    assert req.user_id == user.id
    assert req.endpoint == "/buy/browse/v1/item_summary/search"
    assert req.status_code == 200
    assert summary.fetched == 1


def test_run_rule_once_logs_provider_request_providererror(db_session, user, monkeypatch):
    rule = _make_rule(db_session, user.id)
    monkeypatch.setattr("app.services.rule_runner.get_provider_class", lambda _source: _FailProvider)

    summary = run_rule_once(db_session, user_id=user.id, rule_id=rule.id, limit=5)

    req = db_session.query(models.ProviderRequest).order_by(models.ProviderRequest.created_at.desc()).first()
    assert req is not None
    assert req.user_id == user.id
    assert req.status_code == 429
    assert req.error is not None
    assert summary.fetched == 0


def test_run_rule_once_logs_provider_request_unexpected_exception(db_session, user, monkeypatch):
    rule = _make_rule(db_session, user.id)
    monkeypatch.setattr("app.services.rule_runner.get_provider_class", lambda _source: _CrashProvider)

    summary = run_rule_once(db_session, user_id=user.id, rule_id=rule.id, limit=5)

    req = db_session.query(models.ProviderRequest).order_by(models.ProviderRequest.created_at.desc()).first()
    assert req is not None
    assert req.user_id == user.id
    assert req.status_code is None
    assert req.error is not None
    assert req.meta is not None
    assert req.meta["exception_type"] == "RuntimeError"
    assert summary.fetched == 0
