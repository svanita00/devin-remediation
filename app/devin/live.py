"""Live Devin v3 client — https://api.devin.ai/v3

Verified endpoints (docs.devin.ai, org-scoped):
  POST /organizations/{org}/code-scans                                   -> {scan_id, status}
  GET  /organizations/{org}/code-scans?repo_name=...                     -> list scans (poll status)
  GET  /organizations/{org}/code-scans/findings?scan_id=...&severity=... -> findings
  POST /organizations/{org}/code-scans/{scan}/findings/{id}/remediate    -> {finding_id, session_id}
  GET  /organizations/{org}/sessions/{id}                                -> {status, pull_requests, acus_consumed, origin}
  GET  /organizations/{org}/metrics/sessions?time_after=&time_before=    -> aggregate metrics
  GET  /organizations/{org}/metrics/prs?time_after=&time_before=         -> PR metrics
  GET  /organizations/{org}/consumption/daily                            -> {total_acus, consumption_by_date}

Auth: Bearer <DEVIN_API_KEY> (cog_ PAT). Errors are RFC9457 problem+json.
"""
from __future__ import annotations

from typing import Any, Optional

import httpx

from app.config import settings
from app.devin.client import Finding, RemediateResult, Scan, Session


class LiveDevinClient:
    def __init__(self) -> None:
        if not settings.devin_api_key:
            raise RuntimeError("DEVIN_MODE=live but DEVIN_API_KEY is not set")
        self._org = settings.devin_org_id
        self._client = httpx.AsyncClient(
            base_url=settings.devin_api_base,
            headers={"Authorization": f"Bearer {settings.devin_api_key}"},
            timeout=30.0,
        )

    def _base(self) -> str:
        return f"/organizations/{self._org}"

    # --- Code Scans ---
    async def start_scan(self, repo: str, scan_type: str) -> Scan:
        body: dict[str, Any] = {"repo_name": repo}
        if scan_type and scan_type != "security":
            body["scan_type"] = scan_type
        r = await self._client.post(f"{self._base()}/code-scans", json=body)
        r.raise_for_status()
        d = r.json()
        return Scan(scan_id=d["scan_id"], status=d.get("status", "pending"),
                    repo=repo, scan_type=d.get("scan_type", scan_type), url=d.get("url"))

    async def get_scan(self, scan_id: str, repo: str) -> Scan:
        # List scans (GET /code-scans/scans) and find ours.
        r = await self._client.get(f"{self._base()}/code-scans/scans",
                                   params={"repo_name": repo})
        r.raise_for_status()
        for item in r.json().get("items", []):
            if item.get("scan_id") == scan_id:
                return Scan(scan_id=scan_id, status=item.get("status", "running"),
                            repo=repo, scan_type=item.get("scan_type", "security"),
                            url=item.get("url"))
        return Scan(scan_id=scan_id, status="running", repo=repo)

    async def list_findings(self, scan_id: str, severities: set[str]) -> list[Finding]:
        params: dict[str, Any] = {"scan_id": scan_id, "first": 200}
        if severities:
            params["severity"] = list(severities)
        r = await self._client.get(f"{self._base()}/code-scans/findings", params=params)
        r.raise_for_status()
        out: list[Finding] = []
        for f in r.json().get("items", []):
            snips = f.get("reference_snippets") or []
            file_path = snips[0].get("file_path") if snips else None
            out.append(Finding(
                finding_id=f["finding_id"],
                title=f.get("title") or "(untitled)",
                severity=(f.get("severity") or "").lower(),
                status=(f.get("status") or "open").lower(),
                category=f.get("category"),
                recommendation=f.get("recommendation"),
                file_path=file_path,
                pr_url=f.get("pr_url"),
                session_id=f.get("session_id"),
            ))
        return out

    async def remediate(self, scan_id: str, finding_id: str) -> RemediateResult:
        r = await self._client.post(
            f"{self._base()}/code-scans/{scan_id}/findings/{finding_id}/remediate"
        )
        r.raise_for_status()
        d = r.json()
        return RemediateResult(finding_id=d["finding_id"], session_id=d["session_id"])

    # --- Sessions ---
    async def get_session(self, session_id: str) -> Session:
        r = await self._client.get(f"{self._base()}/sessions/{session_id}")
        r.raise_for_status()
        d = r.json()
        prs = [p.get("pr_url") for p in (d.get("pull_requests") or []) if p.get("pr_url")]
        return Session(
            session_id=session_id,
            status=d.get("status", "running"),
            url=d.get("url"),
            pull_requests=prs,
            acus_consumed=d.get("acus_consumed"),
            origin=d.get("origin"),
        )

    async def list_sessions(self, limit: int = 50) -> list[Session]:
        r = await self._client.get(f"{self._base()}/sessions", params={"limit": limit})
        r.raise_for_status()
        data = r.json()
        items = data.get("sessions") or data.get("items") or []
        out: list[Session] = []
        for d in items:
            prs = [p.get("pr_url") for p in (d.get("pull_requests") or []) if p.get("pr_url")]
            out.append(Session(
                session_id=d.get("session_id"),
                status=d.get("status", "running"),
                url=d.get("url"),
                pull_requests=prs,
                acus_consumed=d.get("acus_consumed"),
                origin=d.get("origin"),
                title=d.get("title") or "",
                tags=d.get("tags") or [],
            ))
        return out

    # --- Observability ---
    async def metrics_sessions(self, after: int, before: int) -> dict[str, Any]:
        r = await self._client.get(f"{self._base()}/metrics/sessions",
                                   params={"time_after": after, "time_before": before})
        r.raise_for_status()
        return r.json()

    async def metrics_prs(self, after: int, before: int) -> dict[str, Any]:
        r = await self._client.get(f"{self._base()}/metrics/prs",
                                   params={"time_after": after, "time_before": before})
        r.raise_for_status()
        return r.json()

    async def consumption_daily(self) -> dict[str, Any]:
        r = await self._client.get(f"{self._base()}/consumption/daily")
        r.raise_for_status()
        return r.json()

    async def trigger_review(self, pr_url: str) -> dict[str, Any]:
        r = await self._client.post(f"{self._base()}/pr-reviews", json={"pr_url": pr_url})
        r.raise_for_status()
        return r.json()

    async def aclose(self) -> None:
        await self._client.aclose()
