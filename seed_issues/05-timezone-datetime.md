[code-quality] Fix timezone-naive datetime usage in superset/daos/key_value.py (DTZ005)

## Summary
`ruff check superset --select DTZ005` flags timezone-naive datetime calls in `superset/daos/key_value.py` (e.g. `datetime.now()`/`utcnow()` without tzinfo). Naive timestamps are ambiguous and cause subtle correctness bugs (e.g. key-value expiry across timezones).

## Scope
Fix only `superset/daos/key_value.py`. Make each datetime timezone-aware (`datetime.now(timezone.utc)`), preserving behavior.

## Acceptance criteria
- [ ] `ruff check superset/daos/key_value.py --select DTZ005` == 0 errors
- [ ] Behavior unchanged for normal inputs; relevant tests pass
- [ ] PR opened referencing this issue

_Assign to Devin: add the `devin-fix` label._
