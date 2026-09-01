[security] Fix HIGH npm advisory in `brace-expansion` (frontend)

## Summary
`npm audit` in `superset-frontend/` reports a HIGH advisory in `brace-expansion` (transitive) with a non-breaking fix available.

## Suggested fix
Run `npm audit fix` (NOT `--force`) in `superset-frontend/`, applying only non-major changes. Update `package-lock.json`. Verify the frontend still builds.

## Acceptance criteria
- [ ] `brace-expansion` advisory resolved in `npm audit`
- [ ] Only non-major version changes applied
- [ ] `superset-frontend` still installs/builds
- [ ] PR opened referencing this issue

_Assign to Devin: add the `devin-fix` label._
