[security] Bump `python-multipart` to >=0.0.30 — HIGH: quadratic querystring parsing (ReDoS/CPU DoS)

## Summary
`python-multipart==0.0.29` (in `requirements/development.txt`, transitive via `fastmcp-slim`/`mcp`) is affected by a HIGH-severity ReDoS/CPU-DoS (GHSA-5rvq-cxj2-64vf). Fixed in 0.0.30.

## Suggested fix
Raise the constraint in the source (`requirements/development.in` or `pyproject.toml`) and recompile with `uv pip compile`.

## Acceptance criteria
- [ ] `python-multipart>=0.0.30` resolved in `requirements/development.txt`
- [ ] Pinned file regenerated with the project's tooling; no new conflicts
- [ ] PR opened referencing this issue

_Assign to Devin: add the `devin-fix` label._
