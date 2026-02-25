from __future__ import annotations

from urllib.parse import urlencode

from app.core.config import settings


def to_affiliate_url(raw_url: str) -> str:
    """Build an eBay Partner Network redirect URL from a raw listing URL."""
    clean = (raw_url or "").strip()
    if not clean:
        return ""

    campaign_id = (settings.ebay_campaign_id or "").strip()
    if not campaign_id:
        return clean

    params = {
        "mkevt": "1",
        "mkcid": "1",
        "mkrid": "711-53200-19255-0",
        "campid": campaign_id,
        "toolid": "10001",
        "customid": (settings.ebay_custom_id or "").strip(),
    }
    q = urlencode({k: v for k, v in params.items() if v})
    separator = "&" if "?" in clean else "?"
    return f"{clean}{separator}{q}"
