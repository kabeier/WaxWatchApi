## Summary

- Describe the change.
- Link related issues/tickets.

## Validation

- [ ] I ran relevant local checks (lint/tests/typecheck/CI parity targets).
- [ ] `make lint` and `make fmt-check` both passed locally (or in equivalent CI-parity workflow).

## Governance sync checklist (required when tests/CI/Make/env vars are affected)

- [ ] `.env.sample` updated with non-secret defaults and environment notes.
- [ ] `Makefile` updated to reflect command/test workflow changes.
- [ ] `.github/workflows/ci.yml` updated to reflect CI workflow changes.
- [ ] `CONTRIBUTING.md` updated with policy/process changes.
- [ ] `CHANGELOG.md` updated for API/runtime/migration-affecting behavior changes (or N/A with reason: `...`).
- [ ] `docs/DEPLOYMENT.md` updated (or N/A).
- [ ] `docs/FRONTEND_API_CONTRACT.md` updated (or N/A).

## Notes

- Include rollout, migration, or follow-up tasks if needed.
