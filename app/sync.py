"""Live sync: pull remediation sessions from the Devin API into our store.

Sessions created via the native Automation, direct API, or Code Scan don't go
through our orchestrator — so in live mode we reconcile them by listing sessions
from the Devin API and upserting the ones tagged/titled as remediations. This is
the "control plane reads the native API" design: the dashboard reflects reality.
"""
from __future__ import annotations

import re

from app.config import settings
from app.devin.client import get_devin_client
from app import store

_REMEDIATION_TAGS = {"takehome", "auto-remediation", "event-trigger", "scheduled-sweep"}
_TITLE_HINTS = ("fix #", "bump", "markup", "deck", "jaraco", "multipart", "slack",
                "timezone", "datetime", "brace", "xss", "blind except", "narrow")
# Code-scan internal sub-sessions (Agentic MapReduce) are discovery machinery, not remediations.
_EXCLUDE = ("code scan", "threat model", "investigate batch", "security scan", "perform security")
# Map a session to the issue it remediates by keyword (sessions via automation lack issue-N tags).
_ISSUE_BY_KEYWORD = [
    ("multipart", 1), ("jaraco", 2), ("brace", 3), ("markup", 4), ("xss", 4),
    ("datetime", 5), ("dtz", 5), ("key_value", 5), ("timezone", 5),
    ("slack", 6), ("blind except", 6), ("deck", 7), ("loaders", 7),
]


def _status(s) -> str:
    # A PR is the goal — if one exists the remediation succeeded, regardless of
    # whether the session then finished (exit) or went idle (suspended).
    if s.pull_requests:
        return "success"
    if s.status == "error":
        return "failed"
    if s.status in ("exit", "suspended"):
        return "needs_attention"   # finished/idle with no PR = wants a human
    return "running"


def _issue_number(s) -> int | None:
    for t in s.tags:
        m = re.match(r"issue-(\d+)", t)
        if m:
            return int(m.group(1))
    m = re.search(r"#(\d+)", s.title)
    if m:
        return int(m.group(1))
    title = (s.title or "").lower()
    for kw, n in _ISSUE_BY_KEYWORD:
        if kw in title:
            return n
    return None


def _is_remediation(s) -> bool:
    title = (s.title or "").lower()
    if any(x in title for x in _EXCLUDE):        # drop code-scan internals
        return False
    if set(s.tags) & _REMEDIATION_TAGS:
        return True
    if s.origin == "automation":
        return True
    return any(h in title for h in _TITLE_HINTS)


async def sync_live_sessions() -> int:
    """Reconcile Devin sessions into the store AND auto-review any new PR (any origin).
    Returns count synced. Live only. Idempotent — reviews fire once per PR."""
    if settings.devin_mode != "live":
        return 0
    client = get_devin_client()
    try:
        try:
            sessions = await client.list_sessions(limit=50)
        except Exception:
            return 0
        run_id = store.get_or_create_live_run(settings.target_repo)
        n = 0
        for s in sessions:
            if not s.session_id or not _is_remediation(s):
                continue
            # skip old out-of-quota "ghost" sessions (suspended, no work, no PR)
            if s.status == "suspended" and not s.pull_requests and not (s.acus_consumed or 0):
                continue
            store.upsert_remediation_by_session(
                run_id, s.session_id,
                issue_number=_issue_number(s),
                title=s.title,
                status=_status(s),
                pr_url=s.pull_requests[0] if s.pull_requests else None,
                acus_consumed=s.acus_consumed,
                session_url=s.url,
            )
            n += 1
            # Auto-review each PR exactly once — the control plane reviews every
            # PR itself, regardless of whether it came from automation/API/code-scan.
            if settings.auto_review and s.pull_requests:
                row = store.get_remediation_by_session(s.session_id)
                if row and not row.get("reviewed"):
                    try:
                        await client.trigger_review(s.pull_requests[0])
                        store.log(f"🔍 Devin Review auto-triggered on {s.pull_requests[0]}")
                    except Exception:
                        pass
                    store.upsert_remediation_by_session(run_id, s.session_id, reviewed=1)
        if n:
            store.update_scan_run(run_id, findings_total=len(store.list_remediations()))
        return n
    finally:
        await client.aclose()
