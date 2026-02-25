# Product Checklist

Use this checklist for product-facing backend changes that impact frontend integration.

## API contract governance

- [ ] If `app/api/` or `app/schemas/` changed, update `docs/FRONTEND_API_CONTRACT.md` in the same PR.
- [ ] Bump the **Contract version** at the top of `docs/FRONTEND_API_CONTRACT.md`.
- [ ] Add a changelog entry summarizing endpoint/schema changes.
- [ ] For breaking changes, document deprecation + removal windows per the contract's breaking-change rules.
- [ ] Run `make api-contract-check` locally to verify the contract guard passes.

## Release communication

- [ ] Call out notable contract changes in PR notes.
- [ ] Confirm frontend owners have migration notes for breaking changes.
