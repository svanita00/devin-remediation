"""The orchestrator: drive Devin's native Code Scan -> findings -> remediate -> PR,
and record everything for the control plane. Runs as a background task so the
trigger (manual endpoint or weekly scheduler) returns immediately.
"""
from __future__ import annotations

import asyncio

from app.config import remediate_severity_set, settings
from app.devin.client import SCAN_TERMINAL, SESSION_TERMINAL, get_devin_client
from app import store


def _normalize(status: str, pr_url: str | None) -> str:
    # A PR is the goal — success if one exists, regardless of exit/suspended.
    if pr_url:
        return "success"
    if status == "error":
        return "failed"
    if status in ("exit", "suspended"):
        return "needs_attention"
    return "running"


async def _track_remediation(client, rem_id: int, session_id: str) -> None:
    deadline = asyncio.get_event_loop().time() + settings.scan_poll_timeout_seconds
    last = None
    reviewed = False
    while True:
        s = await client.get_session(session_id)
        pr = s.pull_requests[0] if s.pull_requests else None
        if s.status != last:
            store.log(f"Remediation session {session_id[:16]}… -> {s.status}")
            last = s.status
        # As soon as a PR exists, have Devin self-review it (once).
        if pr and not reviewed and settings.auto_review:
            try:
                await client.trigger_review(pr)
                store.log(f"🔍 Devin Review triggered on {pr}")
            except Exception as exc:
                store.log(f"Devin Review trigger failed: {exc}")
            reviewed = True
        store.update_remediation(
            rem_id, session_id=session_id, session_url=s.url,
            status=_normalize(s.status, pr), pr_url=pr, acus_consumed=s.acus_consumed,
        )
        if s.status in SESSION_TERMINAL:
            if pr:
                store.log(f"✅ PR opened: {pr}")
            break
        if asyncio.get_event_loop().time() > deadline:
            store.update_remediation(rem_id, status="failed")
            store.log(f"❌ Remediation {session_id[:16]}… timed out")
            break
        await asyncio.sleep(settings.poll_interval_seconds)


async def run_scan(trigger: str = "manual") -> int:
    """Full flow: start scan -> poll -> findings -> remediate top-N -> track PRs."""
    run_id = store.create_scan_run(settings.target_repo, settings.scan_type, trigger)
    client = get_devin_client()
    try:
        store.log(f"[{trigger}] Starting {settings.scan_type} scan on {settings.target_repo} "
                  f"(mode={settings.devin_mode})")
        scan = await client.start_scan(settings.target_repo, settings.scan_type)
        store.update_scan_run(run_id, scan_id=scan.scan_id, status=scan.status)

        # poll scan to completion
        deadline = asyncio.get_event_loop().time() + settings.scan_poll_timeout_seconds
        while scan.status not in SCAN_TERMINAL:
            if asyncio.get_event_loop().time() > deadline:
                store.update_scan_run(run_id, status="failed")
                store.log("❌ Scan timed out")
                return run_id
            await asyncio.sleep(settings.poll_interval_seconds)
            scan = await client.get_scan(scan.scan_id, settings.target_repo)
            store.update_scan_run(run_id, status=scan.status)

        if scan.status != "completed":
            store.log(f"⚠️ Scan ended as '{scan.status}'")
            return run_id

        sevs = remediate_severity_set()
        findings = await client.list_findings(scan.scan_id, sevs)
        store.update_scan_run(run_id, findings_total=len(findings))
        store.log(f"Scan complete: {len(findings)} finding(s) at severities {sorted(sevs)}")

        # remediate up to the cap, in parallel
        to_fix = findings[: settings.max_remediations_per_run]
        tasks = []
        for f in to_fix:
            rem_id = store.create_remediation(run_id, {
                "finding_id": f.finding_id, "title": f.title, "severity": f.severity,
                "category": f.category, "file_path": f.file_path,
            })
            res = await client.remediate(scan.scan_id, f.finding_id)
            store.update_remediation(rem_id, session_id=res.session_id, status="running")
            store.log(f"Dispatched remediation for '{f.title[:60]}' -> {res.session_id[:16]}…")
            tasks.append(_track_remediation(client, rem_id, res.session_id))

        store.update_scan_run(run_id, remediations_started=len(tasks))
        if tasks:
            await asyncio.gather(*tasks)
        store.log(f"[{trigger}] Scan run #{run_id} finished")
        return run_id
    except Exception as exc:
        store.update_scan_run(run_id, status="failed")
        store.log(f"❌ Scan run error: {exc}")
        return run_id
    finally:
        await client.aclose()


def trigger_scan(trigger: str = "manual") -> None:
    asyncio.create_task(run_scan(trigger))
