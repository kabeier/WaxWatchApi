# WaxWatch Frontend API Contract

**Contract version:** `2026-03-02.0`

This contract captures **current API behavior** and maps it to intended React surfaces so frontend can scaffold screens directly from OpenAPI payloads.

## Changelog

- `2026-03-02.0`
  - Documented `/readyz` DB readiness timeout enforcement now uses backend-agnostic `_run_with_timeout(...)` wrapping, while keeping Postgres `SET LOCAL statement_timeout` as a secondary safeguard.
  - Confirmed readiness timeout failures surface explicit reasons (for example `db readiness probe timed out after ...`) and no frontend request/response schema changes were introduced.
- `2026-03-01.0`
  - Documented watch-rule creation resilience update: `POST /api/watch-rules` now preserves `201` success even if post-commit background backfill enqueue fails; failures are logged for retry/operations follow-up.
  - Confirmed no frontend request/response schema changes (server-side task-dispatch reliability behavior only).
- `2026-02-28.5`
  - Clarified `/readyz` DB probe dialect-name normalization to safely handle non-string/missing dialect metadata on lightweight connection/bind doubles while preserving Postgres statement-timeout behavior.
  - Confirmed no frontend request/response schema changes (operational-readiness behavior only).
- `2026-02-28.4`
  - Recorded additional `/readyz` probe compatibility hardening for test doubles that omit transaction helpers (`in_transaction()`/`begin()`), while keeping existing Postgres statement-timeout behavior.
  - Confirmed this is operational-readiness behavior only with no frontend request/response schema changes.
- `2026-02-28.3`
  - Documented additional `/readyz` DB probe compatibility hardening: when a connection does not expose `begin()`, the probe now executes directly instead of raising attribute errors in lightweight doubles.
  - Confirmed no frontend request/response schema changes (operational-readiness behavior only).
- `2026-02-28.2`
  - Synced contract governance for `/readyz` probe hardening: DB dialect detection now supports bind-owned dialect metadata and defensive transaction-state checks for compatibility with SQLAlchemy test doubles.
  - Confirmed no frontend request/response schema changes (operational behavior only).
- `2026-02-28.1`
  - Documented `/readyz` DB probe implementation hardening (in-thread bind/connection handling with Postgres `SET LOCAL statement_timeout`), and clarified this is an operational-readiness behavior change with no frontend request/response schema impact.
- `2026-02-28.0`
  - Clarified that recent structured-logging and auth/dependency observability hardening changes are server-side telemetry-only updates; frontend request/response envelopes and endpoint semantics remain unchanged.
- `2026-02-26.2`
  - Documented observability endpoint behavior update: `/metrics` now emits `waxwatch_db_connection_utilization` at scrape time using live SQLAlchemy pool usage, while remaining non-frontend/non-schema API surface (`include_in_schema=false`).
- `2026-02-26.1`
  - Added API throttling contract: high-risk endpoints can return `429` with `code: rate_limited`, `Retry-After` header, and `error.details.scope` + `retry_after_seconds` for client backoff handling.
- `2026-02-26.0`
  - Extended `PATCH /api/me` + `GET /api/me` preferences contract with notification policy fields: `quiet_hours_start`, `quiet_hours_end`, `notification_timezone`, and `delivery_frequency` (`instant|hourly|daily`).
  - Clarified delivery semantics: notifications created during quiet hours are deferred until quiet hours end in the configured notification timezone; non-instant frequencies defer delivery based on the last successful send for that channel.
- `2026-02-25.1`
  - Added frontend contract coverage for `GET /api/outbound/ebay/{listing_id}` including auth requirements, `307` redirect behavior, `404` conditions, click-logging side effects, and frontend retry/analytics guidance.
- `2026-02-25`
  - Added explicit contract versioning metadata at the top of this file.
  - Added a changelog section for endpoint/schema contract tracking.
  - Added breaking-change/deprecation rules with minimum support windows.
  - Added CI contract-sync workflow requirement keyed on `app/api/` and `app/schemas/` changes.
  - Clarified profile hard-delete semantics: `DELETE /api/me/hard-delete` performs immediate permanent deletion (no API-enforced retention window).

## 1) Auth + Session Assumptions

- All user-facing endpoints in this document require `Authorization: Bearer <jwt>`.
- JWT requirements:
  - Verified against configured JWKS.
  - Must contain valid `exp`, `iss`, `aud`, `sub`.
  - `sub` must be a UUID (used as `user_id`).
- Missing/invalid token yields a standardized `error` envelope.
- Session lifecycle assumptions for React:
  - Login/token issuance happens outside this API (Supabase/Auth provider).
  - `POST /api/me/logout` returns a logout marker payload for client-side/session-provider sign-out orchestration.
  - `DELETE /api/me` deactivates local account state; frontend should then clear session and route to signed-out state.
  - `DELETE /api/me/hard-delete` immediately and permanently deletes the authenticated user record when it exists.

---

## 2) CORS Configuration by Environment

Backend CORS is controlled by env vars and should be set per deployment target:

- `CORS_ALLOWED_ORIGINS`: Comma-separated or JSON list of exact frontend origins.
- `CORS_ALLOWED_METHODS`: Allowed HTTP methods (`GET,POST,PUT,PATCH,DELETE,OPTIONS` by default).
- `CORS_ALLOWED_HEADERS`: Allowed request headers (`Authorization,Content-Type` by default).
- `CORS_ALLOW_CREDENTIALS`: `true` only when frontend must send cookies/auth credentials cross-origin.

Recommended values:

- **Local dev**: `CORS_ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000`
- **Staging**: `CORS_ALLOWED_ORIGINS=https://staging.your-frontend.example`
- **Production**: `CORS_ALLOWED_ORIGINS=https://app.your-frontend.example`

Security rule: when `CORS_ALLOW_CREDENTIALS=true`, do **not** use wildcard (`*`) for origins, methods, or headers.

---

## 3) Standardized Response Envelopes

### 3.1 Error format (global)

All framework/HTTP and validation failures are returned as:

```json
{
  "error": {
    "message": "validation error",
    "code": "validation_error",
    "status": 422,
    "details": [
      {
        "loc": ["body", "name"],
        "msg": "Field required",
        "type": "missing"
      }
    ]
  }
}
```

- `code` is currently one of:
  - `validation_error`
  - `http_error`
  - `rate_limited`
- Domain not-found and business-rule failures are emitted through `http_error` with useful `message` text.

### 3.2 Pagination conventions

Current API uses **query-param pagination** (not envelope pagination) with a shared contract:

- `limit` (default `50`, min `1`, max `200`)
- `offset` (default `0`, min `0`) for index-based paging
- `cursor` (optional) for keyset paging based on stable sort key: `created_at DESC, id DESC`

Rules:

- Provide **either** `offset` or `cursor`.
- If `cursor` is present, `offset` must be `0`.
- Invalid cursor format returns `422`.
- Requesting a page past available rows returns `200 []` (empty array).

Stable ordering guarantee:

- All major list endpoints (`watch-rules`, `watch-releases`, `events`, `notifications`, `provider-requests`) sort by:
  - primary: `created_at DESC`
  - tie-breaker: `id DESC`

Cursor examples:

```http
GET /api/events?limit=2
```

Response (array). Use the last row to create the next cursor:

```json
[
  {"id": "c7f...", "created_at": "2026-01-20T12:00:05+00:00", "type": "RULE_UPDATED"},
  {"id": "9a1...", "created_at": "2026-01-20T12:00:05+00:00", "type": "NEW_MATCH"}
]
```

Then fetch next page:

```http
GET /api/events?limit=2&cursor=MjAyNi0wMS0yMFQxMjowMDowNSswMDowMHw5YTEuLi4=
```

Offset examples:

```http
GET /api/notifications?limit=25&offset=0
GET /api/notifications?limit=25&offset=25
```

Boundary behavior examples:

```http
GET /api/events?limit=200        # allowed
GET /api/events?limit=201        # 422 validation_error
GET /api/events?offset=-1        # 422 validation_error
GET /api/events?offset=10&cursor=<token>  # 422 (cannot combine)
GET /api/events?offset=99999     # 200 []
```


### 3.3 Rate limiting + client behavior

Some endpoints enforce stricter request throttling (`/api/search*`, `/api/watch-rules*`, `/api/integrations/discogs/*`, `/api/stream/events`).

Scope mapping used in `error.details.scope` for these routes:

- `/api/search*` → `search`
- `/api/watch-rules*` → `watch_rules`
- `/api/integrations/discogs/*` → `discogs`
- `/api/stream/events` → `stream_events`

When throttled, clients receive:

- HTTP `429`
- `Retry-After` response header (seconds)
- Standard envelope:

```json
{
  "error": {
    "message": "rate limit exceeded",
    "code": "rate_limited",
    "status": 429,
    "details": {
      "scope": "watch_rules",
      "retry_after_seconds": 60
    }
  }
}
```

Frontend guidance: pause automatic retries until `Retry-After` elapses, apply exponential backoff for repeated `429`s, and surface a non-fatal "too many requests" message in UX.

---

## 4) Endpoint → React Screen + Action Map

## 4.1 Profile / Account

### `GET /api/me`
- **Screen:** `SettingsProfileScreen` (initial load).
- **Action:** Load user profile and integrations summary.
- **Integrations contract detail:** `integrations[]` only includes providers that are both registered and currently enabled by backend configuration (registry-backed list, not the full DB enum). `integrations[].linked` is derived strictly from whether a row exists in `external_account_links` for the same `user_id` and `provider` (for example, Discogs can be linked while eBay is not). `integrations[].watch_rule_count` is computed independently from `watch_search_rules.query.sources` and must not be used to infer linkage state.

### `PATCH /api/me`
- **Screen:** `SettingsProfileScreen`.
- **Action:** Save profile edits (display name, preferences).
- **Persistence semantics (single source of truth):**
  - `preferences.timezone` → persisted to `users.timezone`.
  - `preferences.currency` → persisted to `users.currency`.
  - `preferences.notifications_email` → persisted to `user_notification_preferences.email_enabled`.
  - `preferences.notifications_push` → persisted to `user_notification_preferences.realtime_enabled`.
- **Read-after-write guarantee:** A successful `PATCH /api/me` is reflected on subsequent `GET /api/me` responses without relying on token metadata syncing.
- **Notification policy preference fields:**
  - `preferences.quiet_hours_start` (`0-23`, optional): local-hour start of the quiet window.
  - `preferences.quiet_hours_end` (`0-23`, optional): local-hour end of the quiet window.
  - `preferences.notification_timezone` (optional IANA timezone): overrides profile timezone for delivery policy evaluation.
  - `preferences.delivery_frequency` (`instant|hourly|daily`): minimum cadence for channel delivery attempts after successful sends.
- **Policy behavior notes:**
  - Quiet hours suppress delivery attempts (notification remains pending) until the end of the quiet window.
  - Hourly/daily frequency can defer pending notifications after a recent successful send on the same channel.

### `POST /api/me/logout`
- **Screen:** Account menu/global app shell.
- **Action:** User clicks **Log out**.
- **Frontend behavior:** Call endpoint, clear local auth/session, redirect to signed-out route.

### `DELETE /api/me`
- **Screen:** `DangerZoneAccountScreen`.
- **Action:** User confirms **Deactivate account**.
- **Frontend behavior:** Show irreversible warning, then clear session after success.

### `DELETE /api/me/hard-delete`
- **Screen:** `DangerZoneAccountScreen`.
- **Action:** User confirms **Permanently delete account**.
- **Backend behavior contract:**
  - Allowed for both active and previously deactivated accounts.
  - Executes immediate permanent deletion when the user exists (no API-enforced waiting/retention period).
  - Returns `404` when the profile is already deleted/non-existent (including repeat requests after success).
- **Frontend behavior:** treat success as terminal account removal and clear local session/auth state immediately.

---

## 4.2 Discogs Integration + Import Lifecycle

### `POST /api/integrations/discogs/oauth/start`
- **Screen:** `IntegrationsScreen` connect CTA.
- **Action:** Start OAuth flow, receive `authorize_url`, `state`, selected `scopes`, and expiry metadata.

### `POST /api/integrations/discogs/oauth/callback`
- **Screen:** `DiscogsOAuthCallbackScreen` route action.
- **Action:** Exchange callback `code` + `state` for provider token. Backend validates stored state nonce + expiry before linking account.

### `POST /api/integrations/discogs/connect`
- **Screen:** Internal/admin fallback only.
- **Action:** Directly store Discogs account/token metadata without OAuth redirect.

### `GET /api/integrations/discogs/status`
- **Screen:** `IntegrationsScreen`.
- **Action:** Determine whether to show **Connect**, **Reconnect**, or **Import** CTA. `connected=true` only after OAuth callback has completed and an access token exists.

### `POST /api/integrations/discogs/disconnect`
- **Screen:** `IntegrationsScreen` disconnect action.
- **Action:** Revoke provider token (best effort) and remove local link/token metadata.

### `POST /api/integrations/discogs/import`
- **Screen:** `DiscogsImportScreen`.
- **Action:** Start import (`wantlist`, `collection`, `both`).
- **Frontend behavior:** Store returned `job_id` and poll job endpoint.
- **Recoverable failure contract:** If queue dispatch fails for a newly created job, endpoint returns `503` with retry guidance (`error.message`: `Discogs import could not be queued. Please retry shortly.`) and the persisted job transitions to `status=failed_to_queue` with error details for polling/ops visibility.
- **In-flight dedupe contract:** If a same-scope job is already `pending`/`running`, endpoint returns that existing job (`200`) without redispatching, so clients may receive the same `job_id` across repeated clicks/retries.

### `GET /api/integrations/discogs/import/{job_id}`
- **Screen:** `DiscogsImportScreen` progress panel.
- **Action:** Poll import status until terminal state.
- **Terminal UX:** On `completed` or `failed`, show counts/errors and CTA to review watch items.
- **Status visibility expectation:** Background/scheduled sync uses the same `import_jobs` records and statuses. Frontend should treat scheduler-created jobs exactly like manual jobs when surfaced (no separate status enum/endpoint).
- **Deduping expectation:** Repeated user-triggered refreshes or scheduler ticks may return an existing in-flight/recent job instead of creating a new one. Frontend should tolerate unchanged `job_id` values and continue polling that job.

### `GET /api/integrations/discogs/imported-items?source={wantlist|collection}&limit={1-100}&offset={>=0}`
- **Screen:** `DiscogsImportedItemsScreen` source tabs (`wantlist`, `collection`).
- **Action:** Fetch paginated imported items for one source at a time.
- **Behavior:**
  - Returns only active watch releases imported from that source.
  - If a release was imported from both sources, it appears in both source lists.
  - `count` is the number of items in the current page (not total available rows).
- **Response payload:**

```json
{
  "source": "wantlist",
  "limit": 25,
  "offset": 0,
  "count": 2,
  "items": [
    {
      "watch_release_id": "24550438-0dfc-4f1f-a19b-3b8b682b5f6f",
      "discogs_release_id": 1001,
      "discogs_master_id": 5001,
      "title": "Demo Want",
      "artist": "Artist A",
      "year": 1999,
      "source": "wantlist",
      "open_in_discogs_url": "https://www.discogs.com/release/1001"
    }
  ]
}
```

### `GET /api/integrations/discogs/imported-items/{watch_release_id}/open-in-discogs?source={wantlist|collection}`
- **Screen:** imported-item row action (`Edit in Discogs`).
- **Action:** Resolve an explicit Discogs URL for an imported row and source.
- **Behavior:**
  - Backend does **not** claim local write-through edits for imported Discogs items.
  - Frontend should open `open_in_discogs_url` in a new tab/window for provider-side edits.
  - Returns `404` when the watch release is not active, missing, or was never imported from the requested source.
- **Response payload:**

```json
{
  "watch_release_id": "24550438-0dfc-4f1f-a19b-3b8b682b5f6f",
  "source": "wantlist",
  "open_in_discogs_url": "https://www.discogs.com/release/1001"
}
```

Lifecycle summary:
1. `status` load
2. `oauth/start` to create state nonce + redirect URL
3. Redirect to Discogs auth and return to frontend
4. `oauth/callback` to validate state + finalize account link
5. `import` start
6. Poll `import/{job_id}` until finished
7. `imported-items` fetch per source with pagination
8. optional `open-in-discogs` row action for provider-side edits
9. Optional `disconnect` when user unlinks account

---

## 4.3 Watch List / Alert CRUD

The API has two watch paradigms; frontend can present both under a single “Alerts” IA with tabs.

### A) Search-rule alerts (`/api/watch-rules`)

- `POST /api/watch-rules` → **Create alert** from search criteria.
- `GET /api/watch-rules?limit&offset` → list alerts.
- `GET /api/watch-rules/{rule_id}` → alert details.
- `PATCH /api/watch-rules/{rule_id}` → edit alert parameters.
- `DELETE /api/watch-rules/{rule_id}` → soft-disable alert.
- `POST /api/watch-rules/{rule_id}/disable` → explicit disable action variant.
- `DELETE /api/watch-rules/{rule_id}/hard` → permanent delete.

**Screens + actions:**
- `AlertsListScreen`: view + paginate + disable/hard-delete.
- `AlertEditorScreen`: create/update rule name, sources, polling interval.
- `query.sources` is validated against the live provider registry; values must be registered+enabled provider keys. Frontend must not submit enum-only/disabled values, and should refresh provider choices from profile integrations or provider-capabilities endpoints.
- `AlertDetailScreen`: inspect scheduling fields (`last_run_at`, `next_run_at`).

**Query validation contract (create + patch):**
- Known query keys and accepted value types:
  - `sources`: required on create; list of provider strings (`discogs`, `ebay`), case-insensitive and normalized to lowercase.
  - `keywords`: optional list of strings; values are trimmed/lowercased and empty/whitespace-only entries are rejected when list is provided.
  - `max_price`: optional number (`int`/`float`), must be `>= 0`.
  - `q`: optional string, trimmed/lowercased, must not be empty when provided.
- Known keys with wrong value types now fail validation (HTTP 422) instead of being silently coerced.

**Validation error examples:**

```json
{
  "error": {
    "code": "validation_error",
    "message": "Validation failed",
    "status": 422,
    "details": [
      {
        "loc": ["body", "query"],
        "msg": "Value error, query.max_price must be non-negative",
        "type": "value_error"
      }
    ]
  }
}
```

```json
{
  "error": {
    "code": "validation_error",
    "message": "Validation failed",
    "status": 422,
    "details": [
      {
        "loc": ["body", "query"],
        "msg": "Value error, query.keywords must contain at least one non-empty keyword when provided",
        "type": "value_error"
      }
    ]
  }
}
```

### B) Release watchlist entries (`/api/watch-releases`)

- `POST /api/watch-releases` → create release watch entry.
- `GET /api/watch-releases?limit&offset` → list watchlist.
- `GET /api/watch-releases/{watch_release_id}` → entry details.
- `PATCH /api/watch-releases/{watch_release_id}` → edit entry.
- `DELETE /api/watch-releases/{watch_release_id}` → disable entry.

**Frontend contract updates (Discogs identity modes):**
- `watch_releases` payloads now include:
  - `discogs_release_id` (required): exact release identity.
  - `discogs_master_id` (optional): Discogs master identity.
  - `match_mode` (required, defaults to `exact_release`): one of
    - `exact_release` → listing must match `discogs_release_id` exactly.
    - `master_release` → listing must match `discogs_master_id`.
- Listing payloads now expose optional `discogs_master_id` alongside `discogs_release_id`.

**Screens + actions:**
- `WatchlistScreen`: list/manage release watches.
- `WatchlistItemEditor`: set target price, condition, active state, and identity `match_mode`.

---

## 4.4 Notification Inbox + Realtime

### `GET /api/notifications?limit=`
- **Screen:** `NotificationInboxScreen`.
- **Action:** Initial list load / infinite append by increasing limit.

### `POST /api/notifications/{notification_id}/read`
- **Screen:** `NotificationInboxScreen`.
- **Action:** **Dismiss notification** / mark as read.

### `GET /api/notifications/unread-count`
- **Screen:** app header badge.
- **Action:** Poll for unread count on interval or after read actions.

### `GET /api/stream/events` (SSE)
- **Screen:** app shell/event bridge.
- **Action:** Subscribe once per authenticated session; fan out to inbox/badge stores.
- **SSE event name:** `notification`
- **SSE payload shape:**

```json
{
  "notification_id": "4c8d9157-4a8c-4ea8-9d27-3ad2fc1e8f95",
  "event_id": "f2eec3e4-1f39-4a9f-9f39-2359f3983be0",
  "event_type": "watch_match_found",
  "created_at": "2026-01-12T18:02:11.123456+00:00"
}
```

Recommended client behavior:
- Append/merge realtime events into inbox cache.
- Refresh unread badge after incoming realtime payload.
- Reconnect SSE with exponential backoff on disconnect.

---

## 4.5 Outbound Marketplace Redirects

### `GET /api/outbound/ebay/{listing_id}`
- **Screen/action:** listing card/button CTA such as `View on eBay`.
- **Auth requirement:** requires `Authorization: Bearer <jwt>` like other user-facing `/api/**` endpoints.
- **Response behavior:** returns `307 Temporary Redirect` with `Location` set to the affiliate-decorated eBay URL. Frontend should treat this as a navigation endpoint, not JSON data.
- **404 conditions:** returns `404` when any of the following is true:
  - `listing_id` does not exist,
  - listing exists but is not an eBay provider listing,
  - listing destination URL is unavailable/empty after backend resolution.
- **Side effect (click logging):** on successful redirect path, backend inserts an `outbound_clicks` record with authenticated `user_id`, `listing_id`, provider, and optional `Referer` header value.

Frontend guidance:
- **Open behavior:** invoke from direct user interaction and open in a new tab/window (for example `target="_blank" rel="noopener noreferrer"`) so the app session remains in-place.
- **Analytics expectations:** frontend may emit a local `outbound_click_attempted` event, but backend click logging is the source of truth for successful outbound redirects.
- **Retry handling:**
  - Do not auto-retry on `404`; treat as terminal and show lightweight feedback (`Listing no longer available`).
  - If network/request execution fails before a response, allow one manual user retry (e.g., click again) rather than background retry loops.

---

## 5) OpenAPI Example Alignment (frontend scaffolding guidance)

The OpenAPI schema now includes representative examples for:
- Profile read/update and auth-required operations.
- Discogs connect/status/import lifecycle.
- Watch-rule and watch-release create/update/list entities.
- Notification inbox rows and unread-count payloads.
- Common validation/error envelope.

Frontend teams should generate API clients from OpenAPI and use examples for:
- mocked storybook fixtures
- e2e happy-path payload contracts
- typed form defaults for create/edit flows

---

## 6) Breaking Change Rules + Deprecation Windows

To keep frontend and backend release trains safe, apply the following contract rules:

1. **Additive-first policy:**
   - Prefer additive, backward-compatible changes before removals/renames.
   - New fields must be optional by default unless released behind coordinated frontend changes.
2. **Deprecation notice requirement:**
   - Any endpoint removal, field removal, or response shape tightening must be announced in this document's changelog before enforcement.
   - Include replacement path, migration notes, and removal target date.
3. **Minimum deprecation window:**
   - **14 days minimum** for non-production/test-only endpoints.
   - **30 days minimum** for user-facing production endpoints and schema fields.
4. **Removal gate:**
   - Breaking removals should ship only after the deprecation window has elapsed and frontend owners confirm migration completion.
5. **Emergency exception path:**
   - Security/compliance incidents may bypass the deprecation window; the changelog must still document what changed and why.

---

## 7) Contract Update Workflow + CI Enforcement

When a pull request modifies API-facing files under:

- `app/api/**`
- `app/schemas/**`

the PR **must** also update this contract file (`docs/FRONTEND_API_CONTRACT.md`) with:

- a changelog entry describing endpoint/schema impact,
- any necessary contract/body examples,
- and deprecation notes for breaking behavior.

Enforcement:

- CI runs `python scripts/check_frontend_contract_sync.py`.
- The check fails when API-facing files changed but `docs/FRONTEND_API_CONTRACT.md` was not updated in the same diff.
- Local equivalents: `make check-contract-sync` and `make check-openapi-snapshot` (or full `make ci-local`).
- Snapshot gate: CI runs `python -m scripts.openapi_snapshot --check` and compares `app/main.py` generated schema output to the committed `docs/openapi.snapshot.json` baseline. Update the baseline with `make openapi-snapshot` whenever intentional API schema changes are introduced.

---

## 4.6 Provider Request Observability (User + Admin)

### `GET /api/provider-requests`
- **Audience:** Authenticated end user.
- **Scope:** Returns only the caller's `provider_requests` rows.
- **Pagination:** Supports shared pagination params (`limit`, `offset`, `cursor`) with stable ordering (`created_at DESC, id DESC`).

### `GET /api/provider-requests/summary`
- **Audience:** Authenticated end user.
- **Scope:** Per-provider summary for only the caller's rows.
- **Response fields:**
  - `provider`
  - `total_requests`
  - `error_requests` (`status_code >= 400`)
  - `avg_duration_ms`

### `GET /api/provider-requests/admin`
- **Audience:** Admin-only (claim/role-gated).
- **Scope:** Cross-user query endpoint for provider request diagnostics.
- **Authorization contract:** Caller must include admin-capable claims (for example `role=admin`, `user_role=admin`, `app_metadata.roles` containing `admin`, or equivalent admin permission claim).
- **Filtering params (all optional):**
  - `provider` (`discogs` | `ebay` | `mock`)
  - `status_code_gte` (100-599)
  - `status_code_lte` (100-599)
  - `created_from` (ISO8601 timestamp)
  - `created_to` (ISO8601 timestamp)
  - `user_id` (UUID)
- **Validation rules:**
  - `status_code_gte` cannot be greater than `status_code_lte`.
  - `created_from` cannot be later than `created_to`.
- **Pagination:** Supports shared pagination params (`limit`, `offset`, `cursor`).
- **Response shape:** Same as user list plus `id` and `user_id` to support cross-user triage views.

### `GET /api/provider-requests/admin/summary`
- **Audience:** Admin-only (same auth gate as `/admin`).
- **Scope:** Cross-user summary grouped by `provider`.
- **Filtering params:** Same filter set as `/api/provider-requests/admin`.
- **Response fields:**
  - `provider`
  - `total_requests`
  - `error_requests`
  - `avg_duration_ms`

## Change synchronization requirement

If API contract changes add new environment variables, test gates, or command workflow expectations, include matching updates to `Makefile`, `.github/workflows/ci.yml`, and `CONTRIBUTING.md` in the same PR, and update `.env.sample` only when env vars are added/removed or defaults change.
