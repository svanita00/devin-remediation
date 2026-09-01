[code-quality] Narrow blind except clauses in superset/utils/slack.py (BLE001)

## Summary
`ruff check superset --select BLE001` flags blind `except` clauses in `superset/utils/slack.py` that swallow real Slack-integration errors and make failures hard to debug.

## Scope
Fix only `superset/utils/slack.py`. Narrow each broad `except` to the specific expected exception(s) and log rather than silently swallow. Preserve current control flow.

## Acceptance criteria
- [ ] `ruff check superset/utils/slack.py --select BLE001` == 0 errors
- [ ] Unexpected exceptions no longer silently swallowed; behavior preserved
- [ ] Relevant tests pass
- [ ] PR opened referencing this issue

_Assign to Devin: add the `devin-fix` label._
