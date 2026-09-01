[security] Bump `jaraco.context` to >=6.1.0 — HIGH: path traversal

## Summary
`jaraco-context==6.0.1` (in `requirements/development.txt`, transitive via `keyring`) is affected by a HIGH-severity path traversal (GHSA-58pv-8j8x-9vj2). Fixed in 6.1.0.

## Suggested fix
Raise the constraint in the source (`requirements/development.in` or `pyproject.toml`) and recompile with `uv pip compile`.

## Acceptance criteria
- [ ] `jaraco-context>=6.1.0` resolved in `requirements/development.txt`
- [ ] Pinned file regenerated with the project's tooling; no new conflicts
- [ ] PR opened referencing this issue

_Assign to Devin: add the `devin-fix` label._
