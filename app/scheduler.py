"""In-process scheduler for the full remediation pipeline on a cadence.

A native Devin Automation can only *start a session* — it can't run a multi-step
scan -> triage -> remediate(high/critical) pipeline. So the control plane runs
that pipeline itself on a schedule by invoking the same /scan flow. This is the
governed, policy-aware periodic trigger (auto-remediate high/critical, surface
the rest for human triage).

Enable with WEEKLY_SCAN_ENABLED=true. (A native schedule Automation also exists
as a lighter, no-code alternative — see scripts/setup_devin.py.)
"""
from __future__ import annotations

import asyncio

from app.config import settings
from app import store
from app.scans import run_scan


async def reconcile_loop() -> None:
    """Continuously reconcile Devin sessions into the store and auto-trigger Devin
    Review on any new PR — so review is part of the automation, not a manual step
    or a one-off dashboard load. Live only; disable with RECONCILE_INTERVAL_SECONDS=0."""
    if settings.devin_mode != "live" or settings.reconcile_interval_seconds <= 0:
        return
    from app.sync import sync_live_sessions
    store.log("Continuous reconcile + auto-review loop armed")
    while True:
        await asyncio.sleep(settings.reconcile_interval_seconds)
        try:
            await sync_live_sessions()
        except Exception as e:
            store.log(f"⚠️ reconcile loop error: {type(e).__name__}: {e}")


async def weekly_loop() -> None:
    if not settings.weekly_scan_enabled:
        return
    store.log(f"Scheduled pipeline armed (every {settings.weekly_scan_interval_seconds}s)")
    while True:
        await asyncio.sleep(settings.weekly_scan_interval_seconds)
        store.log("⏰ Scheduled trigger fired — running scan → auto-remediate(high/critical) pipeline")
        await run_scan(trigger="scheduled")
