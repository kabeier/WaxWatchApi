# WaxWatch Frontend API Contract

This contract captures **current API behavior** and maps it to intended React surfaces so frontend can scaffold screens directly from OpenAPI payloads.

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

---

## 2) Standardized Response Envelopes

### 2.1 Error format (global)

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
- Domain not-found and business-rule failures are emitted through `http_error` with useful `message` text.

### 2.2 Pagination conventions

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

---

## 3) Endpoint → React Screen + Action Map

## 3.1 Profile / Account

### `GET /api/me`
- **Screen:** `SettingsProfileScreen` (initial load).
- **Action:** Load user profile and integrations summary.

### `PATCH /api/me`
- **Screen:** `SettingsProfileScreen`.
- **Action:** Save profile edits (display name, preferences).

### `POST /api/me/logout`
- **Screen:** Account menu/global app shell.
- **Action:** User clicks **Log out**.
- **Frontend behavior:** Call endpoint, clear local auth/session, redirect to signed-out route.

### `DELETE /api/me`
- **Screen:** `DangerZoneAccountScreen`.
- **Action:** User confirms **Deactivate account**.
- **Frontend behavior:** Show irreversible warning, then clear session after success.

---

## 3.2 Discogs Integration + Import Lifecycle

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

### `GET /api/integrations/discogs/import/{job_id}`
- **Screen:** `DiscogsImportScreen` progress panel.
- **Action:** Poll import status until terminal state.
- **Terminal UX:** On `completed` or `failed`, show counts/errors and CTA to review watch items.

Lifecycle summary:
1. `status` load
2. `oauth/start` to create state nonce + redirect URL
3. Redirect to Discogs auth and return to frontend
4. `oauth/callback` to validate state + finalize account link
5. `import` start
6. Poll `import/{job_id}` until finished
7. Optional `disconnect` when user unlinks account

---

## 3.3 Watch List / Alert CRUD

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
- `AlertDetailScreen`: inspect scheduling fields (`last_run_at`, `next_run_at`).

### B) Release watchlist entries (`/api/watch-releases`)

- `POST /api/watch-releases` → create release watch entry.
- `GET /api/watch-releases?limit&offset` → list watchlist.
- `GET /api/watch-releases/{watch_release_id}` → entry details.
- `PATCH /api/watch-releases/{watch_release_id}` → edit entry.
- `DELETE /api/watch-releases/{watch_release_id}` → disable entry.

**Screens + actions:**
- `WatchlistScreen`: list/manage release watches.
- `WatchlistItemEditor`: set target price, condition, active state.

---

## 3.4 Notification Inbox + Realtime

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

## 4) OpenAPI Example Alignment (frontend scaffolding guidance)

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
