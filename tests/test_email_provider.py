from __future__ import annotations

import sys
import types

import pytest

from app.services import email_provider
from app.services.email_provider import (
    EmailDeliveryRequest,
    LocalStubEmailProvider,
    SesEmailProvider,
)


@pytest.fixture(autouse=True)
def _clear_provider_cache():
    email_provider.get_email_provider.cache_clear()
    yield
    email_provider.get_email_provider.cache_clear()


def test_local_stub_email_provider_returns_success():
    provider = LocalStubEmailProvider()

    result = provider.send_email(
        EmailDeliveryRequest(to_address="user@example.com", subject="hello", text_body="world")
    )

    assert result.success is True
    assert result.retryable is False
    assert result.provider_message_id == "stub-local-delivery"


def test_ses_email_provider_sends_html_and_configuration_set(monkeypatch):
    sent_payload = {}

    class _FakeClient:
        def send_email(self, **kwargs):
            sent_payload.update(kwargs)
            return {"MessageId": 12345}

    fake_boto3 = types.SimpleNamespace(client=lambda *_args, **_kwargs: _FakeClient())
    monkeypatch.setitem(sys.modules, "boto3", fake_boto3)
    monkeypatch.setattr(email_provider.settings, "ses_sender_email", "sender@example.com")
    monkeypatch.setattr(email_provider.settings, "ses_configuration_set", "cfg-main")
    monkeypatch.setattr(email_provider.settings, "ses_endpoint_url", "")

    provider = SesEmailProvider()
    result = provider.send_email(
        EmailDeliveryRequest(
            to_address="dest@example.com",
            subject="subj",
            text_body="plain",
            html_body="<b>html</b>",
        )
    )

    assert result.success is True
    assert result.provider_message_id == "12345"
    assert sent_payload["ConfigurationSetName"] == "cfg-main"
    assert sent_payload["Destination"]["ToAddresses"] == ["dest@example.com"]
    assert "Html" in sent_payload["Message"]["Body"]


def test_ses_email_provider_maps_retryable_failure(monkeypatch):
    class _FakeClient:
        def send_email(self, **_kwargs):
            exc = RuntimeError("provider down")
            exc.response = {"Error": {"Code": "Throttling", "Message": "slow down"}}
            raise exc

    fake_boto3 = types.SimpleNamespace(client=lambda *_args, **_kwargs: _FakeClient())
    monkeypatch.setitem(sys.modules, "boto3", fake_boto3)

    provider = SesEmailProvider()
    result = provider.send_email(
        EmailDeliveryRequest(to_address="dest@example.com", subject="subj", text_body="plain")
    )

    assert result.success is False
    assert result.retryable is True
    assert result.error_code == "Throttling"
    assert result.error_message == "slow down"


def test_get_email_provider_uses_local_stub_for_unknown_provider(monkeypatch):
    monkeypatch.setattr(email_provider.settings, "notification_email_provider", "unknown")

    provider = email_provider.get_email_provider()

    assert isinstance(provider, LocalStubEmailProvider)


def test_get_email_provider_returns_ses_when_configured(monkeypatch):
    class _FakeClient:
        def send_email(self, **_kwargs):
            return {"MessageId": "m-1"}

    fake_boto3 = types.SimpleNamespace(client=lambda *_args, **_kwargs: _FakeClient())
    monkeypatch.setitem(sys.modules, "boto3", fake_boto3)
    monkeypatch.setattr(email_provider.settings, "notification_email_provider", "ses")

    provider = email_provider.get_email_provider()

    assert isinstance(provider, SesEmailProvider)
