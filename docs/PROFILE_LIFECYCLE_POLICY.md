# Profile Lifecycle Policy

This document defines profile lifecycle behavior for the `/api/me` endpoints.

## Soft Deactivate

- Endpoint: `DELETE /api/me`.
- Behavior:
  - User account is marked inactive (`users.is_active=false`).
  - All active watch rules for the user are auto-disabled (`watch_search_rules.is_active=false`).
  - Authentication is blocked immediately for inactive users via auth dependency checks.
- Result:
  - Existing bearer tokens no longer authorize protected API access once deactivation is committed.

## Hard Delete

- Endpoint: `DELETE /api/me/hard-delete`.
- Behavior:
  - Requires bearer authentication and subject authorization; route dependency (`get_current_user_id_allow_inactive`) still enforces token validity/user identity while allowing inactive subjects to proceed.
  - Checks that the user record exists, then permanently deletes it regardless of `users.is_active` state (active and previously deactivated accounts are both eligible).
  - Returns `404 User profile not found` when the account does not exist (including repeated hard-delete attempts after successful deletion).
  - Current implementation executes synchronously in-request.

## Retention Window

- Soft-deactivated accounts are retained for **30 days** before hard delete eligibility.
- Operationally, hard delete can still be invoked explicitly for immediate removal when policy/admin rules allow.

## Cascade Strategy and Related Entities

Hard delete of `users` cascades or nullifies related entities as follows (from `app/db/models.py`):

- `watch_search_rules`: cascade delete (`User.watch_search_rules`, FK `ondelete="CASCADE"`).
- `events`: cascade delete (`User.events`, FK `ondelete="CASCADE"`).
- `notifications`: cascade delete (`User.notifications`, FK `ondelete="CASCADE"`); event-linked notifications also cascade from events.
- `external_account_links`: cascade delete (`User.external_account_links`, FK `ondelete="CASCADE"`).
- `import_jobs`: cascade delete from user relation/FK (`User.import_jobs`, FK `ondelete="CASCADE"`), and link pointer to external account uses `SET NULL`.
- `provider_requests`: cascade delete (`User.provider_requests`, FK `ondelete="CASCADE"`).
- Other direct user-owned entities (`watch_releases`, `user_notification_preferences`) also use cascade delete.

This strategy ensures hard delete removes personal/account-owned records while preserving globally shared entities (for example, `listings`) unless separately orphaned by non-user constraints.


## Profile Preference Persistence

`/api/me` profile preferences are persisted in the application database as the single source of truth (no external identity-provider metadata sync is required for preference reads/writes):

- `preferences.timezone` is stored on `users.timezone`.
- `preferences.currency` is stored on `users.currency`.
- `preferences.notifications_email` maps to `user_notification_preferences.email_enabled`.
- `preferences.notifications_push` maps to `user_notification_preferences.realtime_enabled`.

Delivery behavior is controlled by `user_notification_preferences`:

- Event fan-out skips email notifications when `email_enabled=false`.
- Event fan-out skips realtime/SSE notifications when `realtime_enabled=false`.
- Existing per-event toggle checks (`event_toggles`) still apply.
