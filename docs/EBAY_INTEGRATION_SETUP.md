# eBay API + EPN Setup (Backend + Webapp)

This guide covers how to provision eBay API credentials, configure WaxWatch, and wire your webapp to consume affiliate-safe URLs.

## 1) Create eBay Developer Account

1. Sign in to the eBay Developer Program: https://developer.ebay.com/
2. Create an application keyset for **Sandbox** and **Production**.
3. Record:
   - `Client ID` (App ID)
   - `Client Secret` (Cert ID)

> WaxWatch server uses OAuth client credentials to call Browse Search.

## 2) Required WaxWatch Backend Environment Variables

Set these in your deployment platform (not committed in `.env`):

- `EBAY_CLIENT_ID`
- `EBAY_CLIENT_SECRET`
- `EBAY_OAUTH_SCOPE` (default: `https://api.ebay.com/oauth/api_scope`)
- `EBAY_MARKETPLACE_ID` (default: `EBAY_US`)
- `EBAY_TIMEOUT_SECONDS` (default: `10.0`)
- `EBAY_MAX_ATTEMPTS` (default: `4`)
- `EBAY_RETRY_BASE_DELAY_MS` (default: `250`)
- `EBAY_RETRY_MAX_DELAY_MS` (default: `5000`)

For affiliate links (EPN), also set:

- `EBAY_CAMPAIGN_ID`
- `EBAY_CUSTOM_ID` (optional - used for your own click attribution)

## 3) Join eBay Partner Network (EPN)

1. Sign up at https://partnernetwork.ebay.com/
2. Create a campaign in EPN and copy your campaign ID.
3. Set `EBAY_CAMPAIGN_ID` in backend env.

WaxWatch stores raw URLs in DB and only appends affiliate params at response time.

## 4) Backend Provider Behavior

- Provider source should be `"ebay"` in watch rule query.
- eBay search endpoint used: `/buy/browse/v1/item_summary/search`.
- Listings are deduped by `(provider="ebay", external_id=itemId)`.
- Raw URLs are stored in DB and `public_url` is emitted for client use.

## 5) Webapp Integration Instructions

When rendering listing links:

1. Prefer `public_url` if present.
2. Fall back to `url` only if `public_url` is absent.
3. Keep link opening in new tab and preserve original event tracking in your analytics layer.

Example (TypeScript):

```ts
const href = listing.public_url ?? listing.url;
window.open(href, "_blank", "noopener,noreferrer");
```

For feed/card components:

- Display price/currency from normalized listing fields.
- Display provider badge `ebay`.
- Do not append affiliate params in the frontend (backend handles it).

## 6) Production Safety Checklist

- [ ] eBay credentials stored in secret manager, not repo.
- [ ] EPN campaign ID configured in each environment.
- [ ] Health checks include at least one scheduled rule run in staging.
- [ ] provider_requests rows show eBay endpoint, status, duration, and error metadata.
- [ ] No external API calls in unit tests (mock/monkeypatch only).
