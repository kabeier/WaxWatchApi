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
  - Requires normal authentication/authorization (`get_current_user_id`) so only the authenticated subject can delete its own account.
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
