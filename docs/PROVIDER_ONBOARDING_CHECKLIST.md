# Provider Onboarding Checklist

Use this checklist when introducing a new provider under `app/providers/`.

## 1) Implement the provider client

- [ ] Create `<provider>.py` implementing `ProviderClient`.
- [ ] Populate required class attributes:
  - `name`
  - `default_endpoint`
  - `capability_contract` (`ProviderCapabilityContract`)
- [ ] `search()` returns normalized `ProviderListing` objects only.
- [ ] Raise `ProviderError` for expected API/auth/rate-limit failures.
- [ ] Emit provider-request logs **per outbound HTTP call** (auth + data + retry attempts), including status, duration, error, and available request-id/rate-limit metadata.

## 2) Define capability contract clearly

Set a `ProviderCapabilityContract` with explicit behavior:

- [ ] `supports_search` reflects whether keyword search is implemented.
- [ ] `requires_auth` reflects runtime credential requirements.
- [ ] `rate_limits_documented` is true when headers/docs are captured in metadata.
- [ ] `listing_completeness` explains what fields are reliably filled.
- [ ] `pagination_model` identifies `offset`, `cursor`, or `none`.

## 3) Add provider config validation

In `app/core/config.py`:

- [ ] Add provider settings fields (credentials, timeout, retry tuning).
- [ ] Extend `_validate_provider_config()` to mark provider enabled/disabled.
- [ ] Ensure missing credentials **disable** provider with reason instead of hard crashing.

## 4) Register the provider

In `app/providers/registry.py`:

- [ ] Register via `register_provider(...)` in `_build_registrations()`.
- [ ] Wire `enabled_check` to `settings.provider_enabled("<provider>")`.
- [ ] Optionally set `test_client_class` for deterministic tests.

## 5) Ensure normalization compatibility

The listing payload must satisfy shared ingest/search expectations:

- [ ] If storing linked external account tokens, persist lifecycle fields in normalized `external_account_links` columns (`refresh_token`, `access_token_expires_at`, `token_type`, `scopes`) and keep `access_token` encrypted at rest.
- [ ] Ensure migrations backfill normalized lifecycle columns from any legacy provider token metadata keys before rolling provider auth changes.
- [ ] `provider`, `external_id`, `url`, `title`, `price`, and `currency` are set.
- [ ] Optional fields map to canonical keys: `condition`, `seller`, `location`, `discogs_release_id`, `raw`.
- [ ] IDs are stable and deterministic for the same remote listing.
- [ ] Prices are numeric and currency is a 3-letter code when available.
- [ ] Snapshot behavior expectation: ingest creates a `price_snapshots` row on listing create, and on updates whenever either `price` or `currency` changes (no new snapshot when both are unchanged).

## 6) Verification

- [ ] Run relevant tests for search/rule-runner/provider logging.
- [ ] Manually validate provider selection behavior:
  - disabled provider is rejected gracefully.
  - enabled provider is selectable and searchable.
