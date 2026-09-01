"""The Devin v3 abstraction.

Upstream code (orchestrator, scheduler, dashboard) talks only to this interface,
never to the API directly. A MockDevinClient runs the whole flow offline for $0;
a LiveDevinClient hits https://api.devin.ai/v3. Same orchestration for both.

We deliberately build on Devin's NATIVE primitives rather than reinventing them:
  - Code Scans   (scan a repo -> findings -> remediate -> PR)
  - Sessions     (each remediation is a Devin session that opens a PR)
  - Metrics      (native aggregate session/PR metrics)
  - Consumption  (native ACU usage)
Our value-add is the orchestration + the unified control plane on top.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Protocol

# Code-scan terminal states (per docs): waiting -> pending -> running -> completed|failed|cancelled
SCAN_TERMINAL = {"completed", "failed", "cancelled"}
# Session status enum (v3): new, claimed, running, exit, error, suspended, resuming
SESSION_TERMINAL = {"exit", "error", "suspended"}


@dataclass
class Scan:
    scan_id: str
    status: str
    repo: str
    scan_type: str = "security"
    url: Optional[str] = None


@dataclass
class Finding:
    finding_id: str
    title: str
    severity: str                       # critical | high | medium | low
    status: str                         # open | dismissed | resolved
    category: Optional[str] = None
    recommendation: Optional[str] = None
    file_path: Optional[str] = None
    pr_url: Optional[str] = None
    session_id: Optional[str] = None


@dataclass
class RemediateResult:
    finding_id: str
    session_id: str


@dataclass
class Session:
    session_id: str
    status: str                         # v3 status enum
    url: Optional[str] = None
    pull_requests: list[str] = field(default_factory=list)
    acus_consumed: Optional[float] = None
    origin: Optional[str] = None        # api | automation | code_scan | ...
    title: str = ""
    tags: list[str] = field(default_factory=list)


class DevinClient(Protocol):
    # --- Code Scans ---
    async def start_scan(self, repo: str, scan_type: str) -> Scan: ...
    async def get_scan(self, scan_id: str, repo: str) -> Scan: ...
    async def list_findings(self, scan_id: str, severities: set[str]) -> list[Finding]: ...
    async def remediate(self, scan_id: str, finding_id: str) -> RemediateResult: ...

    # --- Sessions ---
    async def get_session(self, session_id: str) -> Session: ...

    async def list_sessions(self, limit: int = 50) -> list[Session]: ...

    # --- Devin Review (self-review each PR) ---
    async def trigger_review(self, pr_url: str) -> dict[str, Any]: ...

    # --- Observability (native aggregates) ---
    async def metrics_sessions(self, after: int, before: int) -> dict[str, Any]: ...
    async def metrics_prs(self, after: int, before: int) -> dict[str, Any]: ...
    async def consumption_daily(self) -> dict[str, Any]: ...

    async def aclose(self) -> None: ...


def get_devin_client() -> DevinClient:
    from app.config import settings

    if settings.devin_mode == "live":
        from app.devin.live import LiveDevinClient

        return LiveDevinClient()
    from app.devin.mock import MockDevinClient

    return MockDevinClient()
