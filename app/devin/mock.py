"""Offline simulation of Devin's v3 Code Scans + Sessions + Metrics.

Mirrors the real lifecycle so the whole control plane runs for $0:
  start_scan -> (after mock_seconds_to_complete) completed
  list_findings -> a fixed set of realistic Superset findings
  remediate    -> launches a mock session that "opens a PR" and consumes ACUs
  metrics/consumption -> derived from what's been remediated.
"""
from __future__ import annotations

import random
import time
import uuid
from typing import Any

from app.config import settings
from app.devin.client import Finding, RemediateResult, Scan, Session

# Realistic findings mirroring what we actually detected on Superset mainline.
_MOCK_FINDINGS = [
    {"title": "python-multipart <0.0.30 quadratic querystring parsing (ReDoS/CPU DoS)",
     "severity": "high", "category": "vulnerable-dependency",
     "file_path": "requirements/development.txt",
     "recommendation": "Bump python-multipart to >=0.0.30"},
    {"title": "jaraco.context 6.0.1 path traversal",
     "severity": "high", "category": "vulnerable-dependency",
     "file_path": "requirements/development.txt",
     "recommendation": "Bump jaraco.context to >=6.1.0"},
    {"title": "Unsafe markupsafe.Markup interpolation (potential XSS)",
     "severity": "medium", "category": "xss",
     "file_path": "superset/models/dashboard.py",
     "recommendation": "Escape interpolated values via Markup(...).format(...)"},
    {"title": "Unsafe markupsafe.Markup interpolation (potential XSS)",
     "severity": "medium", "category": "xss",
     "file_path": "superset/models/slice.py",
     "recommendation": "Escape interpolated values via Markup(...).format(...)"},
]


class MockDevinClient:
    def __init__(self) -> None:
        self._scans: dict[str, dict[str, Any]] = {}
        self._sessions: dict[str, dict[str, Any]] = {}
        self._findings: dict[str, list[dict[str, Any]]] = {}

    async def start_scan(self, repo: str, scan_type: str) -> Scan:
        scan_id = f"scan-mock-{uuid.uuid4().hex[:10]}"
        self._scans[scan_id] = {"created": time.time(), "repo": repo, "scan_type": scan_type}
        n = min(settings.mock_num_findings, len(_MOCK_FINDINGS))
        self._findings[scan_id] = [
            {**f, "finding_id": f"find-{scan_id[-6:]}-{i}", "status": "open",
             "pr_url": None, "session_id": None}
            for i, f in enumerate(_MOCK_FINDINGS[:n])
        ]
        return Scan(scan_id=scan_id, status="pending", repo=repo, scan_type=scan_type)

    async def get_scan(self, scan_id: str, repo: str) -> Scan:
        st = self._scans.get(scan_id)
        if not st:
            return Scan(scan_id=scan_id, status="failed", repo=repo)
        elapsed = time.time() - st["created"]
        status = "completed" if elapsed >= settings.mock_seconds_to_complete else "running"
        return Scan(scan_id=scan_id, status=status, repo=repo, scan_type=st["scan_type"])

    async def list_findings(self, scan_id: str, severities: set[str]) -> list[Finding]:
        rows = self._findings.get(scan_id, [])
        out = []
        for f in rows:
            if severities and f["severity"] not in severities:
                continue
            out.append(Finding(
                finding_id=f["finding_id"], title=f["title"], severity=f["severity"],
                status=f["status"], category=f["category"], recommendation=f["recommendation"],
                file_path=f["file_path"], pr_url=f["pr_url"], session_id=f["session_id"],
            ))
        return out

    async def remediate(self, scan_id: str, finding_id: str) -> RemediateResult:
        session_id = f"devin-mock-{uuid.uuid4().hex[:10]}"
        self._sessions[session_id] = {"created": time.time(), "finding_id": finding_id, "scan_id": scan_id}
        for f in self._findings.get(scan_id, []):
            if f["finding_id"] == finding_id:
                f["session_id"] = session_id
        return RemediateResult(finding_id=finding_id, session_id=session_id)

    async def get_session(self, session_id: str) -> Session:
        st = self._sessions.get(session_id)
        if not st:
            return Session(session_id=session_id, status="error")
        elapsed = time.time() - st["created"]
        random.seed(st["created"])
        acu = round(random.uniform(0.6, 2.0), 2)
        if elapsed < settings.mock_seconds_to_complete:
            return Session(session_id=session_id, status="running", origin="code_scan",
                           acus_consumed=round(acu * min(elapsed / settings.mock_seconds_to_complete, 1), 2))
        # finished: fabricate a PR and mark the finding resolved
        pr = f"https://github.com/{settings.target_repo}/pull/{100 + abs(hash(session_id)) % 90}"
        for rows in self._findings.values():
            for f in rows:
                if f["session_id"] == session_id:
                    f["pr_url"] = pr
                    f["status"] = "resolved"
        return Session(session_id=session_id, status="exit", origin="code_scan",
                       pull_requests=[pr], acus_consumed=acu,
                       url=f"https://app.devin.ai/sessions/{session_id}")

    async def list_sessions(self, limit: int = 50):
        # Mock mode populates the store directly via the orchestrator; no sync needed.
        return []

    async def metrics_sessions(self, after: int, before: int) -> dict[str, Any]:
        n = len(self._sessions)
        merged = sum(1 for s in self._sessions.values()
                     if time.time() - s["created"] >= settings.mock_seconds_to_complete)
        return {
            "sessions_created_count": n,
            "sessions_created_by_origin": {"code_scan": n, "automation": 0, "api": 0},
            "sessions_with_merged_prs_count": 0,
            "avg_acus_per_session": 1.3 if n else 0,
        }

    async def metrics_prs(self, after: int, before: int) -> dict[str, Any]:
        # In mock, native PR metrics reflect the control-plane store (a fresh client
        # instance has no in-memory findings), so the funnel shows realistic numbers.
        from app import store
        opened = sum(1 for r in store.list_remediations() if r["pr_url"])
        merged = round(opened * 0.75)  # simulate a realistic review/merge rate
        return {"prs_created_count": opened, "prs_opened_count": opened, "prs_merged_count": merged}

    async def consumption_daily(self) -> dict[str, Any]:
        total = 0.0
        for sid, s in self._sessions.items():
            random.seed(s["created"])
            if time.time() - s["created"] >= settings.mock_seconds_to_complete:
                total += round(random.uniform(0.6, 2.0), 2)
        return {"total_acus": round(total, 2), "consumption_by_date": []}

    async def trigger_review(self, pr_url: str):
        return {"status": "pending", "pr_url": pr_url}

    async def aclose(self) -> None:
        return None
