from __future__ import annotations

from app.monetization.ebay_affiliate import to_affiliate_url


def test_to_affiliate_url_with_campaign(monkeypatch):
    monkeypatch.setattr("app.monetization.ebay_affiliate.settings.ebay_campaign_id", "12345")
    monkeypatch.setattr("app.monetization.ebay_affiliate.settings.ebay_custom_id", "waxwatch")

    raw = "https://www.ebay.com/itm/123456"
    out = to_affiliate_url(raw)

    assert out.startswith(raw)
    assert "campid=12345" in out
    assert "customid=waxwatch" in out


def test_to_affiliate_url_no_campaign_returns_raw(monkeypatch):
    monkeypatch.setattr("app.monetization.ebay_affiliate.settings.ebay_campaign_id", None)
    raw = "https://www.ebay.com/itm/123456"
    assert to_affiliate_url(raw) == raw


def test_to_affiliate_url_blank_source_returns_empty_string(monkeypatch):
    monkeypatch.setattr("app.monetization.ebay_affiliate.settings.ebay_campaign_id", "12345")

    assert to_affiliate_url("   ") == ""
