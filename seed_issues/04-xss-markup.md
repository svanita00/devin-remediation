[code-quality/security] Eliminate the unsafe-`Markup` XSS class across the backend (fix all sites + add regression test)

## Summary
`ruff check superset --select S704` flags unsafe `markupsafe.Markup(f"...{var}...")` usage (potential XSS). Known sites: `superset/models/dashboard.py`, `superset/models/slice.py`, `superset/models/sql_lab.py`, `superset/utils/core.py`.

## Scope (agentic)
1. Find every unsafe-`Markup` site in `superset/` (don't assume the list is exhaustive).
2. Rewrite to escape interpolated values (e.g. `Markup("<a href=\"{}\">{}</a>").format(href, title)`), preserving output.
3. Add a regression test asserting a malicious input is escaped; it should fail on old code, pass on new.
4. Verify: `ruff check superset --select S704` == 0 errors, and relevant tests pass.

## Acceptance criteria
- [ ] All `S704` findings resolved; regression test added
- [ ] Existing tests pass
- [ ] PR opened referencing this issue

_Assign to Devin: add the `devin-fix` label._
