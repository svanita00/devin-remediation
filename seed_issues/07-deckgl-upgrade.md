[security] Resolve HIGH npm advisories in the deck.gl/loaders.gl stack (frontend)

## Summary
`npm audit` in `superset-frontend/` reports HIGH advisories in the `@deck.gl/*` / `@loaders.gl/*` cluster (geospatial viz). The naive `npm audit` suggestion may be a breaking downgrade — investigate the real vulnerable transitive package before acting.

## Scope (deliberately harder)
- Investigate the dependency graph; identify the actually-vulnerable package and the least-breaking remediation (e.g. an npm override to prune it) rather than a blind major downgrade.
- Adapt any breaking changes so the frontend builds. If feasible, run the app and verify deck.gl charts still render; report what was verified.
- If too broad to fully complete, open a PR with progress and clearly flag what remains.

## Acceptance criteria
- [ ] The deck.gl/loaders.gl HIGH advisories are resolved in `npm audit`
- [ ] `superset-frontend` installs and builds
- [ ] PR opened referencing this issue (with verification notes)

_Assign to Devin: add the `devin-fix` label._
